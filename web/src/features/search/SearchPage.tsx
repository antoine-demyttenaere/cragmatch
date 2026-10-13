import { useState } from "react";

import { ApiError, apiRequest } from "../../api/client";
import type { NaturalSearchResponse, ParsedFilters, Sector, SimilarMatch, SimilarSearchResponse } from "../../api/types";
import Button from "../../components/Button";
import Field from "../../components/Field";
import SegmentedControl from "../../components/SegmentedControl";
import StateMessage from "../../components/StateMessage";
import { BARCELONA, GRADES } from "../../constants";
import StaysPanel from "../stays/StaysPanel";
import FilterForm, { type FilterValues } from "./FilterForm";
import NaturalForm from "./NaturalForm";
import SectorCard from "./SectorCard";
import styles from "./SearchPage.module.css";
import UnderstoodFilters from "./UnderstoodFilters";
import VibeForm from "./VibeForm";

type Mode = "filters" | "natural" | "vibe";

const MODES: { value: Mode; label: string }[] = [
  { value: "filters", label: "Filters" },
  { value: "natural", label: "Describe it (AI)" },
  { value: "vibe", label: "Vibe (AI)" },
];

// "relevance" keeps the order the API returned: the ranking for the vibe
// search, the database order for the other two.
type SortBy = "relevance" | "name" | "grade";

// The result belongs to the search that produced it, so parsed filters and
// scores can never show next to another search's results.
type SearchResult =
  | { kind: "filters"; sectors: Sector[] }
  | { kind: "natural"; sectors: Sector[]; parsed: ParsedFilters }
  | { kind: "vibe"; matches: SimilarMatch[] };

// What the results area shows. Only one of these is true at a time.
type View =
  | { state: "idle" }
  | { state: "loading" }
  | { state: "done"; result: SearchResult }
  | { state: "notice"; title: string; message: string } // the AI search couldn't help: not our user's fault
  | { state: "error"; message: string };

// A row to render, whichever search it came from.
interface Row {
  sector: Sector;
  similarity?: number;
  reason?: string | null;
}

function rowsOf(result: SearchResult): Row[] {
  if (result.kind === "vibe") {
    return result.matches.map((m) => ({ sector: m.sector, similarity: m.similarity, reason: m.reason }));
  }
  return result.sectors.map((sector) => ({ sector }));
}

function sortRows(rows: Row[], sortBy: SortBy): Row[] {
  const sorted = [...rows];
  if (sortBy === "name") sorted.sort((a, b) => a.sector.name.localeCompare(b.sector.name));
  if (sortBy === "grade") sorted.sort((a, b) => GRADES.indexOf(a.sector.grade_min) - GRADES.indexOf(b.sector.grade_min));
  return sorted;
}

// 422 = the text isn't a climbing search; 503 = Claude or Voyage is down;
// 429 = rate limit. All three are shown as a notice, not an error.
function isNoticeError(err: unknown): err is ApiError {
  return err instanceof ApiError && (err.status === 422 || err.status === 503 || err.status === 429);
}

function noticeTitle(err: ApiError): string {
  return err.status === 429 ? "Too many searches" : "The assistant couldn't help with that";
}

