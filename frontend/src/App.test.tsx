import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import App from "./App";
import type { ActionVerdict, Evidence, Guard } from "./api/types";
import ActionCard from "./components/ActionCard";
import GuardCard from "./components/GuardCard";
import { canExecuteGuard, formatStatus } from "./lib/status";

describe("RemedyGraph audit dashboard", () => {
  it("renders the evidence-first audit and approval controls", () => {
    const markup = renderToStaticMarkup(<App />);

    expect(markup).toContain("Turn incident promises into proof.");
    expect(markup).toContain("Recommendations cascade into catalog");
    expect(markup).toContain("Bounded by design");
    expect(markup).toContain("Skip to audit workspace");
    expect(markup).toContain("<progress");
    expect(markup).toContain('aria-label="Actions assessed"');
    expect(markup).toContain("Assessed protection coverage");
    expect(markup).toContain("Corrective actions");
    expect(markup).toContain("Evidence graph");
    expect(markup).toContain("Generate guard previews");
    expect(markup).toContain("disabled");
  });

  it("keeps execution disabled until a guard has been approved and written", () => {
    expect(canExecuteGuard("PREVIEWED")).toBe(false);
    expect(canExecuteGuard("REJECTED")).toBe(false);
    expect(canExecuteGuard("WRITTEN")).toBe(true);
    expect(canExecuteGuard("PASSED")).toBe(true);
    expect(formatStatus("PARTIAL_COMPLETE")).toBe("partial complete");
  });

  it("renders missing proof beside located action evidence", () => {
    const action: ActionVerdict = {
      id: "verdict-1",
      action_id: "action-1",
      verdict: "PARTIAL",
      rationale: "Fallback exists without regression protection.",
      citations: [],
      missing_proofs: ["A relevant regression test is missing."],
    };
    const evidence: Evidence[] = [{
      id: "evidence-1",
      action_id: "action-1",
      kind: "code",
      role: "supporting",
      source_path: "catalog.py",
      line_start: 12,
      excerpt: "return cached_result",
    }];

    const markup = renderToStaticMarkup(
      <ActionCard action={action} evidence={evidence} index={0} />,
    );
    expect(markup).toContain("A relevant regression test is missing.");
    expect(markup).toContain("catalog.py:12");
    expect(markup).toContain("return cached_result");
  });

  it("keeps an unapproved guard preview read-only", () => {
    const guard: Guard = {
      id: "guard-1",
      name: "Bounded retries",
      guard_type: "static_repository",
      intent: "Protect the retry limit",
      assertions: ["Retries remain bounded"],
      target_path: "retry.py",
      preview: "assert retry_limit == 3",
      preview_sha256: "a".repeat(64),
      status: "PREVIEWED",
    };

    const markup = renderToStaticMarkup(
      <GuardCard
        guard={guard}
        busy={false}
        pendingAction={null}
        onDecision={() => undefined}
        onExecute={() => undefined}
      />,
    );
    expect(markup).toContain("Approve and write");
    expect(markup).toMatch(/<button[^>]*disabled=""[^>]*>Execute approved guard/);
  });
});
