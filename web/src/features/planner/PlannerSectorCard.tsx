import type { ReactNode } from "react";

import type { PlannerSector } from "../../api/types";
import Card from "../../components/Card";
import Chip from "../../components/Chip";
import Icon from "../../components/Icon";
import { styleLabel } from "../../constants";
import styles from "../search/SectorCard.module.css";
import { distanceLabel, walkInLabel } from "../search/sectorLabels";

interface PlannerSectorCardProps {
  sector: PlannerSector;
  // The actions under the card details.
  children?: ReactNode;
}

// The planner's flat sector (no region, no ids to open stays), in the look of SectorCard.
function PlannerSectorCard({ sector, children }: PlannerSectorCardProps) {
  return (
    <Card>
      <div className={styles.card}>
        <div>
          <h3 className={styles.name}>{sector.sector_name}</h3>
          <p className={styles.place}>
            <Icon name="pin" size={16} /> {sector.crag_name}
          </p>
        </div>

        <div className={styles.chips}>
          <Chip tone="grade">{sector.grade_min} to {sector.grade_max}</Chip>
          <Chip tone="style">{styleLabel(sector.style)}</Chip>
        </div>

        <p className={styles.walk}>
          <Icon name="clock" size={16} /> {walkInLabel(sector.approach_minutes)} · {distanceLabel(sector.distance_km)}
        </p>

        {children}
      </div>
    </Card>
  );
}

export default PlannerSectorCard;
