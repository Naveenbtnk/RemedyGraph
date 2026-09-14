# Deployment and Demo Strategy

## Supported deployment

RemedyGraph is intentionally local-first because it reads user-selected repositories and can write
an approved generated guard. The supported setup is:

1. Run the FastAPI backend and React frontend on the local machine or in a recorded demo.
2. Audit only bundled synthetic repositories or a repository inside an explicitly configured
   `WORKSPACE_ROOT`.
3. Keep the mock provider for the reproducible demo; it requires no API key or network call.
4. Store runtime SQLite files outside Git and never expose the backend directly to the public web.

Static frontend hosting alone cannot perform repository audits. A public backend would need tenant
isolation, authentication, a hardened operating-system sandbox, quotas, encrypted storage, and a
separate disposable worker. Those controls are not implemented in this release.

For a small private evaluation, each tester can run the local application on their own computer.
The [pilot guide](PILOT.md) covers setup, workspace selection, a sample audit, and sanitized
feedback. Do not point the hosted demo at a tester's local API or expose the API to the internet.

## Public read-only demo on Vercel

Import this repository with the Vite preset and `frontend` as the root directory. The committed
`frontend/vercel.json` overrides the dashboard build command with `npm run build:demo`, uses
`npm ci` and `dist`, and sets response headers. Do not import backend `REMEDYGRAPH_*` variables.
No environment variables are required for this static site.

The demo includes the synthetic I04 incident and a curated snapshot from a locally measured
audit: one missing, one partial, one verified action, and 50% assessed protection coverage.
Its repository and postmortem fields are read-only; audit submission and guard controls are
disabled. Its evidence graph shows selected relationships rather than the full persisted graph.
The banner links visitors to the local setup instructions for a real audit. Run
`npm run build:demo --prefix frontend` to verify the public build before deployment.

Other frontend hosts must reproduce the security headers configured for Vite preview:
restrict scripts and styles to the same origin, deny framing and object embedding, disable camera,
microphone, and geolocation, use `nosniff`, and omit referrer data. Keep the API CORS origin set to
the exact frontend origin; the current release accepts neither cross-origin credentials nor
request headers beyond `Content-Type`.

## Local operation

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
