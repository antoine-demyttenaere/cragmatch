import type { Sector } from "../../api/types";
import Button from "../../components/Button";
import Card from "../../components/Card";
import Chip from "../../components/Chip";
import Icon from "../../components/Icon";
import { styleLabel } from "../../constants";
import styles from "./SectorCard.module.css";

interface SectorCardProps {
  sector: Sector;
  // Only set for results of the "Vibe" search.
  similarity?: number;
  reason?: string | null;
  onShowStays: (sector: Sector) => void;
}

function SectorCard({ sector, similarity, reason, onShowStays }: SectorCardProps) {
  const walkIn = sector.approach_minutes !== null ? `${sector.approach_minutes} min walk-in` : "Walk-in unknown";

  return (
    <Card as="li">
      <div className={styles.card}>
        <div className={styles.top}>
          <div>
            <h3 className={styles.name}>{sector.name}</h3>
            <p className={styles.place}>
              <Icon name="pin" size={16} /> {sector.crag.name}, {sector.crag.region}
            </p>
          </div>
          {similarity !== undefined && <Chip tone="highlight">{Math.round(similarity * 100)}% match</Chip>}
        </div>

        <div className={styles.chips}>
          <Chip tone="grade">{sector.grade_min} to {sector.grade_max}</Chip>
          <Chip tone="style">{styleLabel(sector.style)}</Chip>
        </div>

        <p className={styles.walk}>
          <Icon name="clock" size={16} /> {walkIn}
        </p>

        {reason && <blockquote className={styles.reason}>{reason}</blockquote>}

        <Button variant="secondary" onClick={() => onShowStays(sector)}>Stays nearby</Button>
      </div>
    </Card>
  );
}

export default SectorCard;
