# RemedyGraph Technical Architecture

**Status:** Approved MVP architecture
**Style:** Local-first modular monolith

## 1. Architectural Drivers

- Evidence must be traceable to exact repository locations.
- Concrete facts must be decided deterministically.
- Model usage must be bounded and provider-independent.
- Repository investigation must be read-only by default.
- Generated code must remain behind a human approval boundary.
- The MVP must be buildable and demonstrable in five days.

## 2. System Context

```text
User
  |
  v
React/Vite dashboard
  |
  v
FastAPI modular monolith
  |-- Audit workflow (LangGraph)
  |-- Deterministic investigation tools
  |-- Hybrid retrieval
  |-- Guard preview/execution service
  |-- Evaluation service
  |
  +--> Local repository (read-only during audit)
  +--> SQLite + local vector index
  +--> Configurable LLM provider
  +--> Isolated/allowlisted test subprocess
```

## 3. Component Responsibilities

### Frontend

- Start and monitor audits.
- Render action verdicts and evidence.
- Visualize the evidence graph.
- Preview guard diffs and capture explicit approval.
- Display measured evaluation results.

### API Layer

- Validate requests and serialize responses.
- Enforce project/run/guard authorization state for the local user.
- Delegate behavior to services; contain no verification logic.

### Audit Service

- Create and persist audit runs.
- Initialize workflow state and budgets.
- Coordinate indexing, investigation, verification, and final audit assembly.

### LangGraph Workflow

- Provides explicit stages, typed state, bounded loops, failure handling, and resumable run metadata.
- Logical nodes are not separate network services.

### Deterministic Tool Layer

- Searches code and tests.
- Parses Python AST and typed configuration.
- Reads relevant Git history.
- Executes only fixed, allowlisted checks/tests.
- Produces typed evidence and check results.

### Retrieval Layer

- Ingests source, configuration, tests, documentation, and bounded Git context.
- Combines lexical and semantic retrieval.
- Preserves location and scoring metadata.

### LLM Provider Layer

- Exposes one structured-generation interface.
- Supports an OpenAI-compatible endpoint, Gemini API adapter when available, and deterministic mock provider.
- Enforces timeouts, retries, call budgets, schema validation, and logging without secret values.

## 4. Workflow

```text
START
 -> parse_input
 -> extract_actions
 -> retrieve_policy_context
 -> compile_invariants
 -> index_repository
 -> investigate_next_invariant
      -> plan_queries
      -> hybrid_retrieve
      -> call_read_only_tools
      -> execute_selected_allowlisted_check
      -> repeat while evidence gap exists and round budget remains
 -> verify_invariant
 -> repeat for remaining invariants
 -> generate_guard_specs_for_gaps
 -> build_graph
 -> calculate_assessed_coverage
 -> persist_audit
 -> END
```

Default bounds:

- Maximum six model calls per incident.
- Maximum three investigation rounds per invariant.
- Maximum eight final retrieved chunks per invariant.
- Per-file size and total-index size limits.
- Test execution timeout and output cap.

## 5. Agent Nodes

### Action Extractor

Input: postmortem text.
Output: atomic `ActionItem` records.
Constraint: may not invent implementation evidence.

### Invariant Compiler

Input: action plus policy/runbook context.
Output: one or more `Invariant` records with check strategy and expected values.
Constraint: ambiguous requirements become `manual_review`.

### Evidence Investigator

Input: invariant, repository summary, prior evidence, remaining budget.
Output: bounded typed tool calls and evidence.
Constraint: tools are allowlisted and read-only.

### Verification Agent

Input: invariant, evidence, deterministic check results.
Output: structured verdict and missing proofs.
Constraint: cannot override failed deterministic checks.

### Guard Agent

Input: partial/missing invariant and relevant code/test context.
Output: `GuardSpec` and optional code preview.
Constraint: no repository write or execution without approval.

## 6. Retrieval Architecture

### Supported Corpus

- Markdown and text documentation.
- Local PDF, DOCX, and PPTX through the optional constrained MarkItDown adapter.
- Python source for symbol-aware indexing.
- YAML, JSON, TOML, and dotenv-like configuration with secret redaction.
- Test files.
- Bounded Git messages/diffs as supporting evidence.

### Chunking

- Prose: heading-aware sections and paragraphs.
- Python: module, class, and function chunks from AST line ranges.
- Config: path/key-oriented records.
- Tests: test function/class plus fixture references.

Every chunk stores path, line range, document type, language, symbol, content hash, and index version.

### Ingestion and Conversion Boundary

- Canonicalize `WORKSPACE_ROOT`, the selected repository, and each file before reading.
- Do not follow symlinks; reject any resolved file outside the selected repository or workspace.
- Apply configured per-file, total-byte, and file-count limits before ingestion.
- Ignore Git internals, dependency/build directories, secret files, unsupported formats, and binary
  content.
- Decode native Markdown, UTF-8 plain text, source, and configuration files without a model.
- Invoke MarkItDown only for local PDF, DOCX, and PPTX via `convert_local`, with plugins disabled and
  without remote, cloud, LLM-client, or OCR configuration. The dependency is optional.
- Preserve raw-content SHA-256 and converter provenance; redact secret-like content before indexing.
- Record conversion failures by safe relative source path without aborting the remaining index.

### Hybrid Retrieval

1. SQLite FTS5/BM25 retrieves lexical candidates.
2. A local sentence-transformer retrieves semantic candidates.
3. Candidates are merged and deduplicated.
4. Deterministic reranking boosts exact identifiers, path role, symbols, invariant terms, and tests.
5. Top eight chunks form the model context.

