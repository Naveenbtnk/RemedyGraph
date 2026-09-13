import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";
import { canExecuteGuard, formatStatus } from "./ui";
import type { GuardStatus } from "./ui";

type Verdict = "VERIFIED" | "PARTIAL" | "MISSING" | "UNVERIFIABLE";
type PendingAction = "audit" | "preview" | "decision" | "execution" | null;

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
const REQUEST_TIMEOUT_MS = 120_000;
const MAX_ERROR_LENGTH = 500;
const DEFAULT_INCIDENT = `# Payment retry storm

Affected services: payments

## Corrective actions
- Bound retries to 3.
- Add a circuit breaker.
- Add a regression test for retry exhaustion.
`;

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  try {
    const response = await fetch(`${API_BASE}${path}`, {
      ...init,
      credentials: "omit",
      headers: { "Content-Type": "application/json", ...init?.headers },
      referrerPolicy: "no-referrer",
      signal: init?.signal ?? controller.signal,
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      const detail =
        typeof payload.detail === "string"
          ? payload.detail.slice(0, MAX_ERROR_LENGTH)
          : `Request failed (${response.status})`;
      throw new Error(detail);
    }
    return payload as T;
  } catch (reason) {
    if (reason instanceof DOMException && reason.name === "AbortError") {
      throw new Error("The local service did not respond within two minutes.");
    }
    throw reason;
  } finally {
    window.clearTimeout(timeout);
  }
}

function VerdictBadge({ verdict }: { verdict: Verdict }) {
  return <span className={`verdict verdict-${verdict.toLowerCase()}`}>{verdict}</span>;
}

