# ruff: noqa: E501
"""Versioned SQLite persistence for complete, integrity-checked audit snapshots."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from threading import RLock
from typing import TypeVar

from backend.app.audit.budget import (
    MAX_MODEL_CALLS_PER_INCIDENT,
    BudgetExceeded,
    BudgetKind,
)
from backend.app.audit.contracts import (
    ActionVerdict,
    AuditRunSummary,
    AuditWorkflowState,
    BudgetUsage,
    CompiledInvariant,
    DeterministicCheckResult,
    DeterministicCheckSpec,
    EvidenceGraphEdge,
    EvidenceGraphNode,
    EvidenceRecord,
    RepositoryIndexMetadata,
    WorkflowEvent,
)
from backend.app.audit.graph import EvidenceGraphBuilder
from backend.app.guards.contracts import GuardApproval, GuardExecution, GuardSpec, GuardStatus
from backend.app.models import ActionItem, DomainModel, Incident, Project, RunStatus

ModelT = TypeVar("ModelT", bound=DomainModel)
SCHEMA_VERSION = 3


class UnsupportedSchemaVersion(RuntimeError):
    """Raised when a database cannot be safely opened by this application version."""


class AuditStateIntegrityError(ValueError):
    """Raised before an inconsistent audit snapshot can enter persistence."""


class StorageBusyError(RuntimeError):
    """Raised when SQLite cannot safely acquire the required write reservation."""

    failure_code = "storage_busy"

    def __init__(self) -> None:
        super().__init__("storage is temporarily busy; retry later")


class SQLiteStore:
    """Local single-user store with versioning and transactional complete snapshots."""

    def __init__(self, database: str | Path = ":memory:") -> None:
        database_text = str(database)
        if database_text != ":memory:":
            Path(database_text).parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(database_text, check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        self._lock = RLock()
        self._closed = False
        try:
            self._initialize_schema()
        except Exception:
            self.close()
            raise

    @property
    def schema_version(self) -> int:
        return int(self.connection.execute("PRAGMA user_version").fetchone()[0])

    @property
    def is_closed(self) -> bool:
        """Return whether the underlying SQLite connection has been closed."""

        with self._lock:
            return self._closed

    def close(self) -> None:
        """Close the SQLite connection at most once."""

        with self._lock:
            if self._closed:
                return
            self.connection.close()
            self._closed = True

    def _initialize_schema(self) -> None:
        version = self.schema_version
        if version not in {0, 1, 2, SCHEMA_VERSION}:
            raise UnsupportedSchemaVersion(
                f"database schema version {version} is unsupported; expected {SCHEMA_VERSION}"
            )
        tables = {
            str(row[0])
            for row in self.connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
        }
        if version == 0 and tables:
            raise UnsupportedSchemaVersion("unversioned non-empty databases are unsupported")
        if version == 0:
            self._create_schema()
            return
        if version == 1:
            self._migrate_v1_to_v2()
            tables.add("incident_budget_counters")
            version = 2
        if version == 2:
            self._migrate_v2_to_v3()
            tables.update({"guard_specs", "guard_approvals", "guard_executions"})
        required = {
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
            "guard_specs",
            "guard_approvals",
            "guard_executions",
        }
        if not required <= tables:
            raise UnsupportedSchemaVersion("versioned database is missing required tables")

    def _create_schema(self) -> None:
        with self.connection:
            self.connection.executescript(
                """
                CREATE TABLE projects (
                    id TEXT PRIMARY KEY, repository_path TEXT NOT NULL UNIQUE, payload TEXT NOT NULL
                );
                CREATE TABLE incidents (
                    id TEXT PRIMARY KEY, project_id TEXT REFERENCES projects(id), payload TEXT NOT NULL,
                    UNIQUE(id, project_id)
                );
                CREATE TABLE corrective_actions (
                    id TEXT PRIMARY KEY, incident_id TEXT NOT NULL REFERENCES incidents(id) ON DELETE CASCADE,
                    ordering INTEGER NOT NULL, payload TEXT NOT NULL, UNIQUE(id, incident_id)
                );
                CREATE TABLE incident_budget_counters (
                    incident_id TEXT PRIMARY KEY REFERENCES incidents(id) ON DELETE CASCADE,
                    payload TEXT NOT NULL
                );
                CREATE TABLE audit_runs (
                    id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id),
                    incident_id TEXT NOT NULL, status TEXT NOT NULL, payload TEXT NOT NULL,
                    FOREIGN KEY(incident_id, project_id) REFERENCES incidents(id, project_id)
                );
                CREATE TABLE repository_index_metadata (
                    id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                    run_id TEXT REFERENCES audit_runs(id) ON DELETE CASCADE,
                    created_at TEXT NOT NULL, payload TEXT NOT NULL
                );
                CREATE TABLE compiled_invariants (
                    id TEXT NOT NULL, run_id TEXT NOT NULL REFERENCES audit_runs(id) ON DELETE CASCADE,
                    action_id TEXT NOT NULL REFERENCES corrective_actions(id), payload TEXT NOT NULL,
                    PRIMARY KEY(id, run_id), UNIQUE(id, run_id, action_id)
                );
                CREATE TABLE deterministic_checks (
                    id TEXT NOT NULL, run_id TEXT NOT NULL REFERENCES audit_runs(id) ON DELETE CASCADE,
                    invariant_id TEXT NOT NULL, payload TEXT NOT NULL,
                    PRIMARY KEY(id, run_id), UNIQUE(id, run_id, invariant_id),
                    FOREIGN KEY(invariant_id, run_id) REFERENCES compiled_invariants(id, run_id)
                );
                CREATE TABLE evidence (
                    id TEXT NOT NULL, run_id TEXT NOT NULL REFERENCES audit_runs(id) ON DELETE CASCADE,
                    action_id TEXT NOT NULL REFERENCES corrective_actions(id), invariant_id TEXT NOT NULL,
                    payload TEXT NOT NULL, PRIMARY KEY(id, run_id),
                    FOREIGN KEY(invariant_id, run_id, action_id)
                        REFERENCES compiled_invariants(id, run_id, action_id)
                );
                CREATE TABLE deterministic_check_results (
                    id TEXT NOT NULL, run_id TEXT NOT NULL REFERENCES audit_runs(id) ON DELETE CASCADE,
                    invariant_id TEXT NOT NULL, check_spec_id TEXT NOT NULL, payload TEXT NOT NULL,
                    PRIMARY KEY(id, run_id),
                    FOREIGN KEY(invariant_id, run_id) REFERENCES compiled_invariants(id, run_id),
                    FOREIGN KEY(check_spec_id, run_id, invariant_id)
                        REFERENCES deterministic_checks(id, run_id, invariant_id)
                );
                CREATE TABLE verdicts (
                    id TEXT NOT NULL, run_id TEXT NOT NULL REFERENCES audit_runs(id) ON DELETE CASCADE,
                    action_id TEXT NOT NULL REFERENCES corrective_actions(id), payload TEXT NOT NULL,
                    PRIMARY KEY(id, run_id)
                );
                CREATE TABLE evidence_graph_nodes (
                    id TEXT NOT NULL, run_id TEXT NOT NULL REFERENCES audit_runs(id) ON DELETE CASCADE,
                    record_id TEXT NOT NULL, payload TEXT NOT NULL, PRIMARY KEY(id, run_id),
                    UNIQUE(run_id, record_id)
                );
                CREATE TABLE evidence_graph_edges (
                    id TEXT NOT NULL, run_id TEXT NOT NULL REFERENCES audit_runs(id) ON DELETE CASCADE,
                    source_node_id TEXT NOT NULL, target_node_id TEXT NOT NULL, payload TEXT NOT NULL,
                    PRIMARY KEY(id, run_id),
                    UNIQUE(run_id, source_node_id, target_node_id),
                    FOREIGN KEY(source_node_id, run_id) REFERENCES evidence_graph_nodes(id, run_id),
                    FOREIGN KEY(target_node_id, run_id) REFERENCES evidence_graph_nodes(id, run_id)
                );
                CREATE TABLE workflow_events (
                    id TEXT NOT NULL, run_id TEXT NOT NULL REFERENCES audit_runs(id) ON DELETE CASCADE,
                    sequence INTEGER NOT NULL, payload TEXT NOT NULL, UNIQUE(run_id, sequence)
                    , PRIMARY KEY(id, run_id)
                );
                CREATE TABLE budget_counters (
                    run_id TEXT PRIMARY KEY REFERENCES audit_runs(id) ON DELETE CASCADE, payload TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS guard_specs (
                    id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES audit_runs(id) ON DELETE CASCADE,
                    action_id TEXT NOT NULL REFERENCES corrective_actions(id), invariant_id TEXT NOT NULL,
                    status TEXT NOT NULL, created_at TEXT NOT NULL, payload TEXT NOT NULL,
                    FOREIGN KEY(invariant_id, run_id, action_id)
                        REFERENCES compiled_invariants(id, run_id, action_id)
                );
                CREATE TABLE IF NOT EXISTS guard_approvals (
                    guard_id TEXT PRIMARY KEY REFERENCES guard_specs(id) ON DELETE CASCADE,
                    run_id TEXT NOT NULL REFERENCES audit_runs(id) ON DELETE CASCADE, payload TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS guard_executions (
                    id TEXT PRIMARY KEY, guard_id TEXT NOT NULL REFERENCES guard_specs(id) ON DELETE CASCADE,
                    run_id TEXT NOT NULL REFERENCES audit_runs(id) ON DELETE CASCADE,
                    created_at TEXT NOT NULL, payload TEXT NOT NULL
                );
                CREATE INDEX idx_actions_incident ON corrective_actions(incident_id, ordering);
                CREATE INDEX idx_invariants_run ON compiled_invariants(run_id, action_id);
                CREATE INDEX idx_evidence_run ON evidence(run_id, invariant_id);
                CREATE INDEX idx_checks_run ON deterministic_checks(run_id, invariant_id);
                CREATE INDEX idx_results_run ON deterministic_check_results(run_id, invariant_id);
                CREATE INDEX idx_verdicts_run ON verdicts(run_id, action_id);
                CREATE INDEX IF NOT EXISTS idx_guards_run ON guard_specs(run_id, created_at, id);
                CREATE INDEX IF NOT EXISTS idx_guard_executions_guard
                    ON guard_executions(guard_id, created_at, id);
                """
            )
            self.connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")

    def _migrate_v1_to_v2(self) -> None:
        with self.connection:
            self.connection.execute(
                "CREATE TABLE incident_budget_counters ("
                "incident_id TEXT PRIMARY KEY REFERENCES incidents(id) ON DELETE CASCADE, "
                "payload TEXT NOT NULL)"
            )
            totals: dict[str, tuple[int, int]] = {}
            for row in self.connection.execute(
                "SELECT audit_runs.incident_id, budget_counters.payload "
                "FROM audit_runs JOIN budget_counters ON budget_counters.run_id = audit_runs.id"
            ):
                usage = BudgetUsage.model_validate_json(row["payload"])
                used, limit = totals.get(str(row["incident_id"]), (0, MAX_MODEL_CALLS_PER_INCIDENT))
                totals[str(row["incident_id"])] = (
                    min(MAX_MODEL_CALLS_PER_INCIDENT, used + usage.model_calls_used),
                    min(limit, usage.model_calls_limit, MAX_MODEL_CALLS_PER_INCIDENT),
                )
            for incident_id, (used, limit) in totals.items():
                migrated = BudgetUsage(model_calls_used=min(used, limit), model_calls_limit=limit)
                self.connection.execute(
                    "INSERT INTO incident_budget_counters(incident_id, payload) VALUES (?, ?)",
                    (incident_id, self._dump(migrated)),
                )
            self.connection.execute("PRAGMA user_version = 2")

    def _migrate_v2_to_v3(self) -> None:
        with self.connection:
            self.connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS guard_specs (
                    id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES audit_runs(id) ON DELETE CASCADE,
                    action_id TEXT NOT NULL REFERENCES corrective_actions(id), invariant_id TEXT NOT NULL,
                    status TEXT NOT NULL, created_at TEXT NOT NULL, payload TEXT NOT NULL,
                    FOREIGN KEY(invariant_id, run_id, action_id)
                        REFERENCES compiled_invariants(id, run_id, action_id)
                );
                CREATE TABLE IF NOT EXISTS guard_approvals (
                    guard_id TEXT PRIMARY KEY REFERENCES guard_specs(id) ON DELETE CASCADE,
                    run_id TEXT NOT NULL REFERENCES audit_runs(id) ON DELETE CASCADE, payload TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS guard_executions (
                    id TEXT PRIMARY KEY, guard_id TEXT NOT NULL REFERENCES guard_specs(id) ON DELETE CASCADE,
                    run_id TEXT NOT NULL REFERENCES audit_runs(id) ON DELETE CASCADE,
                    created_at TEXT NOT NULL, payload TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_guards_run ON guard_specs(run_id, created_at, id);
                CREATE INDEX IF NOT EXISTS idx_guard_executions_guard
                    ON guard_executions(guard_id, created_at, id);
                """
            )
            self.connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")

    def save_project(self, project: Project) -> None:
        with self._lock, self.connection:
            self.connection.execute(
                "INSERT INTO projects(id, repository_path, payload) VALUES (?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET repository_path=excluded.repository_path, payload=excluded.payload",
                (project.id, project.repository_path, self._dump(project)),
            )

    def get_project(self, project_id: str) -> Project | None:
        return self._get_one("projects", Project, project_id)

    def save_incident(self, incident: Incident) -> None:
        if incident.project_id is not None and self.get_project(incident.project_id) is None:
            raise AuditStateIntegrityError("incident references an unknown project")
        if len({item.id for item in incident.actions}) != len(incident.actions):
            raise AuditStateIntegrityError("incident contains duplicate corrective actions")
        if any(item.incident_id != incident.id for item in incident.actions):
            raise AuditStateIntegrityError("corrective action does not belong to incident")
        base = incident.model_copy(update={"actions": []})
        with self._lock:
            try:
                with self.connection:
                    self.connection.execute(
                        "INSERT INTO incidents(id, project_id, payload) VALUES (?, ?, ?) "
                        "ON CONFLICT(id) DO UPDATE SET project_id=excluded.project_id, payload=excluded.payload",
                        (incident.id, incident.project_id, self._dump(base)),
                    )
                    action_ids = [item.id for item in incident.actions]
                    self._delete_absent(
                        "corrective_actions", "incident_id", incident.id, action_ids
                    )
                    for action in incident.actions:
                        self.connection.execute(
                            "INSERT INTO corrective_actions(id, incident_id, ordering, payload) VALUES (?, ?, ?, ?) "
                            "ON CONFLICT(id) DO UPDATE SET incident_id=excluded.incident_id, ordering=excluded.ordering, payload=excluded.payload",
                            (action.id, incident.id, action.order, self._dump(action)),
                        )
            except sqlite3.IntegrityError as exc:
                raise AuditStateIntegrityError("incident violates persistence integrity") from exc

    def get_incident(self, incident_id: str) -> Incident | None:
        with self._lock:
            row = self.connection.execute(
                "SELECT payload FROM incidents WHERE id = ?", (incident_id,)
            ).fetchone()
            if row is None:
                return None
            actions = self._list(
                "corrective_actions", ActionItem, "incident_id", incident_id, "ordering, id"
            )
            return Incident.model_validate_json(row["payload"]).model_copy(
                update={"actions": actions}
            )

    def get_action(self, action_id: str) -> ActionItem | None:
        return self._get_one("corrective_actions", ActionItem, action_id)

    def get_incident_budget(self, incident_id: str) -> BudgetUsage | None:
        with self._lock:
            row = self.connection.execute(
                "SELECT payload FROM incident_budget_counters WHERE incident_id = ?",
                (incident_id,),
            ).fetchone()
        return BudgetUsage.model_validate_json(row["payload"]) if row else None

    def reserve_incident_model_call(self, incident_id: str, limit: int) -> BudgetUsage:
        """Atomically charge an incident before a provider call can begin."""

        with self._lock:
            try:
                with self.connection:
                    # A deferred transaction permits two connections to read the same counter.
                    # Reserve the database writer before any ownership or budget read instead.
                    self.connection.execute("BEGIN IMMEDIATE")
                    incident = self.connection.execute(
                        "SELECT 1 FROM incidents WHERE id = ?", (incident_id,)
                    ).fetchone()
                    if incident is None:
                        raise AuditStateIntegrityError(
                            "model budget references an unknown incident"
                        )
                    row = self.connection.execute(
                        "SELECT payload FROM incident_budget_counters WHERE incident_id = ?",
                        (incident_id,),
                    ).fetchone()
                    current = (
                        BudgetUsage.model_validate_json(row["payload"])
                        if row
                        else BudgetUsage(model_calls_limit=limit)
                    )
                    effective_limit = min(
                        current.model_calls_limit, limit, MAX_MODEL_CALLS_PER_INCIDENT
                    )
                    if current.model_calls_used >= effective_limit:
                        raise BudgetExceeded(BudgetKind.MODEL_CALL, "model call budget exhausted")
                    updated = BudgetUsage(
                        model_calls_used=current.model_calls_used + 1,
                        model_calls_limit=effective_limit,
                        investigation_round_limit=current.investigation_round_limit,
                        investigation_rounds=current.investigation_rounds,
                        deterministic_checks_run=current.deterministic_checks_run,
                    )
                    self.connection.execute(
                        "INSERT INTO incident_budget_counters(incident_id, payload) VALUES (?, ?) "
                        "ON CONFLICT(incident_id) DO UPDATE SET payload=excluded.payload",
                        (incident_id, self._dump(updated)),
                    )
                    return updated
            except sqlite3.IntegrityError as exc:
                raise AuditStateIntegrityError("incident model budget violates integrity") from exc
            except sqlite3.OperationalError as exc:
                if self._is_database_lock_error(exc):
                    raise StorageBusyError() from exc
                raise

    def save_repository_index(self, metadata: RepositoryIndexMetadata) -> None:
        if self.get_project(metadata.project_id) is None:
            raise AuditStateIntegrityError("repository index references an unknown project")
        if metadata.run_id is not None:
            run = self.get_run_summary(metadata.run_id)
            if run is None or run.project_id != metadata.project_id:
                raise AuditStateIntegrityError("repository index run does not belong to project")
        with self._lock, self.connection:
            self.connection.execute(
                "INSERT INTO repository_index_metadata(id, project_id, run_id, created_at, payload) VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET project_id=excluded.project_id, run_id=excluded.run_id, created_at=excluded.created_at, payload=excluded.payload",
                (
                    metadata.id,
                    metadata.project_id,
                    metadata.run_id,
                    metadata.created_at.isoformat(),
                    self._dump(metadata),
                ),
            )

    def latest_repository_index(self, project_id: str) -> RepositoryIndexMetadata | None:
        with self._lock:
            row = self.connection.execute(
                "SELECT payload FROM repository_index_metadata WHERE project_id = ? ORDER BY created_at DESC, id DESC LIMIT 1",
                (project_id,),
            ).fetchone()
        return RepositoryIndexMetadata.model_validate_json(row["payload"]) if row else None

    def save_audit_state(self, state: AuditWorkflowState) -> None:
        """Replace one complete audit snapshot atomically after validating all ownership."""

        with self._lock:
            self._validate_audit_state(state)
            summary = state.summary
            try:
                with self.connection:
                    self.connection.execute(
                        "INSERT INTO audit_runs(id, project_id, incident_id, status, payload) VALUES (?, ?, ?, ?, ?) "
                        "ON CONFLICT(id) DO UPDATE SET status=excluded.status, payload=excluded.payload",
                        (
                            summary.id,
                            summary.project_id,
                            summary.incident_id,
                            summary.status.value,
                            self._dump(summary),
                        ),
                    )
                    for table in (
                        "evidence_graph_edges",
                        "evidence_graph_nodes",
                        "deterministic_check_results",
                        "verdicts",
                        "evidence",
                        "deterministic_checks",
                        "compiled_invariants",
                        "workflow_events",
                        "budget_counters",
                    ):
                        self.connection.execute(
                            f"DELETE FROM {table} WHERE run_id = ?", (summary.id,)
                        )
                    for invariant in state.invariants:
                        self.connection.execute(
                            "INSERT INTO compiled_invariants(id, run_id, action_id, payload) VALUES (?, ?, ?, ?)",
                            (invariant.id, summary.id, invariant.action_id, self._dump(invariant)),
                        )
                    for spec in state.check_specs:
                        self.connection.execute(
                            "INSERT INTO deterministic_checks(id, run_id, invariant_id, payload) VALUES (?, ?, ?, ?)",
                            (spec.id, summary.id, spec.invariant_id, self._dump(spec)),
                        )
                    for evidence in state.evidence:
                        self.connection.execute(
                            "INSERT INTO evidence(id, run_id, action_id, invariant_id, payload) VALUES (?, ?, ?, ?, ?)",
                            (
                                evidence.id,
                                summary.id,
                                evidence.action_id,
                                evidence.invariant_id,
                                self._dump(evidence),
                            ),
                        )
                    for result in state.check_results:
                        self.connection.execute(
                            "INSERT INTO deterministic_check_results(id, run_id, invariant_id, check_spec_id, payload) VALUES (?, ?, ?, ?, ?)",
                            (
                                result.id,
                                summary.id,
                                result.invariant_id,
                                result.check_spec_id,
                                self._dump(result),
                            ),
                        )
                    for verdict in state.verdicts:
                        self.connection.execute(
                            "INSERT INTO verdicts(id, run_id, action_id, payload) VALUES (?, ?, ?, ?)",
                            (verdict.id, summary.id, verdict.action_id, self._dump(verdict)),
                        )
                    for node in state.graph_nodes:
                        self.connection.execute(
                            "INSERT INTO evidence_graph_nodes(id, run_id, record_id, payload) VALUES (?, ?, ?, ?)",
                            (node.id, summary.id, node.record_id, self._dump(node)),
                        )
                    for edge in state.graph_edges:
                        self.connection.execute(
                            "INSERT INTO evidence_graph_edges(id, run_id, source_node_id, target_node_id, payload) VALUES (?, ?, ?, ?, ?)",
                            (
                                edge.id,
                                summary.id,
                                edge.source_node_id,
                                edge.target_node_id,
                                self._dump(edge),
                            ),
                        )
                    for event in state.events:
                        self.connection.execute(
                            "INSERT INTO workflow_events(id, run_id, sequence, payload) VALUES (?, ?, ?, ?)",
                            (event.id, summary.id, event.sequence, self._dump(event)),
                        )
                    self.connection.execute(
                        "INSERT INTO budget_counters(run_id, payload) VALUES (?, ?)",
                        (summary.id, self._dump(summary.budget)),
                    )
            except sqlite3.IntegrityError as exc:
                raise AuditStateIntegrityError(
                    "audit snapshot violates persistence integrity"
                ) from exc

    def _validate_audit_state(self, state: AuditWorkflowState) -> None:
        summary = state.summary
        project = self.get_project(summary.project_id)
        incident = self.get_incident(summary.incident_id)
        if project is None:
            raise AuditStateIntegrityError("audit run references an unknown project")
        if incident is None:
            raise AuditStateIntegrityError("audit run references an unknown incident")
        if incident.project_id != project.id:
            raise AuditStateIntegrityError("audit run project does not own incident")
        existing = self.get_run_summary(summary.id)
        if existing is not None and (
            existing.project_id != summary.project_id or existing.incident_id != summary.incident_id
        ):
            raise AuditStateIntegrityError("audit run ownership is immutable")

        self._require_unique("actions", [item.id for item in state.actions])
        incident_actions = {item.id: item for item in incident.actions}
        state_actions = {item.id: item for item in state.actions}
        if state_actions != incident_actions:
            raise AuditStateIntegrityError("audit actions do not exactly match the run incident")

        self._require_unique("invariants", [item.id for item in state.invariants])
        invariants = {item.id: item for item in state.invariants}
        if any(item.action_id not in state_actions for item in state.invariants):
            raise AuditStateIntegrityError("invariant action does not belong to run incident")

        self._require_unique("checks", [item.id for item in state.check_specs])
        specs = {item.id: item for item in state.check_specs}
        if any(item.invariant_id not in invariants for item in state.check_specs):
            raise AuditStateIntegrityError("check references an invariant outside the run")

        self._require_unique("evidence", [item.id for item in state.evidence])
        evidence = {item.id: item for item in state.evidence}
        for evidence_item in state.evidence:
            invariant = invariants.get(evidence_item.invariant_id)
            if (
                evidence_item.run_id != summary.id
                or invariant is None
                or evidence_item.action_id != invariant.action_id
            ):
                raise AuditStateIntegrityError("evidence ownership does not match run invariant")

        self._require_unique("check results", [item.id for item in state.check_results])
        for check_result in state.check_results:
            spec = specs.get(check_result.check_spec_id)
            if (
                check_result.run_id != summary.id
                or spec is None
                or check_result.invariant_id != spec.invariant_id
                or any(evidence_id not in evidence for evidence_id in check_result.evidence_ids)
                or any(
                    evidence[evidence_id].invariant_id != check_result.invariant_id
                    for evidence_id in check_result.evidence_ids
                )
            ):
                raise AuditStateIntegrityError("check result ownership does not match run check")

        self._require_unique("verdicts", [item.id for item in state.verdicts])
        for action_verdict in state.verdicts:
            if action_verdict.run_id != summary.id or action_verdict.action_id not in state_actions:
                raise AuditStateIntegrityError("verdict ownership does not match run action")
            if any(
                invariant_id not in invariants
                or invariants[invariant_id].action_id != action_verdict.action_id
                for invariant_id in action_verdict.invariant_ids
            ):
                raise AuditStateIntegrityError("verdict references an invariant for another action")
            if any(
                citation.evidence_id not in evidence
                or evidence[citation.evidence_id].action_id != action_verdict.action_id
                or citation != evidence[citation.evidence_id].citation()
                for citation in action_verdict.citations
            ):
                raise AuditStateIntegrityError("verdict citation does not belong to action")

        self._require_unique("events", [item.id for item in state.events])
        self._require_unique("event sequences", [item.sequence for item in state.events])
        if any(item.run_id != summary.id for item in state.events):
            raise AuditStateIntegrityError("workflow event belongs to another run")
        if set(summary.budget.investigation_rounds) - set(invariants):
            raise AuditStateIntegrityError("budget references an invariant outside the run")

        if state.graph_nodes or state.graph_edges:
            try:
                EvidenceGraphBuilder.validate(
                    state.graph_nodes,
                    state.graph_edges,
                    run_id=summary.id,
                    incident=incident,
                    actions=state.actions,
                    invariants=state.invariants,
                    evidence=state.evidence,
                    checks=state.check_results,
                    verdicts=state.verdicts,
                )
            except ValueError as exc:
                raise AuditStateIntegrityError(str(exc)) from exc
        elif summary.status == RunStatus.COMPLETE and (
            state.actions
            or state.invariants
            or state.evidence
            or state.check_results
            or state.verdicts
        ):
            raise AuditStateIntegrityError("complete audit snapshot requires an evidence graph")

    @staticmethod
    def _require_unique(label: str, values: list[object]) -> None:
        if len(values) != len(set(values)):
            raise AuditStateIntegrityError(f"audit snapshot contains duplicate {label}")

    def get_run_summary(self, run_id: str) -> AuditRunSummary | None:
        return self._get_one("audit_runs", AuditRunSummary, run_id)

    def list_invariants(self, run_id: str) -> list[CompiledInvariant]:
        return self._list("compiled_invariants", CompiledInvariant, "run_id", run_id, "rowid")

    def list_evidence(self, run_id: str) -> list[EvidenceRecord]:
        return self._list("evidence", EvidenceRecord, "run_id", run_id, "rowid")

    def list_check_specs(self, run_id: str) -> list[DeterministicCheckSpec]:
        return self._list("deterministic_checks", DeterministicCheckSpec, "run_id", run_id, "rowid")

    def list_check_results(self, run_id: str) -> list[DeterministicCheckResult]:
        return self._list(
            "deterministic_check_results", DeterministicCheckResult, "run_id", run_id, "rowid"
        )

    def list_verdicts(self, run_id: str) -> list[ActionVerdict]:
        return self._list("verdicts", ActionVerdict, "run_id", run_id, "rowid")

    def list_graph_nodes(self, run_id: str) -> list[EvidenceGraphNode]:
        return self._list("evidence_graph_nodes", EvidenceGraphNode, "run_id", run_id, "rowid")

    def list_graph_edges(self, run_id: str) -> list[EvidenceGraphEdge]:
        return self._list("evidence_graph_edges", EvidenceGraphEdge, "run_id", run_id, "rowid")

    def list_workflow_events(self, run_id: str) -> list[WorkflowEvent]:
        return self._list("workflow_events", WorkflowEvent, "run_id", run_id, "sequence, id")

    def get_budget(self, run_id: str) -> BudgetUsage | None:
        with self._lock:
            row = self.connection.execute(
                "SELECT payload FROM budget_counters WHERE run_id = ?", (run_id,)
            ).fetchone()
        return BudgetUsage.model_validate_json(row["payload"]) if row else None

    def save_guard(self, guard: GuardSpec) -> None:
        """Persist an immutable preview or update its lifecycle status."""

        self._validate_guard(guard)
        with self._lock, self.connection:
            self.connection.execute(
                "INSERT INTO guard_specs(id, run_id, action_id, invariant_id, status, created_at, payload) "
                "VALUES (?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET status=excluded.status, payload=excluded.payload",
                (
                    guard.id,
                    guard.run_id,
                    guard.action_id,
                    guard.invariant_id,
                    guard.status.value,
                    guard.created_at.isoformat(),
                    self._dump(guard),
                ),
            )

    def get_guard(self, guard_id: str) -> GuardSpec | None:
        with self._lock:
            row = self.connection.execute(
                "SELECT payload FROM guard_specs WHERE id = ?", (guard_id,)
            ).fetchone()
        return GuardSpec.model_validate_json(row["payload"]) if row else None

    def list_guards(self, run_id: str) -> list[GuardSpec]:
        with self._lock:
            rows = self.connection.execute(
                "SELECT payload FROM guard_specs WHERE run_id = ? ORDER BY created_at, id",
                (run_id,),
            ).fetchall()
        return [GuardSpec.model_validate_json(row["payload"]) for row in rows]

    def record_guard_decision(self, guard: GuardSpec, approval: GuardApproval) -> None:
        self._validate_guard(guard)
        if approval.guard_id != guard.id or approval.run_id != guard.run_id:
            raise AuditStateIntegrityError("guard approval ownership mismatch")
        if approval.preview_sha256 != guard.preview_sha256:
            raise AuditStateIntegrityError("guard approval does not match preview")
        expected_status = GuardStatus.WRITTEN if approval.approved else GuardStatus.REJECTED
        if guard.status != expected_status:
            raise AuditStateIntegrityError("guard decision status is inconsistent")
        with self._lock, self.connection:
            existing = self.connection.execute(
                "SELECT 1 FROM guard_approvals WHERE guard_id = ?", (guard.id,)
            ).fetchone()
            if existing is not None:
                raise AuditStateIntegrityError("guard decision is immutable")
            self.connection.execute(
                "UPDATE guard_specs SET status = ?, payload = ? WHERE id = ? AND run_id = ?",
                (guard.status.value, self._dump(guard), guard.id, guard.run_id),
            )
            self.connection.execute(
                "INSERT INTO guard_approvals(guard_id, run_id, payload) VALUES (?, ?, ?)",
                (guard.id, guard.run_id, self._dump(approval)),
            )

    def restore_guard_preview(self, guard: GuardSpec) -> None:
        """Compensate a failed artifact write and remove its unusable approval."""

        self._validate_guard(guard)
        with self._lock, self.connection:
            self.connection.execute("DELETE FROM guard_approvals WHERE guard_id = ?", (guard.id,))
            self.connection.execute(
                "UPDATE guard_specs SET status = ?, payload = ? WHERE id = ? AND run_id = ?",
                (GuardStatus.PREVIEWED.value, self._dump(guard), guard.id, guard.run_id),
            )

    def get_guard_approval(self, guard_id: str) -> GuardApproval | None:
        with self._lock:
            row = self.connection.execute(
                "SELECT payload FROM guard_approvals WHERE guard_id = ?", (guard_id,)
            ).fetchone()
        return GuardApproval.model_validate_json(row["payload"]) if row else None

    def save_guard_execution(self, guard: GuardSpec, execution: GuardExecution) -> None:
        self._validate_guard(guard)
        approval = self.get_guard_approval(guard.id)
        if approval is None or not approval.approved:
            raise AuditStateIntegrityError("guard execution requires approval")
        if execution.guard_id != guard.id or execution.run_id != guard.run_id:
            raise AuditStateIntegrityError("guard execution ownership mismatch")
        if execution.artifact_sha256 != guard.preview_sha256:
            raise AuditStateIntegrityError("guard execution artifact differs from approved preview")
        with self._lock, self.connection:
            self.connection.execute(
                "UPDATE guard_specs SET status = ?, payload = ? WHERE id = ? AND run_id = ?",
                (guard.status.value, self._dump(guard), guard.id, guard.run_id),
            )
            self.connection.execute(
                "INSERT INTO guard_executions(id, guard_id, run_id, created_at, payload) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    execution.id,
                    execution.guard_id,
                    execution.run_id,
                    execution.created_at.isoformat(),
                    self._dump(execution),
                ),
            )

    def list_guard_executions(self, guard_id: str) -> list[GuardExecution]:
        with self._lock:
            rows = self.connection.execute(
                "SELECT payload FROM guard_executions WHERE guard_id = ? ORDER BY created_at, id",
                (guard_id,),
            ).fetchall()
        return [GuardExecution.model_validate_json(row["payload"]) for row in rows]

    def _validate_guard(self, guard: GuardSpec) -> None:
        summary = self.get_run_summary(guard.run_id)
        if summary is None or summary.status != RunStatus.COMPLETE:
            raise AuditStateIntegrityError("guard requires a completed audit run")
        invariant = next(
            (item for item in self.list_invariants(guard.run_id) if item.id == guard.invariant_id),
            None,
        )
        verdict = next(
            (
                item
                for item in self.list_verdicts(guard.run_id)
                if item.action_id == guard.action_id
            ),
            None,
        )
        if invariant is None or invariant.action_id != guard.action_id:
            raise AuditStateIntegrityError("guard invariant does not belong to action")
        if verdict is None or verdict.verdict.value not in {"PARTIAL", "MISSING"}:
            raise AuditStateIntegrityError("guards are limited to partial or missing actions")

    def load_audit_state(self, run_id: str) -> AuditWorkflowState | None:
        summary = self.get_run_summary(run_id)
        if summary is None:
            return None
        incident = self.get_incident(summary.incident_id)
        if incident is None:
            raise AuditStateIntegrityError("persisted audit references a missing incident")
        budget = self.get_budget(run_id)
        if budget is not None:
            summary = summary.model_copy(update={"budget": budget})
        incident_budget = self.get_incident_budget(summary.incident_id)
        if incident_budget is not None:
            summary = summary.model_copy(
                update={
                    "budget": summary.budget.model_copy(
                        update={
                            "model_calls_used": incident_budget.model_calls_used,
                            "model_calls_limit": incident_budget.model_calls_limit,
                        }
                    )
                }
            )
        state = AuditWorkflowState(
            summary=summary,
            actions=incident.actions,
            invariants=self.list_invariants(run_id),
            check_specs=self.list_check_specs(run_id),
            evidence=self.list_evidence(run_id),
            check_results=self.list_check_results(run_id),
            verdicts=self.list_verdicts(run_id),
            graph_nodes=self.list_graph_nodes(run_id),
            graph_edges=self.list_graph_edges(run_id),
            events=self.list_workflow_events(run_id),
        )
        self._validate_audit_state(state)
        return state

    def _get_one(self, table: str, model: type[ModelT], record_id: str) -> ModelT | None:
        if table not in {"projects", "incidents", "corrective_actions", "audit_runs"}:
            raise ValueError("invalid internal persistence table")
        with self._lock:
            row = self.connection.execute(
                f"SELECT payload FROM {table} WHERE id = ?", (record_id,)
            ).fetchone()
        return model.model_validate_json(row["payload"]) if row else None

    def _list(
        self,
        table: str,
        model: type[ModelT],
        foreign_column: str,
        foreign_id: str,
        ordering: str,
    ) -> list[ModelT]:
        allowed_tables = {
            "corrective_actions",
            "compiled_invariants",
            "evidence",
            "deterministic_checks",
            "deterministic_check_results",
            "verdicts",
            "evidence_graph_nodes",
            "evidence_graph_edges",
            "workflow_events",
        }
        if (
            table not in allowed_tables
            or foreign_column not in {"incident_id", "run_id"}
            or ordering not in {"rowid", "ordering, id", "sequence, id"}
        ):
            raise ValueError("invalid internal persistence query")
        with self._lock:
            rows = self.connection.execute(
                f"SELECT payload FROM {table} WHERE {foreign_column} = ? ORDER BY {ordering}",
                (foreign_id,),
            ).fetchall()
        return [model.model_validate_json(row["payload"]) for row in rows]

    def _delete_absent(
        self, table: str, foreign_column: str, foreign_id: str, retained_ids: list[str]
    ) -> None:
        if table != "corrective_actions" or foreign_column != "incident_id":
            raise ValueError("invalid internal snapshot delete")
        if retained_ids:
            placeholders = ",".join("?" for _ in retained_ids)
            self.connection.execute(
                f"DELETE FROM {table} WHERE {foreign_column} = ? AND id NOT IN ({placeholders})",
                (foreign_id, *retained_ids),
            )
        else:
            self.connection.execute(
                f"DELETE FROM {table} WHERE {foreign_column} = ?", (foreign_id,)
            )

    @staticmethod
    def _dump(model: DomainModel) -> str:
        return model.model_dump_json()

    @staticmethod
    def _is_database_lock_error(exc: sqlite3.OperationalError) -> bool:
        error_code = getattr(exc, "sqlite_errorcode", None)
        if isinstance(error_code, int) and error_code & 0xFF in {
            sqlite3.SQLITE_BUSY,
            sqlite3.SQLITE_LOCKED,
        }:
            return True
        message = str(exc).casefold()
        return "database is locked" in message or "database table is locked" in message
