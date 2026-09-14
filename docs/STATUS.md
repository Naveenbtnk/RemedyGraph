# Project Status

**Updated:** 2026-09-14

**Release:** Local, single-user `0.1.0`

**Baseline:** `main` at `04fe8a568124b46cc50347c30d29138ab3f0db10` passed GitHub CI

**Current work:** Public demo deployed; private local pilot onboarding prepared

## Implemented

- FastAPI application with typed requests, a configurable workspace boundary, and versioned
  SQLite persistence. Incident-level model-attempt reservation is atomic across connections.
- Safe local ingestion and hybrid retrieval with redacted evidence and exact source locations.
- Bounded audit workflow with deterministic invariant checks, conservative verdicts, and an
  evidence graph. Unsupported or unavailable requirements remain explicit.
- Human-approved, application-owned guard previews with bounded writing and execution.
- React dashboard for audit setup, status, verdicts, evidence, graph inventory, and guard lifecycle.
- Synthetic five-incident RemedyBench smoke set, saved measured JSON result, and network-free CI.

## Maintenance changes

- Separated frontend API contracts and request handling from reusable presentation components.
- Aligned setup, deployment, architecture, design, and testing documentation with implemented
  behavior; removed obsolete planning labels and a redundant image note.
- Added backend and frontend environment examples, an editor configuration, and an updated
  screenshot of the current dashboard.
- Refreshed GitHub Actions dependencies and kept runtime frontend dependencies separate from
  build and test tools.
- Kept the established backend package path, API routes, benchmark fixtures, and historical
  architecture decisions stable.

Changed paths: `README.md`, `.env.example`, `.editorconfig`, `.github/workflows/ci.yml`,
`frontend/.env.example`, `frontend/package*.json`, `frontend/src/App*`, `frontend/src/api/`,
`frontend/src/components/`, `frontend/src/lib/`, selected backend comments, `docs/PRD.md`,
`docs/ARCHITECTURE.md`, `docs/DESIGN.md`, `docs/DEPLOYMENT.md`, `docs/TESTING.md`, this status,
and `docs/images/dashboard.png`. The obsolete `frontend/src/ui.ts` and image note were removed.

## Public demo preparation

- Added a separate Vite demo build with a bundled synthetic I04 audit. The locally measured
  result has one missing, one partial, and one verified action with 50% assessed protection
  coverage. The public view presents selected evidence relationships and labels the selection.
- Read-only fields, disabled audit and guard actions, and an explicit local-setup link distinguish
  the static showcase from the local application.
- `frontend/vercel.json` selects the demo build, keeps the Vercel deployment frontend-only, and
  sets a content security policy that disallows outbound connections. No backend environment
  variables or live API are needed.

Changed paths for this addition: `frontend/src/App.tsx`, `frontend/src/App.test.tsx`,
`frontend/src/styles.css`, `frontend/src/demo/`, `frontend/package.json`, `frontend/vercel.json`,
`README.md`, `docs/ARCHITECTURE.md`, `docs/DESIGN.md`, `docs/DEPLOYMENT.md`,
`docs/TESTING.md`, and this status.

The read-only showcase is deployed at <https://remedy-graph.vercel.app>. A private local pilot
guide now gives selected testers a reproducible installation, sample check, real-repository
workflow, and sanitized feedback checklist. Each tester runs the API on loopback on their own
computer; this does not add a shared backend or authentication.

## Verification

The integrated `main` checkout passes 104 backend tests and 8 frontend tests. Ruff lint and format
checks, mypy, Python compilation, frontend lint, local and demo builds, and the RemedyBench check
pass. The npm dependency audit found no vulnerabilities. README links, CI YAML parsing,
`git diff --check`, secret review, and a tracked runtime-database scan pass. GitHub CI passed for
the integrated demo release. The pilot documentation change passed 104 backend tests, 8 frontend
tests, Ruff, mypy, Python compilation, both frontend builds, and the RemedyBench smoke check.

## Known limitations

- The supported deployment is local and single-user. Public multi-tenant hosting would require
  authentication, tenant isolation, and a stronger operating-system execution sandbox.
- The default provider is deterministic and local. Live vendor adapters are not implemented.
- Python is the primary structurally verified language. Runtime-only requirements remain
  `UNVERIFIABLE` without their required context.
- SQLite is in-memory unless `REMEDYGRAPH_DATABASE_PATH` is set. The semantic vector snapshot is
  process-local.
- Guards are narrow application-owned static assertions, not a general code-generation system.
- Published perfect benchmark scores cover only five synthetic cases and do not establish
  performance on arbitrary repositories.
- The application source has no assigned license; benchmark-authored fixtures are CC0-1.0.

## Next task

Collect sanitized pilot feedback on action extraction, verdict accuracy, and setup friction from
a small number of local users. A broader benchmark and persisted evaluation API remain separate
future work.
