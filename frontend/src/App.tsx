import { FormEvent, useMemo, useState } from "react";
import type { ReactNode } from "react";

type Verdict = "VERIFIED" | "PARTIAL" | "MISSING" | "UNVERIFIABLE";
type GuardStatus =
  | "PREVIEWED"
  | "REJECTED"
  | "WRITTEN"
  | "PASSED"
  | "FAILED"
  | "TIMED_OUT"
  | "ERROR";

interface Budget {
  model_calls_used: number;
  model_calls_limit: number;
  investigation_rounds: Record<string, number>;
}

interface RunSummary {
  id: string;
  status: string;
  total_actions: number;
  completed_actions: number;
  verdict_counts: Partial<Record<Verdict, number>>;
  assessed_protection_coverage: number;
  budget: Budget;
  error?: string | null;
}

interface Citation {
  evidence_id: string;
  source_path?: string | null;
  line_start?: number | null;
  line_end?: number | null;
}

interface ActionVerdict {
  id: string;
  action_id: string;
  verdict: Verdict;
  rationale: string;
  citations: Citation[];
  missing_proofs: string[];
}

interface Evidence {
  id: string;
  action_id: string;
  kind: string;
  role: string;
  source_path?: string | null;
  line_start?: number | null;
  excerpt?: string | null;
}

interface GraphNode {
  id: string;
  node_type: string;
  label: string;
}

interface Graph {
  nodes: GraphNode[];
  edges: unknown[];
}

interface GuardExecution {
  id: string;
  status: string;
  exit_code?: number | null;
  stdout: string;
  stderr: string;
  duration_ms: number;
}

interface Guard {
  id: string;
  name: string;
  guard_type: string;
  intent: string;
  assertions: string[];
  target_path: string;
  preview: string;
  preview_sha256: string;
  status: GuardStatus;
}

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000/api/v1";
const DEFAULT_INCIDENT = `# Payment retry storm

Affected services: payments

## Corrective actions
- Bound retries to 3.
- Add a circuit breaker.
- Add a regression test for retry exhaustion.
`;

export function canExecuteGuard(status: GuardStatus): boolean {
  return ["WRITTEN", "PASSED", "FAILED", "TIMED_OUT", "ERROR"].includes(status);
}

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = typeof payload.detail === "string" ? payload.detail : `Request failed (${response.status})`;
    throw new Error(detail);
  }
  return payload as T;
}

function VerdictBadge({ verdict }: { verdict: Verdict }) {
  return <span className={`verdict verdict-${verdict.toLowerCase()}`}>{verdict}</span>;
}

function Panel({
  title,
  children,
  className = "",
}: {
  title: string;
  children: ReactNode;
  className?: string;
}) {
  return <section className={`panel ${className}`}><h2>{title}</h2>{children}</section>;
}

