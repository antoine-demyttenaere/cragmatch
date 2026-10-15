import type { PlannerRun } from "../../api/types";
import { nodeLabel } from "./plannerNodes";
import type { Outcome } from "./runPath";

export interface StepLine {
  node: string;
  title: string;
  text: string;
  // Field names exactly as the trace has them.
  changed: string[];
}

type TextRun = Pick<PlannerRun, "trace" | "status" | "rejections" | "proposal" | "plan">;

const NOT_THIS_ONE = "The group said not this one";

function mergeText(next: string | undefined): string {
  // The step changes the same fields either way, so the next node says what it found.
  if (next === "explain_conflicts") return "Compared everyone's preferences: no common ground.";
  if (next === "search_sectors") return "Compared everyone's preferences: they have common ground.";
  return "Compared everyone's preferences.";
}

function staysText(run: TextRun): string {
  if (!run.plan) return "Looked for places to stay near the crag.";
  const count = run.plan.stays.length;
  const places = count === 0 ? "no places" : count === 1 ? "1 place" : `${count} places`;
  return `Found ${places} to stay near the crag.`;
}

// `proposalIndex` counts the proposing picks so far, from 0.
function proposalText(run: TextRun, proposalIndex: number): string {
  if (proposalIndex < run.rejections.length) {
    return proposalIndex === 0 ? "Proposed a sector." : "Proposed another sector.";
  }
  // The turned-down sectors can't be named: only the current proposal or the plan can.
  const sector = run.proposal ?? run.plan?.sector;
  return sector ? `Proposed ${sector.crag_name}, ${sector.sector_name}.` : "Proposed a sector.";
}

function decisionText(run: TextRun, rejectionIndex: number): string {
  const reason = run.rejections[rejectionIndex]?.reason;
  return reason ? `${NOT_THIS_ONE}: ${reason}` : `${NOT_THIS_ONE}.`;
}

export function describeSteps(run: TextRun): StepLine[] {
  let proposals = 0;
  let rejections = 0;

  return run.trace.map((step, i) => {
    let text: string;
    switch (step.node) {
      case "merge_preferences":
        text = mergeText(run.trace[i + 1]?.node);
        break;
      case "search_sectors":
        text = step.changed.includes("message")
          ? "Searched for sectors everyone can climb: none found."
          : "Searched for sectors everyone can climb.";
        break;
      case "pick_sector":
        if (step.changed.includes("message")) {
          text = run.rejections.length === 0
            ? "No sector to propose, so the run ends."
            : "No sector left to propose, so the run ends.";
        } else {
          text = proposalText(run, proposals++);
        }
        break;
      case "approve_sector":
        text = step.changed.includes("rejections")
          ? decisionText(run, rejections++)
          : "The group approved it.";
        break;
      case "find_stays":
        text = staysText(run);
        break;
      case "propose_plan":
        // Its fields are the same when the sector was deleted, so the status decides.
        text = run.status === "planned" ? "Put the plan together." : "Couldn't put a plan together.";
        break;
      case "explain_conflicts":
        text = "Wrote down why the group has no common ground.";
        break;
      default:
        text = `Ran ${step.node}.`;
    }
    return { node: step.node, title: nodeLabel(step.node), text, changed: step.changed };
  });
}

export function stopLabel(outcome: Outcome): string {
  if (outcome === "waiting") return "Waiting for you";
  if (outcome === "planned") return "Plan ready";
  return "No plan";
}
