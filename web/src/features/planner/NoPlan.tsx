import type { PlannerRun } from "../../api/types";
import Button from "../../components/Button";
import StateMessage from "../../components/StateMessage";
import { noPlanTitle, offersMemberEdit } from "./plannerOutcome";

interface NoPlanProps {
  run: PlannerRun;
  onPlanAgain: () => void;
}

// A normal outcome (a notice), not an error.
function NoPlan({ run, onPlanAgain }: NoPlanProps) {
  // A button, not href="#members", so the address bar keeps the clean share link.
  function editMembers() {
    document.getElementById("members")?.scrollIntoView({ behavior: "smooth" });
  }

  return (
    <StateMessage
      tone="notice"
      title={noPlanTitle(run)}
      action={
        <>
          <Button onClick={onPlanAgain}>Plan again</Button>
          {offersMemberEdit(run) && <Button variant="ghost" onClick={editMembers}>Edit members</Button>}
        </>
      }
    >
      {run.message}
    </StateMessage>
  );
}

export default NoPlan;
