export type GuardStatus =
  | "PREVIEWED"
  | "REJECTED"
  | "WRITTEN"
  | "PASSED"
  | "FAILED"
  | "TIMED_OUT"
  | "ERROR";

export function canExecuteGuard(status: GuardStatus): boolean {
  return ["WRITTEN", "PASSED", "FAILED", "TIMED_OUT", "ERROR"].includes(status);
}

export function formatStatus(status: string): string {
  return status.toLowerCase().replaceAll("_", " ");
}
