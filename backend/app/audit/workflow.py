"""Bounded LangGraph workflow for deterministic audits."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from langgraph.graph import END, START, StateGraph

from backend.app.audit.budget import BudgetExceeded, BudgetTracker
from backend.app.audit.checks import DeterministicCheckRunner
from backend.app.audit.compiler import DeterministicInvariantCompiler
from backend.app.audit.contracts import (
    AuditFailureCode,
    AuditRunSummary,
    AuditWorkflowState,
    BudgetUsage,
    EvidenceRecord,
    EvidenceRole,
    RepositoryIndexMetadata,
    WorkflowEvent,
    WorkflowEventType,
)
from backend.app.audit.graph import EvidenceGraphBuilder
from backend.app.audit.verifier import VerdictEngine
from backend.app.ids import stable_id
from backend.app.models import EvidenceKind, Incident, Project, RunStatus, Verdict
from backend.app.rag.chunking import DocumentChunker
from backend.app.rag.contracts import DocumentType
from backend.app.rag.embeddings import DeterministicFakeEncoder, SemanticIndex
from backend.app.rag.index import LexicalIndex
from backend.app.rag.ingestion import RepositoryIngestor
from backend.app.rag.pipeline import RepositoryIndexer
from backend.app.rag.retrieval import HybridRetriever
from backend.app.rag.safety import IndexLimits
from backend.app.settings import Settings
from backend.app.storage import SQLiteStore


class AuditWorkflow:
    """Run compile/index/investigate/verify stages with explicit persisted bounds."""

    def __init__(self, store: SQLiteStore, settings: Settings) -> None:
        self.store = store
        self.settings = settings
        self.compiler = DeterministicInvariantCompiler()
        self.verifier = VerdictEngine()
        self.graph_builder = EvidenceGraphBuilder()
        builder = StateGraph(AuditWorkflowState)
        builder.add_node("load_incident_actions", self._load_incident_actions)
        builder.add_node("compile_invariants", self._compile_invariants)
        builder.add_node("retrieve_candidates", self._retrieve_candidates)
        builder.add_node("investigate_checks", self._investigate_checks)
        builder.add_node("assign_verdicts", self._assign_verdicts)
        builder.add_node("build_evidence_graph", self._build_evidence_graph)
        builder.add_node("persist_completion", self._persist_completion)
        builder.add_edge(START, "load_incident_actions")
        builder.add_edge("load_incident_actions", "compile_invariants")
        builder.add_edge("compile_invariants", "retrieve_candidates")
        builder.add_edge("retrieve_candidates", "investigate_checks")
        builder.add_edge("investigate_checks", "assign_verdicts")
        builder.add_edge("assign_verdicts", "build_evidence_graph")
        builder.add_edge("build_evidence_graph", "persist_completion")
        builder.add_edge("persist_completion", END)
        self.graph = builder.compile()

    def run(
        self, project: Project, incident: Incident, *, run_id: str | None = None
    ) -> AuditWorkflowState:
        resolved_run_id = run_id or f"run_{uuid4().hex}"
        incident_budget = self.store.get_incident_budget(incident.id)
        budget = BudgetUsage(
            model_calls_used=incident_budget.model_calls_used if incident_budget else 0,
            model_calls_limit=(
                min(incident_budget.model_calls_limit, self.settings.max_model_calls)
                if incident_budget
                else self.settings.max_model_calls
            ),
            investigation_round_limit=self.settings.max_investigation_rounds,
        )
        summary = AuditRunSummary(
            id=resolved_run_id,
            project_id=project.id,
            incident_id=incident.id,
            total_actions=len(incident.actions),
            budget=budget,
        )
        initial = AuditWorkflowState(summary=summary, actions=incident.actions)
        try:
            self.store.save_audit_state(initial)
            output = self.graph.invoke(initial)
            return AuditWorkflowState.model_validate(output)
        except Exception as exc:
            current = self.store.load_audit_state(resolved_run_id) or initial
            failure_code = (
                exc.failure_code
                if isinstance(exc, BudgetExceeded)
                else (
                    AuditFailureCode.INVALID_STATE
                    if isinstance(exc, ValueError)
                    else AuditFailureCode.WORKFLOW_FAILED
                )
            )
            failed_summary = current.summary.model_copy(
                update={
                    "status": RunStatus.FAILED,
                    "failure_code": failure_code,
                    "error": f"audit failed safely: {type(exc).__name__}",
                    "updated_at": datetime.now(UTC),
                }
            )
            failed = current.model_copy(update={"summary": failed_summary})
            failed = self._event(
                failed,
                WorkflowEventType.FAILURE,
                RunStatus.FAILED,
                failed_summary.error or "audit failed",
            )
            self.store.save_audit_state(failed)
            return failed

    def _load_incident_actions(self, state: AuditWorkflowState) -> dict[str, object]:
        state = self._stage(state, RunStatus.PARSING)
        project = self._required_project(state.summary.project_id)
        incident = self._required_incident(state.summary.incident_id)
        if incident.project_id != project.id:
            raise ValueError("incident does not belong to audit project")
        state = state.model_copy(update={"actions": incident.actions})
        state = self._event(
            state,
            WorkflowEventType.STAGE_COMPLETED,
            RunStatus.PARSING,
            f"loaded {len(incident.actions)} corrective action(s)",
        )
        self.store.save_audit_state(state)
        return state.model_dump()

    def _compile_invariants(self, state: AuditWorkflowState) -> dict[str, object]:
        state = self._stage(state, RunStatus.COMPILING_INVARIANTS)
        result = self.compiler.compile(state.actions)
        state = state.model_copy(
            update={"invariants": result.invariants, "check_specs": result.check_specs}
        )
        state = self._event(
            state,
            WorkflowEventType.STAGE_COMPLETED,
            RunStatus.COMPILING_INVARIANTS,
            f"compiled {len(result.invariants)} invariant(s)",
        )
        self.store.save_audit_state(state)
        return state.model_dump()

    def _retrieve_candidates(self, state: AuditWorkflowState) -> dict[str, object]:
        state = self._stage(state, RunStatus.INDEXING)
        project = self._required_project(state.summary.project_id)
        repository = Path(project.repository_path)
        limits = self._limits()
        lexical = LexicalIndex()
        semantic = SemanticIndex(DeterministicFakeEncoder())
        tracker = BudgetTracker(state.summary.budget)
        evidence = list(state.evidence)
        specs_by_invariant = {
            invariant.id: [spec for spec in state.check_specs if spec.invariant_id == invariant.id]
            for invariant in state.invariants
        }
        try:
            result = RepositoryIndexer(
                RepositoryIngestor(self.settings.workspace_root, repository, limits=limits),
                DocumentChunker(),
                lexical,
                semantic,
            ).build()
            retriever = HybridRetriever(lexical, semantic)
            metadata = RepositoryIndexMetadata(
                id=stable_id("repository_index", state.summary.id, project.id, *result.chunk_ids),
                project_id=project.id,
                run_id=state.summary.id,
                index_version="day3-v1",
                documents_indexed=result.documents_indexed,
                chunks_indexed=result.chunks_indexed,
                total_bytes=result.total_bytes,
                chunk_ids=result.chunk_ids,
                failures=[failure.model_dump(mode="json") for failure in result.failures],
                skipped=result.skipped,
            )
            self.store.save_repository_index(metadata)
            for invariant in state.invariants:
                supported_specs = [
                    spec
                    for spec in specs_by_invariant[invariant.id]
                    if spec.availability.value == "supported"
                ]
                if not supported_specs:
                    continue
                tracker.consume_investigation_round(invariant.id)
                summary = state.summary.model_copy(
                    update={"budget": tracker.usage, "updated_at": datetime.now(UTC)}
                )
                state = state.model_copy(update={"summary": summary, "evidence": evidence})
                state = self._event(
                    state,
                    WorkflowEventType.BUDGET_CONSUMED,
                    RunStatus.INDEXING,
                    f"reserved investigation round for {invariant.id}",
                )
                self.store.save_audit_state(state)
                for candidate in retriever.search(
                    invariant.original_action,
                    top_k=self.settings.retrieval_top_k,
                    prefer_tests=any(
                        spec.check_type.value == "test_protection" for spec in supported_specs
                    ),
                ):
                    kind = {
                        DocumentType.SOURCE: EvidenceKind.CODE,
                        DocumentType.CONFIGURATION: EvidenceKind.CONFIGURATION,
                        DocumentType.TEST: EvidenceKind.TEST,
                        DocumentType.DOCUMENT: EvidenceKind.DOCUMENT,
                    }[candidate.chunk.document_type]
                    evidence.append(
                        EvidenceRecord(
                            id=stable_id(
                                "evidence", state.summary.id, invariant.id, candidate.chunk.id
                            ),
                            run_id=state.summary.id,
                            action_id=invariant.action_id,
                            invariant_id=invariant.id,
                            kind=kind,
                            role=EvidenceRole.SUPPORTING_ONLY,
                            source_path=candidate.chunk.source_path,
                            line_start=candidate.chunk.line_start,
                            line_end=candidate.chunk.line_end,
                            excerpt=candidate.chunk.text,
                            retrieval_score=candidate.final_score,
                            source_record_id=candidate.chunk.id,
                        )
                    )
        finally:
            lexical.close()
        evidence = list({item.id: item for item in evidence}.values())
        summary = state.summary.model_copy(
            update={"budget": tracker.usage, "updated_at": datetime.now(UTC)}
        )
        state = state.model_copy(update={"summary": summary, "evidence": evidence})
        state = self._event(
            state,
            WorkflowEventType.STAGE_COMPLETED,
            RunStatus.INDEXING,
            f"indexed {result.chunks_indexed} chunk(s) and retained {len(evidence)} candidate(s)",
        )
        self.store.save_audit_state(state)
        return state.model_dump()

    def _investigate_checks(self, state: AuditWorkflowState) -> dict[str, object]:
        state = self._stage(state, RunStatus.INVESTIGATING)
        project = self._required_project(state.summary.project_id)
        runner = DeterministicCheckRunner(
            self.settings.workspace_root,
            Path(project.repository_path),
            limits=self._limits(),
        )
        tracker = BudgetTracker(state.summary.budget)
        evidence = list(state.evidence)
        results = list(state.check_results)
        action_by_invariant = {item.id: item.action_id for item in state.invariants}
        for spec in state.check_specs:
            execution = runner.run(
                spec,
                run_id=state.summary.id,
                action_id=action_by_invariant[spec.invariant_id],
            )
            tracker.record_check()
            evidence.extend(execution.evidence)
            results.append(execution.result)
        evidence = list({item.id: item for item in evidence}.values())
        summary = state.summary.model_copy(
            update={"budget": tracker.usage, "updated_at": datetime.now(UTC)}
        )
        state = state.model_copy(
            update={"summary": summary, "evidence": evidence, "check_results": results}
        )
        state = self._event(
            state,
            WorkflowEventType.STAGE_COMPLETED,
            RunStatus.INVESTIGATING,
            f"ran {len(results)} deterministic check(s)",
        )
        self.store.save_audit_state(state)
        return state.model_dump()

    def _assign_verdicts(self, state: AuditWorkflowState) -> dict[str, object]:
        state = self._stage(state, RunStatus.VERIFYING)
        verdicts = []
        for action in state.actions:
            invariants = [item for item in state.invariants if item.action_id == action.id]
            verdicts.append(
                self.verifier.verify_action(
                    run_id=state.summary.id,
                    action=action,
                    invariants=invariants,
                    results=state.check_results,
                    evidence=state.evidence,
                )
            )
        counts = {verdict: sum(item.verdict == verdict for item in verdicts) for verdict in Verdict}
        summary = state.summary.model_copy(
            update={
                "completed_actions": len(verdicts),
                "verdict_counts": counts,
                "assessed_protection_coverage": self.verifier.assessed_coverage(verdicts),
                "updated_at": datetime.now(UTC),
            }
        )
        state = state.model_copy(update={"summary": summary, "verdicts": verdicts})
        state = self._event(
            state,
            WorkflowEventType.STAGE_COMPLETED,
            RunStatus.VERIFYING,
            f"assigned {len(verdicts)} conservative verdict(s)",
        )
        self.store.save_audit_state(state)
        return state.model_dump()

    def _build_evidence_graph(self, state: AuditWorkflowState) -> dict[str, object]:
        incident = self._required_incident(state.summary.incident_id)
        nodes, edges = self.graph_builder.build(
            run_id=state.summary.id,
            incident=incident,
            actions=state.actions,
            invariants=state.invariants,
            evidence=state.evidence,
            checks=state.check_results,
            verdicts=state.verdicts,
        )
        state = state.model_copy(update={"graph_nodes": nodes, "graph_edges": edges})
        state = self._event(
            state,
            WorkflowEventType.STAGE_COMPLETED,
            RunStatus.VERIFYING,
            f"built evidence graph with {len(nodes)} node(s) and {len(edges)} edge(s)",
        )
        self.store.save_audit_state(state)
        return state.model_dump()

    def _persist_completion(self, state: AuditWorkflowState) -> dict[str, object]:
        summary = state.summary.model_copy(
            update={
                "status": RunStatus.COMPLETE,
                "failure_code": None,
                "error": None,
                "updated_at": datetime.now(UTC),
            }
        )
        state = state.model_copy(update={"summary": summary})
        state = self._event(
            state, WorkflowEventType.STAGE_COMPLETED, RunStatus.COMPLETE, "audit completed"
        )
        self.store.save_audit_state(state)
        return state.model_dump()

    def _stage(self, state: AuditWorkflowState, status: RunStatus) -> AuditWorkflowState:
        summary = state.summary.model_copy(
            update={"status": status, "updated_at": datetime.now(UTC)}
        )
        state = state.model_copy(update={"summary": summary})
        return self._event(
            state, WorkflowEventType.STAGE_STARTED, status, f"{status.value} started"
        )

    @staticmethod
    def _event(
        state: AuditWorkflowState,
        event_type: WorkflowEventType,
        stage: RunStatus,
        detail: str,
    ) -> AuditWorkflowState:
        sequence = len(state.events)
        event = WorkflowEvent(
            id=stable_id("workflow_event", state.summary.id, sequence, event_type.value),
            run_id=state.summary.id,
            sequence=sequence,
            event_type=event_type,
            stage=stage,
            detail=detail,
        )
        return state.model_copy(update={"events": [*state.events, event]})

    def _limits(self) -> IndexLimits:
        return IndexLimits(
            max_file_bytes=self.settings.max_file_bytes,
            max_index_bytes=self.settings.max_index_bytes,
            max_files=self.settings.max_index_files,
        )

    def _required_project(self, project_id: str) -> Project:
        project = self.store.get_project(project_id)
        if project is None:
            raise RuntimeError("project not found")
        return project

    def _required_incident(self, incident_id: str) -> Incident:
        incident = self.store.get_incident(incident_id)
        if incident is None:
            raise RuntimeError("incident not found")
        return incident
