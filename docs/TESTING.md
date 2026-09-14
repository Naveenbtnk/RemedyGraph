# RemedyGraph Testing and Evaluation Strategy

**Status:** Active local-release strategy

## 1. Quality Goal

Tests must demonstrate that RemedyGraph is conservative, evidence-grounded, safe to run locally, and reproducible. Model fluency is not a substitute for measured correctness.

## 2. Test Layers

### Unit Tests

Fast, deterministic, network-free tests for:

- Postmortem parsing and compound-action splitting.
- Schema validation and stable IDs.
- Invariant check-type selection fixtures.
- Workspace path containment and symlink escape rejection.
- File allow/deny rules and size limits.
- Secret redaction.
- Native text metadata, constrained MarkItDown invocation, optional dependency absence, and
  explicit conversion failures.
- Markdown, Python, test, and configuration chunk metadata.
- BM25/vector merge, deduplication, and reranking.
- Retrieval logging with redacted queries, ranks, scores, IDs, and timing.
- Deterministic fake embeddings and local-files-only sentence-transformer configuration without
  downloading a model.
- Python AST symbol and rollback-pattern detection.
- YAML, JSON, and TOML parsing.
- Numeric threshold and configuration predicates.
- Python AST call/wiring proof that rejects declaration-, identifier-, comment-, and string-only
  matches; enabled structured configuration is handled separately.
- Nontrivial regression structure that rejects `assert True`, constant comparisons, and tests that
  do not exercise relevant imported implementation symbols or calls.
- Bounded supporting-only literal-pattern scans and rejection of arbitrary command parameters.
- Verdict aggregation constraints.
- Assessed protection coverage calculation.
- Guard syntax/path validation.
- Exact application-template and approved-digest validation; arbitrary imports, modified artifacts,
  traversal, and symlink targets are rejected.
- Provider timeout, malformed JSON, and schema-retry behavior.
- Incident-lifecycle budget reservation: six extraction attempts allowed, seventh rejected, failed
  extraction charged, stable-incident resubmission unable to reset usage, and synchronized
  independent connections permitting exactly one consumer of the final slot.
- Audit-run provider gateway success/failure accounting against the same incident counter.
- Competing incident services invoke the provider only after winning the atomic reservation, and
  SQLite lock exhaustion returns a typed service-unavailable API response.

### Integration Tests

Tests combining real internal components with a deterministic model stub:

- Postmortem to extracted actions and invariants.
- Repository ingestion to located evidence.
- Verified, partial, missing, and unverifiable audit paths.
- Contradictory config versus documentation.
- Git-only evidence cannot produce verified.
- Generated guard catches a seeded bad state.
- Generated guard passes the corresponding good state.
- Approval is required before guard writing/execution.
- Preview and rejection leave the repository unchanged; approval writes only to the generated path.
- Execution output is redacted and bounded, timeout is typed, and the command is application-owned.
- Run persistence and reload.
- Complete-snapshot shrink/replacement and rollback after a mid-transaction database failure.
- Schema-version creation, version-1 migration, reopen, and unsupported-version rejection.
- Cross-project/run/action/invariant rejection for all persisted audit records.
- Graph nodes have correct record types and same-run ownership; duplicate, unknown, cross-run, and
  relationship-mismatched nodes/edges are rejected.

### API Contract Tests

- Request and response validation for every public endpoint.
- Stable verdict and run-status enums.
- Error shape for invalid paths, unsupported files, missing runs, provider failure, and execution timeout.
- Audit start/status/budget, verdict, evidence, and graph responses; unknown IDs,
  project/incident mismatch, typed invalid-state failure, and typed budget exhaustion.
- OpenAPI snapshot after the API stabilizes.

### Frontend Tests

- Audit setup, summary, and guard controls render with accessible labels.
- An action card shows missing proof beside located evidence.
- An unapproved guard preview cannot execute.
- Status formatting and guard execution eligibility are deterministic.
- The production build succeeds.

### Manual Demo Smoke Test

Using the bundled `I04` incident and repository:

1. Register the repository and paste the incident text.
2. Start the audit and confirm the expected missing, partial, and verified verdicts.
3. Expand the circuit-breaker and fallback actions to inspect their evidence gaps.
4. Generate a guard preview, approve it, and execute it through the bounded runner.
5. Compare the displayed result with the saved RemedyBench report.

## 3. RemedyBench

### Initial Dataset

