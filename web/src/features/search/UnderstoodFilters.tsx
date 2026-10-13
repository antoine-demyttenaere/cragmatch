import type { ParsedFilters } from "../../api/types";
import Chip from "../../components/Chip";
import { styleLabel } from "../../constants";
import styles from "./UnderstoodFilters.module.css";

function UnderstoodFilters({ filters }: { filters: ParsedFilters }) {
  return (
    <div className={styles.strip}>
      <p className={styles.title}>Here's what I understood</p>
      <div className={styles.chips}>
        <Chip tone="grade">{filters.min_grade} to {filters.max_grade}</Chip>
        {filters.style && <Chip tone="style">{styleLabel(filters.style)}</Chip>}
        <Chip>Within {filters.max_distance_km} km</Chip>
      </div>
    </div>
  );
}

export default UnderstoodFilters;
