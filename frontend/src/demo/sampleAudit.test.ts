import { describe, expect, it } from "vitest";
import { sampleActions, sampleEvidence, sampleGraph, sampleRun } from "./sampleAudit";

describe("public sample audit", () => {
  it("keeps citations and selected graph relationships internally consistent", () => {
    const evidenceIds = new Set(sampleEvidence.map((record) => record.id));
    const nodeIds = new Set(sampleGraph.nodes.map((node) => node.id));

    expect(sampleRun.completed_actions).toBe(sampleActions.length);
    expect(sampleRun.verdict_counts).toEqual({ VERIFIED: 1, PARTIAL: 1, MISSING: 1 });
    expect(sampleRun.assessed_protection_coverage).toBe(50);
    for (const action of sampleActions) {
      expect(action.citations.every((citation) => evidenceIds.has(citation.evidence_id))).toBe(true);
      expect(
        action.verdict === "VERIFIED" || action.citations.length > 0 || action.missing_proofs.length > 0,
      ).toBe(true);
    }
    for (const edge of sampleGraph.edges) {
      expect(nodeIds.has(edge.source_node_id)).toBe(true);
      expect(nodeIds.has(edge.target_node_id)).toBe(true);
    }
  });
});
