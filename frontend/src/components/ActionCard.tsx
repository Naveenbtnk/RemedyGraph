import type { ActionVerdict, Evidence } from "../api/types";
import VerdictBadge from "./VerdictBadge";

interface ActionCardProps {
  action: ActionVerdict;
  evidence: Evidence[];
  index: number;
}

export default function ActionCard({ action, evidence, index }: ActionCardProps) {
  const records = evidence.filter((item) => item.action_id === action.action_id);

  return (
    <details className="action-card">
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
}
