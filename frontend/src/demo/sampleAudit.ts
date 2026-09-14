import type { ActionVerdict, Evidence, EvidenceGraph, GraphEdge, RunSummary } from "../api/types";

function edge(index: number, source: string, target: string, type: string): GraphEdge {
  return {
    id: `demo-edge-${index}`,
    source_node_id: source,
    target_node_id: target,
    edge_type: type,
  };
}

export const sampleIncident = `# Recommendations cascade into catalog

Catalog called recommendations synchronously and lacked complete failure isolation.

## Corrective actions

- Add a circuit breaker.
- Serve a safe fallback while open.
- Test half-open recovery.
`;

export const sampleRun: RunSummary = {
  id: "demo-i04-catalog",
  status: "COMPLETE",
  total_actions: 3,
  completed_actions: 3,
  verdict_counts: { VERIFIED: 1, PARTIAL: 1, MISSING: 1 },
  assessed_protection_coverage: 50.0,
  budget: {
    model_calls_used: 1,
    model_calls_limit: 6,
    investigation_rounds: {
      "demo-invariant-circuit-breaker": 1,
      "demo-invariant-fallback": 1,
      "demo-invariant-half-open": 1,
    },
  },
};

export const sampleActions: ActionVerdict[] = [
  {
    id: "demo-verdict-circuit-breaker",
    action_id: "demo-action-circuit-breaker",
    verdict: "MISSING",
    rationale: "A required deterministic implementation check failed or found no implementation.",
    citations: [],
    missing_proofs: [
      "Required executable terms were not found.",
    ],
  },
  {
    id: "demo-verdict-fallback",
    action_id: "demo-action-fallback",
    verdict: "PARTIAL",
    rationale: "Some implementation or protection is present, but required proof is incomplete.",
    citations: [{ evidence_id: "demo-evidence-open-path", source_path: "catalog.py", line_start: 14 }],
    missing_proofs: [
      "Adequate regression protection is absent.",
      "No matching behavioral test assertion was found.",
    ],
  },
  {
    id: "demo-verdict-half-open",
    action_id: "demo-action-half-open",
    verdict: "VERIFIED",
    rationale: "All required deterministic checks pass with implementation and regression evidence.",
    citations: [{ evidence_id: "demo-evidence-recovery-test", source_path: "tests/test_catalog.py", line_start: 4 }],
    missing_proofs: [],
  },
];

export const sampleEvidence: Evidence[] = [
  {
    id: "demo-evidence-circuit-declaration",
    action_id: "demo-action-circuit-breaker",
    kind: "code",
    role: "supporting_only",
    source_path: "catalog.py",
    line_start: 1,
    excerpt:
      'class CircuitBreakerConfig:\n    """Unused declaration: this is intentionally not implementation proof."""',
  },
  {
    id: "demo-evidence-circuit-gap",
    action_id: "demo-action-circuit-breaker",
    kind: "absent",
    role: "missing",
    excerpt: "missing executable terms: circuit, breaker",
  },
  {
    id: "demo-evidence-fallback",
    action_id: "demo-action-fallback",
    kind: "code",
    role: "supporting",
    source_path: "catalog.py",
    line_start: 8,
    excerpt: "def safe_fallback() -> dict[str, bool]:\n    return {\"degraded\": True}",
  },
  {
    id: "demo-evidence-open-path",
    action_id: "demo-action-fallback",
    kind: "code",
    role: "supporting",
    source_path: "catalog.py",
    line_start: 13,
    excerpt: "if OPEN_STATE:\n    return safe_fallback()",
  },
  {
    id: "demo-evidence-fallback-gap",
    action_id: "demo-action-fallback",
    kind: "absent",
    role: "missing",
    excerpt: "no matching behavioral test assertion found",
  },
  {
    id: "demo-evidence-recovery-code",
    action_id: "demo-action-half-open",
    kind: "code",
    role: "supporting",
    source_path: "catalog.py",
    line_start: 18,
    excerpt: "def recover_half_open() -> bool:\n    return True",
  },
  {
    id: "demo-evidence-recovery-test",
    action_id: "demo-action-half-open",
    kind: "test",
    role: "supporting",
    source_path: "tests/test_catalog.py",
    line_start: 4,
    excerpt: "def test_half_open_recovery() -> None:\n    assert recover_half_open() is True",
  },
];

export const sampleGraph: EvidenceGraph = {
  nodes: [
    { id: "demo-incident", node_type: "incident", label: "Recommendations cascade into catalog" },
    { id: "demo-action-circuit-breaker", node_type: "action", label: "Add a circuit breaker" },
    { id: "demo-action-fallback", node_type: "action", label: "Serve a safe fallback while open" },
    { id: "demo-action-half-open", node_type: "action", label: "Test half-open recovery" },
    {
      id: "demo-invariant-circuit-breaker",
      node_type: "invariant",
      label: "Circuit breaker wired into the catalog path",
    },
    { id: "demo-invariant-fallback", node_type: "invariant", label: "Safe fallback while open" },
    {
      id: "demo-invariant-half-open",
      node_type: "invariant",
      label: "Half-open recovery regression protection",
    },
    { id: "demo-evidence-circuit-declaration", node_type: "evidence", label: "catalog.py:1" },
    { id: "demo-evidence-circuit-gap", node_type: "evidence", label: "missing circuit-breaker wiring" },
    { id: "demo-evidence-fallback", node_type: "evidence", label: "catalog.py:8" },
    { id: "demo-evidence-open-path", node_type: "evidence", label: "catalog.py:13" },
    { id: "demo-evidence-fallback-gap", node_type: "evidence", label: "missing fallback regression test" },
    { id: "demo-evidence-recovery-test", node_type: "evidence", label: "tests/test_catalog.py:4" },
    { id: "demo-verdict-circuit-breaker", node_type: "verdict", label: "MISSING" },
    { id: "demo-verdict-fallback", node_type: "verdict", label: "PARTIAL" },
    { id: "demo-verdict-half-open", node_type: "verdict", label: "VERIFIED" },
  ],
  edges: [
    edge(1, "demo-incident", "demo-action-circuit-breaker", "contains"),
    edge(2, "demo-incident", "demo-action-fallback", "contains"),
    edge(3, "demo-incident", "demo-action-half-open", "contains"),
    edge(4, "demo-action-circuit-breaker", "demo-invariant-circuit-breaker", "compiled_to"),
    edge(5, "demo-action-fallback", "demo-invariant-fallback", "compiled_to"),
    edge(6, "demo-action-half-open", "demo-invariant-half-open", "compiled_to"),
    edge(7, "demo-invariant-circuit-breaker", "demo-evidence-circuit-declaration", "supported_by"),
    edge(8, "demo-invariant-circuit-breaker", "demo-evidence-circuit-gap", "evidence_gap"),
    edge(9, "demo-invariant-fallback", "demo-evidence-fallback", "supported_by"),
    edge(10, "demo-invariant-fallback", "demo-evidence-open-path", "supported_by"),
    edge(11, "demo-invariant-fallback", "demo-evidence-fallback-gap", "evidence_gap"),
    edge(12, "demo-invariant-half-open", "demo-evidence-recovery-test", "tested_by"),
    edge(13, "demo-action-circuit-breaker", "demo-verdict-circuit-breaker", "classified_as"),
    edge(14, "demo-action-fallback", "demo-verdict-fallback", "classified_as"),
    edge(15, "demo-action-half-open", "demo-verdict-half-open", "classified_as"),
  ],
};
