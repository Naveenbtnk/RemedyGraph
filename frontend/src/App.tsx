import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { requestJson } from "./api/client";
import type {
  ActionVerdict,
  Evidence,
  EvidenceGraph,
  Guard,
  GuardExecution,
  RunSummary,
} from "./api/types";
import ActionCard from "./components/ActionCard";
import GuardCard from "./components/GuardCard";
import { isDemoMode } from "./demo/mode";
import { sampleActions, sampleEvidence, sampleGraph, sampleIncident, sampleRun } from "./demo/sampleAudit";
import Panel from "./components/Panel";
import { formatStatus } from "./lib/status";
import type { PendingAction } from "./lib/status";

const DEFAULT_INCIDENT = sampleIncident;
interface AppProps {
  demoMode?: boolean;
}

export default function App({ demoMode = isDemoMode(import.meta.env.MODE) }: AppProps = {}) {
  const isPublicDemo = demoMode;
  const [repositoryPath, setRepositoryPath] = useState(isPublicDemo ? "remedybench/repositories/I04" : "");
  const [incidentText, setIncidentText] = useState(DEFAULT_INCIDENT);
  const [run, setRun] = useState<RunSummary | null>(isPublicDemo ? sampleRun : null);
  const [actions, setActions] = useState<ActionVerdict[]>(isPublicDemo ? sampleActions : []);
  const [evidence, setEvidence] = useState<Evidence[]>(isPublicDemo ? sampleEvidence : []);
  const [graph, setGraph] = useState<EvidenceGraph>(isPublicDemo ? sampleGraph : { nodes: [], edges: [] });
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
    if (isPublicDemo) return;
    setPendingAction("audit");
    setError(null);
    setRun(null);
    setActions([]);
    setEvidence([]);
    setGraph({ nodes: [], edges: [] });
    setGuards([]);
    setExecutions({});
    try {
      const project = await requestJson<{ id: string }>("/projects", {
        method: "POST",
        body: JSON.stringify({ repository_path: repositoryPath }),
      });
      const incident = await requestJson<{ id: string }>("/incidents", {
        method: "POST",
        body: JSON.stringify({ project_id: project.id, source_text: incidentText }),
      });
      const created = await requestJson<RunSummary>("/runs", {
        method: "POST",
        body: JSON.stringify({ project_id: project.id, incident_id: incident.id }),
      });
      setRun(created);
      const [actionData, evidenceData, graphData] = await Promise.all([
        requestJson<{ verdicts: ActionVerdict[] }>(`/runs/${created.id}/actions`),
        requestJson<{ evidence: Evidence[] }>(`/runs/${created.id}/evidence`),
        requestJson<EvidenceGraph>(`/runs/${created.id}/graph`),
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
    if (!run || isPublicDemo) return;
    setPendingAction("preview");
    setError(null);
    try {
      const result = await requestJson<{ guards: Guard[] }>(`/runs/${run.id}/guards/preview`, {
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
    if (!run || isPublicDemo) return;
    setPendingAction("decision");
    setError(null);
    try {
      const updated = await requestJson<Guard>(`/runs/${run.id}/guards/${guard.id}/approve`, {
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
    if (!run || isPublicDemo) return;
    setPendingAction("execution");
    setError(null);
    try {
      const result = await requestJson<GuardExecution>(`/runs/${run.id}/guards/${guard.id}/execute`, {
        method: "POST",
      });
      setExecutions((current) => ({ ...current, [guard.id]: result }));
      const listed = await requestJson<{ guards: Guard[] }>(`/runs/${run.id}/guards`);
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
            <span className="context-label">{isPublicDemo ? "Public sample" : "Local workspace"}</span>
            <span className="run-state">
              <span className="status-dot" aria-hidden="true" />
              {isPublicDemo ? "Read-only demo" : run ? `Run ${formatStatus(run.status)}` : "System ready"}
            </span>
          </div>
        </header>

        {isPublicDemo && (
          <div className="demo-banner" role="note">
            <div>
              <strong>Public sample</strong>
              <span>Explore a saved audit of a synthetic repository. Nothing here accesses your files.</span>
            </div>
            <a href="https://github.com/Naveenbtnk/RemedyGraph/blob/main/docs/PILOT.md">
              Run your own audit locally <span aria-hidden="true">↗</span>
            </a>
          </div>
        )}

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
            <p>{isPublicDemo ? "Read-only" : "Local-first"}</p>
            <small>
              {isPublicDemo
                ? "Bundled results only. Local audits run on your machine."
                : "Your repository stays inside the configured workspace."}
            </small>
          </div>
        </section>

        <Panel
          title={isPublicDemo ? "Explore the sample audit" : "Configure the audit"}
          kicker={isPublicDemo ? "Bundled incident I04" : "New assessment"}
          className="setup-panel"
        >
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
                readOnly={isPublicDemo}
                required
              />
              <small id="repository-help">
                {isPublicDemo
                  ? "This public site does not access repositories."
                  : "Must be inside the configured workspace root."}
              </small>
            </label>
            <label>
              <span>Incident postmortem</span>
              <textarea
                value={incidentText}
                onChange={(event) => setIncidentText(event.target.value)}
                rows={8}
                maxLength={1_000_000}
                aria-describedby="incident-help"
                readOnly={isPublicDemo}
                required
              />
              <small id="incident-help">
                {isPublicDemo
                  ? "Bundled synthetic incident. No content is sent or stored."
                  : <>
                      Markdown or plain text with explicit corrective actions ·{" "}
                      {incidentText.length.toLocaleString()} characters
                    </>}
              </small>
            </label>
            <div className="form-action">
              <div className="limit-note">
                <span>Bounded by design</span>
                <small>6 model attempts · 3 investigation rounds</small>
              </div>
              <button className="primary" type="submit" disabled={busy || isPublicDemo}>
                <span>
                  {isPublicDemo
                    ? "Sample audit loaded"
                    : pendingAction === "audit" ? "Auditing…" : "Start audit"}
                </span>
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
          <span>{isPublicDemo ? "Bundled sample · no live API" : run ? run.id : "Awaiting first run"}</span>
        </div>
        <div className="summary-grid" aria-label="Audit summary">
          <Panel title="Run status" kicker="Progress" className="summary-card">
            <p className="metric metric-status">
              {run ? formatStatus(run.status) : "Not started"}
            </p>
            <p className="muted">
              {isPublicDemo
                ? "A deterministic sample result for safe public exploration."
                : run
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
              {actions.map((action, index) => (
                <ActionCard action={action} evidence={evidence} index={index} key={action.id} />
              ))}
            </div>
          )}
        </Panel>

        <div className="two-column">
          <Panel title="Evidence graph" kicker="Traceability" className="graph-panel">
            <p className="metric compact-metric">
              {graph.nodes.length} nodes <span>·</span> {graph.edges.length} edges
            </p>
            <p className="muted">
              {isPublicDemo
                ? "Selected relationships from the bundled audit; run locally for the full trace."
                : "An accessible inventory of the audit’s evidence relationships."}
            </p>
            <ul className="graph-list">
              {graph.nodes.map((node) => (
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
              {isPublicDemo
                ? "Guard creation and execution are disabled in the public demo."
                : "Previews never modify the repository. Every guard requires an explicit decision."}
            </p>
            <button
              className="secondary-action"
              type="button"
              onClick={previewGuards}
              disabled={!run || run.status !== "COMPLETE" || busy || isPublicDemo}
            >
              {isPublicDemo
                ? "Guard previews are local-only"
                : pendingAction === "preview" ? "Generating previews…" : "Generate guard previews"}
              <span aria-hidden="true">→</span>
            </button>
          </Panel>
        </div>

        {guards.map((guard) => (
          <GuardCard
            guard={guard}
            execution={executions[guard.id]}
            busy={busy}
            pendingAction={pendingAction}
            onDecision={decideGuard}
            onExecute={executeGuard}
            key={guard.id}
          />
        ))}

        <footer>
          <span>RemedyGraph</span>
          <span>Evidence-backed reliability auditing</span>
          <span>Local-first · 2026</span>
        </footer>
      </main>
    </div>
  );
}
