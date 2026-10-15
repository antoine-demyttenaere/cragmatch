import { useEffect, useState, type ReactNode } from "react";

import type { PlannerRun } from "../../api/types";
import Button from "../../components/Button";
import StateMessage from "../../components/StateMessage";
import PlannerDiagram from "./PlannerDiagram";
import { firstNewStep, runPath } from "./runPath";
import StepList from "./StepList";
import styles from "./TraceReplay.module.css";
import type { GraphState } from "./usePlannerGraph";

const STEP_MS = 500;

interface TraceReplayProps {
  run: PlannerRun;
  graph: GraphState;
  onRetryGraph: () => void;
  // True for a run started or answered in this tab: it plays, instead of showing at once.
  animate: boolean;
  // The outcome (proposal, plan or no plan), shown when the replay has ended.
  children: ReactNode;
}

function prefersReducedMotion(): boolean {
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

// The parent keys this by the trace length, so a longer trace starts a fresh counter.
function TraceReplay({ run, graph, onRetryGraph, animate, children }: TraceReplayProps) {
  const total = run.trace.length;
  const [reducedMotion] = useState(prefersReducedMotion);
  const [shown, setShown] = useState(animate && !reducedMotion ? firstNewStep(run.trace) : total);

  useEffect(() => {
    if (shown >= total) return;
    const timer = setTimeout(() => setShown((n) => n + 1), STEP_MS);
    return () => clearTimeout(timer);
  }, [shown, total]);

  const done = shown >= total;
  const path = runPath(run, shown);

  return (
    <div className={styles.replay}>
      {!reducedMotion && (
        <div className={styles.controls}>
          {!done && <Button variant="ghost" onClick={() => setShown(total)}>Skip</Button>}
          {done && total > 0 && <Button variant="ghost" onClick={() => setShown(0)}>Replay</Button>}
        </div>
      )}

      <div className={styles.grid}>
        <div className={styles.diagramArea}>
          {graph.state === "loading" && <StateMessage tone="loading" title="Loading the diagram" />}
          {graph.state === "error" && (
            <StateMessage
              tone="error"
              title="Couldn't load the diagram"
              action={<Button onClick={onRetryGraph}>Try again</Button>}
            >
              {graph.message}
            </StateMessage>
          )}
          {graph.state === "ready" && <PlannerDiagram graph={graph.graph} path={path} />}
        </div>
        <StepList run={run} shown={shown} path={path} />
      </div>

      {/* Hidden, not unmounted, so a reason typed during a Replay is kept. */}
      <div hidden={!done}>{children}</div>
    </div>
  );
}

export default TraceReplay;