- Target 15 incidents and 40–60 atomic actions.
- Balance verified, partial, and missing labels; include unverifiable cases separately.
- Keep ground truth outside the searchable repository corpus.
- Version incident text, fixture repository, labels, and evaluator together.

### Fault Categories

- Missing transaction rollback.
- Incorrect timeout.
- Missing retry jitter.
- Unbounded queue.
- Missing circuit breaker.
- Missing rate limit.
- Missing health check.
- Missing or misconfigured alert.
- Unsafe fallback.
- Missing database index.
- Missing regression test.
- Incorrect feature-flag default.

### Ground-Truth Requirements

Every action annotation includes:

- Gold action boundary.
- Gold invariant/check type.
- Gold verdict.
- Gold evidence paths and line locations when applicable.
- Expected deterministic values.
- Required missing proof.
- Guard expectation: automatable or manual.

## 4. Evaluation Metrics

| Metric | Definition |
|---|---|
| Action extraction precision/recall/F1 | Match extracted atomic actions to annotations |
| Invariant validity rate | Rubric-based validity of generated invariants |
| Evidence Recall@5 | Gold evidence appears in top five results |
| Citation accuracy | Cited evidence actually supports the associated claim |
| Verification accuracy | Exact verdict match |
| Verification macro-F1 | Balanced verdict-class performance |
| False-positive rate | Correct remediation incorrectly flagged |
| Guard runnable rate | Generated guards parse and execute |
| Guard detection rate | Runnable guards detect seeded bad state |
| Model calls per incident | Cost-efficiency measure |
| P50/P95 duration | Operational performance |

## 5. Reproducibility

Every evaluation result stores:

- Repository commit.
- RemedyBench version/hash.
- Benchmark hash canonicalizes text-fixture CRLF/LF line endings and sorts case-sensitive relative
  POSIX paths across checkouts.
- Provider and exact model name.
- Prompt version.
- Retrieval/check configuration.
- Random seed where applicable.
- Start/end timestamps.
- Raw per-case predictions and aggregate metrics.

Do not place target values in the README results table. Publish only outputs from a saved evaluation artifact.

## 6. Model Testing Policy

- Unit and normal CI tests use deterministic stubs, never paid or rate-limited APIs.
- Provider contract tests use recorded/redacted fixtures where permitted.
- Live model tests are opt-in and excluded from default CI.
- All model output passes through schema validation.
- Tests must cover malformed output, timeout, retry exhaustion, and provider unavailability.

## 7. Security Tests

- Reject `..` path traversal and absolute paths outside the workspace.
- Reject symlink escape.
- Ignore `.env`, keys, binaries, dependency trees, Git objects, and oversized files.
- Reject remote/escaped document paths and keep MarkItDown plugins, cloud services, and LLM OCR
  disabled.
- Redact common secret patterns before persistence and display.
- Confirm retrieved prompt-injection text cannot select arbitrary tools/commands.
- Confirm runner uses an allowlisted command, scrubbed environment, timeout, and output cap.
- Confirm unapproved guards cannot be written or executed.
- Confirm generated guard paths remain inside the designated directory.

## 8. Expected Commands

These commands become authoritative after scaffolding confirms the selected tools:

```text
Backend unit/integration: pytest
Backend lint/format:       ruff check . / ruff format --check .
Backend type check:        mypy backend
Frontend lint:             npm run lint --prefix frontend
Frontend tests:            npm test --prefix frontend
Frontend build:            npm run build --prefix frontend
Evaluation smoke:          python -m backend.app.evaluation.cli --benchmark remedybench --check
```

Update this section when package scripts are created. Do not retain commands that no longer work.

## 9. Release Gate

- Backend lint, formatting, type checks, compilation, and the complete pytest suite pass.
- Frontend type/lint check, component tests, and production build pass.
- The saved RemedyBench artifact matches a fresh deterministic run across Windows and Linux
  checkout conventions.
- A failed deterministic check cannot become `VERIFIED`; trivial or unrelated tests do not count
  as regression protection.
- Incident model-attempt and per-invariant investigation budgets remain enforced across concurrent
  SQLite connections.
- Audit snapshots, evidence graphs, and guard approvals retain their cross-record integrity.
- `git diff --check`, secret review, and a tracked runtime-database scan pass.

## 10. Definition of Tested

A change is tested only when the relevant automated checks pass, results are reported in the handoff, skipped checks are explained, and no unrelated failing checks are hidden.