The semantic interface has a deterministic fake encoder for tests and an optional
sentence-transformers adapter. The adapter defaults to local-files-only model loading. The Day 2
vector index is process-local; SQLite FTS5 stores the lexical corpus and full chunk metadata.

Each retrieval records the redacted query, returned chunk IDs, lexical/semantic/final ranks and
scores, and elapsed time.

Ground-truth benchmark labels must never enter the searchable corpus.

## 7. Deterministic Tools

| Tool | Purpose | Mutation |
|---|---|---|
| `search_code` | Literal/regex search with line excerpts | None |
| `get_symbol` | AST/Tree-sitter symbol extraction | None |
| `inspect_config` | Typed configuration lookup with redaction | None |
| `find_tests` | Locate relevant test names/assertions | None |
| `find_git_changes` | Read bounded commit/diff context | None |
| `run_static_check` | Evaluate known AST/config predicates | None |
| `run_test` | Execute selected allowlisted test | Test-side effects isolated |
| `generate_guard` | Produce guard specification/preview | None until approval |

Model output can select a tool and provide typed arguments, but never a command string.

## 8. Domain Model

Core entities:

- `Project`: allowed repository root and index metadata.
- `Incident`: source postmortem and metadata.
- `ActionItem`: atomic promised remediation.
- `Invariant`: measurable interpretation of an action.
- `Evidence`: located supporting, contradictory, absent, or execution evidence.
- `CheckResult`: deterministic expected/actual result.
- `VerificationResult`: verdict, confidence, rationale, evidence IDs, missing proofs.
- `GuardSpec`: proposed test/static/config/manual protection.
- `AuditRun`: workflow state, budgets, versions, timings, and final summary.
- `EvaluationRun`: benchmark version, model/prompt versions, and metrics.

Identifiers must be stable within an audit and opaque to the frontend.

## 9. API Surface

| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/health` | Service/version health |
| `POST` | `/api/v1/projects` | Register allowed local project |
| `POST` | `/api/v1/incidents` | Store postmortem |
| `POST` | `/api/v1/runs` | Start audit |
| `GET` | `/api/v1/runs/{run_id}` | Run status and summary |
| `GET` | `/api/v1/runs/{run_id}/actions` | Action verdicts |
| `GET` | `/api/v1/runs/{run_id}/evidence` | Evidence records |
| `GET` | `/api/v1/runs/{run_id}/graph` | Evidence graph |
| `POST` | `/api/v1/runs/{run_id}/guards/preview` | Create guard previews |
| `POST` | `/api/v1/runs/{run_id}/guards/{guard_id}/approve` | Record approval |
| `POST` | `/api/v1/runs/{run_id}/guards/{guard_id}/execute` | Execute approved guard |
| `POST` | `/api/v1/evaluations` | Run benchmark evaluation |
| `GET` | `/api/v1/evaluations/{evaluation_id}` | Evaluation status/results |

OpenAPI output becomes the frontend/backend contract once the API skeleton exists.

## 10. Storage

SQLite stores application records, workflow state, FTS chunks, evidence metadata, approvals, and evaluation summaries. Large generated logs/artifacts are stored on disk with database references.

Do not commit runtime databases, indexes, uploaded postmortems, generated guards, or evaluation artifacts unless they are curated fixtures.

## 11. Verdict Engine

Deterministic checks run before semantic aggregation.

```text
all required checks pass and regression proof exists -> VERIFIED
some requirements pass, others absent/contradictory -> PARTIAL
core implementation absent or core check fails       -> MISSING
required context/runtime unavailable                  -> UNVERIFIABLE
```

Confidence communicates uncertainty within the selected verdict. It cannot change verdict constraints.

Assessed protection coverage:

```text
VERIFIED = 1.0
PARTIAL = 0.5
MISSING = 0.0
UNVERIFIABLE = 0.0
coverage = weighted verdict value / assessed weight * 100
```

## 12. Guard Execution Boundary

1. Guard agent emits a typed `GuardSpec` and preview.
2. Backend validates target path, syntax, imports, and allowed guard type.
3. UI obtains explicit approval.
4. Backend writes only under a generated/temporary guard directory.
5. Runner selects a predefined command, scrubs environment, disables network when possible, applies timeout/output caps, and records results.
6. Promoting a guard into project tests remains a separate human-reviewed operation.

## 13. Security

- Canonicalize paths and enforce workspace containment.
- Ignore symlinks that escape the workspace.
- Redact key/token/password-like values before storage or display.
- Keep optional document conversion local-only and disable MarkItDown plugins and LLM/cloud paths.
- Treat retrieved repository content as untrusted.
- Keep prompts structurally separated from retrieved content.
- Never evaluate arbitrary model-generated shell.
- Use least-privilege subprocess environment and temporary directories.
- Log security-relevant denials without secret values.

## 14. Observability

Each run records:

- Stage transitions and duration.
- Provider/model and prompt versions.
- Model call counts and token information when available.
- Retrieval queries, chunk IDs, ranks, and scores.
- Tool names, bounded arguments, status, and duration.
- Deterministic check results.
- Guard approval and execution events.

## 15. Planned Repository Layout

```text
backend/
  api/ agents/ graph/ llm/ rag/ services/ tools/
frontend/
  src/components/ src/pages/ src/lib/
contracts/
remedybench/
  incidents/ repositories/ ground_truth/
evals/
tests/
  unit/ integration/ fixtures/
docs/
coordination/
.github/workflows/
```

## 16. Deployment

The default deployment is local development. Docker Compose is optional and should not block the native setup. The portfolio demo may deploy only the frontend/API if repository-analysis permissions can be constrained safely; otherwise provide a recorded demo and local quickstart.
