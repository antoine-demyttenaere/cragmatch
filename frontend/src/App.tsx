import { useState } from "react";

import type { Sector } from "./types";

import SectorCard from "./SectorCard";


const BARCELONA = { lat: 41.3874, lon: 2.1686 };

const GRADES = ["4", "5", "5+", "6a", "6a+", "6b", "6b+", "6c", "6c+", "7a", "7a+", "7b", "7b+", "7c", "7c+", "8a", "8a+", "8b", "8b+", "8c", "8c+", "9a"];

type ClimbingStyle = "sport" | "boulder" | "trad" | "multi-pitch";

function App() {
  const [minGrade, setMinGrade] = useState("6a");
  const [maxGrade, setMaxGrade] = useState("7a");
  const [style, setStyle] = useState<ClimbingStyle | "">("");
  const [maxDistanceKm, setMaxDistanceKm] = useState(120);
  const [sectors, setSectors] = useState<Sector[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sortBy, setSortBy] = useState<"name" | "grade">("name");

  // TODO: compute a *sorted copy* of `sectors` for rendering — don't
  // mutate `sectors` itself (Array.prototype.sort() sorts in place,
  // which is a common React bug source: it can mutate state without
  // React noticing, since the array reference doesn't change).
  // [...sectors].sort((a, b) => ...) makes a copy first, then sorts that.
  //
  // For sortBy === "name": alphabetical, a.name.localeCompare(b.name)
  // For sortBy === "grade": use your backend's grade ordering concept —
  // for now, just sort by grade_min as a plain string (imperfect vs
  // true French-grade order, but consistent with what the user sees
  // without duplicating app/grades.py's logic in TypeScript yet).
  const sortedSectors = [...sectors].sort((a, b) => {
    if (sortBy === "name") {
      return a.name.localeCompare(b.name);
    }
    return a.grade_min.localeCompare(b.grade_min);
  });



  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();

    const params = new URLSearchParams({
      min_grade: minGrade,
      max_grade: maxGrade,
      origin_lat: String(BARCELONA.lat),
      origin_lon: String(BARCELONA.lon),
      max_distance_km: String(maxDistanceKm),
    });
    if (style) params.set("style", style);

    setLoading(true);
    setError(null);

    try {
      const response = await fetch(`http://localhost:8000/sectors/search?${params}`);
      if (!response.ok) {
        const body = await response.json();
        throw new Error(body.detail ?? "Failed to fetch sectors");
      }

      const data: Sector[] = await response.json();
      setSectors(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div>
      <h1>CragMatch</h1>
      <form onSubmit={handleSubmit}>
        <label>
          Min grade:
          <select value={minGrade} onChange={(e) => setMinGrade(e.target.value)}>
            {GRADES.map((g) => <option key={g} value={g}>{g}</option>)}
          </select>
        </label>

        <label>
          Max grade:
          <select value={maxGrade} onChange={(e) => setMaxGrade(e.target.value)}>
            {GRADES.map((g) => <option key={g} value={g}>{g}</option>)}
          </select>
        </label>

        <label>
          Style:
          <select value={style} onChange={(e) => setStyle(e.target.value as ClimbingStyle | "")}>
            <option value="">Any</option>
            <option value="sport">Sport</option>
            <option value="boulder">Boulder</option>
            <option value="trad">Trad</option>
            <option value="multi-pitch">Multi-pitch</option>
          </select>
        </label>

        <label>
          Max distance (km):
          <input
            type="number"
            value={maxDistanceKm}
            onChange={(e) => setMaxDistanceKm(Number(e.target.value))}
          />
        </label>

        <button type="submit">Search</button>
      </form>
      
      <label>
        Sort by:
        <select value={sortBy} onChange={(e) => setSortBy(e.target.value as "name" | "grade")}>
          <option value="name">Name</option>
          <option value="grade">Grade (easiest first)</option>
        </select>
      </label>

      {loading && <p>Searching...</p>}
      {error && <p style={{ color: "red" }}>Error: {error}</p>}
      {!loading && !error && sectors.length === 0 && <p>No matches yet — try a search.</p>}
      <ul>
        {sortedSectors.map((sector) => (
          <SectorCard key={sector.id} sector={sector} />
        ))}
      </ul>
    </div>
  );
}

export default App;