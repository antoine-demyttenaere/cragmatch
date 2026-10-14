import type { PlannerPlan } from "../../api/types";
import Button from "../../components/Button";
import StateMessage from "../../components/StateMessage";
import StayList from "../stays/StayList";
import TripLinks from "../stays/TripLinks";
import PlannerSectorCard from "./PlannerSectorCard";
import styles from "./RunView.module.css";

function PlanResult({ plan, onPlanAgain }: { plan: PlannerPlan; onPlanAgain: () => void }) {
  return (
    <section aria-labelledby="plan-title" className={styles.run}>
      <h3 id="plan-title" className={styles.heading}>Your trip</h3>
      <PlannerSectorCard sector={plan.sector} />
      <TripLinks checkin={plan.checkin} checkout={plan.checkout} guests={plan.guests} links={plan.links} />
      {plan.stays.length > 0 ? (
        <StayList stays={plan.stays} />
      ) : (
        <StateMessage tone="empty" title="No stays found near the crag">
          The booking links still search the area.
        </StateMessage>
      )}
      <div className={styles.actions}>
        <Button variant="ghost" onClick={onPlanAgain}>Plan again</Button>
      </div>
    </section>
  );
}

export default PlanResult;
