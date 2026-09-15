"""Public report contracts for repository-local pilot audits."""

from datetime import datetime
from typing import Literal

from pydantic import Field

from backend.app.audit.contracts import AuditFailureCode, BudgetUsage, EvidenceRole
from backend.app.models import DomainModel, EvidenceKind, RunStatus, Verdict


class PilotCitation(DomainModel):
    source_path: str | None = None
    line_start: int | None = Field(default=None, ge=1)
    line_end: int | None = Field(default=None, ge=1)


class PilotActionResult(DomainModel):
    action: str
    source_line: int | None = Field(default=None, ge=1)
    source_section: str | None = None
    verdict: Verdict
    rationale: str
    missing_proofs: list[str] = Field(default_factory=list)
    citations: list[PilotCitation] = Field(default_factory=list)


class PilotEvidenceRecord(DomainModel):
    kind: EvidenceKind
    role: EvidenceRole
    source_path: str | None = None
    line_start: int | None = Field(default=None, ge=1)
    line_end: int | None = Field(default=None, ge=1)


class PilotCheckResult(DomainModel):
    check_type: str
    outcome: str
    required: bool
    core: bool


class PilotRunSummary(DomainModel):
    status: RunStatus
    total_actions: int = Field(ge=0)
    completed_actions: int = Field(ge=0)
    verdict_counts: dict[Verdict, int] = Field(default_factory=dict)
    assessed_protection_coverage: float = Field(ge=0, le=100)
    budget: BudgetUsage
    failure_code: AuditFailureCode | None = None
    error: str | None = None


class PilotAuditReport(DomainModel):
    schema_version: Literal[1] = 1
    tool: Literal["RemedyGraph"] = "RemedyGraph"
    tool_version: str
    generated_at: datetime
    repository_name: str
    repository_commit: str | None = None
    incident_title: str
    summary: PilotRunSummary
    actions: list[PilotActionResult] = Field(default_factory=list)
    evidence: list[PilotEvidenceRecord] = Field(default_factory=list)
    checks: list[PilotCheckResult] = Field(default_factory=list)
