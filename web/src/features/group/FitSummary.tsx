import type { GroupSectorMatch } from "../../api/types";
import Chip from "../../components/Chip";
import styles from "./FitSummary.module.css";

function FitSummary({ match }: { match: GroupSectorMatch }) {
  const everyoneFits = match.fit_count === match.member_count;
  return (
    <div className={styles.summary}>
      <Chip tone={everyoneFits ? "highlight" : "neutral"}>{match.fit_count} of {match.member_count}</Chip>
      {match.fits.length > 0 && <p className={styles.fits}>Fits: {match.fits.join(", ")}</p>}
      {match.misfits.length > 0 && (
        <ul className={styles.misfits}>
          {match.misfits.map((misfit, index) => (
            // The reason is the backend's own wording ("too far (112 km > 80 km)").
            // Names aren't unique and misfits have no id, so the position is part of the key.
            <li key={`${index}-${misfit.name}`}>{misfit.name}: {misfit.reason}</li>
          ))}
        </ul>
      )}
    </div>
  );
}

export default FitSummary;
