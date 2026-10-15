import type { PlannerRun } from "../../api/types";
import { APPROVAL_NODE, END_NODE, START_NODE } from "./plannerNodes";

export type Outcome = "waiting" | "planned" | "no_plan";

export interface RunPath {
  visits: Map<string, number>;
  taken: Set<string>;
  current: string | null;
  stop: { node: string; outcome: Outcome } | null;
}

export function edgeKey(source: string, target: string): string {
  return `${source}->${target}`;
}

// What the diagram highlights after the first `shown` steps of the trace.
export function runPath(run: Pick<PlannerRun, "trace" | "status">, shown: number): RunPath {
  const total = run.trace.length;
  const count = Math.min(Math.max(shown, 0), total);
  const steps = run.trace.slice(0, count).map((step) => step.node);
  const done = count >= total;

  const visits = new Map<string, number>();
  const taken = new Set<string>();
  const bump = (node: string) => visits.set(node, (visits.get(node) ?? 0) + 1);

  if (count > 0) {
    bump(START_NODE);
    taken.add(edgeKey(START_NODE, steps[0]));
  }
  steps.forEach((node, i) => {
    bump(node);
    if (i > 0) taken.add(edgeKey(steps[i - 1], node));
  });

  // An empty trace has no last step to continue from, so it has no stop either.
  if (total === 0 || !done) {
    return { visits, taken, current: count > 0 ? steps[count - 1] : null, stop: null };
  }

  const last = steps[count - 1];
  if (run.status === "waiting_for_approval") {
    // The paused node is not in the trace: add it from the status.
    taken.add(edgeKey(last, APPROVAL_NODE));
    return { visits, taken, current: null, stop: { node: APPROVAL_NODE, outcome: "waiting" } };
  }
  bump(END_NODE);
  taken.add(edgeKey(last, END_NODE));
  const outcome = run.status === "planned" ? "planned" : "no_plan";
  return { visits, taken, current: null, stop: { node: END_NODE, outcome } };
}

// A start runs from step 0, and an answer resumes at the approval node, so the
// steps of the latest answer begin at the last approval step. That is why nothing
// else has to remember the old trace.
export function firstNewStep(trace: PlannerRun["trace"]): number {
  for (let i = trace.length - 1; i >= 0; i--) {
    if (trace[i].node === APPROVAL_NODE) return i;
  }
  return 0;
}
