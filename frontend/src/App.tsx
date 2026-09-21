import { useState } from "react";

const BARCELONA = { lat: 41.3874, lon: 2.1686 };

const GRADES = ["4", "5", "5+", "6a", "6a+", "6b", "6b+", "6c", "6c+", "7a", "7a+", "7b", "7b+", "7c", "7c+", "8a", "8a+", "8b", "8b+", "8c", "8c+", "9a"];

type ClimbingStyle = "sport" | "boulder" | "trad" | "multi-pitch";

interface Sector {
  id: number;
  name: string;
  style: ClimbingStyle;
  grade_min: string;
  grade_max: string;
  crag_id: number;
  crag: {
    id: number;
    name: string;
    region: string;
  };
}


function App() {
  const [minGrade, setMinGrade] = useState("6a");
  const [maxGrade, setMaxGrade] = useState("7a");
  const [style, setStyle] = useState<ClimbingStyle | "">("");
  const [maxDistanceKm, setMaxDistanceKm] = useState(120);
  const [sectors, setSectors] = useState<Sector[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);


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
      // TODO: what should happen if response.ok is false? (e.g. your
      // backend's 400 "Invalid grade" case). Throw an Error with a useful
      // message so the catch block below handles it — don't let a 4xx
      // silently fall through to .json() as if it succeeded.
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
      {loading && <p>Searching...</p>}
      {error && <p style={{ color: "red" }}>Error: {error}</p>}
      {!loading && !error && sectors.length === 0 && <p>No matches yet — try a search.</p>}
      <ul>
        {sectors.map((sector) => (
          <li key={sector.id}>
            {sector.name} ({sector.crag.name}) — {sector.style} — {sector.grade_min} to {sector.grade_max}
          </li>
        ))}
      </ul>
    </div>
  );
}

export default App;