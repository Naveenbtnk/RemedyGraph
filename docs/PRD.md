# RemedyGraph Product Requirements Document

**Status:** Approved for MVP implementation
**Version:** 1.0
**Target build window:** Five focused development days

## 1. Product Summary

RemedyGraph audits whether corrective actions from software incident postmortems are genuinely implemented and protected against regression. It extracts actions, compiles measurable invariants, investigates a repository, runs deterministic checks, classifies each action, and proposes CI guards for missing protection.

The output is an engineering audit with traceable evidence, not a conversational answer.

## 2. Problem

Postmortems often end with corrective actions such as “bound retries,” “reduce the timeout,” or “add a regression test.” Those statements may become tickets and later be marked complete, but teams frequently lack an executable connection between the original incident lesson and the current repository.

This creates three risks:

1. An action is marked complete while only part of it was implemented.
2. A fix exists but lacks a regression test or policy guard.
3. A later change silently removes the protection.

Existing document chatbots can summarize the postmortem, and coding agents can generate code, but neither necessarily produces a constrained, evidence-backed remediation audit.

## 3. Target Users

### Primary

- Site reliability engineers reviewing postmortem actions.
- Backend engineers validating fixes before closing incident tasks.
- Engineering managers checking remediation coverage.

### Secondary

- Security and platform engineers auditing reliability controls.
- Interviewers and recruiters evaluating the technical portfolio project.

## 4. Product Promise

Given a postmortem and a repository, RemedyGraph will answer:

- What atomic corrective actions were promised?
- What measurable behavior would prove each action?
- What code, configuration, test, document, Git, or execution evidence exists?
- Which actions are verified, partial, missing, or unverifiable?
- What minimal CI guard could prevent the same gap from returning?

## 5. Goals

1. Extract atomic, structured corrective actions from unstructured postmortems.
2. Convert actions into explicit, checkable engineering invariants.
3. Retrieve relevant evidence with exact file and line locations.
4. Apply deterministic checks for concrete facts and thresholds.
5. Produce conservative, explainable verdicts.
6. Generate reviewable tests or policy guards for incomplete actions.
7. Measure quality and cost on RemedyBench.
8. Run locally without requiring paid infrastructure.

## 6. Non-Goals

- Live incident detection, alert triage, or root-cause analysis.
- Automatic production remediation.
- Automatic commits, pull requests, or merges.
- Enterprise authentication or multi-tenancy.
- Real Jira, Slack, PagerDuty, or observability integrations.
- Complete language coverage.
- Formal verification or a guarantee of operational reliability.

## 7. Core User Journey

1. User selects a local repository inside an allowed workspace.
2. User uploads or selects a Markdown/plain-text postmortem.
3. RemedyGraph extracts corrective actions and displays them for audit.
4. RemedyGraph compiles invariants and indexes relevant repository content.
5. The investigator gathers evidence and invokes deterministic tools.
6. The verifier assigns a verdict with evidence citations and missing proofs.
7. The dashboard displays assessed protection coverage and an evidence graph.
8. For partial or missing actions, the user previews suggested CI guards.
9. The user explicitly approves a selected guard for isolated execution.
10. RemedyGraph stores the execution result in the audit.

## 8. Functional Requirements

### FR-1: Project Registration

- Accept a local repository path.
- Resolve and validate the absolute path against `WORKSPACE_ROOT`.
- Reject paths outside the allowed workspace.
- Store project metadata without storing secrets.

### FR-2: Postmortem Ingestion

- Accept Markdown and plain text.
- Preserve the source text and a content hash.
- Extract title, summary, affected services, and action items.
- Split compound actions while preserving thresholds, units, and scope.

### FR-3: Invariant Compilation

- Convert each action into one or more atomic invariants.
- Select a supported check type.
- Mark ambiguous/manual requirements for manual review.
- Retrieve policy/runbook context when terms such as “standard” are undefined.

### FR-4: Repository Indexing

- Index supported source, configuration, test, and documentation files.
- Ignore binaries, build output, dependencies, secret files, and oversized files.
- Preserve path, symbol, line range, type, language, content hash, and retrieval IDs.

### FR-5: Evidence Investigation

- Support hybrid retrieval and exact code/config/test search.
- Support Python AST analysis, typed configuration parsing, read-only Git history, and allowlisted test execution.
- Limit each action to three investigation rounds by default.
- Log tool inputs, bounded outputs, durations, and failures.

### FR-6: Verification

- Return `VERIFIED`, `PARTIAL`, `MISSING`, or `UNVERIFIABLE`.
- Cite evidence IDs and concrete locations.
- Explain missing or contradictory proof.
- Prevent semantic confidence from overriding failed deterministic checks.

### FR-7: CI Guard Generation

- Generate only for partial or missing protections.
- Prefer deterministic pytest, static, or configuration guards.
- Show intent, assumptions, assertions, target paths, and code preview.
- Require explicit approval before writing or execution.
- Execute through a fixed allowlist with timeout and output limits.

### FR-8: Dashboard

- Display incident summary, run status, assessed protection coverage, and action verdicts.
- Provide evidence details and graph visualization.
- Provide guard preview and execution results.
- Avoid a chat-first interface.

### FR-9: Evaluation

- Evaluate action extraction, retrieval, verdicts, and generated guards.
- Store model, prompt version, configuration, dataset version, and raw metrics.
- Never display placeholder values as measured results.

## 9. Verdict Definitions

| Verdict | Required interpretation |
|---|---|
| `VERIFIED` | Required deterministic checks pass and adequate regression proof exists |
| `PARTIAL` | Some required implementation/protection exists, but at least one proof is absent or contradictory |
| `MISSING` | No credible implementation exists or a core deterministic check fails |
| `UNVERIFIABLE` | Required runtime/context is unavailable or the action is inherently manual |

## 10. MVP Acceptance Criteria

- One command starts the local development stack after dependencies are installed.
- A bundled incident and demo repository complete an end-to-end audit.
- At least one action demonstrates each primary verdict: verified, partial, and missing.
- Every verdict contains evidence or a missing-evidence explanation.
- Numeric/configuration checks are deterministic.
- A generated guard can be previewed and executed only after approval.
- A RemedyBench smoke set produces reproducible evaluation output.
- Backend tests and frontend build pass in CI.
- No API keys, tokens, secrets, fabricated metrics, or generated databases are committed.

## 11. Success Metrics

Targets are goals, not claims. Actual values must come from saved evaluations.

- Action extraction F1 target: at least 0.85.
- Evidence Recall@5 target: at least 0.80.
- Verification macro-F1 target: at least 0.75.
- Evidence citation accuracy target: at least 0.90.
- Runnable guard rate target: at least 0.75.
- Average model calls target: no more than six per incident.
- Demo incident completion target: under two minutes on a typical development laptop, excluding first-time model download.

## 12. Five-Day Scope

| Day | Deliverable |
|---|---|
| 1 | Backend/frontend skeleton, schemas, provider interface, postmortem extraction |
| 2 | Safe repository indexing, hybrid retrieval, investigation tools |
| 3 | Agent workflow, deterministic checks, verdicts, audit persistence |
| 4 | Guard preview/execution and dashboard vertical slice |
| 5 | RemedyBench, evaluation, CI, documentation, screenshots, demo |

## 13. Release Criteria

The MVP is ready to demonstrate when a new user can clone the repository, follow the README, run the bundled sample, inspect evidence-backed verdicts, preview and approve a guard, and reproduce the published evaluation table.
