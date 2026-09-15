import json
from pathlib import Path

import pytest

from backend.app.pilot.cli import main


def _repository(tmp_path: Path) -> Path:
    repository = tmp_path / "customer-repository"
    repository.mkdir()
    (repository / "service.py").write_text(
        "def recover_half_open() -> bool:\n    return True\n",
        encoding="utf-8",
    )
    (repository / "test_service.py").write_text(
        "from service import recover_half_open\n\n"
        "def test_half_open_recovery() -> None:\n"
        "    assert recover_half_open() is True\n",
        encoding="utf-8",
    )
    (repository / "postmortem.md").write_text(
        "# Recovery incident\n\n## Corrective actions\n- Test half-open recovery.\n",
        encoding="utf-8",
    )
    return repository


def test_pilot_cli_writes_minimized_report_without_absolute_paths(tmp_path: Path) -> None:
    repository = _repository(tmp_path)

    exit_code = main(
        [
            "--repository",
            str(repository),
            "--postmortem",
            "postmortem.md",
        ]
    )

    report_path = repository / ".remedygraph" / "report.json"
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    serialized = json.dumps(payload)
    assert exit_code == 0
    assert payload["schema_version"] == 1
    assert payload["summary"]["status"] == "COMPLETE"
    assert payload["repository_name"] == repository.name
    assert payload["actions"][0]["action"] == "Test half-open recovery"
    assert str(repository) not in serialized
    assert "excerpt" not in serialized
    assert "metadata" not in serialized
    assert "actual" not in serialized


def test_pilot_cli_rejects_postmortem_outside_repository(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    outside = tmp_path / "outside.md"
    outside.write_text("- Add a circuit breaker.\n", encoding="utf-8")

    exit_code = main(
        [
            "--repository",
            str(repository),
            "--postmortem",
            str(outside),
        ]
    )

    assert exit_code == 2
    assert not (repository / ".remedygraph" / "report.json").exists()


def test_pilot_cli_rejects_output_outside_repository(tmp_path: Path) -> None:
    repository = _repository(tmp_path)

    exit_code = main(
        [
            "--repository",
            str(repository),
            "--postmortem",
            "postmortem.md",
            "--output",
            "../report.json",
        ]
    )

    assert exit_code == 2
    assert not (tmp_path / "report.json").exists()


def test_pilot_cli_rejects_repository_outside_github_workspace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = _repository(tmp_path)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setenv("GITHUB_WORKSPACE", str(workspace))

    exit_code = main(
        [
            "--repository",
            str(repository),
            "--postmortem",
            "postmortem.md",
        ]
    )

    assert exit_code == 2
    assert not (repository / ".remedygraph" / "report.json").exists()
