import { useState } from "react";

import { apiRequest } from "./api";
import { BARCELONA, GRADES, STYLES, type ClimbingStyle } from "./constants";
import SectorCard from "./SectorCard";
import StaysPanel from "./StaysPanel";
import type { ParsedFilters, Sector, SimilarMatch } from "./types";


// "relevance" keeps the order the API returned: the ranking for the
// similarity search, the database order for the other two searches.
type SortBy = "relevance" | "name" | "grade";

// Extra info the similarity search returns per sector, keyed by sector id.
type MatchInfo = Record<number, { similarity: number; reason: string | null }>;


// The three single-person searches from Stages 2-3: filters, natural
// language, and "describe the vibe".
function SearchPage() {
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
  const [staysFor, setStaysFor] = useState<Sector | null>(null);


  const sortedSectors = [...sectors].sort((a, b) => {
    if (sortBy === "name") {
      return a.name.localeCompare(b.name);
    }
    if (sortBy === "grade") {
      return GRADES.indexOf(a.grade_min) - GRADES.indexOf(b.grade_min);
    }
    return 0; // "relevance": keep the API's order (sort is stable)
  });


  // Every search starts the same way. It also clears the extras that belong
  // to ONE kind of search (parsed filters, match scores, open stays panel),
  // so they never show up next to results from a different search.
  function startSearch() {
    setLoading(true);
    setError(null);
    setNlParsedFilters(null);
    setMatchInfo({});
    setStaysFor(null);
  }

  // Runs a search function with the shared loading/error handling.
  async function run(search: () => Promise<void>) {
    startSearch();
    try {
      await search();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setLoading(false);
    }
  }


  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const params = new URLSearchParams({
      min_grade: minGrade,
      max_grade: maxGrade,
      origin_lat: String(BARCELONA.lat),
      origin_lon: String(BARCELONA.lon),
      max_distance_km: String(maxDistanceKm),
    });
    if (style) params.set("style", style);

    run(async () => {
      setSectors(await apiRequest<Sector[]>(`/sectors/search?${params}`));
    });
  }

  function handleNaturalSearch(e: React.FormEvent) {
    e.preventDefault();
    run(async () => {
      const data = await apiRequest<{ parsed_filters: ParsedFilters; results: Sector[] }>(
        "/search/natural", { method: "POST", body: JSON.stringify({ query: nlQuery }) },
      );
      setSectors(data.results);
      setNlParsedFilters(data.parsed_filters);
    });
  }

  function handleVibeSearch(e: React.FormEvent) {
    e.preventDefault();
    run(async () => {
      const data = await apiRequest<{ results: SimilarMatch[] }>(
        "/search/similar", { method: "POST", body: JSON.stringify({ query: vibeQuery, limit: 5 }) },
      );
      // The list reuses the same `sectors` state as the other two searches;
      // the scores and reasons go into matchInfo, keyed by id.
      setSectors(data.results.map((match) => match.sector));
      setMatchInfo(Object.fromEntries(
        data.results.map((match) => [match.sector.id, { similarity: match.similarity, reason: match.reason }]),
      ));
      setSortBy("relevance"); // best match first
    });
  }

  return (
    <div>
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
            {STYLES.map((s) => <option key={s} value={s}>{s}</option>)}
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
            onShowStays={setStaysFor}
          />
        ))}
      </ul>

      {staysFor && <StaysPanel sector={staysFor} onClose={() => setStaysFor(null)} />}
    </div>
  );
}

export default SearchPage;
