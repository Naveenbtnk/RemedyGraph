import type { Guard, GuardExecution } from "../api/types";
import { canExecuteGuard } from "../lib/status";
import type { PendingAction } from "../lib/status";
import Panel from "./Panel";

interface GuardCardProps {
  guard: Guard;
  execution?: GuardExecution;
  busy: boolean;
  pendingAction: PendingAction;
  onDecision: (guard: Guard, approved: boolean) => void;
  onExecute: (guard: Guard) => void;
}

export default function GuardCard({
  guard,
  execution,
  busy,
  pendingAction,
  onDecision,
  onExecute,
}: GuardCardProps) {
  return (
    <Panel title={guard.name} kicker="Guard preview" className="guard-panel">
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
          onClick={() => onDecision(guard, false)}
          disabled={guard.status !== "PREVIEWED" || busy}
        >
          {pendingAction === "decision" ? "Saving decision…" : "Reject"}
        </button>
        <button
          className="primary"
          type="button"
          onClick={() => onDecision(guard, true)}
          disabled={guard.status !== "PREVIEWED" || busy}
        >
          {pendingAction === "decision" ? "Saving decision…" : "Approve and write"}
        </button>
        <button
          type="button"
          onClick={() => onExecute(guard)}
          disabled={!canExecuteGuard(guard.status) || busy}
        >
          {pendingAction === "execution" ? "Executing guard…" : "Execute approved guard"}
        </button>
      </div>
      {execution && (
        <div className="execution">
          <h3>Execution: {execution.status}</h3>
          <p className="muted">
            Exit {execution.exit_code ?? "—"} · {execution.duration_ms.toFixed(0)} ms
          </p>
          <pre>{execution.stdout || execution.stderr || "No output"}</pre>
        </div>
      )}
    </Panel>
  );
}
