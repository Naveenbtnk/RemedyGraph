import type { Verdict } from "../api/types";

export default function VerdictBadge({ verdict }: { verdict: Verdict }) {
  return <span className={`verdict verdict-${verdict.toLowerCase()}`}>{verdict}</span>;
}
