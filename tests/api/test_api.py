import sqlite3

import pytest
from fastapi.testclient import TestClient

from backend.app.audit.budget import BudgetExceeded, BudgetKind
from backend.app.main import create_app
from backend.app.settings import Settings


def test_health(client) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["version"] == "0.1.0"


def test_project_and_incident_endpoints_return_typed_records(client, tmp_path) -> None:
    project_response = client.post(
        "/api/v1/projects",
        json={"name": "demo", "repository_path": str(tmp_path)},
    )
    assert project_response.status_code == 201
    project = project_response.json()

    incident_response = client.post(
        "/api/v1/incidents",
        json={
            "project_id": project["id"],
            "source_name": "INC-042.md",
            "source_text": """# Payment retry storm

Affected services: payments, alerts

The payment API exhausted workers during a provider outage.

## Corrective actions
- Bound retries to 3 and add jitter.
- Add a regression test for retry exhaustion.
""",
        },
    )

    assert incident_response.status_code == 201
    incident = incident_response.json()
    assert incident["title"] == "Payment retry storm"
    assert incident["affected_services"] == ["payments", "alerts"]
    assert len(incident["actions"]) == 3
    assert incident["source_text_hash"]


def test_project_outside_workspace_is_rejected(client, tmp_path) -> None:
    outside = tmp_path.parent / "outside"
    outside.mkdir()

    response = client.post("/api/v1/projects", json={"repository_path": str(outside)})

    assert response.status_code == 422
    assert "inside" in response.json()["detail"]


def test_audit_run_read_endpoints_return_persisted_trace(client, tmp_path) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / "settings.yaml").write_text("retry:\n  limit: 3\n", encoding="utf-8")
    (tmp_path / "tests" / "test_retry.py").write_text(
        "def test_retry_bound():\n    assert 3 == 3\n", encoding="utf-8"
    )
    project = client.post("/api/v1/projects", json={"repository_path": str(tmp_path)}).json()
    incident = client.post(
        "/api/v1/incidents",
        json={
            "project_id": project["id"],
            "source_text": "# Retry storm\n\n- Bound retries to 3.\n",
        },
    ).json()

    created = client.post(
        "/api/v1/runs",
        json={"project_id": project["id"], "incident_id": incident["id"]},
    )

    assert created.status_code == 201
    run = created.json()
    assert run["status"] == "COMPLETE"
    assert run["budget"]["model_calls_used"] == 1
    run_id = run["id"]
    assert client.get(f"/api/v1/runs/{run_id}").status_code == 200
    actions = client.get(f"/api/v1/runs/{run_id}/actions").json()["verdicts"]
    evidence = client.get(f"/api/v1/runs/{run_id}/evidence").json()["evidence"]
    graph = client.get(f"/api/v1/runs/{run_id}/graph").json()
    assert actions
    assert evidence
    assert graph["nodes"]
    assert graph["edges"]


def test_missing_audit_run_returns_404(client) -> None:
    response = client.get("/api/v1/runs/run_missing")

    assert response.status_code == 404
    assert response.json()["detail"] == "audit run not found"


@pytest.mark.parametrize("suffix", ["", "/actions", "/evidence", "/graph"])
def test_all_audit_read_endpoints_reject_unknown_ids(client, suffix: str) -> None:
    response = client.get(f"/api/v1/runs/run_missing{suffix}")

    assert response.status_code == 404
    assert response.json()["detail"] == "audit run not found"


def test_start_audit_rejects_project_incident_mismatch(client, tmp_path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    project_1 = client.post("/api/v1/projects", json={"repository_path": str(first)}).json()
    project_2 = client.post("/api/v1/projects", json={"repository_path": str(second)}).json()
    incident = client.post(
        "/api/v1/incidents",
        json={"project_id": project_1["id"], "source_text": "# Incident\n\n- Add a timeout."},
    ).json()

    response = client.post(
        "/api/v1/runs",
        json={"project_id": project_2["id"], "incident_id": incident["id"]},
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "incident does not belong to project"


@pytest.mark.parametrize(
    ("failure", "expected_code"),
    [
        (
            BudgetExceeded(BudgetKind.INVESTIGATION_ROUND, "round limit"),
            "investigation_round_budget_exhausted",
        ),
        (ValueError("invalid workflow state"), "invalid_state"),
    ],
)
def test_audit_failure_is_safe_typed_and_persisted(
    client, tmp_path, monkeypatch, failure: Exception, expected_code: str
) -> None:
    project = client.post("/api/v1/projects", json={"repository_path": str(tmp_path)}).json()
    incident = client.post(
        "/api/v1/incidents",
        json={"project_id": project["id"], "source_text": "# Incident\n\n- Add a timeout."},
    ).json()
    workflow = client.app.state.audit_workflow
    attempts = 0

    def fail_once(_state):
        nonlocal attempts
        attempts += 1
        raise failure

    monkeypatch.setattr(workflow.graph, "invoke", fail_once)
    created = client.post(
        "/api/v1/runs",
        json={"project_id": project["id"], "incident_id": incident["id"]},
    )

    assert created.status_code == 201
    payload = created.json()
    assert payload["status"] == "FAILED"
    assert payload["failure_code"] == expected_code
    assert payload["error"].startswith("audit failed safely:")
    assert attempts == 1
    persisted = client.get(f"/api/v1/runs/{payload['id']}")
    assert persisted.status_code == 200
    assert persisted.json()["failure_code"] == expected_code


def test_database_lock_returns_typed_service_unavailable(tmp_path) -> None:
    database_path = tmp_path / "locked.sqlite3"
    app = create_app(Settings(workspace_root=tmp_path, database_path=str(database_path)))
    request = {"source_text": "# Incident\n\n- Add bounded retries."}

    with TestClient(app) as client:
        incident = client.post("/api/v1/incidents", json=request)
        assert incident.status_code == 201
        app.state.store.connection.execute("PRAGMA busy_timeout = 1")
        blocker = sqlite3.connect(database_path)
        blocker.execute("BEGIN IMMEDIATE")
        try:
            response = client.post("/api/v1/incidents", json=request)
        finally:
            blocker.rollback()
            blocker.close()

        budget = app.state.store.get_incident_budget(incident.json()["id"])
        assert budget is not None
        assert budget.model_calls_used == 1

    assert response.status_code == 503
    assert response.json() == {
        "detail": "storage is temporarily busy; retry later",
        "failure_code": "storage_busy",
    }
