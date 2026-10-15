// Test data only: the real graph and traces the backend produces today.
import type { PlannerGraph, PlannerPlan, PlannerRun, PlannerSector, TraceStep } from "../../api/types";

export const PLANNER_GRAPH: PlannerGraph = {
  nodes: [
    "__start__",
    "merge_preferences",
    "search_sectors",
    "pick_sector",
    "approve_sector",
    "find_stays",
    "propose_plan",
    "explain_conflicts",
    "__end__",
  ],
  edges: [
    { source: "__start__", target: "merge_preferences", conditional: false },
    { source: "merge_preferences", target: "search_sectors", conditional: true },
    { source: "merge_preferences", target: "explain_conflicts", conditional: true },
    { source: "search_sectors", target: "pick_sector", conditional: false },
    { source: "pick_sector", target: "approve_sector", conditional: true },
    { source: "pick_sector", target: "__end__", conditional: true },
    { source: "approve_sector", target: "find_stays", conditional: true },
    { source: "approve_sector", target: "pick_sector", conditional: true },
    { source: "find_stays", target: "propose_plan", conditional: false },
    { source: "explain_conflicts", target: "__end__", conditional: false },
    { source: "propose_plan", target: "__end__", conditional: false },
  ],
};

export const SECTOR: PlannerSector = {
  sector_id: 7,
  sector_name: "Can Marges",
  crag_name: "Siurana",
  style: "sport",
  grade_min: "6a",
  grade_max: "7a",
  approach_minutes: 15,
  distance_km: 150,
};

function step(node: string, changed: string[]): TraceStep {
  return { node, changed };
}

export const MERGE = step("merge_preferences", ["members", "guests", "filters", "conflicts"]);
export const SEARCH_FOUND = step("search_sectors", ["candidates"]);
export const SEARCH_NONE = step("search_sectors", ["candidates", "message"]);
export const PICK_PROPOSE = step("pick_sector", ["chosen_sector", "approved"]);
export const PICK_NONE = step("pick_sector", ["chosen_sector", "message"]);
export const APPROVE_YES = step("approve_sector", ["approved"]);
export const APPROVE_NO = step("approve_sector", ["approved", "rejections"]);
export const FIND_STAYS = step("find_stays", ["stays"]);
export const PROPOSE_PLAN = step("propose_plan", ["plan", "message"]);
export const EXPLAIN = step("explain_conflicts", ["message"]);

export function makeRun(partial: Partial<PlannerRun> = {}): PlannerRun {
  return {
    run_id: "run-1",
    share_code: "ABC123",
    status: "waiting_for_approval",
    checkin: "2026-10-17",
    nights: 2,
    guests: 2,
    proposal: null,
    plan: null,
    message: null,
    rejections: [],
    trace: [],
    created_at: "2026-10-14T10:00:00Z",
    ...partial,
  };
}

const PLAN: PlannerPlan = {
  sector: SECTOR,
  checkin: "2026-10-17",
  checkout: "2026-10-19",
  nights: 2,
  guests: 2,
  stays: [
    {
      stay: {
        id: 1,
        name: "Refugi A",
        type: "hostel",
        latitude: 41.2,
        longitude: 0.9,
        price_range: null,
        source: "curated",
        url: null,
      },
      distance_km: 2,
    },
    {
      stay: {
        id: 2,
        name: "Casa B",
        type: "apartment",
        latitude: 41.3,
        longitude: 0.9,
        price_range: null,
        source: "osm",
        url: null,
      },
      distance_km: 4,
    },
  ],
  links: { airbnb: "https://example.com/a", booking: "https://example.com/b" },
};

export const waitingRun = makeRun({
  proposal: SECTOR,
  trace: [MERGE, SEARCH_FOUND, PICK_PROPOSE],
});

export const rejectedOnceRun = makeRun({
  proposal: { ...SECTOR, sector_id: 8, sector_name: "Can Marges" },
  rejections: [{ sector_id: 5, reason: "too far" }],
  trace: [MERGE, SEARCH_FOUND, PICK_PROPOSE, APPROVE_NO, PICK_PROPOSE],
});

export const plannedRun = makeRun({
  status: "planned",
  plan: PLAN,
  trace: [MERGE, SEARCH_FOUND, PICK_PROPOSE, APPROVE_YES, FIND_STAYS, PROPOSE_PLAN],
});

export const noCommonGroundRun = makeRun({
  status: "no_plan",
  message: "No common ground",
  trace: [MERGE, EXPLAIN],
});

export const noMatchRun = makeRun({
  status: "no_plan",
  message: "No sector suits everyone",
  trace: [MERGE, SEARCH_NONE, PICK_NONE],
});

export const threeRejectionsRun = makeRun({
  status: "no_plan",
  rejections: [
    { sector_id: 5, reason: "too far" },
    { sector_id: 6, reason: "" },
    { sector_id: 7, reason: "too hard" },
  ],
  trace: [
    MERGE,
    SEARCH_FOUND,
    PICK_PROPOSE,
    APPROVE_NO,
    PICK_PROPOSE,
    APPROVE_NO,
    PICK_PROPOSE,
    APPROVE_NO,
    PICK_NONE,
  ],
});
