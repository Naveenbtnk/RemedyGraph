"""Fixed-command, bounded execution for approved generated guards."""

from __future__ import annotations

import ast
import hashlib
import os
import subprocess
import sys
import time
from pathlib import Path

from backend.app.guards.contracts import GuardExecution, GuardExecutionStatus, GuardSpec
from backend.app.guards.generator import TEMPLATE_VERSION, GuardGenerator
from backend.app.ids import stable_id
from backend.app.rag.redaction import redact_text


class GuardSafetyError(ValueError):
    """Raised when a guard crosses the generated-artifact safety boundary."""


class GuardRunner:
    def __init__(
        self,
        workspace_root: Path,
        repository_root: Path,
        *,
        timeout_seconds: float = 5,
        output_limit: int = 16_384,
    ) -> None:
        self.workspace_root = workspace_root.resolve()
        self.repository_root = repository_root.resolve()
        self.timeout_seconds = timeout_seconds
        self.output_limit = output_limit
        self._require_within(self.repository_root, self.workspace_root, "repository")

    def write_approved(self, guard: GuardSpec) -> Path:
        self.validate_preview(guard)
        target = self._target(guard)
        target.parent.mkdir(parents=True, exist_ok=True)
        self._reject_symlink_components(target)
        target.write_text(guard.preview, encoding="utf-8", newline="\n")
        return target

    def execute(self, guard: GuardSpec) -> GuardExecution:
        target = self._target(guard)
        self._reject_symlink_components(target)
        if not target.is_file() or target.is_symlink():
            raise GuardSafetyError("approved guard artifact is missing or unsafe")
        content = target.read_text(encoding="utf-8")
        digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
        if digest != guard.preview_sha256:
            raise GuardSafetyError("approved guard artifact changed after approval")
        self.validate_preview(guard)
        command = [sys.executable, "-I", "-S", "-B", str(target)]
        started = time.perf_counter()
        try:
            completed = subprocess.run(
                command,
                cwd=self.repository_root,
                env=self._scrubbed_environment(),
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                check=False,
                shell=False,
            )
            duration = (time.perf_counter() - started) * 1000
            stdout, stdout_cut = self._bounded(completed.stdout)
            stderr, stderr_cut = self._bounded(completed.stderr)
            result_status = (
                GuardExecutionStatus.PASSED
                if completed.returncode == 0
                else GuardExecutionStatus.FAILED
            )
            return GuardExecution(
                id=stable_id("guard_execution", guard.id, time.time_ns()),
                guard_id=guard.id,
                run_id=guard.run_id,
                status=result_status,
                command_label=guard.execution_label,
                exit_code=completed.returncode,
                stdout=redact_text(stdout),
                stderr=redact_text(stderr),
                duration_ms=duration,
                output_truncated=stdout_cut or stderr_cut,
                artifact_sha256=digest,
            )
        except subprocess.TimeoutExpired as exc:
            duration = (time.perf_counter() - started) * 1000
            stdout, stdout_cut = self._bounded(self._as_text(exc.stdout))
            stderr, stderr_cut = self._bounded(self._as_text(exc.stderr))
            return GuardExecution(
                id=stable_id("guard_execution", guard.id, time.time_ns()),
                guard_id=guard.id,
                run_id=guard.run_id,
                status=GuardExecutionStatus.TIMED_OUT,
                command_label=guard.execution_label,
                stdout=redact_text(stdout),
                stderr=redact_text(stderr),
                duration_ms=duration,
                timed_out=True,
                output_truncated=stdout_cut or stderr_cut,
                artifact_sha256=digest,
            )
        except OSError as exc:
            duration = (time.perf_counter() - started) * 1000
            message, truncated = self._bounded(str(exc))
            return GuardExecution(
                id=stable_id("guard_execution", guard.id, time.time_ns()),
                guard_id=guard.id,
                run_id=guard.run_id,
                status=GuardExecutionStatus.ERROR,
                command_label=guard.execution_label,
                stderr=redact_text(message),
                duration_ms=duration,
                output_truncated=truncated,
                artifact_sha256=digest,
            )

    def validate_preview(self, guard: GuardSpec) -> None:
        if guard.template_version != TEMPLATE_VERSION:
            raise GuardSafetyError("guard template version is not allowlisted")
        expected_preview = GuardGenerator.render(
            guard.terms,
            guard_type=guard.guard_type,
            test_only=guard.test_only,
            match_all=guard.match_all,
            expected_literals=guard.expected_literals,
        )
        if guard.preview != expected_preview:
            raise GuardSafetyError("guard preview does not match the application-owned template")
        digest = hashlib.sha256(guard.preview.encode("utf-8")).hexdigest()
        if digest != guard.preview_sha256:
            raise GuardSafetyError("guard preview hash does not match content")
        if len(guard.preview.encode("utf-8")) > 64_000:
            raise GuardSafetyError("guard preview exceeds size limit")
        try:
            tree = ast.parse(guard.preview)
        except SyntaxError as exc:
            raise GuardSafetyError("guard preview is not valid Python") from exc
        allowed_imports = {"ast", "pathlib"}
        forbidden_names = {"eval", "exec", "compile", "__import__", "open", "input"}
        forbidden_attributes = {
            "system",
            "popen",
            "spawn",
            "socket",
            "connect",
            "urlopen",
            "unlink",
            "rmdir",
            "rename",
            "replace",
            "write_text",
            "write_bytes",
        }
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                if any(alias.name.split(".")[0] not in allowed_imports for alias in node.names):
                    raise GuardSafetyError("guard imports a non-allowlisted module")
            if isinstance(node, ast.ImportFrom):
                if node.module is None or node.module.split(".")[0] not in allowed_imports:
                    raise GuardSafetyError("guard imports a non-allowlisted module")
            if isinstance(node, ast.Name) and node.id in forbidden_names:
                raise GuardSafetyError("guard uses a forbidden operation")
            if isinstance(node, ast.Attribute) and node.attr in forbidden_attributes:
                raise GuardSafetyError("guard uses a forbidden operation")

    def _target(self, guard: GuardSpec) -> Path:
        expected = (
            Path(".remedygraph") / "generated_guards" / guard.run_id / f"{guard.id}.py"
        ).as_posix()
        if guard.target_path != expected:
            raise GuardSafetyError("guard target does not match its immutable identity")
        target = (self.repository_root / Path(*guard.target_path.split("/"))).resolve(strict=False)
        self._require_within(target, self.repository_root, "guard target")
        self._require_within(target, self.workspace_root, "guard target")
        return target

    def _reject_symlink_components(self, target: Path) -> None:
        current = self.repository_root
        for part in target.relative_to(self.repository_root).parts:
            current /= part
            if current.exists() and current.is_symlink():
                raise GuardSafetyError("generated guard path contains a symlink")

    def _scrubbed_environment(self) -> dict[str, str]:
        environment = {
            "PYTHONIOENCODING": "utf-8",
            "PYTHONHASHSEED": "0",
            "PYTHONDONTWRITEBYTECODE": "1",
            "HTTP_PROXY": "http://127.0.0.1:9",
            "HTTPS_PROXY": "http://127.0.0.1:9",
            "ALL_PROXY": "http://127.0.0.1:9",
            "NO_PROXY": "",
        }
        for key in ("SYSTEMROOT", "WINDIR", "TEMP", "TMP"):
            if value := os.environ.get(key):
                environment[key] = value
        return environment

    def _bounded(self, value: str) -> tuple[str, bool]:
        encoded = value.encode("utf-8", errors="replace")
        if len(encoded) <= self.output_limit:
            return value, False
        return encoded[: self.output_limit].decode("utf-8", errors="ignore"), True

    @staticmethod
    def _as_text(value: str | bytes | None) -> str:
        if value is None:
            return ""
        return value.decode("utf-8", errors="replace") if isinstance(value, bytes) else value

    @staticmethod
    def _require_within(candidate: Path, root: Path, label: str) -> None:
        try:
            candidate.relative_to(root)
        except ValueError as exc:
            raise GuardSafetyError(f"{label} escapes its allowed root") from exc