export default function App() {
  const [repositoryPath, setRepositoryPath] = useState("");
  const [incidentText, setIncidentText] = useState(DEFAULT_INCIDENT);
  const [run, setRun] = useState<RunSummary | null>(null);
  const [actions, setActions] = useState<ActionVerdict[]>([]);
  const [evidence, setEvidence] = useState<Evidence[]>([]);
  const [graph, setGraph] = useState<Graph>({ nodes: [], edges: [] });
  const [guards, setGuards] = useState<Guard[]>([]);
  const [executions, setExecutions] = useState<Record<string, GuardExecution>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const counts = useMemo(
    () => ({
      VERIFIED: run?.verdict_counts.VERIFIED ?? 0,
      PARTIAL: run?.verdict_counts.PARTIAL ?? 0,
      MISSING: run?.verdict_counts.MISSING ?? 0,
      UNVERIFIABLE: run?.verdict_counts.UNVERIFIABLE ?? 0,
    }),
    [run],
  );

  async function startAudit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    setGuards([]);
    setExecutions({});
    try {
      const project = await api<{ id: string }>("/projects", {
        method: "POST",
        body: JSON.stringify({ repository_path: repositoryPath }),
      });
      const incident = await api<{ id: string }>("/incidents", {
        method: "POST",
        body: JSON.stringify({ project_id: project.id, source_text: incidentText }),
      });
      const created = await api<RunSummary>("/runs", {
        method: "POST",
        body: JSON.stringify({ project_id: project.id, incident_id: incident.id }),
      });
      setRun(created);
      const [actionData, evidenceData, graphData] = await Promise.all([
        api<{ verdicts: ActionVerdict[] }>(`/runs/${created.id}/actions`),
        api<{ evidence: Evidence[] }>(`/runs/${created.id}/evidence`),
        api<Graph>(`/runs/${created.id}/graph`),
      ]);
      setActions(actionData.verdicts);
      setEvidence(evidenceData.evidence);
      setGraph(graphData);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Audit failed");
    } finally {
      setBusy(false);
    }
  }

  async function previewGuards() {
    if (!run) return;
    setBusy(true);
    setError(null);
    try {
      const result = await api<{ guards: Guard[] }>(`/runs/${run.id}/guards/preview`, {
        method: "POST",
      });
      setGuards(result.guards);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Preview failed");
    } finally {
      setBusy(false);
    }
  }

  async function decideGuard(guard: Guard, approved: boolean) {
    if (!run) return;
    setBusy(true);
    setError(null);
    try {
      const updated = await api<Guard>(`/runs/${run.id}/guards/${guard.id}/approve`, {
        method: "POST",
        body: JSON.stringify({ approved, preview_sha256: guard.preview_sha256 }),
      });
      setGuards((current) => current.map((item) => item.id === updated.id ? updated : item));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Decision failed");
    } finally {
      setBusy(false);
    }
  }

  async function executeGuard(guard: Guard) {
    if (!run) return;
    setBusy(true);
    setError(null);
    try {
      const result = await api<GuardExecution>(`/runs/${run.id}/guards/${guard.id}/execute`, {
        method: "POST",
      });
      setExecutions((current) => ({ ...current, [guard.id]: result }));
      const listed = await api<{ guards: Guard[] }>(`/runs/${run.id}/guards`);
      setGuards(listed.guards);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Execution failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="shell">
      <header className="topbar">
        <div><p className="eyebrow">POSTMORTEM-TO-CI AUDITOR</p><h1>RemedyGraph</h1></div>
        <span className="run-state"><span aria-hidden="true">●</span>{run ? `Run: ${run.status}` : "Ready"}</span>
      </header>

      <Panel title="Start a local audit" className="setup-panel">
        <form onSubmit={startAudit} className="audit-form">
          <label>Repository path<input value={repositoryPath} onChange={(event) => setRepositoryPath(event.target.value)} placeholder="C:\\workspace\\service" required /></label>
          <label>Incident postmortem<textarea value={incidentText} onChange={(event) => setIncidentText(event.target.value)} rows={8} required /></label>
          <button className="primary" type="submit" disabled={busy}>{busy ? "Working…" : "Start audit"}</button>
        </form>
        {error && <p className="error" role="alert">{error}</p>}
        {run?.error && <p className="error" role="alert">{run.error}</p>}
      </Panel>

      <div className="summary-grid" aria-label="Audit summary">
        <Panel title="Run status"><p className="metric">{run?.status ?? "Not started"}</p><p className="muted">{run ? `${run.completed_actions}/${run.total_actions} actions assessed` : "Select a repository to begin."}</p></Panel>
        <Panel title="Assessed protection coverage"><p className="metric">{run ? `${run.assessed_protection_coverage.toFixed(1)}%` : "—"}</p><p className="muted">{counts.VERIFIED} verified · {counts.PARTIAL} partial · {counts.MISSING} missing · {counts.UNVERIFIABLE} unverifiable</p></Panel>
        <Panel title="Bounded usage"><p className="metric code">{run ? `${run.budget.model_calls_used}/${run.budget.model_calls_limit}` : "—"}</p><p className="muted">Persisted model attempts</p></Panel>
      </div>

      <Panel title="Corrective actions">
        {actions.length === 0 ? <p className="empty">No audit results yet.</p> : <div className="action-list">{actions.map((action) => {
          const records = evidence.filter((item) => item.action_id === action.action_id);
          return <details className="action-card" key={action.id}>
            <summary><VerdictBadge verdict={action.verdict} /><span>{action.rationale}</span><span className="count">{records.length} evidence</span></summary>
            <div className="action-detail">
              {action.missing_proofs.length > 0 && <div><h3>Missing proof</h3><ul>{action.missing_proofs.map((proof) => <li key={proof}>{proof}</li>)}</ul></div>}
              <h3>Evidence</h3>
              {records.length === 0 ? <p className="muted">No repository evidence located.</p> : records.map((record) => <article className="evidence" key={record.id}><div><span className="chip">{record.kind}</span><span className="chip secondary">{record.role}</span></div><p className="code path">{record.source_path ?? "No source path"}{record.line_start ? `:${record.line_start}` : ""}</p>{record.excerpt && <pre>{record.excerpt}</pre>}</article>)}
            </div>
          </details>;
        })}</div>}
      </Panel>

      <div className="two-column">
        <Panel title="Evidence graph"><p className="metric">{graph.nodes.length} nodes · {graph.edges.length} edges</p><p className="muted">Accessible graph inventory</p><ul className="graph-list">{graph.nodes.slice(0, 8).map((node) => <li key={node.id}><span className="chip">{node.node_type}</span> {node.label}</li>)}</ul></Panel>
        <Panel title="CI guard proposals"><p className="muted">Previews never modify the repository. Every guard requires an explicit decision.</p><button type="button" onClick={previewGuards} disabled={!run || run.status !== "COMPLETE" || busy}>Generate guard previews</button></Panel>
      </div>

      {guards.map((guard) => <Panel title={guard.name} className="guard-panel" key={guard.id}>
        <div className="guard-meta"><span className="chip">{guard.guard_type}</span><span className={`guard-status status-${guard.status.toLowerCase()}`}>{guard.status}</span></div>
        <p>{guard.intent}</p><p className="code path">{guard.target_path}</p>
        <h3>Assertions</h3><ul>{guard.assertions.map((assertion) => <li key={assertion}>{assertion}</li>)}</ul>
        <pre className="preview"><code>{guard.preview}</code></pre>
        <p className="safety">Safety boundary: the application selects a fixed isolated Python command; repository promotion remains manual.</p>
        <div className="button-row">
          <button type="button" onClick={() => decideGuard(guard, false)} disabled={guard.status !== "PREVIEWED" || busy}>Reject</button>
          <button className="primary" type="button" onClick={() => decideGuard(guard, true)} disabled={guard.status !== "PREVIEWED" || busy}>Approve and write</button>
          <button type="button" onClick={() => executeGuard(guard)} disabled={!canExecuteGuard(guard.status) || busy}>Execute approved guard</button>
        </div>
        {executions[guard.id] && <div className="execution"><h3>Execution: {executions[guard.id].status}</h3><p className="muted">Exit {executions[guard.id].exit_code ?? "—"} · {executions[guard.id].duration_ms.toFixed(0)} ms</p><pre>{executions[guard.id].stdout || executions[guard.id].stderr || "No output"}</pre></div>}
      </Panel>)}
    </main>
  );
}
