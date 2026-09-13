# RemedyGraph Implementation Status

**Last updated:** 2026-09-13
**Current phase:** Phase 5 — RemedyBench evaluation and demo packaging
**Overall status:** Five-day MVP published; CI portability correction under verification

## Completed

- GitHub repository created and cloned locally.
- Product requirements defined.
- Product and dashboard design defined.
- Technical architecture and safety boundaries defined.
- Architecture decisions recorded.
- Test and evaluation strategy defined.
- Root agent instructions created.
- Multi-agent ownership and change-request process defined.
- FastAPI backend scaffold with typed settings, health, project, and incident API routes.
- Initial Pydantic domain models and request/response schemas with stable opaque IDs.
- Workspace-bound project registration validation and in-memory Day 1 application services.
- Provider interface and deterministic, network-free mock action extractor.
- React/Vite TypeScript frontend dashboard shell with a production build and smoke test.
- Backend API/unit tests, frontend lint/test scripts, and pinned frontend dependency lockfile.
- Typed normalized-document, chunk, search-result, evidence-candidate, index-result, retrieval-log,
  and deterministic investigation-tool contracts.
- Canonical workspace/repository containment and a deterministic safe walker with symlink, secret,
  binary, dependency/build, file-size, total-size, and file-count restrictions.
- Native Markdown/UTF-8 text ingestion with raw SHA-256 provenance and pre-index secret redaction.
- Optional local-only Microsoft MarkItDown PDF/DOCX/PPTX adapter with plugins, remote URLs, cloud
  services, and LLM OCR disabled; ADR-013 records the boundary.
- Heading-aware document chunking and Python AST symbol-aware chunking with exact source locations.
- SQLite FTS5/BM25 lexical indexing, local embedding interface, deterministic fake encoder,
  optional local-files-only sentence-transformer adapter, and repository index build service.
- Full repository rebuilds transactionally replace SQLite chunk/FTS rows and atomically swap a
  precomputed semantic snapshot, so modified or deleted evidence cannot survive reindexing.
- Hybrid candidate merge, chunk-ID deduplication, deterministic reranking, top-k selection, and
  structured retrieval logs with redacted queries, ranks, scores, IDs, and timing.
- Read-only `search_code`, Python `get_symbol`, JSON/YAML/TOML `inspect_config`, `find_tests`, and
  bounded fixed-argument `find_git_changes` tools.
- Safety, conversion, redaction, source-location, retrieval, AST/config/Git tool, and gold-evidence
  Recall@5 automated coverage.
- Typed contracts for compiled invariants, workflow state, evidence/citations, deterministic check
  specifications/results, action verdicts, evidence-graph records, run summaries, repository index
  metadata, workflow events, and budget usage.
- Deterministic invariant compiler for numeric/configuration, code/static, test/protection, and
  runtime/context requirements, preserving original action text and source location while returning
  explicit unsupported or unavailable requirements instead of invented checks.
- Bounded LangGraph audit workflow with explicit load-actions, compile, retrieve-candidates,
  read-only checks, conservative-verdict, evidence-graph, and persistence/completion nodes.
- A persisted six-attempt budget spans each stable incident's full lifecycle: corrective-action
  extraction and audit gateways reserve the same counter before provider invocation, failed calls
  remain charged, and repeated incident submission cannot reset usage.
- A default three-round-per-invariant investigation budget, deterministic local indexing/retrieval,
  and safe failure state persistence.
- Allowlisted numeric configuration/Python constant checks, Python AST call/wiring and enabled
  configuration checks, bounded supporting-only literal scans, and nontrivial relevant regression
  structure checks with typed results and located evidence.
- Declaration-, identifier-, comment-, string-, disabled-config-, constant-assertion-, and unrelated
  test-shaped false proofs are rejected; the exact unused `CircuitBreaker` plus `assert True` case
  produces `MISSING`, never `VERIFIED`.
- Conservative verdict aggregation enforcing deterministic failure precedence, regression proof for
  `VERIFIED`, explicit missing-proof reasons, and a ban on Git/document-only verification.
