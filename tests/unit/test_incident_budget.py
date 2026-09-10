from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier, Lock

import pytest

from backend.app.audit.budget import BudgetExceeded
from backend.app.llm.base import GenerationRequest
from backend.app.models import ActionExtraction, Project
from backend.app.schemas import IncidentCreate
from backend.app.services import IncidentService
from backend.app.storage import SQLiteStore


class ExtractionProvider:
    provider_name = "counting-extraction"

    def __init__(self, *, fail: bool = False) -> None:
        self.calls = 0
        self.fail = fail
        self._lock = Lock()

    def generate(
        self, request: GenerationRequest, output_model: type[ActionExtraction]
    ) -> ActionExtraction:
        with self._lock:
            self.calls += 1
        if self.fail:
            raise RuntimeError("extraction failed")
        return output_model(actions=[])


def service_fixture(
    tmp_path: Path, provider: ExtractionProvider
) -> tuple[SQLiteStore, IncidentService, IncidentCreate]:
    repository = tmp_path / "repo"
    repository.mkdir()
    project = Project(id="project_1", name="fixture", repository_path=str(repository))
    store = SQLiteStore(tmp_path / "incident-budget.sqlite3")
    store.save_project(project)
    service = IncidentService(store, provider, max_model_calls=6)
    request = IncidentCreate(
        project_id=project.id,
        source_text="# Incident\n\n- Add bounded retries.",
    )
    return store, service, request


def test_six_extraction_attempts_are_allowed_and_seventh_is_rejected(tmp_path: Path) -> None:
    provider = ExtractionProvider()
    store, service, request = service_fixture(tmp_path, provider)

    incident_ids = {service.create(request).id for _ in range(6)}

    assert len(incident_ids) == 1
    assert provider.calls == 6
    with pytest.raises(BudgetExceeded, match="model call budget exhausted"):
        service.create(request)
    assert provider.calls == 6
    incident_id = incident_ids.pop()
    budget = store.get_incident_budget(incident_id)
    assert budget is not None
    assert budget.model_calls_used == budget.model_calls_limit == 6


def test_failed_extraction_attempt_is_persisted_before_provider_invocation(tmp_path: Path) -> None:
    provider = ExtractionProvider(fail=True)
    store, service, request = service_fixture(tmp_path, provider)

    with pytest.raises(RuntimeError, match="extraction failed"):
        service.create(request)

    incidents = store.connection.execute("SELECT id FROM incidents").fetchall()
    assert len(incidents) == 1
    budget = store.get_incident_budget(str(incidents[0][0]))
    assert budget is not None
    assert budget.model_calls_used == 1
    assert provider.calls == 1


def test_repeated_stable_incident_cannot_reset_budget_across_service_instances(
    tmp_path: Path,
) -> None:
    first_provider = ExtractionProvider()
    store, first_service, request = service_fixture(tmp_path, first_provider)
    incident = first_service.create(request)
    store.close()
    reopened = SQLiteStore(tmp_path / "incident-budget.sqlite3")
    second_provider = ExtractionProvider()
    second_service = IncidentService(reopened, second_provider, max_model_calls=6)

    repeated = second_service.create(request)

    assert repeated.id == incident.id
    budget = reopened.get_incident_budget(incident.id)
    assert budget is not None
    assert budget.model_calls_used == 2
    assert first_provider.calls == second_provider.calls == 1


def test_independent_stores_atomically_compete_for_final_incident_slot(tmp_path: Path) -> None:
    provider = ExtractionProvider()
    initial_store, service, request = service_fixture(tmp_path, provider)
    incident = service.create(request)
    for _ in range(4):
        service.create(request)
    database_path = tmp_path / "incident-budget.sqlite3"
    initial_store.close()
    stores = [SQLiteStore(database_path), SQLiteStore(database_path)]
    start = Barrier(3)

    def reserve(store: SQLiteStore) -> tuple[str, int | None]:
        start.wait(timeout=5)
        try:
            usage = store.reserve_incident_model_call(incident.id, 6)
        except BudgetExceeded:
            return "exceeded", None
        return "reserved", usage.model_calls_used

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(reserve, store) for store in stores]
            start.wait(timeout=5)
            outcomes = [future.result(timeout=5) for future in futures]

        assert sorted(outcomes) == [("exceeded", None), ("reserved", 6)]
        budget = stores[0].get_incident_budget(incident.id)
        assert budget is not None
        assert budget.model_calls_used == budget.model_calls_limit == 6
    finally:
        for store in stores:
            store.close()


def test_competing_services_invoke_provider_only_for_reserved_final_slot(tmp_path: Path) -> None:
    initial_provider = ExtractionProvider()
    initial_store, service, request = service_fixture(tmp_path, initial_provider)
    incident = service.create(request)
    for _ in range(4):
        service.create(request)
    database_path = tmp_path / "incident-budget.sqlite3"
    initial_store.close()
    stores = [SQLiteStore(database_path), SQLiteStore(database_path)]
    providers = [ExtractionProvider(), ExtractionProvider()]
    services = [
        IncidentService(store, provider, max_model_calls=6)
        for store, provider in zip(stores, providers, strict=True)
    ]
    start = Barrier(3)

    def create_incident(worker: IncidentService) -> str:
        start.wait(timeout=5)
        try:
            worker.create(request)
        except BudgetExceeded:
            return "exceeded"
        return "created"

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(create_incident, worker) for worker in services]
            start.wait(timeout=5)
            outcomes = [future.result(timeout=5) for future in futures]

        assert sorted(outcomes) == ["created", "exceeded"]
        assert sum(provider.calls for provider in providers) == 1
        assert initial_provider.calls == 5
        budget = stores[0].get_incident_budget(incident.id)
        assert budget is not None
        assert budget.model_calls_used == budget.model_calls_limit == 6
    finally:
        for store in stores:
            store.close()
