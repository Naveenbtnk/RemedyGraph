import type { GuardStatus } from "../api/types";

export type PendingAction = "audit" | "preview" | "decision" | "execution" | null;

export function canExecuteGuard(status: GuardStatus): boolean {
  return ["WRITTEN", "PASSED", "FAILED", "TIMED_OUT", "ERROR"].includes(status);
}

export function formatStatus(status: string): string {
  return status.toLowerCase().replaceAll("_", " ");
}
