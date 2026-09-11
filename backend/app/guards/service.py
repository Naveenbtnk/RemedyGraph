"""Guard lifecycle orchestration with explicit per-preview approval."""

from __future__ import annotations

from pathlib import Path

from fastapi import HTTPException, status

from backend.app.guards.contracts import (
    GuardApproval,
    GuardExecution,
    GuardExecutionStatus,
    GuardSpec,
    GuardStatus,
)
from backend.app.guards.generator import GuardGenerator
from backend.app.guards.runner import GuardRunner, GuardSafetyError
from backend.app.ids import stable_id
from backend.app.models import RunStatus, utc_now
from backend.app.storage import SQLiteStore


class GuardService:
    def __init__(
        self,
        store: SQLiteStore,
        workspace_root: Path,
        *,
        timeout_seconds: float,
        output_limit: int,
    ) -> None:
        self.store = store
        self.workspace_root = workspace_root.resolve()
        self.timeout_seconds = timeout_seconds
        self.output_limit = output_limit
        self.generator = GuardGenerator()

    def preview(self, run_id: str) -> list[GuardSpec]:
        state = self.store.load_audit_state(run_id)
        if state is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="audit run not found")
        if state.summary.status != RunStatus.COMPLETE:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="guards require a completed audit run",
            )
        existing = self.store.list_guards(run_id)
        if existing:
            return existing
        guards = self.generator.generate(state)
        for guard in guards:
            self.store.save_guard(guard)
        return guards

    def list_guards(self, run_id: str) -> list[GuardSpec]:
        if self.store.get_run_summary(run_id) is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="audit run not found")
        return self.store.list_guards(run_id)

    def decide(
        self, run_id: str, guard_id: str, *, approved: bool, preview_sha256: str
    ) -> GuardSpec:
        guard = self._guard(run_id, guard_id)
        if guard.status != GuardStatus.PREVIEWED:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="guard decision has already been recorded",
            )
        if preview_sha256 != guard.preview_sha256:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="guard preview changed; request a fresh preview",
            )
        approval = GuardApproval(
            id=stable_id("guard_approval", guard.id, preview_sha256),
            guard_id=guard.id,
            run_id=run_id,
            approved=approved,
            preview_sha256=preview_sha256,
        )
        if not approved:
            rejected = guard.model_copy(
                update={"status": GuardStatus.REJECTED, "updated_at": utc_now()}
            )
            self.store.record_guard_decision(rejected, approval)
            return rejected
        runner = self._runner(run_id)
        runner.validate_preview(guard)
        approved_guard = guard.model_copy(
            update={"status": GuardStatus.WRITTEN, "updated_at": utc_now()}
        )
        self.store.record_guard_decision(approved_guard, approval)
        try:
            runner.write_approved(approved_guard)
        except Exception:
            self.store.restore_guard_preview(guard)
            raise
        return approved_guard

    def execute(self, run_id: str, guard_id: str) -> GuardExecution:
        guard = self._guard(run_id, guard_id)
        if guard.status not in {
            GuardStatus.WRITTEN,
            GuardStatus.PASSED,
            GuardStatus.FAILED,
            GuardStatus.TIMED_OUT,
            GuardStatus.ERROR,
        }:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="guard must be explicitly approved and written before execution",
            )
        approval = self.store.get_guard_approval(guard.id)
        if (
            approval is None
            or not approval.approved
            or approval.preview_sha256 != guard.preview_sha256
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="valid approval not found"
            )
        try:
            execution = self._runner(run_id).execute(guard)
        except GuardSafetyError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
            ) from exc
        guard_status = {
            GuardExecutionStatus.PASSED: GuardStatus.PASSED,
            GuardExecutionStatus.FAILED: GuardStatus.FAILED,
            GuardExecutionStatus.TIMED_OUT: GuardStatus.TIMED_OUT,
            GuardExecutionStatus.ERROR: GuardStatus.ERROR,
        }[execution.status]
        updated = guard.model_copy(update={"status": guard_status, "updated_at": utc_now()})
        self.store.save_guard_execution(updated, execution)
        return execution

    def executions(self, run_id: str, guard_id: str) -> list[GuardExecution]:
        self._guard(run_id, guard_id)
        return self.store.list_guard_executions(guard_id)

    def _guard(self, run_id: str, guard_id: str) -> GuardSpec:
        guard = self.store.get_guard(guard_id)
        if guard is None or guard.run_id != run_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="guard not found")
        return guard

    def _runner(self, run_id: str) -> GuardRunner:
        summary = self.store.get_run_summary(run_id)
        if summary is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="audit run not found")
        project = self.store.get_project(summary.project_id)
        if project is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="audit project is missing"
            )
        return GuardRunner(
            self.workspace_root,
            Path(project.repository_path),
            timeout_seconds=self.timeout_seconds,
            output_limit=self.output_limit,
        )
