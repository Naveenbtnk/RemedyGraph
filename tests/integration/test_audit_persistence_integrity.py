import hashlib
from pathlib import Path

import pytest

from backend.app.audit.contracts import (
    AuditRunSummary,
    AuditWorkflowState,
    BudgetUsage,
    GraphEdgeType,
    GraphNodeType,
)
from backend.app.audit.workflow import AuditWorkflow
from backend.app.models import ActionItem, Incident, Project, RunStatus
from backend.app.settings import Settings
from backend.app.storage import (
    SCHEMA_VERSION,
    AuditStateIntegrityError,
    SQLiteStore,
    UnsupportedSchemaVersion,
)


def completed_audit(tmp_path: Path) -> tuple[SQLiteStore, AuditWorkflowState, Incident]:
    repository = tmp_path / "repo"
    (repository / "tests").mkdir(parents=True)
    (repository / "limits.py").write_text(
        "MAX_RETRIES = 3\nTIMEOUT_SECONDS = 5\n", encoding="utf-8"
    )
    (repository / "tests" / "test_limits.py").write_text(
        """from limits import MAX_RETRIES, TIMEOUT_SECONDS

def test_retry_bound():
    assert MAX_RETRIES == 3

def test_timeout_bound():
    assert TIMEOUT_SECONDS == 5
""",
        encoding="utf-8",
    )
    project = Project(id="project_1", name="fixture", repository_path=str(repository))
    actions = [
        ActionItem(
            id="action_retry",
            incident_id="incident_1",
            text="Bound retries to 3",
            order=0,
        ),
        ActionItem(
            id="action_timeout",
            incident_id="incident_1",
            text="Set timeout to 5 seconds",
            order=1,
        ),
    ]
    incident = Incident(
        id="incident_1",
        project_id=project.id,
        title="fixture",
        source_text_hash=hashlib.sha256(b"fixture").hexdigest(),
        actions=actions,
    )
    store = SQLiteStore(tmp_path / "audit.sqlite3")
    store.save_project(project)
    store.save_incident(incident)
    state = AuditWorkflow(store, Settings(workspace_root=tmp_path)).run(
        project, incident, run_id="run_1"
    )
    assert state.summary.status == RunStatus.COMPLETE
    return store, state, incident


def test_schema_version_is_created_and_validated_on_reopen(tmp_path: Path) -> None:
    database = tmp_path / "versioned.sqlite3"
    store = SQLiteStore(database)
    assert store.schema_version == SCHEMA_VERSION
    store.close()

    reopened = SQLiteStore(database)
    assert reopened.schema_version == SCHEMA_VERSION
    reopened.close()


def test_unsupported_schema_version_is_rejected(tmp_path: Path) -> None:
    database = tmp_path / "future.sqlite3"
    store = SQLiteStore(database)
    store.connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION + 1}")
    store.close()

    with pytest.raises(UnsupportedSchemaVersion, match="unsupported"):
        SQLiteStore(database)


def test_version_one_database_migrates_incident_budget_table(tmp_path: Path) -> None:
    database = tmp_path / "version-one.sqlite3"
    store = SQLiteStore(database)
    repository = tmp_path / "version-one-repo"
    repository.mkdir()
    project = Project(id="migration_project", name="fixture", repository_path=str(repository))
    incident = Incident(
        id="migration_incident",
        project_id=project.id,
        title="fixture",
        source_text_hash=hashlib.sha256(b"migration").hexdigest(),
    )
    store.save_project(project)
    store.save_incident(incident)
    store.save_audit_state(
        AuditWorkflowState(
            summary=AuditRunSummary(
                id="migration_run",
                project_id=project.id,
                incident_id=incident.id,
                budget=BudgetUsage(model_calls_used=2),
            )
        )
    )
    store.connection.execute("DROP TABLE incident_budget_counters")
    store.connection.execute("PRAGMA user_version = 1")
    store.close()

    migrated = SQLiteStore(database)

    assert migrated.schema_version == SCHEMA_VERSION
    assert (
        migrated.connection.execute(
            "SELECT name FROM sqlite_master WHERE name = 'incident_budget_counters'"
        ).fetchone()
        is not None
    )
    migrated_budget = migrated.get_incident_budget(incident.id)
    assert migrated_budget is not None
    assert migrated_budget.model_calls_used == 2
    migrated.close()


