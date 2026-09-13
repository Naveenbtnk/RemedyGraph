# Deployment and Demo Strategy

## Recommended portfolio deployment

RemedyGraph is intentionally local-first because it reads user-selected repositories and can write
an approved generated guard. The safest portfolio presentation is:

1. Run the FastAPI backend and React frontend on the recruiter's machine or in a recorded demo.
2. Audit only bundled synthetic repositories or a repository inside an explicitly configured
   `WORKSPACE_ROOT`.
3. Keep the mock provider for the reproducible demo; it requires no API key or network call.
4. Store runtime SQLite files outside Git and never expose the backend directly to the public web.

Static frontend hosting alone cannot perform repository audits. A public backend would need tenant
isolation, authentication, a hardened operating-system sandbox, quotas, encrypted storage, and a
separate disposable worker. Those are intentionally outside the five-day MVP.

Production frontend hosting must reproduce the security headers configured for Vite preview:
restrict scripts and styles to the same origin, deny framing and object embedding, disable camera,
microphone, and geolocation, use `nosniff`, and omit referrer data. Keep the API CORS origin set to
the exact frontend origin; the MVP intentionally accepts neither cross-origin credentials nor
request headers beyond `Content-Type`.

## Free-cost operation

- Backend and frontend run locally with Python and Node.js.
- SQLite FTS5 and the deterministic fake encoder are built into the default path.
- Microsoft MarkItDown and sentence-transformers are optional extras.
- Default tests and RemedyBench make no paid API calls and download no models.
- GitHub Actions uses standard repository CI minutes; no cloud database is required.

## Environment boundary

Set `REMEDYGRAPH_WORKSPACE_ROOT` to the narrowest directory containing repositories that may be
audited. For persistence, set `REMEDYGRAPH_DATABASE_PATH` to a local path outside the Git checkout.
Generated guards remain below each audited repository's `.remedygraph/generated_guards` directory
and require explicit preview approval.

## Demo checklist

1. Start the API with `uvicorn backend.app.main:app --reload`.
2. Start the UI with `npm run dev --prefix frontend`.
3. Open `http://localhost:5173`.
4. Select `remedybench/repositories/I04` and paste `remedybench/incidents/I04.md`.
5. Show the MISSING circuit-breaker verdict, PARTIAL fallback, and VERIFIED recovery test.
6. Generate guard previews, review one, approve it, and execute it against the seeded bad state.
7. Finish with the saved RemedyBench result and its reproducibility metadata.