function SearchPage() {
  const [mode, setMode] = useState<Mode>("filters");
  const [view, setView] = useState<View>({ state: "idle" });
  const [sortBy, setSortBy] = useState<SortBy>("relevance");
  const [staysFor, setStaysFor] = useState<Sector | null>(null);

  const loading = view.state === "loading";

  async function run(search: () => Promise<SearchResult>) {
    setView({ state: "loading" });
    try {
      setView({ state: "done", result: await search() });
    } catch (err) {
      const message = err instanceof Error ? err.message : "Something went wrong";
      setView(isNoticeError(err) ? { state: "notice", title: noticeTitle(err), message } : { state: "error", message });
    }
  }

  function searchFilters(values: FilterValues) {
    const params = new URLSearchParams({
      min_grade: values.minGrade,
      max_grade: values.maxGrade,
      origin_lat: String(BARCELONA.lat),
      origin_lon: String(BARCELONA.lon),
      max_distance_km: String(values.maxDistanceKm),
    });
    if (values.style) params.set("style", values.style);
    run(async () => ({ kind: "filters", sectors: await apiRequest<Sector[]>(`/sectors/search?${params}`) }));
  }

  function searchNatural(query: string) {
    run(async () => {
      const data = await apiRequest<NaturalSearchResponse>(
        "/search/natural", { method: "POST", body: JSON.stringify({ query }) },
      );
      return { kind: "natural", sectors: data.results, parsed: data.parsed_filters };
    });
  }

  function searchVibe(query: string) {
    run(async () => {
      const data = await apiRequest<SimilarSearchResponse>(
        "/search/similar", { method: "POST", body: JSON.stringify({ query, limit: 5 }) },
      );
      return { kind: "vibe", matches: data.results };
    });
  }

  const result = view.state === "done" ? view.result : null;
  // Vibe results are ranked, so sorting would throw the ranking away.
  const canSort = result !== null && result.kind !== "vibe";
  const rows = result ? sortRows(rowsOf(result), canSort ? sortBy : "relevance") : [];

  return (
    <div className={styles.page}>
      <section className={styles.hero}>
        <h1>Find where to climb from Barcelona</h1>
        <p className={styles.lead}>Search by grade and distance, describe your day, or just say what vibe you want.</p>
      </section>

      <SegmentedControl label="Search mode" options={MODES} value={mode} onChange={setMode} />

      {/* All three forms stay mounted and are just hidden, so switching
          modes keeps what you typed. */}
      <div className={styles.formArea}>
        <div hidden={mode !== "filters"}><FilterForm loading={loading} onSubmit={searchFilters} /></div>
        <div hidden={mode !== "natural"}><NaturalForm loading={loading} onSubmit={searchNatural} /></div>
        <div hidden={mode !== "vibe"}><VibeForm loading={loading} onSubmit={searchVibe} /></div>
      </div>

      <section aria-label="Results" className={styles.results}>
        {view.state === "loading" && <StateMessage tone="loading" title="Searching" />}

        {view.state === "error" && (
          <StateMessage tone="error" title="Something went wrong">{view.message}</StateMessage>
        )}

        {view.state === "notice" && (
          <StateMessage
            tone="notice"
            title={view.title}
            action={<Button variant="secondary" onClick={() => setMode("filters")}>Use filters instead</Button>}
          >
            {view.message}
          </StateMessage>
        )}

        {result?.kind === "natural" && <UnderstoodFilters filters={result.parsed} />}

        {result && rows.length === 0 && (
          <StateMessage tone="empty" title="No matching sectors">
            Try widening your filters: a bigger distance or a wider grade range.
          </StateMessage>
        )}

        {rows.length > 0 && (
          <>
            <div className={styles.toolbar}>
              <p className={styles.count}>{rows.length} {rows.length === 1 ? "sector" : "sectors"}</p>
              {canSort && (
                <Field label="Sort by">
                  {(fieldProps) => (
                    <select {...fieldProps} value={sortBy} onChange={(e) => setSortBy(e.target.value as SortBy)}>
                      <option value="relevance">Relevance</option>
                      <option value="name">Name</option>
                      <option value="grade">Grade (easiest first)</option>
                    </select>
                  )}
                </Field>
              )}
            </div>
            <ul className={styles.grid}>
              {rows.map(({ sector, similarity, reason }) => (
                <SectorCard
                  key={sector.id}
                  sector={sector}
                  similarity={similarity}
                  reason={reason}
                  onShowStays={setStaysFor}
                />
              ))}
            </ul>
          </>
        )}

        {view.state === "idle" && (
          <StateMessage tone="empty" title="Ready when you are">
            Pick a search above to see sectors that fit.
          </StateMessage>
        )}
      </section>

      {staysFor && <StaysPanel sector={staysFor} onClose={() => setStaysFor(null)} />}
    </div>
  );
}

export default SearchPage;
