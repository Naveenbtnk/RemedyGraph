# RemedyGraph

RemedyGraph is an agentic RAG reliability auditor that checks whether corrective actions promised in incident postmortems are actually implemented and protected against regression.

It converts postmortem prose into measurable invariants, investigates source code, configuration, tests, documentation, and Git history, applies deterministic checks, and produces evidence-backed verdicts plus reviewable CI guards.

## Why It Is Different

RemedyGraph does not answer questions about documents. It closes an engineering loop:

```text
Postmortem
  -> corrective action
  -> measurable invariant
  -> repository evidence
  -> VERIFIED / PARTIAL / MISSING / UNVERIFIABLE
  -> executable regression guard
```

The model chooses where to investigate and interprets ambiguous language. Deterministic programs decide whether concrete evidence passes.

## Current Status

Planning foundation complete. Implementation has not started. See `docs/STATUS.md` for the current handoff and next task.

## Documentation

- `AGENTS.md` — instructions for Codex, AutoClaw, and human contributors.
- `docs/PRD.md` — product requirements and MVP acceptance criteria.
- `docs/DESIGN.md` — product flow and dashboard design.
- `docs/ARCHITECTURE.md` — technical architecture and contracts.
- `docs/DECISIONS.md` — accepted technical decisions.
- `docs/TESTING.md` — test and evaluation strategy.
- `docs/STATUS.md` — current implementation state.
- `coordination/OWNERSHIP.md` — multi-agent file ownership.
- `coordination/CHANGE_REQUESTS.md` — cross-owner change requests.

## Planned Stack

- FastAPI, Pydantic, SQLite, and LangGraph.
- SQLite FTS5/BM25 plus local sentence-transformer embeddings.
- Python AST and typed configuration inspection.
- React, Vite, TypeScript, and React Flow.
- pytest and GitHub Actions.

## Safety Boundary

RemedyGraph is an audit assistant, not proof that a system is incident-free. Generated guards are previews until a human approves writing and execution.

## Repository

https://github.com/bt1nk/RemedyGraph
