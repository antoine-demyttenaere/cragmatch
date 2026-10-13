import { useEffect, useState } from "react";

import { apiRequest } from "../../api/client";
import type { NearbyStay, Sector } from "../../api/types";
import Chip, { ChipButton } from "../../components/Chip";
import Field from "../../components/Field";
import Icon from "../../components/Icon";
import Sheet from "../../components/Sheet";
import StateMessage from "../../components/StateMessage";
import { STAY_TYPES, stayTypeLabel } from "../../constants";
import styles from "./StaysPanel.module.css";

interface StaysPanelProps {
  sector: Sector;
  onClose: () => void;
}

// Single-sector stays (group booking options come with the group screen).
function StaysPanel({ sector, onClose }: StaysPanelProps) {
  const [type, setType] = useState("");
  const [maxDistanceKm, setMaxDistanceKm] = useState(10);
  const [stays, setStays] = useState<NearbyStay[]>([]);
  // Which request the current results (or error) belong to.
  const [loadedUrl, setLoadedUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const params = new URLSearchParams({ max_distance_km: String(maxDistanceKm) });
  if (type) params.set("type", type);
  const url = `/sectors/${sector.id}/stays?${params}`;

  // Loading is derived, not stored: we're loading whenever the results on
  // screen belong to a different request than the one the filters describe.
  const loading = loadedUrl !== url;

  useEffect(() => {
    // `cancelled` stops a slow, older response from overwriting a newer one
    // if the filters change quickly. No setState before the await: the
    // react-hooks lint rule forbids synchronous updates at the start of an effect.
    let cancelled = false;
    (async () => {
      try {
        const data = await apiRequest<NearbyStay[]>(url);
        if (cancelled) return;
        setStays(data);
        setError(null);
      } catch (err) {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : "Something went wrong");
      }
      setLoadedUrl(url);
    })();

    return () => {
      cancelled = true;
    };
  }, [url]);

  return (
    <Sheet title={`Stays near ${sector.name} (${sector.crag.name})`} onClose={onClose}>
      <div className={styles.filters}>
        <div role="group" aria-label="Stay type" className={styles.types}>
          <ChipButton selected={type === ""} onClick={() => setType("")}>Any</ChipButton>
          {STAY_TYPES.map((t) => (
            <ChipButton key={t} selected={type === t} onClick={() => setType(t)}>{stayTypeLabel(t)}</ChipButton>
          ))}
        </div>
        <Field label={`Within ${maxDistanceKm} km`}>
          {(fieldProps) => (
            <input
              {...fieldProps}
              type="range"
              min={1}
              max={50}
              value={maxDistanceKm}
              onChange={(e) => setMaxDistanceKm(Number(e.target.value))}
            />
          )}
        </Field>
      </div>

      {loading && <StateMessage tone="loading" title="Loading stays" />}
      {!loading && error && <StateMessage tone="error" title="Couldn't load stays">{error}</StateMessage>}
      {!loading && !error && stays.length === 0 && (
        <StateMessage tone="empty" title="No stays found">
          No stays within {maxDistanceKm} km. Try a bigger radius.
        </StateMessage>
      )}
      {!loading && !error && stays.length > 0 && (
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
      )}
    </Sheet>
  );
}

export default StaysPanel;
