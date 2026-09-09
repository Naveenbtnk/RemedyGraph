import type { ReactNode } from "react";

type Verdict = "VERIFIED" | "PARTIAL" | "MISSING" | "UNVERIFIABLE";

const sampleActions: ReadonlyArray<{ action: string; verdict: Verdict; evidence: string }> = [
  { action: "Bound retries to 3", verdict: "VERIFIED", evidence: "3 items" },
  { action: "Add exponential backoff + jitter", verdict: "PARTIAL", evidence: "2 items" },
  { action: "Add circuit breaker", verdict: "MISSING", evidence: "No proof" },
];

function VerdictBadge({ verdict }: { verdict: Verdict }) {
  return <span className={`verdict verdict-${verdict.toLowerCase()}`}>{verdict}</span>;
}

function Panel({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="panel">
      <h2>{title}</h2>
      {children}
    </section>
  );
}

export default function App() {
  return (
    <main className="shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">RELIABILITY AUDIT</p>
          <h1>RemedyGraph</h1>
        </div>
        <span className="run-state"><span aria-hidden="true">●</span> Day 1 scaffold</span>
      </header>

      <div className="context">
        <div>
          <p className="eyebrow">INCIDENT</p>
          <h2>INC-042 · Payment Retry Storm</h2>
          <p className="muted">A traceable path from postmortem claims to engineering proof.</p>
        </div>
        <button type="button" disabled>Start audit</button>
      </div>

      <div className="summary-grid">
        <Panel title="Audit readiness">
          <p className="metric">Ready for input</p>
          <p className="muted">Connect a local repository and Markdown postmortem to begin.</p>
        </Panel>
        <Panel title="Assessed protection coverage">
          <p className="metric">—</p>
          <p className="muted">Coverage appears after deterministic checks run.</p>
        </Panel>
        <Panel title="Provider">
          <p className="metric code">mock</p>
          <p className="muted">Deterministic and network-free for local development.</p>
        </Panel>
      </div>

      <Panel title="Corrective actions">
        <div className="table-wrap">
          <table>
            <thead><tr><th>Action</th><th>Verdict</th><th>Evidence</th></tr></thead>
            <tbody>{sampleActions.map((item) => (
              <tr key={item.action}>
                <td>{item.action}</td>
                <td><VerdictBadge verdict={item.verdict} /></td>
                <td className="muted">{item.evidence}</td>
              </tr>
            ))}</tbody>
          </table>
        </div>
        <p className="footnote">Sample presentation only; audit workflow is introduced in a later phase.</p>
      </Panel>
    </main>
  );
}
