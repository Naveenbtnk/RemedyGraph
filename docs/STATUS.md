# RemedyGraph Implementation Status

**Last updated:** 2026-09-09
**Current phase:** Phase 2 — Day 2 indexing and investigation
**Overall status:** Day 2 complete; ready for the Day 3 verification workflow

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
- Hybrid candidate merge, chunk-ID deduplication, deterministic reranking, top-k selection, and
  structured retrieval logs with redacted queries, ranks, scores, IDs, and timing.
- Read-only `search_code`, Python `get_symbol`, JSON/YAML/TOML `inspect_config`, `find_tests`, and
  bounded fixed-argument `find_git_changes` tools.
- Safety, conversion, redaction, source-location, retrieval, AST/config/Git tool, and gold-evidence
  Recall@5 automated coverage.

## Files Changed

- `pyproject.toml`, `.env.example`
- `backend/app/settings.py`
- `backend/app/rag/**`, `backend/app/tools/**`
- `tests/unit/test_repository_ingestion.py`
- `tests/unit/test_chunking_and_retrieval.py`
- `tests/unit/test_investigation_tools.py`
- `tests/fixtures/gold_retrieval/**`
- `docs/ARCHITECTURE.md`, `docs/DECISIONS.md`, `docs/TESTING.md`, `docs/STATUS.md`

## Not Started

- LangGraph audit workflow.
- Deterministic checks and verdict aggregation.
- SQLite audit/workflow persistence and evidence graph assembly.
- Guard generation/execution.
- RemedyBench cases and evaluation.
- CI and deployment/demo artifacts.

## Verification

- `python -m pytest` — 37 passed.
- `ruff check .` and `ruff format --check .` — passed.
- `mypy backend` — passed.
- `npm run lint --prefix frontend` — passed.
- `npm test --prefix frontend` — 1 passed.
- `npm run build --prefix frontend` — passed.
- `python -m compileall -q backend tests` — passed.

## Limitations

- Day 1 application records still use an in-memory store; SQLite audit persistence is Day 3 scope.
- The mock provider supports bounded action extraction only and makes no network calls.
- The frontend is a static dashboard shell; it is not connected to the API yet.
- MarkItDown is optional; scanned/image-only documents may be incomplete because plugins and
  LLM-powered OCR are disabled. Conversion failures are reported and indexing continues.
- Sentence-transformer embeddings require an explicitly installed optional dependency and a model
  already available locally. The deterministic fake encoder is used in default tests.
- The Day 2 semantic vector index is process-local; persisted audit/index lifecycle management is
  deferred to Day 3.
- Invariant compilation, deterministic checks, verdicts, guards, and evaluation remain unimplemented.

## Next Task

Implement the Day 3 bounded LangGraph audit and deterministic verification workflow: compile typed
invariants; persist projects, incidents, index metadata, audit runs, evidence, checks, verdicts, and
the evidence graph in SQLite; enforce six model calls per incident and three investigation rounds
per invariant; add allowlisted static/config/test checks; require evidence citations or explicit
missing-proof reasons; prevent failed deterministic checks or Git/document-only support from
producing `VERIFIED`; produce all four verdict classes; expose the run/evidence API surface; and add
unit/integration/API tests for contradictory evidence, persistence/reload, graph references, and
bounded failure paths. Do not implement Day 4 guard writing/execution or dashboard integration.

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
