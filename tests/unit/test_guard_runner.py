"""Security and bounded-output tests for the generated guard runner."""

import hashlib
import subprocess
from pathlib import Path

import pytest

from backend.app.guards.contracts import GuardSpec, GuardType
from backend.app.guards.generator import GuardGenerator
from backend.app.guards.runner import GuardRunner, GuardSafetyError


def _guard(preview: str | None = None) -> GuardSpec:
    rendered = preview or GuardGenerator.render(
        ["circuit", "breaker"],
        guard_type=GuardType.STATIC_REPOSITORY,
        test_only=False,
        match_all=True,
        expected_literals=[],
    )
    return GuardSpec(
        id="guard_1",
        run_id="run_1",
        action_id="action_1",
        invariant_id="invariant_1",
        name="fixture",
        guard_type="static_repository",
        intent="fixture",
        target_path=".remedygraph/generated_guards/run_1/guard_1.py",
        preview=rendered,
        preview_sha256=hashlib.sha256(rendered.encode()).hexdigest(),
        terms=["circuit", "breaker"],
    )


def test_runner_rejects_non_allowlisted_import_and_mutated_artifact(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    runner = GuardRunner(tmp_path, repository)
    malicious = _guard("import socket\nsocket.create_connection(('example.com', 80))\n")
    with pytest.raises(GuardSafetyError, match="application-owned template"):
        runner.write_approved(malicious)

    safe = _guard()
    artifact = runner.write_approved(safe)
    artifact.write_text(safe.preview + "# changed\n", encoding="utf-8")
    with pytest.raises(GuardSafetyError, match="changed after approval"):
        runner.execute(safe)


def test_runner_reports_timeout_and_caps_redacted_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    runner = GuardRunner(tmp_path, repository, timeout_seconds=0.01, output_limit=1_024)
    guard = _guard()
    runner.write_approved(guard)

    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(
            cmd=args[0], timeout=0.01, output=b"token=secret-value\n" + b"x" * 2_000
        )

    monkeypatch.setattr(subprocess, "run", timeout)
    result = runner.execute(guard)
    assert result.status == "TIMED_OUT"
    assert result.timed_out is True
    assert result.output_truncated is True
    assert "secret-value" not in result.stdout
    assert len(result.stdout.encode()) <= 1_024


def test_runner_returns_typed_error_when_process_cannot_start(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    runner = GuardRunner(tmp_path, repository)
    guard = _guard()
    runner.write_approved(guard)

    def unavailable(*args, **kwargs):
        raise OSError("runner unavailable")

    monkeypatch.setattr(subprocess, "run", unavailable)
    result = runner.execute(guard)
    assert result.status == "ERROR"
    assert result.exit_code is None
    assert "runner unavailable" in result.stderr
