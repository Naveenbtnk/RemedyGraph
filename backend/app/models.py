"""Pydantic domain models shared by services and API responses."""

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


def utc_now() -> datetime:
    return datetime.now(UTC)


class DomainModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CheckType(StrEnum):
    CONFIGURATION_THRESHOLD = "configuration_threshold"
    STATIC_PATTERN = "static_pattern"
    REGRESSION_TEST = "regression_test"
    MANUAL_REVIEW = "manual_review"


class Verdict(StrEnum):
    VERIFIED = "VERIFIED"
    PARTIAL = "PARTIAL"
    MISSING = "MISSING"
    UNVERIFIABLE = "UNVERIFIABLE"


class EvidenceKind(StrEnum):
    CODE = "code"
    CONFIGURATION = "configuration"
    TEST = "test"
    DOCUMENT = "document"
    GIT = "git"
    EXECUTION = "execution"
    ABSENT = "absent"


class RunStatus(StrEnum):
    QUEUED = "QUEUED"
    PARSING = "PARSING"
    EXTRACTING_ACTIONS = "EXTRACTING_ACTIONS"
    COMPLETE = "COMPLETE"
    FAILED = "FAILED"


class Project(DomainModel):
    id: str
    name: str
    repository_path: str
    created_at: datetime = Field(default_factory=utc_now)
    index_version: str = "day1-unindexed"


class Incident(DomainModel):
    id: str
    project_id: str | None = None
    title: str
    summary: str | None = None
    affected_services: list[str] = Field(default_factory=list)
    source_name: str | None = None
    source_text_hash: str
    actions: list["ActionItem"] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)


class ActionItem(DomainModel):
    id: str
    incident_id: str
    text: str
    source_line: int | None = None
    source_section: str | None = None
    order: int = Field(ge=0)


class Invariant(DomainModel):
    id: str
    action_id: str
    statement: str
    check_type: CheckType
    expected_value: Any | None = None
    unit: str | None = None
    required_proof: list[str] = Field(default_factory=list)


class Evidence(DomainModel):
    id: str
    invariant_id: str
    kind: EvidenceKind
    path: str | None = None
    line_start: int | None = None
    line_end: int | None = None
    excerpt: str | None = None
    strength: str = "unknown"
    supports: bool | None = None


class CheckResult(DomainModel):
    id: str
    invariant_id: str
    expected: Any | None = None
    actual: Any | None = None
    passed: bool | None = None
    detail: str


class VerificationResult(DomainModel):
    id: str
    invariant_id: str
    verdict: Verdict
    confidence: float = Field(ge=0, le=1)
    rationale: str
    evidence_ids: list[str] = Field(default_factory=list)
    missing_proofs: list[str] = Field(default_factory=list)


class GuardSpec(DomainModel):
    id: str
    invariant_id: str
    name: str
    guard_type: str
    intent: str
    assumptions: list[str] = Field(default_factory=list)
    assertions: list[str] = Field(default_factory=list)
    target_path: str
    preview: str
    approved: bool = False


class AuditRun(DomainModel):
    id: str
    project_id: str
    incident_id: str
    status: RunStatus = RunStatus.QUEUED
    model_calls: int = Field(default=0, ge=0)
    max_model_calls: int = Field(default=6, ge=1)
    created_at: datetime = Field(default_factory=utc_now)


class EvaluationRun(DomainModel):
    id: str
    dataset_version: str
    provider: str
    prompt_version: str
    metrics: dict[str, float] = Field(default_factory=dict)


class ExtractedAction(DomainModel):
    """Provider-owned structured output for postmortem extraction."""

    text: str
    source_line: int | None = None
    source_section: str | None = None


class ActionExtraction(DomainModel):
    actions: list[ExtractedAction] = Field(default_factory=list)
