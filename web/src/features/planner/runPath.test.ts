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
import { edgeKey, firstNewStep, runPath } from "./runPath";

describe("runPath", () => {
  it("a waiting run goes merge, search, pick and stops at the approval node", () => {
    const path = runPath(waitingRun, 3);
    expect(path.visits.get("merge_preferences")).toBe(1);
    expect(path.visits.get("pick_sector")).toBe(1);
    expect(path.taken.has(edgeKey("__start__", "merge_preferences"))).toBe(true);
    expect(path.taken.has(edgeKey("search_sectors", "pick_sector"))).toBe(true);
    expect(path.taken.has(edgeKey("pick_sector", "approve_sector"))).toBe(true);
    expect(path.stop).toEqual({ node: "approve_sector", outcome: "waiting" });
  });

  it("a rejection takes the loop back to pick_sector and counts the visits", () => {
    const path = runPath(rejectedOnceRun, 5);
    expect(path.taken.has(edgeKey("approve_sector", "pick_sector"))).toBe(true);
    expect(path.visits.get("pick_sector")).toBe(2);
    expect(path.stop?.outcome).toBe("waiting");
  });

  it("an approved run ends at the end with a plan", () => {
    const path = runPath(plannedRun, 6);
    expect(path.taken.has(edgeKey("find_stays", "propose_plan"))).toBe(true);
    expect(path.taken.has(edgeKey("propose_plan", "__end__"))).toBe(true);
    expect(path.stop).toEqual({ node: "__end__", outcome: "planned" });
  });

  it("no common ground goes through explain_conflicts and never visits search", () => {
    const path = runPath(noCommonGroundRun, 2);
    expect(path.taken.has(edgeKey("merge_preferences", "explain_conflicts"))).toBe(true);
    expect(path.visits.has("search_sectors")).toBe(false);
    expect([...path.taken].some((key) => key.includes("search_sectors"))).toBe(false);
    expect(path.stop).toEqual({ node: "__end__", outcome: "no_plan" });
  });

  it("strict search with no sector ends after pick_sector without a plan", () => {
    const path = runPath(noMatchRun, 3);
    expect(path.taken.has(edgeKey("pick_sector", "__end__"))).toBe(true);
    expect(path.visits.has("approve_sector")).toBe(false);
    expect(path.stop?.outcome).toBe("no_plan");
  });

  it("three rejections end without a plan after four picks", () => {
    const path = runPath(threeRejectionsRun, 9);
    expect(path.visits.get("pick_sector")).toBe(4);
    expect(path.visits.get("approve_sector")).toBe(3);
    expect(path.stop?.outcome).toBe("no_plan");
  });

  it("a partial reveal shows only the first steps", () => {
    const path = runPath(waitingRun, 2);
    expect(path.visits.get("merge_preferences")).toBe(1);
    expect(path.visits.get("search_sectors")).toBe(1);
    expect(path.visits.has("pick_sector")).toBe(false);
    expect(path.current).toBe("search_sectors");
    expect(path.stop).toBeNull();
    expect([...path.taken].some((key) => key.endsWith("->pick_sector"))).toBe(false);
  });

  it("shown is clamped to the trace", () => {
    expect(runPath(waitingRun, 99)).toEqual(runPath(waitingRun, waitingRun.trace.length));
    expect(runPath(waitingRun, -1)).toEqual(runPath(waitingRun, 0));
  });

  it("an empty trace highlights nothing and has no stop", () => {
    const path = runPath(makeRun(), 0);
    expect(path.visits.size).toBe(0);
    expect(path.taken.size).toBe(0);
    expect(path.current).toBeNull();
    expect(path.stop).toBeNull();
  });

  it("a node the graph does not know is still counted", () => {
    const run = makeRun({ status: "no_plan", trace: [{ node: "mystery_node", changed: [] }] });
    const path = runPath(run, 1);
    expect(path.visits.get("mystery_node")).toBe(1);
    expect(path.taken.has(edgeKey("__start__", "mystery_node"))).toBe(true);
  });
});

describe("firstNewStep", () => {
  it("starts a new run at 0 and an answer at the last approval step", () => {
    expect(firstNewStep(waitingRun.trace)).toBe(0);
    expect(firstNewStep(rejectedOnceRun.trace)).toBe(3);
    expect(firstNewStep(plannedRun.trace)).toBe(3);
    expect(firstNewStep(threeRejectionsRun.trace)).toBe(7);
  });
});
