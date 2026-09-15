"""Run a bounded audit in a checked-out repository and write a minimized JSON report."""

from __future__ import annotations

import argparse
import os
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from backend.app.audit.contracts import AuditRunCreate, AuditWorkflowState
from backend.app.audit.workflow import AuditWorkflow
from backend.app.llm.mock import MockLLMProvider
from backend.app.models import RunStatus, Verdict
from backend.app.pilot.contracts import (
    PilotActionResult,
    PilotAuditReport,
    PilotCheckResult,
    PilotCitation,
    PilotEvidenceRecord,
    PilotRunSummary,
)
from backend.app.rag.safety import PathSafetyError, WorkspaceBoundary
from backend.app.schemas import IncidentCreate, ProjectCreate
from backend.app.services import AuditService, IncidentService, ProjectService
from backend.app.settings import Settings
from backend.app.storage import SQLiteStore

REPORT_PATH = ".remedygraph/report.json"
POSTMORTEM_SUFFIXES = frozenset({".md", ".markdown", ".txt"})


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run a read-only RemedyGraph audit and emit a minimized JSON report."
    )
    parser.add_argument("--repository", default=".", help="checked-out repository directory")
    parser.add_argument(
        "--postmortem",
        required=True,
        help="Markdown or text postmortem path inside the repository",
    )
    parser.add_argument(
        "--output",
        default=REPORT_PATH,
        help=f"report path inside the repository (default: {REPORT_PATH})",
    )
    return parser


def _contained_output(repository: Path, requested: str) -> Path:
    candidate = Path(requested)
    if not candidate.is_absolute():
        candidate = repository / candidate
    resolved = candidate.resolve(strict=False)
    try:
        resolved.relative_to(repository)
    except ValueError as exc:
        raise PathSafetyError("output path must remain inside the repository") from exc
    if candidate.is_symlink() or resolved.exists() and resolved.is_dir():
        raise PathSafetyError("output path must be a regular file, not a symlink or directory")
    parent = resolved.parent
    while parent != repository:
        if parent.is_symlink():
            raise PathSafetyError("output path cannot traverse a symlink")
        parent = parent.parent
    return resolved


def _read_postmortem(repository: Path, requested: str) -> tuple[Path, str]:
    boundary = WorkspaceBoundary(repository)
    candidate = Path(requested)
    if not candidate.is_absolute():
        candidate = repository / candidate
    source = boundary.file(candidate, repository)
    if source.suffix.lower() not in POSTMORTEM_SUFFIXES:
        raise ValueError("postmortem must be Markdown or plain text")
    if source.stat().st_size > 1_000_000:
        raise ValueError("postmortem exceeds the 1,000,000 byte limit")
    try:
        text = source.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("postmortem must be UTF-8 text") from exc
    if not text.strip():
        raise ValueError("postmortem must not be empty")
    return source, text


def _repository(requested: str) -> Path:
    repository = Path(requested).expanduser().resolve(strict=True)
    if not repository.is_dir():
        raise PathSafetyError("repository must be an existing directory")
    github_workspace = os.environ.get("GITHUB_WORKSPACE")
    if github_workspace:
        workspace = Path(github_workspace).resolve(strict=True)
        try:
            repository.relative_to(workspace)
        except ValueError as exc:
            raise PathSafetyError("repository must remain inside GITHUB_WORKSPACE") from exc
    return repository


def _report(
    state: AuditWorkflowState,
    *,
    incident_title: str,
    repository: Path,
    tool_version: str,
) -> PilotAuditReport:
    verdict_by_action = {item.action_id: item for item in state.verdicts}
    spec_by_id = {item.id: item for item in state.check_specs}
    actions: list[PilotActionResult] = []
    for action in state.actions:
        verdict = verdict_by_action.get(action.id)
        if verdict is None:
            actions.append(
                PilotActionResult(
                    action=action.text,
                    source_line=action.source_line,
                    source_section=action.source_section,
                    verdict=Verdict.UNVERIFIABLE,
                    rationale="The bounded workflow did not produce a verdict.",
                    missing_proofs=["audit verdict unavailable"],
                )
            )
            continue
        actions.append(
            PilotActionResult(
                action=action.text,
                source_line=action.source_line,
                source_section=action.source_section,
                verdict=verdict.verdict,
                rationale=verdict.rationale,
                missing_proofs=verdict.missing_proofs,
                citations=[
                    PilotCitation(
                        source_path=citation.source_path,
                        line_start=citation.line_start,
                        line_end=citation.line_end,
                    )
                    for citation in verdict.citations
                ],
            )
        )
    return PilotAuditReport(
        tool_version=tool_version,
        generated_at=datetime.now(UTC),
        repository_name=repository.name,
        repository_commit=os.environ.get("GITHUB_SHA") or None,
        incident_title=incident_title,
        summary=PilotRunSummary(
            status=state.summary.status,
            total_actions=state.summary.total_actions,
            completed_actions=state.summary.completed_actions,
            verdict_counts=state.summary.verdict_counts,
            assessed_protection_coverage=state.summary.assessed_protection_coverage,
            budget=state.summary.budget,
            failure_code=state.summary.failure_code,
            error=state.summary.error,
        ),
        actions=actions,
        evidence=[
            PilotEvidenceRecord(
                kind=item.kind,
                role=item.role,
                source_path=item.source_path,
                line_start=item.line_start,
                line_end=item.line_end,
            )
            for item in state.evidence
        ],
        checks=[
            PilotCheckResult(
                check_type=(
                    spec_by_id[item.check_spec_id].check_type.value
                    if item.check_spec_id in spec_by_id
                    else "unknown"
                ),
                outcome=item.outcome.value,
                required=(
                    spec_by_id[item.check_spec_id].required
                    if item.check_spec_id in spec_by_id
                    else True
                ),
                core=item.core,
            )
            for item in state.check_results
        ],
    )


def run(repository_arg: str, postmortem_arg: str, output_arg: str) -> tuple[Path, RunStatus]:
    repository = _repository(repository_arg)
    source, postmortem = _read_postmortem(repository, postmortem_arg)
    output = _contained_output(repository, output_arg)

    with TemporaryDirectory(prefix="remedygraph-pilot-") as temporary_directory:
        settings = Settings(
            workspace_root=repository,
            database_path=str(Path(temporary_directory) / "audit.sqlite3"),
        )
        store = SQLiteStore(settings.database_path)
        try:
            project = ProjectService(store, repository).create(
                ProjectCreate(name=repository.name, repository_path=str(repository))
            )
            incident = IncidentService(store, MockLLMProvider(), settings.max_model_calls).create(
                IncidentCreate(
                    project_id=project.id,
                    source_text=postmortem,
                    source_name=source.relative_to(repository).as_posix(),
                )
            )
            audit_service = AuditService(store, AuditWorkflow(store, settings))
            summary = audit_service.start(
                AuditRunCreate(project_id=project.id, incident_id=incident.id)
            )
            state = audit_service.state(summary.id)
            report = _report(
                state,
                incident_title=incident.title,
                repository=repository,
                tool_version=settings.app_version,
            )
        finally:
            store.close()

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(report.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return output, state.summary.status


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        output, status = run(args.repository, args.postmortem, args.output)
    except (OSError, PathSafetyError, ValueError) as exc:
        print(f"RemedyGraph audit rejected: {exc}")
        return 2
    print(f"RemedyGraph report: {output}")
    return 0 if status in {RunStatus.COMPLETE, RunStatus.PARTIAL_COMPLETE} else 1


if __name__ == "__main__":
    raise SystemExit(main())
