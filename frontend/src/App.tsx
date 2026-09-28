import { useState } from "react";

import type { Sector, ParsedFilters, SimilarMatch } from "./types";

import SectorCard from "./SectorCard";


const API_URL = "http://localhost:8000";

const BARCELONA = { lat: 41.3874, lon: 2.1686 };

const GRADES = ["4", "5", "5+", "6a", "6a+", "6b", "6b+", "6c", "6c+", "7a", "7a+", "7b", "7b+", "7c", "7c+", "8a", "8a+", "8b", "8b+", "8c", "8c+", "9a"];

type ClimbingStyle = "sport" | "boulder" | "trad" | "multi-pitch";

// "relevance" keeps the order the API returned: the ranking for the
// similarity search, the database order for the other two searches.
type SortBy = "relevance" | "name" | "grade";

// Extra info the similarity search returns per sector, keyed by sector id.
type MatchInfo = Record<number, { similarity: number; reason: string | null }>;


// Turn a failed response into a readable message. The backend's errors come
// in three shapes:
//   - our own HTTPExceptions:        {"detail": "some message"}
//   - FastAPI request validation:    {"detail": [{"msg": "...", ...}, ...]}
//   - slowapi's rate limit (429):    {"error": "Rate limit exceeded: 10 per 1 minute"}
async function errorMessage(response: Response): Promise<string> {
  try {
    const body = await response.json();
    if (typeof body.detail === "string") return body.detail;
    if (Array.isArray(body.detail) && body.detail[0]?.msg) return body.detail[0].msg;
    if (typeof body.error === "string") return body.error;
  } catch {
    // The body wasn't JSON (e.g. a plain-text 500): fall through.
  }
  return `Request failed (HTTP ${response.status})`;
}


function App() {
  const [minGrade, setMinGrade] = useState("6a");
  const [maxGrade, setMaxGrade] = useState("7a");
  const [style, setStyle] = useState<ClimbingStyle | "">("");
  const [maxDistanceKm, setMaxDistanceKm] = useState(120);
  const [sectors, setSectors] = useState<Sector[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sortBy, setSortBy] = useState<SortBy>("relevance");
  const [nlQuery, setNlQuery] = useState("");
  const [nlParsedFilters, setNlParsedFilters] = useState<ParsedFilters | null>(null);
  const [vibeQuery, setVibeQuery] = useState("");
  const [matchInfo, setMatchInfo] = useState<MatchInfo>({});


  const sortedSectors = [...sectors].sort((a, b) => {
    if (sortBy === "name") {
      return a.name.localeCompare(b.name);
    }
    if (sortBy === "grade") {
      return a.grade_min.localeCompare(b.grade_min);
    }
    return 0; // "relevance": keep the API's order (sort is stable)
  });


  // Every search starts the same way. It also clears the extras that belong
  // to ONE kind of search (parsed filters, match scores), so they never show
  // up next to results from a different search.
  function startSearch() {
    setLoading(true);
    setError(null);
    setNlParsedFilters(null);
    setMatchInfo({});
  }


  async function handleNaturalSearch(e: React.FormEvent) {
    e.preventDefault();
    startSearch();

    try {
      const response = await fetch(`${API_URL}/search/natural`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: nlQuery }),
      });

      if (!response.ok) {
        throw new Error(await errorMessage(response));
      }

      const data = await response.json();
      setSectors(data.results);
      setNlParsedFilters(data.parsed_filters);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setLoading(false);
    }
  }


  async function handleVibeSearch(e: React.FormEvent) {
    e.preventDefault();
    startSearch();

    try {
      const response = await fetch(`${API_URL}/search/similar`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: vibeQuery, limit: 5 }),
      });

      if (!response.ok) {
        throw new Error(await errorMessage(response));
      }

      const data: { results: SimilarMatch[] } = await response.json();
      // The list itself reuses the same `sectors` state as the other two
      // searches; the scores and reasons go into matchInfo, keyed by id.
      setSectors(data.results.map((match) => match.sector));
      setMatchInfo(
        Object.fromEntries(
          data.results.map((match) => [
            match.sector.id,
            { similarity: match.similarity, reason: match.reason },
          ]),
        ),
      );
      setSortBy("relevance"); // best match first
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setLoading(false);
    }
  }


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

    startSearch();

    try {
      const response = await fetch(`${API_URL}/sectors/search?${params}`);
      if (!response.ok) {
        throw new Error(await errorMessage(response));
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

      <form onSubmit={handleNaturalSearch}>
        <label>
          Describe your ideal climbing day:
          <input
            type="text"
            value={nlQuery}
            onChange={(e) => setNlQuery(e.target.value)}
            placeholder="somewhere 6a-7a, 1.5h from Barcelona, sport climbing"
          />
        </label>
        <button type="submit">Search</button>
      </form>

      <form onSubmit={handleVibeSearch}>
        <label>
          Describe the vibe you're after:
          <input
            type="text"
            value={vibeQuery}
            onChange={(e) => setVibeQuery(e.target.value)}
            placeholder="quiet crag, short approach"
          />
        </label>
        <button type="submit">Find similar</button>
      </form>

      {nlParsedFilters && (
        <p>
          Searching: {nlParsedFilters.min_grade}–{nlParsedFilters.max_grade}
          {nlParsedFilters.style ? `, ${nlParsedFilters.style}` : ""}
          , ≤{nlParsedFilters.max_distance_km}km
        </p>
      )}

      <label>
        Sort by:
        <select value={sortBy} onChange={(e) => setSortBy(e.target.value as SortBy)}>
          <option value="relevance">Relevance</option>
          <option value="name">Name</option>
          <option value="grade">Grade (easiest first)</option>
        </select>
      </label>

      {loading && <p>Searching...</p>}
      {error && <p style={{ color: "red" }}>Error: {error}</p>}
      {!loading && !error && sectors.length === 0 && <p>No matches yet — try a search.</p>}
      <ul>
        {sortedSectors.map((sector) => (
          <SectorCard
            key={sector.id}
            sector={sector}
            similarity={matchInfo[sector.id]?.similarity}
            reason={matchInfo[sector.id]?.reason}
          />
        ))}
      </ul>
    </div>
  );
}

export default App;