function Panel({
  title,
  kicker,
  children,
  className = "",
}: {
  title: string;
  kicker?: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`panel ${className}`}>
      <div className="panel-heading">
        {kicker && <p className="panel-kicker">{kicker}</p>}
        <h2>{title}</h2>
      </div>
      {children}
    </section>
  );
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
  const [pendingAction, setPendingAction] = useState<PendingAction>(null);
  const [error, setError] = useState<string | null>(null);
  const errorRef = useRef<HTMLParagraphElement>(null);
  const busy = pendingAction !== null;
  const displayedError = error ?? run?.error ?? null;

  useEffect(() => {
    if (displayedError) {
      errorRef.current?.focus();
    }
  }, [displayedError]);

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
    setPendingAction("audit");
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
      setPendingAction(null);
    }
  }

  async function previewGuards() {
    if (!run) return;
    setPendingAction("preview");
    setError(null);
    try {
      const result = await api<{ guards: Guard[] }>(`/runs/${run.id}/guards/preview`, {
        method: "POST",
      });
      setGuards(result.guards);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Preview failed");
    } finally {
      setPendingAction(null);
    }
  }

  async function decideGuard(guard: Guard, approved: boolean) {
    if (!run) return;
    setPendingAction("decision");
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
      setPendingAction(null);
    }
  }

  async function executeGuard(guard: Guard) {
    if (!run) return;
    setPendingAction("execution");
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
      setPendingAction(null);
    }
  }

  return (
    <div className="app-frame">
      <a className="skip-link" href="#audit-workspace">Skip to audit workspace</a>
      <div className="ambient ambient-one" aria-hidden="true" />
      <div className="ambient ambient-two" aria-hidden="true" />
      <main className="shell" id="audit-workspace" aria-busy={busy}>
        <p className="sr-only" role="status" aria-live="polite">
          {pendingAction === "audit" && "Audit in progress."}
          {pendingAction === "preview" && "Generating guard previews."}
          {pendingAction === "decision" && "Saving guard decision."}
          {pendingAction === "execution" && "Executing approved guard."}
        </p>
        <header className="topbar">
          <a className="brand" href="#top" aria-label="RemedyGraph home">
            <span className="brand-mark" aria-hidden="true">
              <i />
              <i />
              <i />
            </span>
            <span>
              <strong>RemedyGraph</strong>
              <small>Engineering assurance</small>
            </span>
          </a>
          <div className="header-context">
            <span className="context-label">Local workspace</span>
            <span className="run-state">
              <span className="status-dot" aria-hidden="true" />
              {run ? `Run ${formatStatus(run.status)}` : "System ready"}
            </span>
          </div>
        </header>

        <section className="hero" id="top">
          <div className="hero-copy">
            <p className="eyebrow">Postmortem assurance workspace</p>
            <h1>Turn incident promises into proof.</h1>
            <p className="hero-description">
              Audit corrective actions against repository evidence, deterministic checks, and
              reviewable CI protections.
            </p>
          </div>
          <div className="hero-note">
            <span className="note-index">01</span>
            <p>Local-first</p>
            <small>Your repository stays inside the configured workspace.</small>
          </div>
        </section>

        <Panel title="Configure the audit" kicker="New assessment" className="setup-panel">
          <form onSubmit={startAudit} className="audit-form">
            <label>
              <span>Repository path</span>
              <input
                value={repositoryPath}
                onChange={(event) => setRepositoryPath(event.target.value)}
                placeholder="C:\\workspace\\service"
                maxLength={4096}
                autoComplete="off"
                spellCheck={false}
                aria-describedby="repository-help"
                required
              />
              <small id="repository-help">Must be inside the configured workspace root.</small>
            </label>
            <label>
              <span>Incident postmortem</span>
              <textarea
                value={incidentText}
                onChange={(event) => setIncidentText(event.target.value)}
                rows={8}
                maxLength={1_000_000}
                aria-describedby="incident-help"
                required
              />
              <small id="incident-help">
                Markdown or plain text with explicit corrective actions ·{" "}
                {incidentText.length.toLocaleString()} characters
              </small>
            </label>
            <div className="form-action">
              <div className="limit-note">
                <span>Bounded by design</span>
                <small>6 model attempts · 3 investigation rounds</small>
              </div>
              <button className="primary" type="submit" disabled={busy}>
                <span>{pendingAction === "audit" ? "Auditing…" : "Start audit"}</span>
                <span aria-hidden="true">→</span>
              </button>
            </div>
          </form>
          {displayedError && (
            <p className="error" role="alert" ref={errorRef} tabIndex={-1}>
              {displayedError}
            </p>
          )}
        </Panel>

        <div className="section-label">
          <span>Audit overview</span>
          <span>{run ? run.id : "Awaiting first run"}</span>
        </div>
        <div className="summary-grid" aria-label="Audit summary">
          <Panel title="Run status" kicker="Progress" className="summary-card">
            <p className="metric metric-status">
              {run ? formatStatus(run.status) : "Not started"}
            </p>
            <p className="muted">
              {run
                ? `${run.completed_actions}/${run.total_actions} actions assessed`
                : "Select a repository to begin."}
            </p>
            <progress
              className="metric-track"
              max={run?.total_actions || 1}
              value={run?.completed_actions ?? 0}
              aria-label="Actions assessed"
            />
          </Panel>
          <Panel
            title="Assessed protection coverage"
            kicker="Deterministic result"
            className="summary-card coverage-card"
          >
            <p className="metric metric-large">
              {run ? `${run.assessed_protection_coverage.toFixed(1)}%` : "—"}
            </p>
            <div className="verdict-summary" aria-label="Verdict counts">
              <span>{counts.VERIFIED} verified</span>
              <span>{counts.PARTIAL} partial</span>
              <span>{counts.MISSING} missing</span>
              <span>{counts.UNVERIFIABLE} unknown</span>
            </div>
          </Panel>
          <Panel title="Bounded usage" kicker="Model budget" className="summary-card">
            <p className="metric metric-large code">
              {run ? `${run.budget.model_calls_used}/${run.budget.model_calls_limit}` : "—"}
            </p>
            <p className="muted">Persisted attempts across the incident lifecycle.</p>
            <progress
              className="metric-track segmented"
              max={run?.budget.model_calls_limit || 1}
              value={run?.budget.model_calls_used ?? 0}
              aria-label="Model-call budget consumed"
            />
          </Panel>
        </div>

        <Panel title="Corrective actions" kicker="Evidence register" className="actions-panel">
          {actions.length === 0 ? (
            <div className="empty-state">
              <span className="empty-mark" aria-hidden="true">↳</span>
              <div>
                <p>No audit results yet.</p>
                <small>Completed action verdicts and their evidence will appear here.</small>
              </div>
            </div>
          ) : (
            <div className="action-list">
              {actions.map((action, index) => {
                const records = evidence.filter((item) => item.action_id === action.action_id);
                return (
                  <details className="action-card" key={action.id}>
                    <summary>
                      <span className="action-index">A{String(index + 1).padStart(2, "0")}</span>
                      <VerdictBadge verdict={action.verdict} />
                      <span className="action-rationale">{action.rationale}</span>
                      <span className="count">{records.length} evidence</span>
                      <span className="summary-toggle" aria-hidden="true">+</span>
                    </summary>
                    <div className="action-detail">
                      {action.missing_proofs.length > 0 && (
                        <div className="missing-proof">
                          <h3>Missing proof</h3>
                          <ul>
                            {action.missing_proofs.map((proof) => (
                              <li key={proof}>{proof}</li>
                            ))}
                          </ul>
                        </div>
                      )}
                      <h3>Located evidence</h3>
                      {records.length === 0 ? (
                        <p className="muted">No repository evidence located.</p>
                      ) : (
                        <div className="evidence-grid">
                          {records.map((record) => (
                            <article className="evidence" key={record.id}>
                              <div>
                                <span className="chip">{record.kind}</span>
                                <span className="chip secondary">{record.role}</span>
                              </div>
                              <p className="code path">
                                {record.source_path ?? "No source path"}
                                {record.line_start ? `:${record.line_start}` : ""}
                              </p>
                              {record.excerpt && <pre>{record.excerpt}</pre>}
                            </article>
                          ))}
                        </div>
                      )}
                    </div>
                  </details>
                );
              })}
            </div>
          )}
        </Panel>

        <div className="two-column">
          <Panel title="Evidence graph" kicker="Traceability" className="graph-panel">
            <p className="metric compact-metric">
              {graph.nodes.length} nodes <span>·</span> {graph.edges.length} edges
            </p>
            <p className="muted">An accessible inventory of the audit’s evidence relationships.</p>
            <ul className="graph-list">
              {graph.nodes.slice(0, 8).map((node) => (
                <li key={node.id}>
                  <span className="graph-node-dot" aria-hidden="true" />
                  <span className="chip">{node.node_type}</span>
                  <span>{node.label}</span>
                </li>
              ))}
            </ul>
          </Panel>
          <Panel title="CI guard proposals" kicker="Human-controlled" className="guard-intro">
            <div className="guard-symbol" aria-hidden="true">✓</div>
            <p className="guard-lead">Close the proof gap with a reviewable protection.</p>
            <p className="muted">
              Previews never modify the repository. Every guard requires an explicit decision.
            </p>
            <button
              className="secondary-action"
              type="button"
              onClick={previewGuards}
              disabled={!run || run.status !== "COMPLETE" || busy}
            >
              {pendingAction === "preview" ? "Generating previews…" : "Generate guard previews"}
              <span aria-hidden="true">→</span>
            </button>
          </Panel>
        </div>

        {guards.map((guard) => (
          <Panel title={guard.name} kicker="Guard preview" className="guard-panel" key={guard.id}>
            <div className="guard-meta">
              <span className="chip">{guard.guard_type}</span>
              <span className={`guard-status status-${guard.status.toLowerCase()}`}>
                {guard.status}
              </span>
            </div>
            <p className="guard-lead">{guard.intent}</p>
            <p className="code path">{guard.target_path}</p>
            <h3>Assertions</h3>
            <ul>
              {guard.assertions.map((assertion) => (
                <li key={assertion}>{assertion}</li>
              ))}
            </ul>
            <pre className="preview">
              <code>{guard.preview}</code>
            </pre>
            <p className="safety">
              <strong>Safety boundary.</strong> The application selects a fixed isolated Python
              command; repository promotion remains manual.
            </p>
            <div className="button-row">
              <button
                type="button"
                onClick={() => decideGuard(guard, false)}
                disabled={guard.status !== "PREVIEWED" || busy}
              >
                {pendingAction === "decision" ? "Saving decision…" : "Reject"}
              </button>
              <button
                className="primary"
                type="button"
                onClick={() => decideGuard(guard, true)}
                disabled={guard.status !== "PREVIEWED" || busy}
              >
                {pendingAction === "decision" ? "Saving decision…" : "Approve and write"}
              </button>
              <button
                type="button"
                onClick={() => executeGuard(guard)}
                disabled={!canExecuteGuard(guard.status) || busy}
              >
                {pendingAction === "execution" ? "Executing guard…" : "Execute approved guard"}
              </button>
            </div>
            {executions[guard.id] && (
              <div className="execution">
                <h3>Execution: {executions[guard.id].status}</h3>
                <p className="muted">
                  Exit {executions[guard.id].exit_code ?? "—"} ·{" "}
                  {executions[guard.id].duration_ms.toFixed(0)} ms
                </p>
                <pre>
                  {executions[guard.id].stdout ||
                    executions[guard.id].stderr ||
                    "No output"}
                </pre>
              </div>
            )}
          </Panel>
        ))}

        <footer>
          <span>RemedyGraph</span>
          <span>Evidence-backed reliability auditing</span>
          <span>Local MVP · 2026</span>
        </footer>
      </main>
    </div>
  );
}
