"""Explicit model-call and investigation-round budget enforcement."""

from __future__ import annotations

from enum import StrEnum
from typing import Generic, Protocol, TypeVar

from backend.app.audit.contracts import (
    AuditFailureCode,
    AuditWorkflowState,
    BudgetUsage,
    WorkflowEvent,
    WorkflowEventType,
)
from backend.app.ids import stable_id
from backend.app.llm.base import GenerationRequest, StructuredGenerationProvider
from backend.app.models import DomainModel, utc_now

OutputModel = TypeVar("OutputModel", bound=DomainModel)
MAX_MODEL_CALLS_PER_INCIDENT = 6


class BudgetKind(StrEnum):
    MODEL_CALL = "model_call"
    INVESTIGATION_ROUND = "investigation_round"


class BudgetExceeded(RuntimeError):
    """Raised before work would exceed a configured audit budget."""

    def __init__(self, kind: BudgetKind, detail: str) -> None:
        super().__init__(detail)
        self.kind = kind
        self.failure_code = (
            AuditFailureCode.MODEL_CALL_BUDGET_EXHAUSTED
            if kind == BudgetKind.MODEL_CALL
            else AuditFailureCode.INVESTIGATION_ROUND_BUDGET_EXHAUSTED
        )


class BudgetTracker:
    def __init__(self, usage: BudgetUsage) -> None:
        self.usage = usage

    def consume_model_call(self) -> BudgetUsage:
        if self.usage.model_calls_used >= self.usage.model_calls_limit:
            raise BudgetExceeded(BudgetKind.MODEL_CALL, "model call budget exhausted")
        self.usage = self.usage.model_copy(
            update={"model_calls_used": self.usage.model_calls_used + 1}
        )
        return self.usage

    def consume_investigation_round(self, invariant_id: str) -> BudgetUsage:
        rounds = dict(self.usage.investigation_rounds)
        current = rounds.get(invariant_id, 0)
        if current >= self.usage.investigation_round_limit:
            raise BudgetExceeded(
                BudgetKind.INVESTIGATION_ROUND,
                f"investigation round budget exhausted for {invariant_id}",
            )
        rounds[invariant_id] = current + 1
        self.usage = self.usage.model_copy(update={"investigation_rounds": rounds})
        return self.usage

    def record_check(self) -> BudgetUsage:
        self.usage = self.usage.model_copy(
            update={"deterministic_checks_run": self.usage.deterministic_checks_run + 1}
        )
        return self.usage


class AuditStateStore(Protocol):
    def load_audit_state(self, run_id: str) -> AuditWorkflowState | None: ...

    def save_audit_state(self, state: AuditWorkflowState) -> None: ...

    def reserve_incident_model_call(self, incident_id: str, limit: int) -> BudgetUsage: ...


class BoundedProviderGateway(Generic[OutputModel]):
    """Reserve and persist model-call budget before every provider invocation."""

    def __init__(
        self,
        provider: StructuredGenerationProvider[OutputModel],
        store: AuditStateStore,
        run_id: str,
    ) -> None:
        self.provider = provider
        self.store = store
        self.run_id = run_id

    def generate(self, request: GenerationRequest, output_model: type[OutputModel]) -> OutputModel:
        state = self.store.load_audit_state(self.run_id)
        if state is None:
            raise ValueError("audit run not found")
        incident_usage = self.store.reserve_incident_model_call(
            state.summary.incident_id, state.summary.budget.model_calls_limit
        )
        usage = state.summary.budget.model_copy(
            update={
                "model_calls_used": incident_usage.model_calls_used,
                "model_calls_limit": incident_usage.model_calls_limit,
            }
        )
        sequence = len(state.events)
        event = WorkflowEvent(
            id=stable_id(
                "workflow_event",
                self.run_id,
                sequence,
                WorkflowEventType.BUDGET_CONSUMED.value,
            ),
            run_id=self.run_id,
            sequence=sequence,
            event_type=WorkflowEventType.BUDGET_CONSUMED,
            stage=state.summary.status,
            detail=f"reserved model call {usage.model_calls_used}/{usage.model_calls_limit}",
        )
        summary = state.summary.model_copy(update={"budget": usage, "updated_at": utc_now()})
        self.store.save_audit_state(
            state.model_copy(update={"summary": summary, "events": [*state.events, event]})
        )
        return self.provider.generate(request, output_model)
