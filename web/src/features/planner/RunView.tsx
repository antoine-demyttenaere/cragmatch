import type { PlannerRun } from "../../api/types";
import Button from "../../components/Button";
import StateMessage from "../../components/StateMessage";
import NoPlan from "./NoPlan";
import PlanResult from "./PlanResult";
import ProposalPanel from "./ProposalPanel";
import styles from "./RunView.module.css";

interface RunViewProps {
  run: PlannerRun;
  notice: string | null;
  onAnswer: (approved: boolean, reason: string | null) => Promise<void>;
  onPlanAgain: () => void;
}

// One run. The parent keys it by run id, so anything kept here resets on a new run.
function RunView({ run, notice, onAnswer, onPlanAgain }: RunViewProps) {
  return (
    <div className={styles.run}>
      {notice && <StateMessage tone="notice">{notice}</StateMessage>}

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
    </div>
  );
}

export default RunView;
