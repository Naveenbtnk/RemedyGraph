"""HTTP request and response schemas."""

from pydantic import Field

from backend.app.audit.contracts import (
    ActionVerdict,
    AuditRunCreate,
    AuditRunSummary,
    EvidenceGraphEdge,
    EvidenceGraphNode,
    EvidenceRecord,
)
from backend.app.guards.contracts import GuardExecution, GuardSpec
from backend.app.models import ActionItem, DomainModel, Incident, Project


class ProjectCreate(DomainModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    repository_path: str = Field(min_length=1, max_length=4096)


class ProjectResponse(Project):
    pass


class IncidentCreate(DomainModel):
    project_id: str | None = None
    source_text: str = Field(min_length=1, max_length=1_000_000)
    source_name: str | None = Field(default=None, max_length=255)
    title: str | None = Field(default=None, min_length=1, max_length=255)


class IncidentResponse(Incident):
    pass


class HealthResponse(DomainModel):
    status: str
    service: str
    version: str


class ActionItemResponse(ActionItem):
    pass


class AuditRunResponse(AuditRunSummary):
    pass


class ActionVerdictsResponse(DomainModel):
    verdicts: list[ActionVerdict]


class EvidenceResponse(DomainModel):
    evidence: list[EvidenceRecord]


class EvidenceGraphResponse(DomainModel):
    nodes: list[EvidenceGraphNode]
    edges: list[EvidenceGraphEdge]


class GuardPreviewsResponse(DomainModel):
    guards: list[GuardSpec]


class GuardApprovalRequest(DomainModel):
    approved: bool
    preview_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class GuardExecutionsResponse(DomainModel):
    executions: list[GuardExecution]


__all__ = ["AuditRunCreate"]
