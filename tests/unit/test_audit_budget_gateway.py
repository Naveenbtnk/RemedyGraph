import hashlib
from pathlib import Path

import pytest

from backend.app.audit.budget import BoundedProviderGateway, BudgetExceeded, BudgetKind
from backend.app.audit.contracts import AuditRunSummary, AuditWorkflowState, BudgetUsage
from backend.app.llm.base import GenerationRequest
from backend.app.models import ActionExtraction, Incident, Project
from backend.app.storage import SQLiteStore


class CountingProvider:
    provider_name = "counting"

    def __init__(self, *, fail: bool = False) -> None:
        self.calls = 0
        self.fail = fail

    def generate(
        self, request: GenerationRequest, output_model: type[ActionExtraction]
    ) -> ActionExtraction:
        self.calls += 1
        if self.fail:
            raise RuntimeError("provider failed")
        return output_model(actions=[])


def audit_store(tmp_path: Path, *, model_limit: int = 6) -> SQLiteStore:
    repository = tmp_path / "repo"
    repository.mkdir()
    project = Project(id="project_1", name="fixture", repository_path=str(repository))
    incident = Incident(
        id="incident_1",
        project_id=project.id,
        title="fixture",
        source_text_hash=hashlib.sha256(b"fixture").hexdigest(),
    )
    store = SQLiteStore(tmp_path / "budget.sqlite3")
    store.save_project(project)
    store.save_incident(incident)
    store.save_audit_state(
        AuditWorkflowState(
            summary=AuditRunSummary(
                id="run_1",
                project_id=project.id,
                incident_id=incident.id,
                budget=BudgetUsage(model_calls_limit=model_limit),
            )
        )
    )
    return store


def test_gateway_persists_each_successful_attempt_and_rejects_seventh(tmp_path: Path) -> None:
    store = audit_store(tmp_path)
    provider = CountingProvider()
    gateway = BoundedProviderGateway(provider, store, "run_1")
    request = GenerationRequest(task="bounded", input_text="fixture")

    for expected in range(1, 7):
        gateway.generate(request, ActionExtraction)
        state = store.load_audit_state("run_1")
        assert state is not None
        assert state.summary.budget.model_calls_used == expected

    with pytest.raises(BudgetExceeded) as exc_info:
        gateway.generate(request, ActionExtraction)

    assert exc_info.value.kind == BudgetKind.MODEL_CALL
    assert provider.calls == 6
    persisted = store.load_audit_state("run_1")
    assert persisted is not None
    assert persisted.summary.budget.model_calls_used == 6
    assert len(persisted.events) == 6


def test_gateway_persists_failed_provider_attempt_without_retry(tmp_path: Path) -> None:
    store = audit_store(tmp_path)
    provider = CountingProvider(fail=True)
    gateway = BoundedProviderGateway(provider, store, "run_1")

    with pytest.raises(RuntimeError, match="provider failed"):
        gateway.generate(GenerationRequest(task="bounded", input_text="fixture"), ActionExtraction)

    state = store.load_audit_state("run_1")
    assert state is not None
    assert state.summary.budget.model_calls_used == 1
    assert provider.calls == 1


def test_gateway_shares_budget_already_consumed_by_incident_extraction(tmp_path: Path) -> None:
    store = audit_store(tmp_path)
    store.reserve_incident_model_call("incident_1", 6)
    provider = CountingProvider()
    gateway = BoundedProviderGateway(provider, store, "run_1")
    request = GenerationRequest(task="bounded", input_text="fixture")

    for _ in range(5):
        gateway.generate(request, ActionExtraction)

    with pytest.raises(BudgetExceeded):
        gateway.generate(request, ActionExtraction)
    state = store.load_audit_state("run_1")
    assert state is not None
    assert state.summary.budget.model_calls_used == 6
    assert provider.calls == 5
