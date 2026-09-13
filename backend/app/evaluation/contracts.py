"""Typed contracts for RemedyBench manifests and measured reports."""

from __future__ import annotations

from datetime import datetime

from pydantic import Field, field_validator

from backend.app.audit.contracts import RequirementKind
from backend.app.guards.contracts import GuardExecutionStatus, GuardType
from backend.app.models import DomainModel, Verdict


class GoldAction(DomainModel):
    id: str
    text: str
    verdict: Verdict
    requirement_kind: RequirementKind
    gold_evidence_paths: list[str] = Field(default_factory=list)
    acceptable_citation_paths: list[str] = Field(default_factory=list)
    expected_guard_type: GuardType | None = None

    @field_validator("gold_evidence_paths", "acceptable_citation_paths")
    @classmethod
    def paths_are_relative(cls, value: list[str]) -> list[str]:
        if any(
            path.startswith(("/", "\\")) or ".." in path.replace("\\", "/").split("/")
            for path in value
        ):
            raise ValueError("benchmark evidence paths must be relative and traversal-free")
        return [path.replace("\\", "/") for path in value]


class BenchmarkCase(DomainModel):
    id: str
    title: str
    incident_path: str
    repository_path: str
    actions: list[GoldAction] = Field(min_length=1)


class BenchmarkProvenance(DomainModel):
    license: str
    synthetic: bool
    author: str
    created: str
    statement: str


class BenchmarkManifest(DomainModel):
    schema_version: int = 1
    benchmark_version: str
    prompt_version: str
    cases: list[BenchmarkCase] = Field(min_length=1)
    provenance: BenchmarkProvenance


class ActionPrediction(DomainModel):
    case_id: str
    gold_action_id: str
    gold_text: str
    extracted_text: str | None = None
    gold_verdict: Verdict
    predicted_verdict: Verdict | None = None
    gold_requirement_kind: RequirementKind
    predicted_requirement_kind: RequirementKind | None = None
    retrieved_paths_at_5: list[str] = Field(default_factory=list)
    citation_paths: list[str] = Field(default_factory=list)
    citation_kinds: list[str] = Field(default_factory=list)
    guard_type: GuardType | None = None
    guard_status: GuardExecutionStatus | None = None
    guard_detected_bad_state: bool | None = None


class CaseEvaluation(DomainModel):
    case_id: str
    title: str
    duration_ms: float = Field(ge=0)
    model_calls: int = Field(ge=0)
    extracted_actions: list[str]
    predictions: list[ActionPrediction]


class EvaluationMetrics(DomainModel):
    cases: int
    gold_actions: int
    extracted_actions: int
    action_extraction_precision: float
    action_extraction_recall: float
    action_extraction_f1: float
    invariant_validity_rate: float
    evidence_recall_at_5: float
    citation_accuracy: float
    verification_accuracy: float
    verification_macro_f1: float
    verification_per_class_f1: dict[str, float]
    false_positive_rate: float
    unsupported_verified_rate: float
    documentation_only_verified_rate: float
    guard_type_accuracy: float
    guard_runnable_rate: float
    guard_detection_rate: float
    average_model_calls_per_incident: float
    p50_duration_ms: float
    p95_duration_ms: float


class EvaluationMetadata(DomainModel):
    evaluation_id: str
    repository_commit: str
    worktree_dirty: bool
    benchmark_version: str
    benchmark_sha256: str
    provider: str
    model: str
    prompt_version: str
    random_seed: int
    retrieval_top_k: int
    started_at: datetime
    completed_at: datetime


class EvaluationReport(DomainModel):
    schema_version: int = 1
    metadata: EvaluationMetadata
    metrics: EvaluationMetrics
    cases: list[CaseEvaluation]
