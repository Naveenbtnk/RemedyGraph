# RemedyBench Smoke Set

This directory contains five small, entirely synthetic reliability incidents and repositories. It
is the reproducible smoke subset of the 15-incident design in
`docs/reviews/glm/REMEDYBENCH_PLAN.md`.

- Version: `0.1.0-smoke`
- License: CC0-1.0 for benchmark-authored prose and fixture code
- Data: synthetic only; no customer data, copied incident reports, real credentials, or production
  telemetry
- Ground truth: `manifest.json`, stored outside every searchable fixture repository

Run from the repository root:

```powershell
python -m backend.app.evaluation.cli --benchmark remedybench --check
```

To produce a measured JSON report, pass `--output <path>`. Evaluation copies every repository into
a temporary workspace before auditing or executing generated guards, so curated fixtures are never
modified.
