import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import App from "./App";

describe("Day 1 dashboard shell", () => {
  it("labels the displayed coverage as assessed protection coverage", () => {
    const markup = renderToStaticMarkup(<App />);

    expect(markup).toContain("Assessed protection coverage");
    expect(markup).toContain("Day 1 scaffold");
  });
});
