import { describeSteps, stopLabel } from "./plannerText";
import type { PlannerRun } from "../../api/types";
import type { RunPath } from "./runPath";
import styles from "./StepList.module.css";

interface StepListProps {
  run: PlannerRun;
  shown: number;
  path: RunPath;
}

function StepList({ run, shown, path }: StepListProps) {
  if (run.trace.length === 0) {
    return <p className={styles.empty}>No steps recorded for this run.</p>;
  }

  const lines = describeSteps(run).slice(0, shown);
  return (
    <ol className={styles.list} aria-live="polite">
      {lines.map((line, i) => (
        <li key={i} className={`${styles.step} ${path.current === line.node && i === shown - 1 ? styles.current : ""}`}>
          <span className={styles.number}>{i + 1}</span>
          <div className={styles.body}>
            <p className={styles.title}>{line.title}</p>
            <p className={styles.text}>{line.text}</p>
            <details className={styles.details}>
              <summary>Details</summary>
              {line.changed.length === 0 ? (
                <p>No fields changed</p>
              ) : (
                <ul>
                  {line.changed.map((field) => <li key={field}><code>{field}</code></li>)}
                </ul>
              )}
            </details>
          </div>
        </li>
      ))}
      {path.stop && (
        <li className={`${styles.step} ${styles.stop}`}>
          <span className={styles.number} aria-hidden="true">•</span>
          <div className={styles.body}>
            <p className={styles.title}>{stopLabel(path.stop.outcome)}</p>
          </div>
        </li>
      )}
    </ol>
  );
}

export default StepList;
