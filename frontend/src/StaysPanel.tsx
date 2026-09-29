import { useEffect, useState } from "react";

import { apiRequest } from "./api";
import { STAY_TYPES } from "./constants";
import type { GroupStaysResponse, NearbyStay, Sector } from "./types";


interface StaysPanelProps {
  sector: Sector;
  // With a group: use the group endpoint (booking links sized for the group).
  groupCode?: string;
  onClose: () => void;
}

function StaysPanel({ sector, groupCode, onClose }: StaysPanelProps) {
  const [type, setType] = useState("");
  const [maxDistanceKm, setMaxDistanceKm] = useState(10);
  const [nights, setNights] = useState(2);
  const [guests, setGuests] = useState<number | "">("");     // "" = let the backend use the member count
  const [checkin, setCheckin] = useState("");                  // "" = let the backend pick next Saturday
  const [stays, setStays] = useState<NearbyStay[]>([]);
  const [trip, setTrip] = useState<GroupStaysResponse | null>(null);
  // Which request the current results (or error) belong to.
  const [loadedUrl, setLoadedUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // The request the current filters describe, computed on every render.
  const params = new URLSearchParams({ max_distance_km: String(maxDistanceKm) });
  if (type) params.set("type", type);
  if (groupCode) {
    params.set("nights", String(nights));
    if (guests !== "") params.set("guests", String(guests));
    if (checkin) params.set("checkin", checkin);
  }
  const url = groupCode
    ? `/groups/${groupCode}/sectors/${sector.id}/stays?${params}`
    : `/sectors/${sector.id}/stays?${params}`;

  // Loading is derived, not stored: we're loading whenever the results on
  // screen belong to a different request than the one the filters describe.
  const loading = loadedUrl !== url;

  useEffect(() => {
    // Re-fetch whenever the URL changes. `cancelled` stops a slow, older
    // response from overwriting a newer one if filters change quickly.
    // (No setState before the await: React's lint rule forbids synchronous
    // state updates at the start of an effect.)
    let cancelled = false;
    (async () => {
      try {
        if (groupCode) {
          const data = await apiRequest<GroupStaysResponse>(url);
          if (cancelled) return;
          setTrip(data);
          setStays(data.stays);
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
    <section style={{ border: "1px solid #ccc", padding: 12, marginTop: 12 }}>
      <h3>
        Stays near {sector.name} ({sector.crag.name}){" "}
        <button type="button" onClick={onClose}>Close</button>
      </h3>

      <label>
        Type:
        <select value={type} onChange={(e) => setType(e.target.value)}>
          <option value="">Any</option>
          {STAY_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
        </select>
      </label>{" "}
      <label>
        Within (km):
        <input type="number" min={1} max={50} value={maxDistanceKm}
          onChange={(e) => setMaxDistanceKm(Number(e.target.value) || 10)} style={{ width: 60 }} />
      </label>

      {groupCode && (
        <div>
          <label>
            Check-in:
            <input type="date" value={checkin || trip?.checkin || ""} onChange={(e) => setCheckin(e.target.value)} />
          </label>{" "}
          <label>
            Nights:
            <input type="number" min={1} max={30} value={nights}
              onChange={(e) => setNights(Number(e.target.value) || 1)} style={{ width: 50 }} />
          </label>{" "}
          <label>
            Guests:
            <input type="number" min={1} max={30} value={guests === "" ? trip?.guests ?? "" : guests}
              onChange={(e) => setGuests(e.target.value === "" ? "" : Number(e.target.value))} style={{ width: 50 }} />
          </label>
          {trip && (
            <p>
              {/* No public Airbnb/Booking API: these open their own search, prefilled. */}
              <a href={trip.links.airbnb} target="_blank" rel="noopener noreferrer">Search on Airbnb</a>
              {" · "}
              <a href={trip.links.booking} target="_blank" rel="noopener noreferrer">Search on Booking.com</a>
              {" "}({trip.guests} guests, {trip.checkin} → {trip.checkout})
            </p>
          )}
        </div>
      )}

      {loading && <p>Loading stays...</p>}
      {error && <p style={{ color: "red" }}>Error: {error}</p>}
      {!loading && !error && stays.length === 0 && <p>No stays found within {maxDistanceKm} km.</p>}
      <ul>
        {stays.map(({ stay, distance_km }) => (
          <li key={stay.id}>
            {stay.name} — {stay.type} — {distance_km} km
            {stay.price_range && <> — {stay.price_range}</>}
            {stay.url && <> — <a href={stay.url} target="_blank" rel="noopener noreferrer">website</a></>}
            {stay.source === "curated" && <> — <em>hand-picked</em></>}
          </li>
        ))}
      </ul>
    </section>
  );
}

export default StaysPanel;
