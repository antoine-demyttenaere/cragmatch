import { describe, expect, it } from "vitest";

import {
  makeRun,
  noCommonGroundRun,
  noMatchRun,
  plannedRun,
  rejectedOnceRun,
  threeRejectionsRun,
  waitingRun,
} from "./planner.fixtures";
import { describeSteps, stopLabel } from "./plannerText";

function texts(run: Parameters<typeof describeSteps>[0]): string[] {
  return describeSteps(run).map((line) => line.text);
}

describe("describeSteps", () => {
  it("gives one line per step with the changed field names as they are", () => {
    const lines = describeSteps(waitingRun);
    expect(lines).toHaveLength(3);
    expect(lines.map((l) => l.title)).toEqual(["Merge preferences", "Search sectors", "Pick a sector"]);
    expect(lines.map((l) => l.changed)).toEqual(waitingRun.trace.map((s) => s.changed));
  });

  it("merge_preferences says whether the group has common ground", () => {
    expect(texts(noCommonGroundRun)[0]).toBe("Compared everyone's preferences: no common ground.");
    expect(texts(waitingRun)[0]).toBe("Compared everyone's preferences: they have common ground.");
    expect(texts(makeRun({ trace: [waitingRun.trace[0]] }))[0]).toBe("Compared everyone's preferences.");
  });

  it("pick_sector names only the sector proposed now", () => {
    const lines = texts(rejectedOnceRun);
    expect(lines[2]).toBe("Proposed a sector.");
    expect(lines[4]).toBe("Proposed Siurana, Can Marges.");
  });

  it("each rejection quotes its own reason and an empty reason adds none", () => {
    const lines = texts(threeRejectionsRun);
    expect(lines[3]).toBe("The group said not this one: too far");
    expect(lines[5]).toBe("The group said not this one.");
    expect(lines[7]).toBe("The group said not this one: too hard");
    expect(lines[4]).toBe("Proposed another sector.");
  });

  it("search and pick say when there is nothing to propose", () => {
    const noMatch = texts(noMatchRun);
    expect(noMatch[1]).toBe("Searched for sectors everyone can climb: none found.");
    expect(noMatch[2]).toBe("No sector to propose, so the run ends.");
    expect(texts(threeRejectionsRun)[8]).toBe("No sector left to propose, so the run ends.");
  });

  it("an approved run describes the stays and the plan", () => {
    const lines = texts(plannedRun);
    expect(lines[3]).toBe("The group approved it.");
    expect(lines[4]).toBe("Found 2 places to stay near the crag.");
    expect(lines[5]).toBe("Put the plan together.");
    expect(lines[2]).toBe("Proposed Siurana, Can Marges.");
  });

  it("an unknown node says it ran", () => {
    const run = makeRun({ trace: [{ node: "mystery_node", changed: [] }] });
    expect(texts(run)).toEqual(["Ran mystery_node."]);
  });
});

describe("stopLabel", () => {
  it("names the three endings", () => {
    expect(stopLabel("waiting")).toBe("Waiting for you");
    expect(stopLabel("planned")).toBe("Plan ready");
    expect(stopLabel("no_plan")).toBe("No plan");
  });
});
