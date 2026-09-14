import { afterEach, describe, expect, it, vi } from "vitest";
import { requestJson } from "./client";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("API client", () => {
  it("omits browser credentials and referrers", async () => {
    vi.stubGlobal("window", globalThis);
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ id: "run-1" })));
    vi.stubGlobal("fetch", fetchMock);

    await expect(requestJson<{ id: string }>("/runs/run-1")).resolves.toEqual({ id: "run-1" });
    expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost:8000/api/v1/runs/run-1",
      expect.objectContaining({ credentials: "omit", referrerPolicy: "no-referrer" }),
    );
  });

  it("bounds a displayed server error", async () => {
    vi.stubGlobal("window", globalThis);
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ detail: "x".repeat(600) }), { status: 400 }),
      ),
    );

    await expect(requestJson("/runs/missing")).rejects.toThrow(/^x{500}$/);
  });
});
