import type { MergedFilters } from "../../api/types";
import Chip from "../../components/Chip";
import { styleLabel } from "../../constants";
import styles from "../search/UnderstoodFilters.module.css";

// What a strict search agreed on, in the same strip as 016's "understood" filters.
function GroupFilters({ filters }: { filters: MergedFilters }) {
  return (
    <div className={styles.strip}>
      <p className={styles.title}>Everyone agrees on</p>
      <div className={styles.chips}>
        <Chip tone="grade">{filters.grade_min} to {filters.grade_max}</Chip>
        <Chip>{filters.max_distance_km !== null ? `Within ${filters.max_distance_km} km` : "Any distance"}</Chip>
        <Chip>
          {filters.max_approach_minutes !== null ? `Max ${filters.max_approach_minutes} min walk-in` : "Any walk-in"}
        </Chip>
        {filters.styles && filters.styles.length > 0 ? (
          filters.styles.map((s) => <Chip key={s} tone="style">{styleLabel(s)}</Chip>)
        ) : (
          <Chip tone="style">Any style</Chip>
        )}
      </div>
    </div>
  );
}

export default GroupFilters;
