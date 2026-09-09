# RemedyGraph Testing and Evaluation Strategy

**Status:** Approved MVP strategy

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
- Markdown, Python, test, and configuration chunk metadata.
- BM25/vector merge, deduplication, and reranking.
- Python AST symbol and rollback-pattern detection.
- YAML, JSON, and TOML parsing.
- Numeric threshold and configuration predicates.
- Verdict aggregation constraints.
- Assessed protection coverage calculation.
- Guard syntax/path validation.
- Provider timeout, malformed JSON, and schema-retry behavior.

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
- Run persistence and reload.
- Graph nodes and edges reference valid records.

### API Contract Tests

- Request and response validation for every public endpoint.
- Stable verdict and run-status enums.
- Error shape for invalid paths, unsupported files, missing runs, provider failure, and execution timeout.
- OpenAPI snapshot after the API stabilizes.

### Frontend Tests

- Action table renders all verdicts and missing-proof states.
- Evidence drawer shows locations and deterministic results.
- Coverage label uses approved wording.
- Guard execution controls remain disabled before approval.
- Loading, failed, empty, and partial-complete states.
- Keyboard access for rows, drawers, dialogs, and graph alternatives.
- Production build succeeds.

### End-to-End Smoke Test

Using a bundled deterministic fixture:

1. Register demo repository.
2. Upload/select `INC-042`.
3. Start audit.
4. Wait for completion.
5. Assert expected verdicts.
6. Open contradictory alert evidence.
7. Generate a guard preview.
8. Approve and execute in the isolated runner.
9. Assert the seeded bad state is detected.

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
Evaluation smoke:          python -m evals.run --suite smoke
```

Update this section when package scripts are created. Do not retain commands that no longer work.

## 9. Phase Gates

### Day 1 Gate

- Schemas and extraction fixtures pass.
- API health and incident endpoints respond.
- Mock provider completes without network access.

### Day 2 Gate

- Indexer respects file/path restrictions.
- Gold evidence for sample incident appears in top five retrieval.
- Tool unit tests pass.

### Day 3 Gate

- End-to-end audit produces expected verdict classes.
- Deterministic failure cannot become verified.
- Audit and graph persist correctly.

### Day 4 Gate

- Guard approval boundary is enforced.
- Seeded bad and good state guard tests pass.
- Dashboard production build succeeds.

### Day 5 Gate

- Full clean test run passes.
- Benchmark results are saved and reproducible.
- README claims match artifacts.
- No secrets or runtime databases are tracked.

## 10. Definition of Tested

A change is tested only when the relevant automated checks pass, results are reported in the handoff, skipped checks are explained, and no unrelated failing checks are hidden.
