import type { PlannerRun } from "../../api/types";
import Button from "../../components/Button";
import StateMessage from "../../components/StateMessage";
import NoPlan from "./NoPlan";
import PlanResult from "./PlanResult";
import ProposalPanel from "./ProposalPanel";
import styles from "./RunView.module.css";
import TraceReplay from "./TraceReplay";
import { usePlannerGraph } from "./usePlannerGraph";

interface RunViewProps {
  run: PlannerRun;
  notice: string | null;
  // True for a run started or answered in this tab: its trace plays step by step.
  animate: boolean;
  onAnswer: (approved: boolean, reason: string | null) => Promise<void>;
  onPlanAgain: () => void;
}

// One run. The parent keys it by run id, so anything kept here resets on a new run.
function RunView({ run, notice, animate, onAnswer, onPlanAgain }: RunViewProps) {
  // Loaded here, not in PlannerSection: this mounts after a planner response, when the
  // planner is already built. Two first requests at once could set it up twice.
  const { graph, reload } = usePlannerGraph();

  return (
    <div className={styles.run}>
      {notice && <StateMessage tone="notice">{notice}</StateMessage>}

      {/* A longer trace is a new thing to play: the key gives it a fresh counter without an effect. */}
      <TraceReplay key={run.trace.length} run={run} graph={graph} onRetryGraph={reload} animate={animate}>
        {run.status === "waiting_for_approval" && run.proposal && (
          <>
            {/* Keyed by sector, so the reason box starts empty for each proposal. */}
            <ProposalPanel key={run.proposal.sector_id} proposal={run.proposal} onAnswer={onAnswer} />
            <div className={styles.actions}>
              <Button variant="ghost" onClick={onPlanAgain}>Start over</Button>
            </div>
          </>
        )}
        {run.status === "planned" && run.plan && <PlanResult plan={run.plan} onPlanAgain={onPlanAgain} />}
        {run.status === "no_plan" && <NoPlan run={run} onPlanAgain={onPlanAgain} />}
      </TraceReplay>
    </div>
  );
}

export default RunView;
