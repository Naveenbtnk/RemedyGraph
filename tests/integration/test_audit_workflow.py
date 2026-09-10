import hashlib
from pathlib import Path

from backend.app.audit.graph import EvidenceGraphBuilder
from backend.app.audit.workflow import AuditWorkflow
from backend.app.models import ActionItem, Incident, Project, RunStatus, Verdict
from backend.app.settings import Settings
from backend.app.storage import SQLiteStore


def test_bounded_audit_persists_and_reloads_all_day3_records(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    (repository / "tests").mkdir(parents=True)
    (repository / "settings.yaml").write_text("retry:\n  limit: 4\n", encoding="utf-8")
    (repository / "retry.py").write_text(
        """MAX_ATTEMPTS = 3

def exponential_backoff_with_jitter(attempt: int) -> float:
    return min(2 ** attempt, 8) + 0.1

def retry_delay(attempt: int) -> float:
    return exponential_backoff_with_jitter(attempt)

def route_failed_message(message: object) -> object:
    return dead_letter_queue.send(message)
""",
        encoding="utf-8",
    )
    (repository / "circuit.py").write_text("class CircuitBreaker:\n    pass\n", encoding="utf-8")
    (repository / "tests" / "test_retry.py").write_text(
        """from retry import MAX_ATTEMPTS, exponential_backoff_with_jitter

def test_retry_exhaustion_is_bounded():
    assert MAX_ATTEMPTS == 3

def test_exponential_backoff_with_jitter():
    assert exponential_backoff_with_jitter(2) <= 8.1
""",
        encoding="utf-8",
    )
    project = Project(id="project_1", name="fixture", repository_path=str(repository))
    action_texts = [
        "Bound retries to 3",
        "Add exponential backoff with jitter",
        "Add a regression test for retry exhaustion",
        "Confirm production gateway deadline exceeds client deadline",
        "Add a circuit breaker",
        "Add a dead letter queue",
    ]
    actions = [
        ActionItem(
            id=f"action_{index}",
            incident_id="incident_1",
            text=text,
            source_line=10 + index,
            source_section="Corrective actions",
            order=index,
        )
        for index, text in enumerate(action_texts)
    ]
    incident = Incident(
        id="incident_1",
        project_id=project.id,
        title="Retry storm",
        source_text_hash=hashlib.sha256(b"fixture").hexdigest(),
        actions=actions,
    )
    database = tmp_path / "audit.sqlite3"
    store = SQLiteStore(database)
    store.save_project(project)
    store.save_incident(incident)
    settings = Settings(
        workspace_root=tmp_path,
        max_model_calls=6,
        max_investigation_rounds=3,
        retrieval_top_k=5,
    )

    workflow = AuditWorkflow(store, settings)
    assert {
        "load_incident_actions",
        "compile_invariants",
        "retrieve_candidates",
        "investigate_checks",
        "assign_verdicts",
        "build_evidence_graph",
        "persist_completion",
    } <= set(workflow.graph.get_graph().nodes)

    state = workflow.run(project, incident, run_id="run_1")

    assert state.summary.status == RunStatus.COMPLETE
    assert state.summary.budget.model_calls_used == 0
    assert all(rounds == 1 for rounds in state.summary.budget.investigation_rounds.values())
    assert {item.verdict for item in state.verdicts} == {
        Verdict.VERIFIED,
        Verdict.PARTIAL,
        Verdict.MISSING,
        Verdict.UNVERIFIABLE,
    }
    assert all(item.citations or item.missing_proofs for item in state.verdicts)
    assert state.graph_nodes
    assert state.graph_edges
    EvidenceGraphBuilder.validate(
        state.graph_nodes,
        state.graph_edges,
        run_id=state.summary.id,
        incident=incident,
        actions=state.actions,
        invariants=state.invariants,
        evidence=state.evidence,
        checks=state.check_results,
        verdicts=state.verdicts,
    )
    store.close()

    reloaded_store = SQLiteStore(database)
    reloaded = reloaded_store.load_audit_state("run_1")
    assert reloaded is not None
    assert reloaded == state
    assert reloaded_store.latest_repository_index(project.id) is not None
    table_names = {
        row[0]
        for row in reloaded_store.connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        )
    }
    assert {
        "projects",
        "incidents",
        "corrective_actions",
        "repository_index_metadata",
        "audit_runs",
        "compiled_invariants",
        "evidence",
        "deterministic_checks",
        "deterministic_check_results",
        "verdicts",
        "evidence_graph_nodes",
        "evidence_graph_edges",
        "workflow_events",
        "budget_counters",
        "incident_budget_counters",
    } <= table_names
    reloaded_store.close()
