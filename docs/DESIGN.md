# RemedyGraph Product and Interaction Design

**Status:** Approved MVP design

## 1. Design Objective

Make an agentic system feel like a reliability engineering product. The interface should emphasize claims, evidence, checks, and protection gaps rather than conversation.

## 2. Design Principles

1. **Evidence first:** verdicts always sit beside inspectable evidence.
2. **Conservative language:** uncertainty is visible and never disguised as success.
3. **Progressive disclosure:** show the audit summary first, details on demand.
4. **Human control:** generated guards are previews until approved.
5. **Operational clarity:** status, failures, and next actions are obvious.
6. **Demo legibility:** the core value should be understandable within 90 seconds.

## 3. Information Architecture

```text
Projects
  -> Incidents
      -> Audit Run
          -> Summary
          -> Corrective Actions
          -> Evidence Graph
          -> Guard Proposals
          -> Run Log

RemedyBench
  -> Cases
  -> Evaluation Run
  -> Metrics
```

## 4. Primary Screens

### 4.1 Start Audit

Purpose: select the repository and postmortem and confirm safe limits.

Fields:

- Project path selector/registered project.
- Postmortem upload or sample incident selector.
- Audit mode: standard or benchmark.
- Displayed limits: model-call budget and investigation rounds.
- `Start Audit` action.

Validation:

- Show a clear error if the path is outside the workspace.
- Show unsupported or oversized file errors before a run begins.
- Guard execution defaults to disabled.

### 4.2 Audit Dashboard

```text
┌───────────────────────────────────────────────────────────────┐
│ RemedyGraph        INC-042 Payment Retry Storm    Run: Done  │
├───────────────────────────────────────────────────────────────┤
│ Assessed protection coverage: 37.5%                          │
│ 1 Verified · 1 Partial · 2 Missing · 0 Unverifiable          │
├───────────────────────────────────────────────────────────────┤
│ Corrective action                   Verdict       Evidence    │
│ Bound retries to 3                  VERIFIED      3 items     │
│ Add exponential backoff + jitter    PARTIAL       2 items     │
│ Add circuit breaker                 MISSING       No proof    │
│ Alert above 10% failures            MISSING       Conflict    │
├───────────────────────────────────────────────────────────────┤
│ [Evidence graph] [Generate guard previews] [Export audit]    │
└───────────────────────────────────────────────────────────────┘
```

Requirements:

- Coverage is visually secondary to verdict counts.
- Each action row exposes evidence and missing proofs.
- Never use a green success state when any core deterministic check failed.
- Status colors must also include icons/text for accessibility.

### 4.3 Evidence Detail Drawer

Show:

- Original action text.
- Compiled invariant and check type.
- Deterministic check inputs, expected value, actual value, and result.
- Evidence cards with source type, path, line range, excerpt, strength, and retrieval score.
- Contradictions and missing proof.
- Model rationale clearly labelled as interpretation.

### 4.4 Evidence Graph

Node types:

- Incident.
- Corrective action.
- Invariant.
- Code/config/test/document/Git/execution evidence.
- Guard proposal.

Edges:

- `contains`, `compiled_to`, `supported_by`, `contradicted_by`, `tested_by`, and `protected_by`.

The graph is an alternate navigation view, not the only way to read evidence.

### 4.5 Guard Preview

Display:

- Guard type and generated name.
- Linked invariant.
- Why the guard is needed.
- Preconditions and assertions.
- Target path.
- Code diff preview.
- Safety notice and execution command selected by the application.

Actions:

- `Reject`.
- `Approve and write`.
- `Approve and execute` when execution is enabled.

Approval must be explicit for each guard in the MVP.

### 4.6 Evaluation Dashboard

Display only measured data:

- Dataset version and commit.
- Model/provider and prompt version.
- Extraction F1.
- Evidence Recall@5.
- Citation accuracy.
- Verification accuracy and macro-F1.
- Guard runnable/detection rate.
- Model calls and latency.

## 5. Run States

```text
QUEUED
 -> PARSING
 -> EXTRACTING_ACTIONS
 -> COMPILING_INVARIANTS
 -> INDEXING
 -> INVESTIGATING
 -> VERIFYING
 -> GENERATING_GUARDS
 -> COMPLETE
```

Terminal alternatives: `FAILED`, `CANCELLED`, or `PARTIAL_COMPLETE`.

The UI should show the current stage, completed stage count, action progress, and a concise failure message. Raw model reasoning is not displayed.

## 6. Responsive Behaviour

- Desktop-first for the portfolio demo.
- At narrow widths, action rows become cards and the evidence drawer becomes a full-screen panel.
- Graph controls must remain keyboard accessible.
- Code excerpts scroll horizontally without stretching the page.

## 7. Visual Direction

- Neutral dark or light engineering dashboard.
- Restrained use of green, amber, red, and grey for verdicts.
- Monospace only for paths, symbols, values, and code.
- Strong hierarchy: incident -> actions -> evidence -> guards.
- Avoid decorative AI imagery, chat bubbles, or anthropomorphic assistants.

## 8. Accessibility

- Meet WCAG AA contrast for primary text and status indicators.
- Every icon has a text label or accessible name.
- All primary workflows work with keyboard navigation.
- Focus moves to validation errors and opened drawers/modals.
- Status is never communicated by color alone.

## 9. Demo Flow

1. Open bundled `INC-042`.
2. Start audit and show bounded progress.
3. Open the partial retry action and show missing jitter evidence.
4. Open the alert action and show actual 20% versus expected 10%.
5. Open the evidence graph.
6. Generate guard previews.
7. Approve one guard and show its execution result.
8. End on the audit summary and reproducible evaluation link.
