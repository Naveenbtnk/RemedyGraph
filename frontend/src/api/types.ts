export type Verdict = "VERIFIED" | "PARTIAL" | "MISSING" | "UNVERIFIABLE";

export type GuardStatus =
  | "PREVIEWED"
  | "REJECTED"
  | "WRITTEN"
  | "PASSED"
  | "FAILED"
  | "TIMED_OUT"
  | "ERROR";

export interface Budget {
  model_calls_used: number;
  model_calls_limit: number;
  investigation_rounds: Record<string, number>;
}

export interface RunSummary {
  id: string;
  status: string;
  total_actions: number;
  completed_actions: number;
  verdict_counts: Partial<Record<Verdict, number>>;
  assessed_protection_coverage: number;
  budget: Budget;
  error?: string | null;
}

export interface Citation {
  evidence_id: string;
  source_path?: string | null;
  line_start?: number | null;
  line_end?: number | null;
}

export interface ActionVerdict {
  id: string;
  action_id: string;
  verdict: Verdict;
  rationale: string;
  citations: Citation[];
  missing_proofs: string[];
}

export interface Evidence {
  id: string;
  action_id: string;
  kind: string;
  role: string;
  source_path?: string | null;
  line_start?: number | null;
  excerpt?: string | null;
}

export interface GraphNode {
  id: string;
  node_type: string;
  label: string;
}

export interface GraphEdge {
  id: string;
  source_node_id: string;
  target_node_id: string;
  edge_type: string;
}

export interface EvidenceGraph {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

export interface GuardExecution {
  id: string;
  status: string;
  exit_code?: number | null;
  stdout: string;
  stderr: string;
  duration_ms: number;
}

export interface Guard {
  id: string;
  name: string;
  guard_type: string;
  intent: string;
  assertions: string[];
  target_path: string;
  preview: string;
  preview_sha256: string;
  status: GuardStatus;
}