- Versioned SQLite schema 2 (including migration from schema 1) and typed reload for projects,
  incidents, incident lifecycle budgets, corrective actions, repository index
  metadata, audit runs, invariants, evidence, checks/results, verdicts, evidence graph nodes/edges,
  workflow events, and budget counters.
- Complete transactional audit snapshot replacement removes stale child records and validates
  project/incident ownership, action/invariant/run provenance, result/evidence/verdict links, and
  correctly typed same-run graph records and relationships before writing.
- Bounded provider gateway persists attempted-call usage before provider invocation, including
  failures; sixth-call/seventh-rejection and third-round/fourth-rejection behavior is tested.
- `/api/v1/runs` create/read, action-verdict, evidence, and graph endpoints backed by persisted audit
  state.
- Day 3 unit, integration, and API coverage for all four verdict classes, contradictory values,
  unavailable/unsupported requirements, budget enforcement, graph integrity, and persistence reload.
- FastAPI owns each application SQLite store through its lifespan and closes the connection exactly
  once on shutdown; closure is idempotent and releases file-backed databases on Windows.
- Incident model-call reservation takes an immediate SQLite write transaction before reading the
  counter, so independent connections/workers cannot both consume the final slot; lock exhaustion
  returns a typed `503 storage_busy` response before provider invocation.
- Deterministic guard previews are generated only for `PARTIAL` and `MISSING` actions and remain
  read-only until a per-preview SHA-256 approval decision is recorded.
- Approved artifacts write only below `.remedygraph/generated_guards/<run>` and execute through an
  application-owned `python -I -S -B` command with `shell=False`, closed input, scrubbed environment,
  proxy-denied network defaults, timeout, redacted output, and byte caps.
- Schema version 3 persists guard previews, immutable approval decisions, and execution history,
  with explicit migrations from versions 1 and 2.
- The React dashboard now creates local audits and displays status, bounded usage, assessed
  protection coverage, action verdicts, missing proof, located evidence, an accessible graph
  inventory, guard previews, approval controls, and execution results.
- The dashboard now uses a responsive monochrome clay visual system with professional black
  typography, raised and inset surfaces, accessible non-color verdict treatments, and a clearer
  audit-first information hierarchy without AI-generator or chat styling.
- Frontend release hardening adds bounded API requests, focused and announced errors, operation-
  specific live status, semantic progress, keyboard skip navigation, input limits aligned with the
  API, and restrictive Vite development/preview security headers; the dependency audit is clean.
- Browser API calls explicitly omit credentials and referrers; backend CORS accepts only the exact
  configured frontend origin and `Content-Type`, with a regression test rejecting an untrusted
  origin.
- RemedyBench smoke version 0.1.0 contains five entirely synthetic incidents and 15 annotated
  actions spanning timeout, retry jitter, circuit breaker/fallback, queue bounds, feature flags,
  hard negatives, and all four verdict classes.
- A typed CLI evaluator runs extraction, invariant compilation, retrieval, citation, verdict, and
  guard checks against disposable repository copies and records commit/hash/configuration metadata.
- The saved measured result records 1.0 extraction F1, Evidence Recall@5, citation accuracy,
  verification macro-F1, guard runnable rate, and seeded-bad-state detection on this bounded smoke
  set; unsupported/document-only VERIFIED rates are zero and average model calls are 1.0.
- Network-free GitHub Actions, an updated quickstart, local-first deployment guidance, and a real
  dashboard capture complete the reproducible portfolio package.
- Release review restored the tracked RemedyBench JSON artifact referenced by the README, aligned
  the published latency figures to that artifact, and added a regression check for artifact
  presence, benchmark hash, aggregate metrics, and per-action predictions.
- Post-merge verification exposed CRLF/LF differences between Windows worktrees; benchmark hashing
  now canonicalizes line endings, with a cross-checkout regression test.
- GitHub CI exposed a further Windows/Linux filename-order difference. The versioned benchmark hash
  now sorts case-sensitive relative POSIX paths, and the saved result was regenerated from a clean
  commit with the portable hash.

## Files Changed

