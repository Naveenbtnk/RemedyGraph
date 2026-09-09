# RemedyGraph Architecture Decision Log

Accepted decisions are authoritative until superseded by a later entry. Add new entries; do not rewrite historical reasoning.

## ADR-001: Local-First MVP

**Status:** Accepted
**Decision:** Run indexing, embeddings, retrieval, parsing, checks, storage, and test execution locally. Use remote models only for semantic tasks.
**Reason:** Keeps additional cost low, protects repository data, reduces model calls, and supports deterministic evaluation.
**Consequence:** Initial setup may download a local embedding model and performance depends on the development machine.

## ADR-002: Modular Monolith

**Status:** Accepted
**Decision:** Use one FastAPI backend process with internal modules and a separate React frontend.
**Reason:** Five days is insufficient justification for distributed services.
**Consequence:** Module boundaries must be enforced in code rather than by networks.

## ADR-003: LangGraph Nodes, Not Agent Services

**Status:** Accepted
**Decision:** Represent agents as typed workflow nodes in one bounded state machine.
**Reason:** Explicit state and loop budgets are easier to test and observe.
**Consequence:** Each node must have a narrow input/output contract.

## ADR-004: Deterministic Facts Override Semantic Judgment

**Status:** Accepted
**Decision:** Models interpret requirements and evidence, while deterministic code evaluates concrete values and executions. A failed deterministic check cannot become verified.
**Reason:** The project’s credibility depends on evidence rather than model opinion.
**Consequence:** New invariant types require corresponding check implementations or manual-review status.

## ADR-005: Hybrid Local Retrieval

**Status:** Accepted
**Decision:** Combine SQLite FTS5/BM25 with local sentence-transformer embeddings and deterministic reranking.
**Reason:** Code contains exact identifiers while postmortems use semantic language.
**Consequence:** Retrieval evaluation must measure both exact and semantic cases.

## ADR-006: SQLite as MVP Storage

**Status:** Accepted
**Decision:** Use SQLite for product records, workflow state, and lexical indexing.
**Reason:** It is free, local, portable, and sufficient for a single-user demo.
**Consequence:** Multi-user scaling and high write concurrency are deferred.

## ADR-007: Provider Abstraction

**Status:** Accepted
**Decision:** Runtime code depends on a structured-generation provider interface rather than one model vendor.
**Reason:** Available GLM, Gemini, OpenRouter-compatible, or future providers may have changing limits.
**Consequence:** Provider-specific features must be normalized and schema validation remains application-owned.

## ADR-008: Four Verdicts

**Status:** Accepted
**Decision:** Use `VERIFIED`, `PARTIAL`, `MISSING`, and `UNVERIFIABLE`.
**Reason:** Unknown context must not be collapsed into missing, and partial implementation must remain visible.
**Consequence:** Evaluation requires balanced examples and explicit class definitions.

## ADR-009: Human Approval for Generated Guards

**Status:** Accepted
**Decision:** Guard generation produces a preview only. Writing and execution require explicit approval.
**Reason:** Generated code and tests may be incorrect or unsafe.
**Consequence:** Fully autonomous remediation is outside the MVP.

## ADR-010: Git Evidence Is Supporting Only

**Status:** Accepted
**Decision:** Commit messages and diffs can guide investigation but cannot alone prove that remediation is effective.
**Reason:** Commit descriptions can be wrong, incomplete, or stale.
**Consequence:** Verification must seek implementation, configuration, tests, or execution evidence.

## ADR-011: Python-First Analysis

**Status:** Accepted
**Decision:** Provide high-quality Python AST/config/test support first; treat other languages as text retrieval during the MVP.
**Reason:** Focus is necessary for a reliable five-day implementation.
**Consequence:** Language support claims must be precise.

## ADR-012: Worktree and Ownership Isolation

**Status:** Accepted
**Decision:** Codex and AutoClaw work in separate branches/worktrees with disjoint write paths defined in `coordination/OWNERSHIP.md`.
**Reason:** Physical separation prevents working-copy overwrites; ownership prevents merge-time duplication.
**Consequence:** Shared-file changes go through the integration owner.

## ADR-013: Constrained MarkItDown Document Adapter

**Status:** Accepted
**Decision:** Keep Markdown and UTF-8 plain text as the native ingestion path. Offer Microsoft
MarkItDown only through a `documents` optional dependency group for local PDF, DOCX, and PPTX
conversion. Call the local-file conversion API after workspace/repository containment checks, keep
plugins disabled, and provide no remote URL, cloud-service, LLM client, or LLM-powered OCR path.
ZIP, YouTube, audio, Excel, and other MarkItDown formats are outside the MVP.
**Reason:** Postmortems and supporting evidence are often office documents, but MarkItDown's broad
conversion surface and optional integrations exceed the local-first security boundary. A narrow
adapter expands useful input coverage without making document conversion a network or tool-plugin
execution path.
**Consequence:** Default installs and tests do not install MarkItDown. Users who need PDF/DOCX/PPTX
must install `remedygraph[documents]`. Converted records preserve source filename, MIME type, raw
SHA-256 hash, converter name/version, and redacted normalized Markdown. Scanned/image-only content
may be incomplete because LLM-powered OCR is intentionally disabled; conversion failures remain
explicit ingestion failures rather than silently empty documents.

## Decision Template

```markdown
## ADR-NNN: Title

**Status:** Proposed | Accepted | Superseded
**Decision:** What was chosen.
**Reason:** Why it was chosen.
**Consequence:** Tradeoffs and follow-up obligations.
**Supersedes:** Optional prior ADR.
```