def test_version_two_database_migrates_guard_lifecycle_tables(tmp_path: Path) -> None:
    database = tmp_path / "version-two.sqlite3"
    store = SQLiteStore(database)
    store.connection.executescript(
        """
        DROP TABLE guard_executions;
        DROP TABLE guard_approvals;
        DROP TABLE guard_specs;
        PRAGMA user_version = 2;
        """
    )
    store.close()

    migrated = SQLiteStore(database)

    assert migrated.schema_version == SCHEMA_VERSION
    tables = {
        str(row[0])
        for row in migrated.connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    assert {"guard_specs", "guard_approvals", "guard_executions"} <= tables
    migrated.close()


def test_store_rejects_cross_project_run_without_partial_rows(tmp_path: Path) -> None:
    repository_1 = tmp_path / "one"
    repository_2 = tmp_path / "two"
    repository_1.mkdir()
    repository_2.mkdir()
    store = SQLiteStore(tmp_path / "cross-project.sqlite3")
    project_1 = Project(id="p1", name="one", repository_path=str(repository_1))
    project_2 = Project(id="p2", name="two", repository_path=str(repository_2))
    store.save_project(project_1)
    store.save_project(project_2)
    incident = Incident(
        id="incident_1",
        project_id=project_1.id,
        title="fixture",
        source_text_hash=hashlib.sha256(b"fixture").hexdigest(),
    )
    store.save_incident(incident)
    invalid = AuditWorkflowState(
        summary=AuditRunSummary(id="invalid_run", project_id=project_2.id, incident_id=incident.id)
    )

    with pytest.raises(AuditStateIntegrityError, match="does not own"):
        store.save_audit_state(invalid)

    assert store.get_run_summary("invalid_run") is None
    assert (
        store.connection.execute(
            "SELECT COUNT(*) FROM budget_counters WHERE run_id = 'invalid_run'"
        ).fetchone()[0]
        == 0
    )


@pytest.mark.parametrize(
    "mutation",
    ["invariant", "check", "evidence", "result", "verdict", "node", "edge"],
)
def test_cross_run_or_cross_action_records_are_rejected(tmp_path: Path, mutation: str) -> None:
    store, state, _ = completed_audit(tmp_path)
    invalid = state.model_copy(deep=True)
    if mutation == "invariant":
        invalid.invariants[0] = invalid.invariants[0].model_copy(update={"action_id": "foreign"})
    elif mutation == "check":
        invalid.check_specs[0] = invalid.check_specs[0].model_copy(
            update={"invariant_id": "foreign"}
        )
    elif mutation == "evidence":
        invalid.evidence[0] = invalid.evidence[0].model_copy(update={"run_id": "run_2"})
    elif mutation == "result":
        invalid.check_results[0] = invalid.check_results[0].model_copy(update={"run_id": "run_2"})
    elif mutation == "verdict":
        invalid.verdicts[0] = invalid.verdicts[0].model_copy(update={"run_id": "run_2"})
    elif mutation == "node":
        invalid.graph_nodes[0] = invalid.graph_nodes[0].model_copy(update={"run_id": "run_2"})
    else:
        invalid.graph_edges[0] = invalid.graph_edges[0].model_copy(update={"run_id": "run_2"})

    with pytest.raises(AuditStateIntegrityError):
        store.save_audit_state(invalid)

    assert store.load_audit_state(state.summary.id) == state


@pytest.mark.parametrize("mutation", ["duplicate", "unknown", "wrong_type", "relationship"])
def test_graph_integrity_rejects_invalid_nodes_and_relationships(
    tmp_path: Path, mutation: str
) -> None:
    store, state, _ = completed_audit(tmp_path)
    invalid = state.model_copy(deep=True)
    if mutation == "duplicate":
        invalid.graph_nodes.append(invalid.graph_nodes[0])
    elif mutation == "unknown":
        invalid.graph_edges[0] = invalid.graph_edges[0].model_copy(
            update={"target_node_id": "unknown_node"}
        )
    elif mutation == "wrong_type":
        evidence_index = next(
            index
            for index, node in enumerate(invalid.graph_nodes)
            if node.node_type == GraphNodeType.EVIDENCE
        )
        invalid.graph_nodes[evidence_index] = invalid.graph_nodes[evidence_index].model_copy(
            update={"node_type": GraphNodeType.VERDICT}
        )
    else:
        invalid.graph_edges[0] = invalid.graph_edges[0].model_copy(
            update={"edge_type": GraphEdgeType.CLASSIFIED_AS}
        )

    with pytest.raises(AuditStateIntegrityError):
        store.save_audit_state(invalid)

    assert store.load_audit_state(state.summary.id) == state


def test_complete_snapshot_removes_all_absent_child_records(tmp_path: Path) -> None:
    store, state, _ = completed_audit(tmp_path)
    retained_invariant = state.invariants[0]
    retained_specs = [
        item for item in state.check_specs if item.invariant_id == retained_invariant.id
    ]
    budget = state.summary.budget.model_copy(
        update={
            "investigation_rounds": {retained_invariant.id: 1},
            "deterministic_checks_run": 0,
        }
    )
    summary = state.summary.model_copy(
        update={
            "status": RunStatus.INVESTIGATING,
            "completed_actions": 0,
            "verdict_counts": {},
            "budget": budget,
        }
    )
    replacement = state.model_copy(
        update={
            "summary": summary,
            "invariants": [retained_invariant],
            "check_specs": retained_specs,
            "evidence": [],
            "check_results": [],
            "verdicts": [],
            "graph_nodes": [],
            "graph_edges": [],
            "events": state.events[:1],
        }
    )

    store.save_audit_state(replacement)
    reloaded = store.load_audit_state(state.summary.id)

    assert reloaded == replacement
    assert len(store.list_invariants(state.summary.id)) == 1
    assert len(store.list_check_specs(state.summary.id)) == len(retained_specs)
    assert store.list_evidence(state.summary.id) == []
    assert store.list_check_results(state.summary.id) == []
    assert store.list_verdicts(state.summary.id) == []
    assert store.list_graph_nodes(state.summary.id) == []
    assert store.list_graph_edges(state.summary.id) == []
    assert store.list_workflow_events(state.summary.id) == state.events[:1]


def test_database_failure_rolls_back_full_snapshot_replacement(tmp_path: Path) -> None:
    store, state, _ = completed_audit(tmp_path)
    store.connection.execute(
        """CREATE TRIGGER reject_invariant BEFORE INSERT ON compiled_invariants
        WHEN NEW.run_id = 'run_1' BEGIN SELECT RAISE(ABORT, 'blocked'); END"""
    )
    changed_summary = state.summary.model_copy(update={"status": RunStatus.INVESTIGATING})
    replacement = state.model_copy(update={"summary": changed_summary})

    with pytest.raises(AuditStateIntegrityError, match="violates"):
        store.save_audit_state(replacement)

    assert store.load_audit_state(state.summary.id) == state
