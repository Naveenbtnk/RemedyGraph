# RemedyGraph

RemedyGraph verifies whether fixes from incident postmortems are actually implemented in code. It
scans a repository, checks each corrective action, and produces evidence-backed verdicts.

**Use case:** A team fixes a production outage but wants proof the issue will not happen again.
RemedyGraph audits the code and confirms whether the fix is complete or missing.

[![CI](https://github.com/Naveenbtnk/RemedyGraph/actions/workflows/ci.yml/badge.svg)](https://github.com/Naveenbtnk/RemedyGraph/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-111111?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-API-111111?style=flat-square&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React-Dashboard-111111?style=flat-square&logo=react&logoColor=white)](https://react.dev/)
[![SQLite](https://img.shields.io/badge/SQLite-Storage-111111?style=flat-square&logo=sqlite&logoColor=white)](https://www.sqlite.org/)
[![Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-111111?style=flat-square&logo=apache&logoColor=white)](LICENSE)
[![Live demo](https://img.shields.io/badge/Live_demo-Vercel-111111?style=flat-square&logo=vercel&logoColor=white)](https://remedy-graph.vercel.app)

RemedyGraph audits whether corrective actions from incident postmortems are implemented and
protected against regression. It turns each action into a measurable requirement, inspects a local
repository, runs bounded deterministic checks, and presents a verdict with traceable evidence.

## Visual Overview

[![RemedyGraph audit dashboard](docs/images/dashboard.png)](https://drive.google.com/file/d/16dq5QTbeR1b6WojloqRdKMLptTgfI_Yb/view?usp=sharing)

*Select the dashboard to watch the full end-to-end audit demonstration, or view the
[short audit walkthrough](https://drive.google.com/file/d/1GDCVhbJ5GdVcIW9e3Py6rDeFdaZOKsAi/view?usp=sharing).*

- Dashboard view showing audit results
- Action level evidence inspection
- End to end audit flow

The result is an audit, not a chatbot response:

```text
postmortem action → invariant → repository evidence → check → verdict → approved guard
```

## Capabilities

- Extract atomic corrective actions from Markdown or plain-text postmortems.
- Index a workspace-bounded local repository with path, size, binary, and secret controls.
- Verify Python code, configuration, and regression-test structure with deterministic checks.
- Report `VERIFIED`, `PARTIAL`, `MISSING`, or `UNVERIFIABLE` with citations or explicit proof gaps.
- Explore an evidence graph and preview CI guards before any write or execution.
- Reproduce the five-incident synthetic RemedyBench evaluation without model credentials.

## Why this matters

- Incident fixes are often not verified after implementation
- Missing validation leads to repeated production failures
- Teams lack proof that corrective actions are enforced

RemedyGraph ensures every fix is measurable, verified, and protected against regression.

The dashboard workflow is local and single-user. The optional repository-local GitHub Actions
pilot lets invited users run the same bounded audit in repositories they control. The default
model provider is deterministic and network-free; a shared multi-user backend is **not** a
supported deployment.

For a small group evaluating their own repositories, use the [private local pilot guide](docs/PILOT.md).
For a repository-owned hosted run, use the [GitHub Actions pilot](docs/GITHUB_PILOT.md).

## Requirements

- Python 3.11 or newer
- Node.js 22 or newer and npm
- Git

## Install

```text
git clone https://github.com/Naveenbtnk/RemedyGraph.git
cd RemedyGraph
python -m venv .venv
```

Activate the environment with `.\.venv\Scripts\Activate.ps1` in PowerShell or
`source .venv/bin/activate` in a POSIX shell. Then install the backend and frontend:

```text
python -m pip install -e ".[dev]"
npm ci --prefix frontend
```

Copy `.env.example` to `.env` if you want to customize server settings. The defaults work when
commands are run from the repository root. Keep `.env` and any runtime database outside version
control.

## Run a local audit

In one terminal, start the API:

```text
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

In another terminal, start the dashboard:

```text
npm run dev --prefix frontend
```

Open [http://localhost:5173](http://localhost:5173). Enter
`remedybench/repositories/I04` as the repository path. The form is prefilled with the matching
[`I04 postmortem`](remedybench/incidents/I04.md), and you can replace it with your own text. That fixture
demonstrates missing, partial, and verified actions in one audit. Expand an action to inspect its
evidence and missing proof. Guard previews are read-only; writing and execution require an explicit
approval for that exact preview.

## Example Audit

Repository: `sample-service`<br>
Incident: API failure due to missing retry logic

Before:

- No retry mechanism
- No test coverage

After running RemedyGraph:

- Invariant: API calls must include retry logic
- Evidence: retry wrapper found in service layer
- Test: retry behavior validated
- Verdict: `VERIFIED`

*Replace with real repository example later.*

## Engineering Highlights

- Designed invariant-based verification system for postmortem actions
- Built deterministic audit pipeline with reproducible results
- Implemented safe repository indexing with strict limits
- Developed evidence graph for traceable verification
- Integrated CI-ready checks and evaluation benchmarks

The API exposes interactive documentation at [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
and a health check at `/health`. Product endpoints are under `/api/v1`.

## Configuration

Backend settings use the `REMEDYGRAPH_` prefix and may be set in the environment or a root `.env`
file. See [`.env.example`](.env.example) for all defaults.

| Variable | Default | Purpose |
|---|---|---|
| `REMEDYGRAPH_WORKSPACE_ROOT` | Current directory | Only repositories inside this resolved root may be audited. Set it as narrowly as possible. |
| `REMEDYGRAPH_DATABASE_PATH` | `:memory:` | SQLite location. Use an absolute path outside the checkout to persist runs. |
| `REMEDYGRAPH_FRONTEND_ORIGIN` | `http://localhost:5173` | Exact origin allowed by API CORS. |
| `REMEDYGRAPH_LLM_PROVIDER` | `mock` | Only the deterministic local provider is currently implemented. |
| `REMEDYGRAPH_MAX_MODEL_CALLS` | `6` | Maximum attempted provider calls per stable incident, including failed attempts. |
| `REMEDYGRAPH_MAX_INVESTIGATION_ROUNDS` | `3` | Maximum investigation rounds per invariant. |
| `REMEDYGRAPH_MAX_FILE_BYTES` | `1000000` | Maximum bytes indexed from one file. |
| `REMEDYGRAPH_MAX_INDEX_BYTES` | `25000000` | Total index byte limit. |
| `REMEDYGRAPH_MAX_INDEX_FILES` | `10000` | Maximum number of indexed files. |
| `REMEDYGRAPH_RETRIEVAL_TOP_K` | `8` | Maximum final retrieval candidates per invariant. |
| `REMEDYGRAPH_GUARD_TIMEOUT_SECONDS` | `5` | Approved guard execution timeout. |
| `REMEDYGRAPH_GUARD_OUTPUT_LIMIT` | `16384` | Maximum captured guard output bytes. |

`REMEDYGRAPH_APP_NAME`, `REMEDYGRAPH_APP_VERSION`, and `REMEDYGRAPH_ENVIRONMENT` set service
metadata. The dashboard uses `VITE_API_BASE_URL` (default
`http://localhost:8000/api/v1`); copy [`frontend/.env.example`](frontend/.env.example) to
`frontend/.env.local` to override it. Vite variables are exposed to the browser: **never put
credentials in them**.

## Evaluation and verification

Run the reproducible benchmark:

```text
python -m backend.app.evaluation.cli --benchmark remedybench --check
```

The checked-in [measured report](evals/results/remedybench-smoke.json) contains the benchmark
version and hash, source commit, per-action predictions, and aggregate metrics. The five-case
synthetic smoke set is useful for regression testing, not a claim of production generalization.

Run the same checks used by CI:

```text
ruff check .
ruff format --check .
mypy backend
python -m pytest -q
python -m compileall -q backend tests
npm run lint --prefix frontend
npm test --prefix frontend -- --run
npm run build --prefix frontend
python -m backend.app.evaluation.cli --benchmark remedybench --check
```

## GitHub Actions pilot

The repository includes a composite action and a copyable
[read-only workflow](docs/examples/remedygraph-audit.yml). The workflow runs on a repository-owned
GitHub runner, uses an ephemeral SQLite database, and uploads a minimized JSON report for seven
days. It does not send source code to RemedyGraph, execute the repository's tests or build, or
write or execute guards.

Copy the example into an invited repository, replace `COMMIT_SHA` with a reviewed full RemedyGraph
commit SHA, and run it manually from the repository's Actions page. Public repositories receive
free standard GitHub-hosted runner usage; private repositories consume the owner's included
minutes and artifact storage. Review the complete
[pilot threat boundary and setup](docs/GITHUB_PILOT.md) before inviting users.

## Deployment and security

For a persistent local installation, set `REMEDYGRAPH_WORKSPACE_ROOT` to a dedicated parent of
the repositories you intend to inspect and `REMEDYGRAPH_DATABASE_PATH` to an absolute location
outside this checkout. Bind the API to `127.0.0.1`. The frontend can be built with
`npm run build --prefix frontend`; `npm run preview --prefix frontend` is a local build preview,
not a production hosting service.

Do not expose the current API to the public internet. Shared public hosting would require authentication,
tenant isolation, a hardened disposable execution worker, storage controls, and additional abuse
limits. Audits never write application source; generated guards
are restricted to an application-owned directory and require preview-bound approval before writing
or execution.

For a public read-only showcase, deploy the `frontend` directory as a Vite project on Vercel.
[`frontend/vercel.json`](frontend/vercel.json) builds the bundled I04 sample with
`npm run build:demo`, serves `dist`, and applies restrictive response headers. No backend or
environment variables are needed. Visitors can inspect sample verdicts and selected evidence;
repository input and guard controls are unavailable. The public view is a curated display of a
locally measured I04 run, not a live audit. See [deployment details](docs/DEPLOYMENT.md).
The current showcase is live at [remedy-graph.vercel.app](https://remedy-graph.vercel.app).

## Repository guide

| Path | Responsibility |
|---|---|
| `backend/app/audit/` | Invariant compilation, deterministic checks, verdicts, workflow, and graph. |
| `backend/app/rag/` | Safe ingestion, indexing, retrieval, and redaction. |
| `backend/app/guards/` | Guard templates, approval lifecycle, and bounded execution. |
| `backend/app/evaluation/` | Typed RemedyBench evaluator and CLI. |
| `backend/app/pilot/`, `action.yml` | Minimized report CLI and repository-local GitHub Action. |
| `frontend/src/api/`, `components/`, `demo/`, `lib/` | Dashboard contracts, request client, presentation, public sample, and shared utilities. |
| `remedybench/` | Synthetic incidents, fixture repositories, and ground truth. |
| `evals/results/` | Curated measured evaluation report. |
| `tests/` | Unit, API, and integration coverage. |
| `docs/` | Architecture, design, testing, deployment, and project status. |

See the [architecture](docs/ARCHITECTURE.md), [testing strategy](docs/TESTING.md), and
[current status](docs/STATUS.md) for implementation details and known limitations.

The benchmark-authored fixtures are CC0-1.0.

## License

RemedyGraph is licensed under the [Apache License 2.0](LICENSE).
