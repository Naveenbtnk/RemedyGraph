# GitHub Actions Pilot

The GitHub Actions pilot runs RemedyGraph inside a customer's repository rather than sending
repository source to a shared RemedyGraph server. GitHub authenticates the user, authorizes access
to the repository, supplies an ephemeral hosted runner, and retains the resulting artifact under
that repository's Actions permissions.

This is a repository-local pilot, not a multi-tenant RemedyGraph service. RemedyGraph does not
receive a repository token, retain source code, or provide a central customer dashboard in this
mode.

## Security model

- The customer deliberately installs a workflow in a repository they control.
- The workflow grants only `contents: read` and disables persisted checkout credentials.
- The audit parses supported files and executes only application-owned deterministic checks. It
  does not run the repository's build, tests, hooks, or model-provided commands.
- When GitHub supplies `GITHUB_WORKSPACE`, the selected repository must remain inside that
  workspace; postmortem and output paths must remain inside the selected repository.
- The job has a ten-minute outer timeout. RemedyGraph retains its file, index, model-call, and
  investigation-round limits.
- The generated JSON omits absolute paths, source excerpts, arbitrary evidence metadata, actual
  configuration values, the SQLite database, and generated guards.
- The report remains a private GitHub Actions artifact for seven days unless the customer changes
  the workflow.
- Guard preview, writing, and execution are not part of this workflow.

Repository files and the postmortem remain untrusted inputs. Do not use `pull_request_target`, run
the workflow automatically on contributions from forks, or add write permissions. Review the
workflow and pin RemedyGraph to a full commit SHA before use.

## Install in a pilot repository

1. Add a UTF-8 Markdown or text postmortem to the repository, for example
   `docs/postmortem.md`. Use explicit corrective-action bullets.
2. Copy [`docs/examples/remedygraph-audit.yml`](examples/remedygraph-audit.yml) to
   `.github/workflows/remedygraph-audit.yml` in the pilot repository.
3. Replace `COMMIT_SHA` with a reviewed full RemedyGraph commit SHA. A moving `main` reference is
   intentionally not recommended.
4. Commit the workflow and postmortem after normal repository review.
5. Open **Actions → RemedyGraph audit → Run workflow**, confirm the postmortem path, and start the
   job.
6. Download `remedygraph-report-<run id>` from the completed workflow run and inspect
   `report.json`.

Standard GitHub-hosted Actions usage is free for public repositories. Private repositories consume
the repository owner's included Actions allowance and artifact storage.

## Report contents

The versioned report contains:

- tool and repository revision metadata;
- completion status, bounded budget usage, verdict counts, and assessed protection coverage;
- original corrective actions, conservative verdicts, rationale, proof gaps, and relative source
  citations;
- an evidence inventory containing only kind, role, relative path, and line range; and
- deterministic check type and outcome without source excerpts or observed values.

The report is still potentially sensitive because filenames, action wording, and engineering proof
gaps can reveal internal system information. Keep private-repository artifacts private and redact
them before sharing pilot feedback.

## Run the action locally

After installing RemedyGraph, the same entry point can be tested without GitHub:

```text
remedygraph-audit --repository . --postmortem docs/postmortem.md
```

The default report path is `.remedygraph/report.json`, which is ignored by Git. Both the
postmortem and output must remain inside the resolved repository. Symlink escapes, unsupported
postmortem formats, invalid UTF-8, empty input, and files over 1 MB are rejected.

## Current limitations

- Installation is manual; a GitHub App and central OAuth callback are not implemented.
- Reports are downloaded from GitHub rather than synchronized to the Vercel showcase.
- The deterministic local action extractor remains the only provider.
- Python has the strongest structural checks; runtime-only requirements remain unverifiable.
- The application source currently has no assigned license. External pilot distribution should not
  begin until the maintainer selects and commits a source license.
