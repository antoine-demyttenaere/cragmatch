// LangGraph's own names for the two ends of every graph.
export const START_NODE = "__start__";
export const END_NODE = "__end__";

// Mirrors APPROVAL_NODE in backend/app/services/trip_planner.py. The paused node is
// not in the trace, so the diagram marks it from the run's status and this name.
// Rename both together.
export const APPROVAL_NODE = "approve_sector";

const LABELS: Record<string, string> = {
  [START_NODE]: "Start",
  [END_NODE]: "End",
  merge_preferences: "Merge preferences",
  search_sectors: "Search sectors",
  pick_sector: "Pick a sector",
  approve_sector: "Group decides",
  find_stays: "Find stays",
  propose_plan: "Propose plan",
  explain_conflicts: "Explain conflicts",
};

// A node the frontend has never seen keeps its raw name instead of breaking.
export function nodeLabel(node: string): string {
  return LABELS[node] ?? node;
}
