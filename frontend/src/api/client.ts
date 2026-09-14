const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000/api/v1";
const REQUEST_TIMEOUT_MS = 120_000;
const MAX_ERROR_LENGTH = 500;

export async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  try {
    const response = await fetch(`${API_BASE}${path}`, {
      ...init,
      credentials: "omit",
      headers: { "Content-Type": "application/json", ...init?.headers },
      referrerPolicy: "no-referrer",
      signal: controller.signal,
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      const detail =
        typeof payload.detail === "string"
          ? payload.detail.slice(0, MAX_ERROR_LENGTH)
          : `Request failed (${response.status})`;
      throw new Error(detail);
    }
    return payload as T;
  } catch (reason) {
    if (reason instanceof DOMException && reason.name === "AbortError") {
      throw new Error("The local service did not respond within two minutes.");
    }
    throw reason;
  } finally {
    window.clearTimeout(timeout);
  }
}