- `pyproject.toml`
- `backend/app/audit/**`, `backend/app/storage.py`
- `backend/app/guards/**`
- `backend/app/llm/mock.py`, `backend/app/main.py`, `backend/app/models.py`
- `backend/app/schemas.py`, `backend/app/services.py`, `backend/app/settings.py`
- `tests/unit/test_audit_core.py`, `tests/unit/test_audit_budget_gateway.py`
- `tests/unit/test_incident_budget.py`
- `tests/integration/test_audit_workflow.py`, `tests/integration/test_audit_persistence_integrity.py`
- `tests/api/test_api.py`
- `tests/api/test_app_lifecycle.py`, `tests/conftest.py`
- `tests/integration/test_guard_lifecycle.py`, `tests/unit/test_guard_runner.py`
- `frontend/src/App.tsx`, `frontend/src/styles.css`, `frontend/src/App.test.tsx`
- `.env.example`, `.gitignore`
- `docs/ARCHITECTURE.md`, `docs/DECISIONS.md`, `docs/TESTING.md`, `docs/STATUS.md`
- `backend/app/evaluation/**`, `remedybench/**`, `evals/results/remedybench-smoke.json`
- `.github/workflows/ci.yml`, `docs/DEPLOYMENT.md`, `docs/images/dashboard.png`, `README.md`

## Deferred Beyond the Five-Day MVP

- Evaluation HTTP endpoints and database-backed evaluation history; the implemented interface is
  the reproducible CLI plus saved JSON artifact.
- Expansion from the five-case smoke set to all 15 planned RemedyBench incidents.
- Authenticated multi-tenant or public-cloud repository execution.

## Verification

- `python -m pytest` — 104 passed.
- `ruff check .` and `ruff format --check .` — passed.
- `mypy backend` — passed.
- `npm run lint --prefix frontend` — passed.
- `npm test --prefix frontend` — 2 passed.
- `npm run build --prefix frontend` — passed.
- `python -m compileall -q backend tests` — passed.
- `python -m backend.app.evaluation.cli --benchmark remedybench --check` — passed.

## Limitations

- SQLite defaults to an in-memory database for local development/tests; set
  `REMEDYGRAPH_DATABASE_PATH` to retain audit state across process restarts.
- The mock provider makes no network calls. Each corrective-action extraction still consumes one
  persisted incident-level model attempt; deterministic audit compilation and verification consume
  no additional calls.
- The dashboard expects the local API at `http://localhost:8000/api/v1` unless
  `VITE_API_BASE_URL` is configured.
- MarkItDown is optional; scanned/image-only documents may be incomplete because plugins and
  LLM-powered OCR are disabled. Conversion failures are reported and indexing continues.
- Sentence-transformer embeddings require an explicitly installed optional dependency and a model
  already available locally. The deterministic fake encoder is used in default tests.
- The semantic vector snapshot remains process-local; durable vector-backend lifecycle management
  is outside the Day 3 bounded-audit scope.
- Test/protection verification is Python-first structural analysis. Audit runs do not execute the
  repository's own test suite; only separately approved application-templated guards can execute.
- Guard templates are deliberately narrow static repository assertions; promoting a preview into a
  maintained project test remains a separate human-reviewed operation.
- Process-level network isolation is platform-dependent; exact template validation prevents guard
  code from importing network or process modules, and proxy variables are denied by default.
- Published perfect scores are limited to the small deterministic smoke set and must not be
  interpreted as production generalization. The full 15-case plan remains future work.

## Next Task

Confirm the corrected GitHub CI run is green, then perform a final local demo and consider a release
tag. Future work can expand RemedyBench to 15 incidents and add persisted evaluation APIs without
weakening existing verdict, approval, path, budget, or execution constraints.

## Current Agent Allocation

- **Codex lane:** implementation, integration, deterministic tests, and shared contracts when acting as integration owner.
- **AutoClaw/GLM lane:** planning review and RemedyBench fixture content after contracts are frozen.
- **Gemini lane:** review recommendations and benchmark edge-case proposals; no direct repository writes unless assigned later.

## Blockers

None. Runtime model credentials, MarkItDown, and sentence-transformer model downloads are not
required by the default test suite.

## Handoff Format

Every completed task must update this file with:

- Summary of behavior delivered.
- Files changed.
- Commands/tests run and results.
- Known limitations or blockers.
- Exact next task.
