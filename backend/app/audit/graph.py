"""Evidence graph assembly with referential-integrity validation."""

from collections.abc import Sequence

from backend.app.audit.contracts import (
    ActionVerdict,
    CompiledInvariant,
    DeterministicCheckResult,
    EvidenceGraphEdge,
    EvidenceGraphNode,
    EvidenceRecord,
    EvidenceRole,
    GraphEdgeType,
    GraphNodeType,
)
from backend.app.ids import stable_id
from backend.app.models import ActionItem, Incident


class EvidenceGraphBuilder:
    def build(
        self,
        *,
        run_id: str,
        incident: Incident,
        actions: Sequence[ActionItem],
        invariants: Sequence[CompiledInvariant],
        evidence: Sequence[EvidenceRecord],
        checks: Sequence[DeterministicCheckResult],
        verdicts: Sequence[ActionVerdict],
    ) -> tuple[list[EvidenceGraphNode], list[EvidenceGraphEdge]]:
        nodes: list[EvidenceGraphNode] = []
        edges: list[EvidenceGraphEdge] = []

        def node(kind: GraphNodeType, record_id: str, label: str) -> str:
            node_id = stable_id("node", run_id, kind.value, record_id)
            nodes.append(
                EvidenceGraphNode(
                    id=node_id, run_id=run_id, node_type=kind, record_id=record_id, label=label
                )
            )
            return node_id

        def edge(source: str, target: str, kind: GraphEdgeType) -> None:
            edges.append(
                EvidenceGraphEdge(
                    id=stable_id("edge", run_id, source, target, kind.value),
                    run_id=run_id,
                    source_node_id=source,
                    target_node_id=target,
                    edge_type=kind,
                )
            )

        incident_node = node(GraphNodeType.INCIDENT, incident.id, incident.title)
        action_nodes = {item.id: node(GraphNodeType.ACTION, item.id, item.text) for item in actions}
        for action_id, action_node in action_nodes.items():
            edge(incident_node, action_node, GraphEdgeType.CONTAINS)
        invariant_nodes = {
            invariant.id: node(GraphNodeType.INVARIANT, invariant.id, invariant.statement)
            for invariant in invariants
        }
        for invariant in invariants:
            edge(
                action_nodes[invariant.action_id],
                invariant_nodes[invariant.id],
                GraphEdgeType.COMPILED_TO,
            )
        for evidence_item in evidence:
            evidence_node = node(
                GraphNodeType.EVIDENCE,
                evidence_item.id,
                evidence_item.source_path or evidence_item.role.value,
            )
            relation = GraphEdgeType.SUPPORTED_BY
            if evidence_item.role == EvidenceRole.CONTRADICTORY:
                relation = GraphEdgeType.CONTRADICTED_BY
            elif evidence_item.role in {EvidenceRole.MISSING, EvidenceRole.UNAVAILABLE}:
                relation = GraphEdgeType.EVIDENCE_GAP
            elif evidence_item.kind.value == "test":
                relation = GraphEdgeType.TESTED_BY
            edge(invariant_nodes[evidence_item.invariant_id], evidence_node, relation)
        for check in checks:
            check_node = node(GraphNodeType.CHECK, check.id, check.outcome.value)
            edge(invariant_nodes[check.invariant_id], check_node, GraphEdgeType.CHECKED_BY)
        for verdict in verdicts:
            verdict_node = node(GraphNodeType.VERDICT, verdict.id, verdict.verdict.value)
            edge(action_nodes[verdict.action_id], verdict_node, GraphEdgeType.CLASSIFIED_AS)
        self.validate(
            nodes,
            edges,
            run_id=run_id,
            incident=incident,
            actions=actions,
            invariants=invariants,
            evidence=evidence,
            checks=checks,
            verdicts=verdicts,
        )
        return nodes, edges

    @staticmethod
    def validate(
        nodes: Sequence[EvidenceGraphNode],
        edges: Sequence[EvidenceGraphEdge],
        *,
        run_id: str,
        incident: Incident,
        actions: Sequence[ActionItem],
        invariants: Sequence[CompiledInvariant],
        evidence: Sequence[EvidenceRecord],
        checks: Sequence[DeterministicCheckResult],
        verdicts: Sequence[ActionVerdict],
    ) -> None:
        node_ids = [item.id for item in nodes]
        if len(node_ids) != len(set(node_ids)):
            raise ValueError("evidence graph contains duplicate node IDs")
        record_keys = [(item.node_type, item.record_id) for item in nodes]
        if len(record_keys) != len(set(record_keys)):
            raise ValueError("evidence graph contains duplicate record nodes")
        if any(item.run_id != run_id for item in nodes):
            raise ValueError("evidence graph contains a cross-run node")
        if any(item.run_id != run_id for item in edges):
            raise ValueError("evidence graph contains a cross-run edge")

        records = {
            GraphNodeType.INCIDENT: {incident.id},
            GraphNodeType.ACTION: {item.id for item in actions},
            GraphNodeType.INVARIANT: {item.id for item in invariants},
            GraphNodeType.EVIDENCE: {item.id for item in evidence},
            GraphNodeType.CHECK: {item.id for item in checks},
            GraphNodeType.VERDICT: {item.id for item in verdicts},
        }
        for graph_node in nodes:
            if graph_node.record_id not in records[graph_node.node_type]:
                raise ValueError("evidence graph node has a missing or mismatched record type")
        expected_record_keys = {
            (node_type, record_id)
            for node_type, record_ids in records.items()
            for record_id in record_ids
        }
        if set(record_keys) != expected_record_keys:
            raise ValueError("evidence graph does not contain exactly one node per record")

        node_by_id = {item.id: item for item in nodes}
        node_by_record = {(item.node_type, item.record_id): item.id for item in nodes}
        actual_edges: set[tuple[str, str, GraphEdgeType]] = set()
        edge_ids: set[str] = set()
        for graph_edge in edges:
            if graph_edge.id in edge_ids:
                raise ValueError("evidence graph contains duplicate edge IDs")
            edge_ids.add(graph_edge.id)
            if (
                graph_edge.source_node_id not in node_by_id
                or graph_edge.target_node_id not in node_by_id
            ):
                raise ValueError("evidence graph edge references an unknown node")
            relationship = (
                graph_edge.source_node_id,
                graph_edge.target_node_id,
                graph_edge.edge_type,
            )
            if relationship in actual_edges:
                raise ValueError("evidence graph contains a duplicate relationship")
            actual_edges.add(relationship)

        expected_edges: set[tuple[str, str, GraphEdgeType]] = set()
        incident_node = node_by_record[(GraphNodeType.INCIDENT, incident.id)]
        for action in actions:
            action_node = node_by_record[(GraphNodeType.ACTION, action.id)]
            expected_edges.add((incident_node, action_node, GraphEdgeType.CONTAINS))
        for invariant in invariants:
            expected_edges.add(
                (
                    node_by_record[(GraphNodeType.ACTION, invariant.action_id)],
                    node_by_record[(GraphNodeType.INVARIANT, invariant.id)],
                    GraphEdgeType.COMPILED_TO,
                )
            )
        for evidence_item in evidence:
            relation = GraphEdgeType.SUPPORTED_BY
            if evidence_item.role == EvidenceRole.CONTRADICTORY:
                relation = GraphEdgeType.CONTRADICTED_BY
            elif evidence_item.role in {EvidenceRole.MISSING, EvidenceRole.UNAVAILABLE}:
                relation = GraphEdgeType.EVIDENCE_GAP
            elif evidence_item.kind.value == "test":
                relation = GraphEdgeType.TESTED_BY
            expected_edges.add(
                (
                    node_by_record[(GraphNodeType.INVARIANT, evidence_item.invariant_id)],
                    node_by_record[(GraphNodeType.EVIDENCE, evidence_item.id)],
                    relation,
                )
            )
        for check_result in checks:
            expected_edges.add(
                (
                    node_by_record[(GraphNodeType.INVARIANT, check_result.invariant_id)],
                    node_by_record[(GraphNodeType.CHECK, check_result.id)],
                    GraphEdgeType.CHECKED_BY,
                )
            )
        for action_verdict in verdicts:
            expected_edges.add(
                (
                    node_by_record[(GraphNodeType.ACTION, action_verdict.action_id)],
                    node_by_record[(GraphNodeType.VERDICT, action_verdict.id)],
                    GraphEdgeType.CLASSIFIED_AS,
                )
            )
        if actual_edges != expected_edges:
            raise ValueError("evidence graph relationships do not match audit records")
