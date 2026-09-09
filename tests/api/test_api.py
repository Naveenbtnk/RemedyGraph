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
