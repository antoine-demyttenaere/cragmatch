import { useEffect, useState } from "react";

import { apiRequest } from "../../api/client";
import type { PlannerGraph } from "../../api/types";

export type GraphState =
  | { state: "loading" }
  | { state: "ready"; graph: PlannerGraph }
  | { state: "error"; message: string };

type Result = { attempt: number } & ({ graph: PlannerGraph } | { message: string });

// Loads the graph structure once per mount (and again on reload()).
export function usePlannerGraph(): { graph: GraphState; reload: () => void } {
  const [attempt, setAttempt] = useState(0);
  // Which attempt the stored result belongs to: loading is derived from it.
  const [result, setResult] = useState<Result | null>(null);

  useEffect(() => {
    // setState only after the await (react-hooks forbids a synchronous update here).
    let cancelled = false;
    (async () => {
      try {
        const graph = await apiRequest<PlannerGraph>("/planner/graph");
        if (!cancelled) setResult({ attempt, graph });
      } catch (err) {
        if (!cancelled) {
          setResult({ attempt, message: err instanceof Error ? err.message : "Something went wrong" });
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [attempt]);

  let graph: GraphState = { state: "loading" };
  if (result && result.attempt === attempt) {
    graph = "graph" in result ? { state: "ready", graph: result.graph } : { state: "error", message: result.message };
  }
  return { graph, reload: () => setAttempt((n) => n + 1) };
}
