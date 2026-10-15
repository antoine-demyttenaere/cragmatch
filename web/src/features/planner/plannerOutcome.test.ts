import { describe, expect, it } from "vitest";

import { makeRun, noCommonGroundRun, noMatchRun, plannedRun, threeRejectionsRun } from "./planner.fixtures";
import { noPlanTitle, offersMemberEdit } from "./plannerOutcome";

describe("plannerOutcome", () => {
  it("noPlanTitle tells no common ground, no matching sector and the other endings apart", () => {
    expect(noPlanTitle(noCommonGroundRun)).toBe("No common ground");
    expect(noPlanTitle(noMatchRun)).toBe("No sector suits everyone");
    expect(noPlanTitle(threeRejectionsRun)).toBe("No plan this time");
    expect(noPlanTitle(makeRun({ status: "no_plan" }))).toBe("No plan this time");
  });

  it("offersMemberEdit only when changing the members can help", () => {
    expect(offersMemberEdit(noCommonGroundRun)).toBe(true);
    expect(offersMemberEdit(noMatchRun)).toBe(true);
    expect(offersMemberEdit(threeRejectionsRun)).toBe(false);
    expect(offersMemberEdit(plannedRun)).toBe(false);
  });
});
