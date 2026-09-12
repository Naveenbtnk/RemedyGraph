import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import App from "./App";
import { canExecuteGuard, formatStatus } from "./ui";

describe("RemedyGraph audit dashboard", () => {
  it("renders the evidence-first audit and approval controls", () => {
    const markup = renderToStaticMarkup(<App />);

    expect(markup).toContain("Turn incident promises into proof.");
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
});
