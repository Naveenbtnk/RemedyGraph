# Multi-Agent Ownership

This file prevents Codex and AutoClaw from producing overlapping changes. A worktree protects the working copy; this ownership policy protects integration.

## Integration Owner

Codex is the default integration owner unless the user explicitly changes the role.

Only the integration owner may directly edit:

- `AGENTS.md`
- `README.md`
- `coordination/**`
- `contracts/**`
- `.github/**`
- Root dependency/configuration files.
- Dependency lockfiles.
- Cross-layer API schemas.
- `docs/STATUS.md`

## Codex Lane

Codex may edit:

- `backend/**`
- `frontend/**`
- `tests/**`
- `evals/**`
- Root/shared files when acting as integration owner.

Codex owns implementation, integration, debugging, safety controls, and automated verification.

## AutoClaw / GLM Lane

AutoClaw may edit:

- `remedybench/incidents/**`
- `remedybench/repositories/**`
- `remedybench/ground_truth/**`
- `docs/reviews/glm/**`

AutoClaw must not edit implementation, shared contracts, dependency files, CI, or accepted decision documents. It may propose changes through `coordination/CHANGE_REQUESTS.md`.

## Gemini Lane

Gemini is review-only by default. Store accepted review artifacts under:

- `docs/reviews/gemini/**`

Gemini receives only the minimum repository content required for review. Do not provide secrets, environment files, private user data, or unredacted production incidents.

## Shared-Contract Rule

Before parallel work begins, the integration owner freezes relevant files under `contracts/`. Other agents consume those contracts but do not alter them.

If a contract is insufficient:

1. Stop work that depends on the disputed contract.
2. Add a structured request to `coordination/CHANGE_REQUESTS.md`.
3. Continue only independent work.
4. Integration owner accepts/rejects the request and records material decisions in `docs/DECISIONS.md`.

## Worktree Convention

```text
Main integration checkout: RemedyGraph                branch main
Codex worktree:          RemedyGraph-codex            branch codex/<task>
AutoClaw worktree:       RemedyGraph-autoclaw         branch autoclaw/<task>
```

Each worktree must start from the same updated `main` commit for a phase.

## Task Card Requirements

Every parallel assignment must state:

- Task ID and objective.
- Starting commit.
- Branch/worktree.
- Allowed paths.
- Forbidden paths.
- Inputs/contracts.
- Required output.
- Verification and completion conditions.

## Pre-Handoff Check

Before handoff, the contributor must provide:

```text
Task:
Branch:
Starting commit:
Changed files:
Tests/checks:
Result:
Known limitations:
Requested integration action:
```

The integration owner verifies changed paths against this file before merging.

## Merge Policy

- Merge one agent branch at a time.
- Verify ownership before merge.
- Run relevant tests after each merge.
- Run the full available suite after all phase branches merge.
- Resolve shared-file conflicts in the integration checkout, never independently in both agent branches.
- Create fresh branches/worktrees from updated `main` for the next phase.
