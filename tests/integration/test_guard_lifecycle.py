"""End-to-end guard preview, approval, write, execution, and persistence tests."""

from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.main import create_app
from backend.app.settings import Settings
from backend.app.storage import SQLiteStore


def _completed_missing_run(client, repository: Path) -> str:
    project = client.post(
        "/api/v1/projects", json={"name": "guard-fixture", "repository_path": str(repository)}
    ).json()
    incident = client.post(
        "/api/v1/incidents",
        json={
            "project_id": project["id"],
            "source_text": "# Outage\n\n- Add a circuit breaker.\n",
        },
    ).json()
    response = client.post(
        "/api/v1/runs",
        json={"project_id": project["id"], "incident_id": incident["id"]},
    )
    assert response.status_code == 201
    assert response.json()["status"] == "COMPLETE"
    return str(response.json()["id"])


def test_guard_requires_approval_and_detects_bad_then_good_state(client, tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    (repository / "service.py").write_text(
        "def call_provider():\n    return True\n", encoding="utf-8"
    )
    run_id = _completed_missing_run(client, repository)

    preview_response = client.post(f"/api/v1/runs/{run_id}/guards/preview")
    assert preview_response.status_code == 200
    guards = preview_response.json()["guards"]
    assert len(guards) == 1
    guard = guards[0]
    artifact = repository / Path(*guard["target_path"].split("/"))
    assert not artifact.exists()

    denied = client.post(f"/api/v1/runs/{run_id}/guards/{guard['id']}/execute")
    assert denied.status_code == 409
    assert not artifact.exists()

    approved = client.post(
        f"/api/v1/runs/{run_id}/guards/{guard['id']}/approve",
        json={"approved": True, "preview_sha256": guard["preview_sha256"]},
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "WRITTEN"
    assert artifact.read_text(encoding="utf-8") == guard["preview"]

    bad = client.post(f"/api/v1/runs/{run_id}/guards/{guard['id']}/execute")
    assert bad.status_code == 200
    assert bad.json()["status"] == "FAILED"
    assert bad.json()["exit_code"] == 1

    (repository / "misleading.py").write_text("# We added a circuit breaker.\n", encoding="utf-8")
    comment_only = client.post(f"/api/v1/runs/{run_id}/guards/{guard['id']}/execute")
    assert comment_only.json()["status"] == "FAILED"

    (repository / "circuit_breaker.py").write_text(
        "class CircuitBreaker:\n    pass\n\nbreaker = CircuitBreaker()\n", encoding="utf-8"
    )
    good = client.post(f"/api/v1/runs/{run_id}/guards/{guard['id']}/execute")
    assert good.status_code == 200
    assert good.json()["status"] == "PASSED"
    assert good.json()["exit_code"] == 0

    executions = client.get(f"/api/v1/runs/{run_id}/guards/{guard['id']}/executions").json()[
        "executions"
    ]
    assert [item["status"] for item in executions] == ["FAILED", "FAILED", "PASSED"]
    persisted = client.get(f"/api/v1/runs/{run_id}/guards").json()["guards"]
    assert persisted[0]["status"] == "PASSED"


def test_rejected_or_stale_guard_never_writes(client, tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    run_id = _completed_missing_run(client, repository)
    guard = client.post(f"/api/v1/runs/{run_id}/guards/preview").json()["guards"][0]
    artifact = repository / Path(*guard["target_path"].split("/"))

    stale = client.post(
        f"/api/v1/runs/{run_id}/guards/{guard['id']}/approve",
        json={"approved": True, "preview_sha256": "0" * 64},
    )
    assert stale.status_code == 409
    assert not artifact.exists()

    rejected = client.post(
        f"/api/v1/runs/{run_id}/guards/{guard['id']}/approve",
        json={"approved": False, "preview_sha256": guard["preview_sha256"]},
    )
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "REJECTED"
    assert not artifact.exists()
    assert client.post(f"/api/v1/runs/{run_id}/guards/{guard['id']}/execute").status_code == 409


def test_guard_approval_and_execution_survive_database_reopen(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    database = tmp_path / "remedygraph.sqlite3"
    settings = Settings(workspace_root=tmp_path, database_path=str(database))

    with TestClient(create_app(settings)) as client:
        run_id = _completed_missing_run(client, repository)
        guard = client.post(f"/api/v1/runs/{run_id}/guards/preview").json()["guards"][0]
        approved = client.post(
            f"/api/v1/runs/{run_id}/guards/{guard['id']}/approve",
            json={"approved": True, "preview_sha256": guard["preview_sha256"]},
        )
        assert approved.status_code == 200
        executed = client.post(f"/api/v1/runs/{run_id}/guards/{guard['id']}/execute")
        assert executed.status_code == 200
        execution_id = executed.json()["id"]

    reopened = SQLiteStore(database)
    try:
        persisted_guard = reopened.get_guard(guard["id"])
        persisted_approval = reopened.get_guard_approval(guard["id"])
        persisted_executions = reopened.list_guard_executions(guard["id"])

        assert persisted_guard is not None
        assert persisted_guard.status == "FAILED"
        assert persisted_approval is not None
        assert persisted_approval.approved is True
        assert persisted_approval.preview_sha256 == guard["preview_sha256"]
        assert [item.id for item in persisted_executions] == [execution_id]
        assert persisted_executions[0].status == "FAILED"
    finally:
        reopened.close()
