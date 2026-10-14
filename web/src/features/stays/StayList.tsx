import type { NearbyStay } from "../../api/types";
import Chip from "../../components/Chip";
import Icon from "../../components/Icon";
import { stayTypeLabel } from "../../constants";
import styles from "./StayList.module.css";

function StayList({ stays }: { stays: NearbyStay[] }) {
  return (
    <ul className={styles.list}>
      {stays.map(({ stay, distance_km }) => (
        <li key={stay.id} className={styles.stay}>
          <span className={styles.icon}><Icon name="tent" size={22} /></span>
          <div className={styles.info}>
            <p className={styles.name}>{stay.name}</p>
            <p className={styles.meta}>
              {stayTypeLabel(stay.type)} · {distance_km} km
              {stay.price_range && <> · {stay.price_range}</>}
            </p>
            {stay.source === "curated" && <Chip tone="grade">Hand-picked</Chip>}
          </div>
          {stay.url && (
            <a href={stay.url} target="_blank" rel="noopener noreferrer" className={styles.link} aria-label={`${stay.name} website`}>
              <Icon name="external" />
            </a>
          )}
        </li>
      ))}
    </ul>
  );
}

export default StayList;
