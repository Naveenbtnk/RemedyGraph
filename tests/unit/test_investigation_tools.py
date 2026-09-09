import json
import subprocess
from pathlib import Path

import pytest

from backend.app.rag.contracts import ToolStatus
from backend.app.tools import InvestigationTools


@pytest.fixture()
def repository(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    (repo / "tests").mkdir(parents=True)
    (repo / "retry.py").write_text(
        """API_KEY = "supersecret"
MAX_ATTEMPTS = 3

class RetryPolicy:
    @staticmethod
    def delay(attempt: int) -> float:
        return attempt * 0.2

def retry(operation):
    for attempt in range(MAX_ATTEMPTS):
        try:
            return operation()
        except TimeoutError:
            if attempt == MAX_ATTEMPTS - 1:
                raise
""",
        encoding="utf-8",
    )
    (repo / "tests" / "test_retry.py").write_text(
        """from retry import MAX_ATTEMPTS

def test_retry_exhaustion_is_bounded():
    assert MAX_ATTEMPTS == 3
""",
        encoding="utf-8",
    )
    (repo / ".env").write_text("PASSWORD=must-not-leak", encoding="utf-8")
    (repo / "settings.json").write_text(
        json.dumps({"retry": {"limit": 3}, "api_token": "json-secret"}), encoding="utf-8"
    )
    (repo / "settings.yaml").write_text(
        "retry:\n  limit: 4\npassword: yaml-secret\n", encoding="utf-8"
    )
    (repo / "settings.toml").write_text(
        '[retry]\nlimit = 5\nsecret = "toml-secret"\n', encoding="utf-8"
    )
    return repo


def test_search_code_returns_bounded_locations_and_redacts(repository: Path) -> None:
    tools = InvestigationTools(repository.parent, repository)

    result = tools.search_code("API_KEY", source_path="retry.py", context_lines=0)

    assert result.status == ToolStatus.OK
    assert len(result.matches) == 1
    assert result.matches[0].line_start == 1
    assert result.matches[0].line_end == 1
    assert "supersecret" not in result.matches[0].excerpt
    assert "[REDACTED]" in result.matches[0].excerpt


def test_search_code_denies_traversal_and_ignored_secret_file(repository: Path) -> None:
    tools = InvestigationTools(repository.parent, repository)

    traversal = tools.search_code("secret", source_path="../outside.txt")
    secret_file = tools.search_code("PASSWORD", source_path=".env")

    assert traversal.status == ToolStatus.DENIED
    assert secret_file.status == ToolStatus.DENIED
    assert traversal.matches == []
    assert secret_file.matches == []


def test_search_code_reports_invalid_regex_without_raising(repository: Path) -> None:
    result = InvestigationTools(repository.parent, repository).search_code("(", regex=True)

    assert result.status == ToolStatus.ERROR
    assert result.error is not None
    assert "invalid regular expression" in result.error


def test_get_symbol_uses_python_ast_and_qualified_names(repository: Path) -> None:
    tools = InvestigationTools(repository.parent, repository)

    result = tools.get_symbol("retry.py", "RetryPolicy.delay")

    assert result.status == ToolStatus.OK
    assert len(result.symbols) == 1
    symbol = result.symbols[0]
    assert symbol.symbol == "RetryPolicy.delay"
    assert symbol.kind == "function"
    assert symbol.line_start == 6
    assert symbol.line_end == 7
    assert symbol.signature == "def delay(attempt: int) -> float:"


@pytest.mark.parametrize(
    ("filename", "key_path", "expected"),
    [
        ("settings.json", "retry.limit", 3),
        ("settings.yaml", ["retry", "limit"], 4),
        ("settings.toml", "retry.limit", 5),
    ],
)
def test_inspect_config_parses_json_yaml_and_toml(
    repository: Path, filename: str, key_path: object, expected: int
) -> None:
    result = InvestigationTools(repository.parent, repository).inspect_config(
        filename,
        key_path=key_path,  # type: ignore[arg-type]
    )

    assert result.status == ToolStatus.OK
    assert result.values[0].value == expected


def test_inspect_config_redacts_nested_secrets(repository: Path) -> None:
    tools = InvestigationTools(repository.parent, repository)

    whole = tools.inspect_config("settings.json")
    selected = tools.inspect_config("settings.yaml", "password")

    assert whole.status == ToolStatus.OK
    assert whole.values[0].value == {
        "retry": {"limit": 3},
        "api_token": "[REDACTED]",
    }
    assert selected.values[0].value == "[REDACTED]"


def test_find_tests_locates_test_symbol_and_assertion(repository: Path) -> None:
    result = InvestigationTools(repository.parent, repository).find_tests("retry exhaustion")

    assert result.status == ToolStatus.OK
    assert result.matches
    assert result.matches[0].source_path == "tests/test_retry.py"
    assert result.matches[0].symbol == "test_retry_exhaustion_is_bounded"
    assert "assert MAX_ATTEMPTS == 3" in result.matches[0].excerpt


def test_find_git_changes_is_read_only_bounded_and_typed(repository: Path) -> None:
    subprocess.run(["git", "init", "-q", str(repository)], check=True)
    subprocess.run(
        ["git", "-C", str(repository), "config", "user.email", "fixture@example.test"],
        check=True,
    )
    subprocess.run(["git", "-C", str(repository), "config", "user.name", "Fixture"], check=True)
    subprocess.run(["git", "-C", str(repository), "add", "retry.py"], check=True)
    subprocess.run(
        ["git", "-C", str(repository), "commit", "-q", "-m", "bound retry attempts"],
        check=True,
    )
    tools = InvestigationTools(repository.parent, repository)

    result = tools.find_git_changes("retry", max_commits=2, max_output_chars=1_000)

    assert result.status == ToolStatus.OK
    assert len(result.changes) == 1
    assert len(result.changes[0].commit) == 40
    assert result.changes[0].subject == "bound retry attempts"
    assert len(result.changes[0].diff_excerpt) <= 1_000


def test_git_query_is_an_argument_not_a_shell_command(repository: Path) -> None:
    marker = repository / "should-not-exist"
    result = InvestigationTools(repository.parent, repository).find_git_changes(
        "; New-Item should-not-exist", max_commits=1
    )

    assert (
        result.status == ToolStatus.ERROR
    )  # Repository is not initialized; no command is evaluated.
    assert not marker.exists()
