import type { PlannerRun } from "../../api/types";

// Told apart from the trace (node and field names), not the message text:
// the trace is structure, the message is wording that may change.
function noCommonGround(run: PlannerRun): boolean {
  return run.trace.some((step) => step.node === "explain_conflicts");
}

function noMatchingSector(run: PlannerRun): boolean {
  return run.trace.some((step) => step.node === "search_sectors" && step.changed.includes("message"));
}

export function noPlanTitle(run: PlannerRun): string {
  if (noCommonGround(run)) return "No common ground";
  if (noMatchingSector(run)) return "No sector suits everyone";
  return "No plan this time";
}

// Editing members only helps when the problem is the members' preferences.
export function offersMemberEdit(run: PlannerRun): boolean {
  return noCommonGround(run) || noMatchingSector(run);
}
