import { useEffect, useState } from "react";

import { ApiError, apiRequest } from "../../api/client";
import type { PlannerAnswer, PlannerRun, PlannerRunStart } from "../../api/types";
import Button from "../../components/Button";
import Card from "../../components/Card";
import StateMessage from "../../components/StateMessage";
import PlannerStart from "./PlannerStart";
import styles from "./PlannerSection.module.css";
import RunView from "./RunView";

interface PlannerSectionProps {
  shareCode: string;
  memberCount: number;
}

// What the section shows. Only one of these is true at a time.
type View =
  | { state: "loading" }
  | { state: "start" }
  | { state: "run"; run: PlannerRun; notice: string | null }
  | { state: "error"; message: string };

// Never throws: a failed load is just another view.
async function loadLatest(runsPath: string): Promise<View> {
  try {
    const run = await apiRequest<PlannerRun | null>(`${runsPath}/latest`);
    return run ? { state: "run", run, notice: null } : { state: "start" };
  } catch (err) {
    return { state: "error", message: err instanceof Error ? err.message : "Something went wrong" };
  }
}

function PlannerSection({ shareCode, memberCount }: PlannerSectionProps) {
  const runsPath = `/groups/${encodeURIComponent(shareCode)}/planner/runs`;
  const [view, setView] = useState<View>({ state: "loading" });

  // State is set only after the await (react-hooks forbids a synchronous
  // update at the start of an effect).
  useEffect(() => {
    let cancelled = false;
    (async () => {
      const next = await loadLatest(runsPath);
      if (!cancelled) setView(next);
    })();
    return () => {
      cancelled = true;
    };
  }, [runsPath]);

  async function retry() {
    setView({ state: "loading" });
    setView(await loadLatest(runsPath));
  }

  async function start(body: PlannerRunStart) {
    const run = await apiRequest<PlannerRun>(runsPath, { method: "POST", body: JSON.stringify(body) });
    setView({ state: "run", run, notice: null });
  }

  async function answer(run: PlannerRun, approved: boolean, reason: string | null) {
    if (!run.proposal) return;
    const body: PlannerAnswer = { approved, reason, sector_id: run.proposal.sector_id };
    try {
      const next = await apiRequest<PlannerRun>(`${runsPath}/${run.run_id}/answer`, {
        method: "POST",
        body: JSON.stringify(body),
      });
      setView({ state: "run", run: next, notice: null });
    } catch (err) {
      if (!(err instanceof ApiError && err.status === 409)) throw err;
      // A friend answered first: show where the run is now.
      try {
        const current = await apiRequest<PlannerRun>(`${runsPath}/${run.run_id}`);
        setView({ state: "run", run: current, notice: "Someone already answered. This is where the run is now." });
      } catch {
        throw new Error("Someone already answered, and the run couldn't be reloaded. Reload the page.");
      }
    }
  }

  return (
    <Card>
      <section className={styles.section} aria-labelledby="planner-title">
        <h2 id="planner-title" className={styles.title}>Plan the trip</h2>
        <p className={styles.intro}>
          The planner proposes a sector everyone can climb. Approve it, and it finds places to stay.
        </p>

        {view.state === "loading" && <StateMessage tone="loading" title="Loading the planner" />}
        {view.state === "error" && (
          <StateMessage tone="error" title="Couldn't load the planner" action={<Button onClick={retry}>Try again</Button>}>
            {view.message}
          </StateMessage>
        )}
        {view.state === "start" && <PlannerStart memberCount={memberCount} onStart={start} />}
        {view.state === "run" && (
          <RunView
            key={view.run.run_id}
            run={view.run}
            notice={view.notice}
            onAnswer={(approved, reason) => answer(view.run, approved, reason)}
            onPlanAgain={() => setView({ state: "start" })}
          />
        )}
      </section>
    </Card>
  );
}

export default PlannerSection;
