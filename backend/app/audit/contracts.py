"""Typed contracts for the Day 3 audit, verification, and evidence graph."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from pathlib import PurePosixPath
from typing import Any, Self

from pydantic import Field, field_validator, model_validator

from backend.app.models import ActionItem, DomainModel, EvidenceKind, RunStatus, Verdict, utc_now


class RequirementKind(StrEnum):
    NUMERIC_CONFIGURATION = "numeric_configuration"
    CODE_STATIC = "code_static"
    TEST_PROTECTION = "test_protection"
    RUNTIME_CONTEXT = "runtime_context"
    UNSUPPORTED = "unsupported"


class RequirementAvailability(StrEnum):
    SUPPORTED = "supported"
    UNSUPPORTED = "unsupported"
    UNAVAILABLE = "unavailable"


class DeterministicCheckType(StrEnum):
    CONFIGURATION_VALUE = "configuration_value"
    STATIC_CODE = "static_code"
    STATIC_PATTERN = "static_pattern"
    TEST_PROTECTION = "test_protection"
    RUNTIME_CONTEXT = "runtime_context"
    UNSUPPORTED = "unsupported"


class CheckOperator(StrEnum):
    EQUALS = "equals"
    LESS_THAN_OR_EQUAL = "less_than_or_equal"
    GREATER_THAN_OR_EQUAL = "greater_than_or_equal"
    EXISTS = "exists"


class CheckOutcome(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    NOT_FOUND = "not_found"
    ERROR = "error"
    UNSUPPORTED = "unsupported"
    UNAVAILABLE = "unavailable"


class EvidenceRole(StrEnum):
    SUPPORTING = "supporting"
    CONTRADICTORY = "contradictory"
    SUPPORTING_ONLY = "supporting_only"
    MISSING = "missing"
    UNAVAILABLE = "unavailable"


class GraphNodeType(StrEnum):
    INCIDENT = "incident"
    ACTION = "corrective_action"
    INVARIANT = "invariant"
    EVIDENCE = "evidence"
    CHECK = "deterministic_check"
    VERDICT = "verdict"


class GraphEdgeType(StrEnum):
    CONTAINS = "contains"
    COMPILED_TO = "compiled_to"
    SUPPORTED_BY = "supported_by"
    CONTRADICTED_BY = "contradicted_by"
    TESTED_BY = "tested_by"
    CHECKED_BY = "checked_by"
    CLASSIFIED_AS = "classified_as"
    EVIDENCE_GAP = "evidence_gap"


class WorkflowEventType(StrEnum):
    STAGE_STARTED = "stage_started"
    STAGE_COMPLETED = "stage_completed"
    BUDGET_CONSUMED = "budget_consumed"
    FAILURE = "failure"


class AuditFailureCode(StrEnum):
    MODEL_CALL_BUDGET_EXHAUSTED = "model_call_budget_exhausted"
    INVESTIGATION_ROUND_BUDGET_EXHAUSTED = "investigation_round_budget_exhausted"
    INVALID_STATE = "invalid_state"
    WORKFLOW_FAILED = "workflow_failed"


class SourceLocation(DomainModel):
    line: int | None = Field(default=None, ge=1)
    section: str | None = None


class CompiledInvariant(DomainModel):
    id: str
    action_id: str
    original_action: str
    source_location: SourceLocation = Field(default_factory=SourceLocation)
    statement: str
    requirement_kind: RequirementKind
    availability: RequirementAvailability = RequirementAvailability.SUPPORTED
    expected_value: Any | None = None
    unit: str | None = None
    required_proof: list[str] = Field(default_factory=list)
    unavailable_reason: str | None = None

    @model_validator(mode="after")
    def unavailable_requirements_explain_why(self) -> Self:
        if self.availability != RequirementAvailability.SUPPORTED and not self.unavailable_reason:
            raise ValueError("unsupported and unavailable requirements need an explicit reason")
        return self


class DeterministicCheckSpec(DomainModel):
    id: str
    invariant_id: str
    check_type: DeterministicCheckType
    operator: CheckOperator = CheckOperator.EXISTS
    description: str
    expected: Any | None = None
    unit: str | None = None
    required: bool = True
    core: bool = True
    availability: RequirementAvailability = RequirementAvailability.SUPPORTED
    parameters: dict[str, Any] = Field(default_factory=dict)
    unavailable_reason: str | None = None

    @model_validator(mode="after")
    def unavailable_checks_explain_why(self) -> Self:
        if self.availability != RequirementAvailability.SUPPORTED and not self.unavailable_reason:
            raise ValueError("unsupported and unavailable checks need an explicit reason")
        return self


class EvidenceCitation(DomainModel):
    evidence_id: str
    source_path: str | None = None
    line_start: int | None = Field(default=None, ge=1)
    line_end: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def citation_range_is_ordered(self) -> Self:
        if self.line_end is not None and self.line_start is None:
            raise ValueError("line_end requires line_start")
        if self.line_start is not None and self.line_end is not None:
            if self.line_end < self.line_start:
                raise ValueError("line_end must not precede line_start")
        return self


class EvidenceRecord(DomainModel):
    id: str
    run_id: str
    action_id: str
    invariant_id: str
    kind: EvidenceKind
    role: EvidenceRole
    source_path: str | None = None
    line_start: int | None = Field(default=None, ge=1)
    line_end: int | None = Field(default=None, ge=1)
    excerpt: str | None = None
    retrieval_score: float | None = None
    source_record_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("source_path")
    @classmethod
    def source_path_is_relative(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.replace("\\", "/")
        candidate = PurePosixPath(normalized)
        if not normalized or candidate.is_absolute() or ".." in candidate.parts:
            raise ValueError("source_path must be a relative repository path")
        return candidate.as_posix()

    @model_validator(mode="after")
    def evidence_range_is_ordered(self) -> Self:
        if self.line_end is not None and self.line_start is None:
            raise ValueError("line_end requires line_start")
        if self.line_start is not None and self.line_end is not None:
            if self.line_end < self.line_start:
                raise ValueError("line_end must not precede line_start")
        return self

    def citation(self) -> EvidenceCitation:
        return EvidenceCitation(
            evidence_id=self.id,
            source_path=self.source_path,
            line_start=self.line_start,
            line_end=self.line_end,
        )


class DeterministicCheckResult(DomainModel):
    id: str
    run_id: str
    invariant_id: str
    check_spec_id: str
    outcome: CheckOutcome
    passed: bool | None = None
    core: bool = True
    expected: Any | None = None
    actual: Any | None = None
    detail: str
    evidence_ids: list[str] = Field(default_factory=list)
    duration_ms: float = Field(default=0, ge=0)

    @model_validator(mode="after")
    def outcome_matches_passed(self) -> Self:
        if self.outcome == CheckOutcome.PASSED and self.passed is not True:
            raise ValueError("passed outcome requires passed=True")
        if (
            self.outcome in {CheckOutcome.FAILED, CheckOutcome.NOT_FOUND}
            and self.passed is not False
        ):
            raise ValueError("failed/not_found outcome requires passed=False")
        if self.outcome in {CheckOutcome.UNAVAILABLE, CheckOutcome.UNSUPPORTED, CheckOutcome.ERROR}:
            if self.passed is not None:
                raise ValueError("non-assessable outcomes require passed=None")
        return self


class CheckExecution(DomainModel):
    result: DeterministicCheckResult
    evidence: list[EvidenceRecord] = Field(default_factory=list)


class ActionVerdict(DomainModel):
    id: str
    run_id: str
    action_id: str
    verdict: Verdict
    rationale: str
    invariant_ids: list[str] = Field(default_factory=list)
    citations: list[EvidenceCitation] = Field(default_factory=list)
    missing_proofs: list[str] = Field(default_factory=list)
    confidence: float = Field(default=1.0, ge=0, le=1)

    @model_validator(mode="after")
    def verdict_has_traceability(self) -> Self:
        if not self.citations and not self.missing_proofs:
            raise ValueError("every verdict must cite evidence or state missing proof")
        return self


class EvidenceGraphNode(DomainModel):
    id: str
    run_id: str
    node_type: GraphNodeType
    record_id: str
    label: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class EvidenceGraphEdge(DomainModel):
    id: str
    run_id: str
    source_node_id: str
    target_node_id: str
    edge_type: GraphEdgeType


class RepositoryIndexMetadata(DomainModel):
    id: str
    project_id: str
    run_id: str | None = None
    index_version: str
    documents_indexed: int = Field(ge=0)
    chunks_indexed: int = Field(ge=0)
    total_bytes: int = Field(ge=0)
    chunk_ids: list[str] = Field(default_factory=list)
    failures: list[dict[str, Any]] = Field(default_factory=list)
    skipped: dict[str, int] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)


class BudgetUsage(DomainModel):
    model_calls_used: int = Field(default=0, ge=0)
    model_calls_limit: int = Field(default=6, ge=1)
    investigation_round_limit: int = Field(default=3, ge=1)
    investigation_rounds: dict[str, int] = Field(default_factory=dict)
    deterministic_checks_run: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def usage_does_not_exceed_limits(self) -> Self:
        if self.model_calls_used > self.model_calls_limit:
            raise ValueError("model call budget exceeded")
        if any(
            value > self.investigation_round_limit for value in self.investigation_rounds.values()
        ):
            raise ValueError("investigation round budget exceeded")
        return self


class AuditRunSummary(DomainModel):
    id: str
    project_id: str
    incident_id: str
    status: RunStatus = RunStatus.QUEUED
    total_actions: int = Field(default=0, ge=0)
    completed_actions: int = Field(default=0, ge=0)
    verdict_counts: dict[Verdict, int] = Field(default_factory=dict)
    assessed_protection_coverage: float = Field(default=0, ge=0, le=100)
    budget: BudgetUsage = Field(default_factory=BudgetUsage)
    failure_code: AuditFailureCode | None = None
    error: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class WorkflowEvent(DomainModel):
    id: str
    run_id: str
    sequence: int = Field(ge=0)
    event_type: WorkflowEventType
    stage: RunStatus
    detail: str
    created_at: datetime = Field(default_factory=utc_now)


class AuditWorkflowState(DomainModel):
    summary: AuditRunSummary
    actions: list[ActionItem] = Field(default_factory=list)
    invariants: list[CompiledInvariant] = Field(default_factory=list)
    check_specs: list[DeterministicCheckSpec] = Field(default_factory=list)
    evidence: list[EvidenceRecord] = Field(default_factory=list)
    check_results: list[DeterministicCheckResult] = Field(default_factory=list)
    verdicts: list[ActionVerdict] = Field(default_factory=list)
    graph_nodes: list[EvidenceGraphNode] = Field(default_factory=list)
    graph_edges: list[EvidenceGraphEdge] = Field(default_factory=list)
    events: list[WorkflowEvent] = Field(default_factory=list)


class AuditRunCreate(DomainModel):
    project_id: str
    incident_id: str
