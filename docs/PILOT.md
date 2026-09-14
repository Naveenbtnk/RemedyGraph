# Private Local Pilot

RemedyGraph's public [Vercel demo](https://remedy-graph.vercel.app) displays a saved synthetic
audit. To audit a real repository, each tester runs the API and dashboard on their own computer.
The API binds to loopback, and the selected repository remains on that computer.

## Pilot scope

Invite a small group of trusted engineers who can run Python, Node.js, and Git locally. Ask them to
try a Python repository and a Markdown or plain-text postmortem with explicit corrective-action
bullets. Start with a repository and postmortem they are authorized to inspect. The pilot is for
reviewing evidence and verdicts; leave guard approval and execution out of the first feedback
round.

This release uses a deterministic, rule-based action extractor (`mock` provider). It recognizes
bulleted actions with supported verbs, such as `- Bound retries to three attempts` or
`- Add a regression test for timeout handling`. It can miss differently phrased actions. Python
implementation and tests have the strongest structural checks; other languages, runtime behavior,
and unavailable context may produce `UNVERIFIABLE`. A verdict is a review aid, not a guarantee of
runtime reliability.

## Install once

Use Python 3.11+, Node.js 22+, npm, and Git. From a terminal:

```text
git clone https://github.com/Naveenbtnk/RemedyGraph.git
cd RemedyGraph
python -m venv .venv
```

Activate the environment with `.\.venv\Scripts\Activate.ps1` in PowerShell, or
`source .venv/bin/activate` on macOS/Linux. Install the application:

```text
python -m pip install -e ".[dev]"
npm ci --prefix frontend
```

Run commands from the `RemedyGraph` directory. The first run needs network access to install
dependencies; ordinary audits using the default provider do not need model credentials.

## Check the installation

In the first terminal, start the API:

```text
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

In a second terminal, also from `RemedyGraph`, start the dashboard:

```text
npm run dev --prefix frontend
```

Open <http://localhost:5173>. Leave the repository path as `remedybench/repositories/I04` and
start the prefilled sample audit. It should show one `MISSING`, one `PARTIAL`, and one `VERIFIED`
action. Stop both servers with Ctrl+C when finished.

## Audit a local repository

Choose a narrow folder that contains the repository. For example, if the repository is
`C:\Users\you\Projects\service-a`, set the workspace root to `C:\Users\you\Projects` before
starting the API. In PowerShell:

```powershell
$env:REMEDYGRAPH_WORKSPACE_ROOT = 'C:\Users\you\Projects'
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

On macOS/Linux:

```sh
export REMEDYGRAPH_WORKSPACE_ROOT="$HOME/Projects"
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

Start the dashboard in the second terminal as above. Enter the **absolute path** to the repository
in the dashboard and paste the postmortem text. Keep the repository inside the configured
workspace. The API rejects paths outside that root. The default SQLite database is in memory, so
audit history disappears when the API stops. If persistence is needed, set
`REMEDYGRAPH_DATABASE_PATH` to an absolute path outside the source checkout; that database may
contain audit metadata and redacted evidence and should stay private.

Read each action's original claim, evidence locations, check result, and missing proof before
judging the verdict. Do not interpret `UNVERIFIABLE` as `MISSING`. Repository content is read-only
during an audit. Guard approval is a separate action that can write a generated file inside the
selected repository; skip it during the initial pilot.

## Feedback to send

For each audit, ask the tester for:

1. Operating system, Python and Node.js versions, and whether installation or startup failed.
2. Repository language and approximate size, without a source archive or access token.
3. Number of postmortem actions expected versus extracted.
4. For a questionable verdict: the action wording, expected verdict, actual verdict, and why the
   cited evidence or missing proof is right or wrong. Redact private paths and content first.
5. Whether the audit completed and whether the evidence was understandable.

Do not send full private repositories, unredacted postmortems, credentials, or the local SQLite
database as pilot feedback. A sanitized minimal example is more useful for reproducing an issue.

## Troubleshooting

- If the dashboard cannot reach the API, confirm that the API terminal is still running and
  <http://127.0.0.1:8000/health> responds. Use the local dashboard URL, not the Vercel demo.
- If a repository is rejected, check that `REMEDYGRAPH_WORKSPACE_ROOT` was set in the **API**
  terminal before starting it and that the repository is inside that directory.
- If no actions are extracted, use Markdown bullets with explicit verbs and one action per bullet.
  Capture the missed wording in sanitized feedback; do not repeatedly submit the same incident,
  because each extraction attempt consumes the incident's six-call budget.
- If a verdict is `UNVERIFIABLE`, inspect its missing-context explanation. The pilot does not run
  the audited repository's own test suite or observe production behavior.

The [README](../README.md) has the full configuration and verification commands.
