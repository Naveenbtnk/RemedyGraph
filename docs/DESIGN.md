# RemedyGraph Interface Design

**Status:** Implemented dashboard design

## Purpose

The interface presents an engineering audit, not a conversation. A user should be able to move
from a corrective action to its evidence, deterministic verdict, and optional guard proposal
without guessing what the system inferred.

## User workflow

1. Enter a repository path inside the configured workspace and paste a Markdown or plain-text
   postmortem.
2. Start the bounded audit and inspect its status, action count, model-attempt budget, and assessed
   protection coverage.
3. Expand each corrective action to see its verdict, missing proof, and located evidence.
4. Inspect the accessible evidence-graph inventory as an alternate traceability view.
5. Generate a guard preview for an incomplete action. Reject it or approve the exact preview for
   writing. Execution is available only after approval and writing.

The dashboard does not execute guards during an audit. Approval and execution are separate user
actions.

## Information hierarchy

```text
Audit setup
  → Run summary and bounded usage
  → Corrective actions and evidence
  → Evidence graph
  → Guard previews and execution results
```

Coverage is visually secondary to verdict counts. Every verdict includes cited evidence or an
explicit proof gap. Status is communicated with text and shape, never color alone.

## Visual system

The dashboard uses a restrained monochrome palette, black typography, and raised/inset surfaces.
Monospace is reserved for paths, values, and code. The layout stacks at narrower viewport widths;
long excerpts scroll inside their cards rather than widening the page. The current implementation
is shown in the [dashboard capture](images/dashboard.png).

## Accessibility

- A skip link reaches the audit workspace.
- Native form controls and progress elements expose labels to assistive technology.
- Operation status is announced in a live region; errors receive focus.
- Corrective-action details use keyboard-operable native disclosure elements.
- Guard approval and execution controls remain disabled until their state permits the action.
- The evidence graph has a text inventory so understanding it does not depend on a visual diagram.

## Demonstration fixture

Use the bundled `I04` incident and repository. The audit reports a missing circuit breaker, a
partial fallback, and verified half-open recovery protection. This illustrates the difference
between an unused declaration, incomplete protection, and a structurally supported result.

## Current boundaries

The evaluation interface is a CLI and a saved JSON report, not a dashboard screen. The evidence
graph is an accessible inventory rather than an interactive canvas. File upload and asynchronous
run polling are not implemented; the current UI accepts pasted text and a local repository path.

The public demo is a separate static build. It displays a curated synthetic I04 result with
read-only fields, disabled audit and guard actions, and a link to the local setup instructions.
Its graph inventory is explicitly labeled as a selection from the full audit trace.
