import { useEffect, useState } from "react";

import { apiRequest } from "../../api/client";
import type { GroupStaysResponse, NearbyStay, Sector } from "../../api/types";
import Chip, { ChipButton } from "../../components/Chip";
import Field from "../../components/Field";
import Icon from "../../components/Icon";
import Sheet from "../../components/Sheet";
import StateMessage from "../../components/StateMessage";
import { STAY_TYPES, stayTypeLabel } from "../../constants";
import styles from "./StaysPanel.module.css";

interface StaysPanelProps {
  sector: Sector;
  // Set for a group's sector: adds dates, guests and Airbnb / Booking.com links.
  groupCode?: string;
  onClose: () => void;
}

// "2026-10-17" -> "Sat 17 Oct". Built from the parts so the browser's time
// zone can't shift the day.
function formatDay(isoDate: string): string {
  const [year, month, day] = isoDate.split("-").map(Number);
  return new Date(year, month - 1, day)
    .toLocaleDateString("en-GB", { weekday: "short", day: "numeric", month: "short" })
    .replace(",", "");
}

const DEFAULT_NIGHTS = 2; // the backend's default too

// A whole number from 1 to 30, or null (the param is then left out).
function wholeNumber(text: string): number | null {
  const n = Number(text);
  return text.trim() !== "" && Number.isInteger(n) && n >= 1 && n <= 30 ? n : null;
}

// Stays near one sector. With a groupCode it also plans the trip dates.
function StaysPanel({ sector, groupCode, onClose }: StaysPanelProps) {
  const [type, setType] = useState("");
  const [maxDistanceKm, setMaxDistanceKm] = useState(10);
  // Group mode only. The raw text is kept so a field can be emptied and
  // retyped; the URL uses the number only when the text is valid. Empty =
  // not chosen: the backend picks next Saturday and the group size.
  const [checkin, setCheckin] = useState("");
  const [nightsText, setNightsText] = useState(String(DEFAULT_NIGHTS));
  const [guestsText, setGuestsText] = useState("");
  const [stays, setStays] = useState<NearbyStay[]>([]);
  const [trip, setTrip] = useState<GroupStaysResponse | null>(null);
  // Which request the current results (or error) belong to.
  const [loadedUrl, setLoadedUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const params = new URLSearchParams({ max_distance_km: String(maxDistanceKm) });
  if (type) params.set("type", type);
  let url = `/sectors/${sector.id}/stays?${params}`;
  if (groupCode) {
    params.set("nights", String(wholeNumber(nightsText) ?? DEFAULT_NIGHTS));
    if (checkin) params.set("checkin", checkin);
    const guests = wholeNumber(guestsText);
    if (guests !== null) params.set("guests", String(guests));
    url = `/groups/${encodeURIComponent(groupCode)}/sectors/${sector.id}/stays?${params}`;
  }

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
        // The group endpoint wraps the same stays with the trip details.
        if (groupCode) {
          const data = await apiRequest<GroupStaysResponse>(url);
          if (cancelled) return;
          setStays(data.stays);
          setTrip(data);
        } else {
          const data = await apiRequest<NearbyStay[]>(url);
          if (cancelled) return;
          setStays(data);
        }
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
  }, [url, groupCode]);

  return (
    <Sheet title={`Stays near ${sector.name} (${sector.crag.name})`} onClose={onClose}>
      <div className={styles.filters}>
        {groupCode && (
          <div className={styles.trip}>
            <Field label="Check-in">
              {(fieldProps) => (
                <input {...fieldProps} type="date" value={checkin || trip?.checkin || ""} onChange={(e) => setCheckin(e.target.value)} />
              )}
            </Field>
            <Field label="Nights">
              {(fieldProps) => (
                <input {...fieldProps} type="number" min={1} max={30} value={nightsText} onChange={(e) => setNightsText(e.target.value)} />
              )}
            </Field>
            <Field label="Guests">
              {(fieldProps) => (
                <input
                  {...fieldProps}
                  type="number"
                  min={1}
                  max={30}
                  placeholder={String(trip?.guests ?? "")}
                  value={guestsText}
                  onChange={(e) => setGuestsText(e.target.value)}
                />
              )}
            </Field>
          </div>
        )}
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

      {!loading && !error && trip && (
        <div className={styles.booking}>
          <p>
            {trip.guests} {trip.guests === 1 ? "guest" : "guests"}, {formatDay(trip.checkin)} to {formatDay(trip.checkout)}
          </p>
          <div className={styles.bookingLinks}>
            <a href={trip.links.airbnb} target="_blank" rel="noopener noreferrer" className={styles.bookingLink}>
              Search on Airbnb <Icon name="external" size={16} />
            </a>
            <a href={trip.links.booking} target="_blank" rel="noopener noreferrer" className={styles.bookingLink}>
              Search on Booking.com <Icon name="external" size={16} />
            </a>
          </div>
        </div>
      )}

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
