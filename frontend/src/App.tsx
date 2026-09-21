import { useState } from "react";

const BARCELONA = { lat: 41.3874, lon: 2.1686 };

const GRADES = ["4", "5", "5+", "6a", "6a+", "6b", "6b+", "6c", "6c+", "7a", "7a+", "7b", "7b+", "7c", "7c+", "8a", "8a+", "8b", "8b+", "8c", "8c+", "9a"];
// ^ a trimmed version of your backend's GRADE_ORDER, just for the dropdown options.
// TODO: type this out fully to match app/grades.py's GRADE_ORDER exactly, or
// come back to this once we discuss sharing a single source of truth (next step).

type Style = "sport" | "boulder" | "trad" | "multi-pitch";

function App() {
  const [minGrade, setMinGrade] = useState("6a");
  const [maxGrade, setMaxGrade] = useState("7a");
  const [style, setStyle] = useState<Style | "">("");
  const [maxDistanceKm, setMaxDistanceKm] = useState(120);

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    // TODO: build the query string and log it for now (console.log) —
    // we'll wire up the actual fetch in Step 2.3, once there's somewhere
    // to render the results. Use URLSearchParams to build it correctly:
    //
    // const params = new URLSearchParams({
    //   min_grade: minGrade,
    //   max_grade: maxGrade,
    //   origin_lat: String(BARCELONA.lat),
    //   origin_lon: String(BARCELONA.lon),
    //   max_distance_km: String(maxDistanceKm),
    // });
    // if (style) params.set("style", style);
    // console.log(params.toString());
    const params = new URLSearchParams({
      min_grade: minGrade,
      max_grade: maxGrade,
      origin_lat: String(BARCELONA.lat),
      origin_lon: String(BARCELONA.lon),
      max_distance_km: String(maxDistanceKm),
    });
    if (style) params.set("style", style);
    console.log(params.toString());
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
          <select value={style} onChange={(e) => setStyle(e.target.value as Style | "")}>
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
    </div>
  );
}

export default App;
