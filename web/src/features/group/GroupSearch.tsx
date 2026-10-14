import { useRef, useState, type ReactNode } from "react";

import { apiRequest } from "../../api/client";
import type { FitMode, Group, GroupSearchResponse, Sector, SearchMode } from "../../api/types";
import Button from "../../components/Button";
import Icon from "../../components/Icon";
import SegmentedControl from "../../components/SegmentedControl";
import StateMessage from "../../components/StateMessage";
import SectorCard from "../search/SectorCard";
import searchStyles from "../search/SearchPage.module.css";
import StaysPanel from "../stays/StaysPanel";
import FitSummary from "./FitSummary";
import GroupFilters from "./GroupFilters";
import styles from "./GroupSearch.module.css";
import { FIT_HELP, MODE_HELP } from "./memberSummary";

const MODE_OPTIONS: { value: SearchMode; label: string }[] = [
  { value: "scored", label: "Scored" },
  { value: "strict", label: "Strict" },
];

const FIT_OPTIONS: { value: FitMode; label: string }[] = [
  { value: "overlap", label: "Overlap" },
  { value: "cover", label: "Cover" },
];

// A result is kept with the Group object it was computed for. Any member
// change re-reads the group (a new object), so stale results stop showing
// without any clearing code.
interface SearchResult {
  group: Group;
  data: GroupSearchResponse;
}

function GroupSearch({ group }: { group: Group }) {
  const [mode, setMode] = useState<SearchMode>("scored");
  const [fit, setFit] = useState<FitMode>("overlap");
  const [result, setResult] = useState<SearchResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [staysFor, setStaysFor] = useState<Sector | null>(null);
  // Only the latest request may write its answer (quick mode switches).
  const latestRequest = useRef(0);

  async function search(nextMode: SearchMode, nextFit: FitMode) {
    const request = ++latestRequest.current;
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams({ mode: nextMode, fit: nextFit });
      const data = await apiRequest<GroupSearchResponse>(`/groups/${group.share_code}/search?${params}`);
      if (request === latestRequest.current) setResult({ group, data });
    } catch (err) {
      if (request === latestRequest.current) setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      if (request === latestRequest.current) setLoading(false);
    }
  }

  if (group.members.length === 0) {
    return (
      <StateMessage tone="empty" title="Add members first">
        Search needs at least one person's preferences.
      </StateMessage>
    );
  }

  const shown = result && result.group === group ? result.data : null;

  function changeMode(value: SearchMode) {
    setMode(value);
    if (shown) search(value, fit);
  }

  function changeFit(value: FitMode) {
    setFit(value);
    if (shown) search(mode, value);
  }

  function tryScored() {
    setMode("scored");
    search("scored", fit);
  }

  const tryScoredAction = <Button variant="secondary" onClick={tryScored}>Try scored mode</Button>;

  return (
    <section aria-label="Group search" className={styles.search}>
      <div className={styles.controls}>
        <div className={styles.control}>
          <p className={styles.controlLabel}>Who should it suit?</p>
          <SegmentedControl label="Who should it suit?" options={MODE_OPTIONS} value={mode} onChange={changeMode} />
          <p className={styles.help}>{MODE_HELP[mode]}</p>
        </div>
        <div className={styles.control}>
          <p className={styles.controlLabel}>Grades fit when</p>
          <SegmentedControl label="Grades fit when" options={FIT_OPTIONS} value={fit} onChange={changeFit} />
          <p className={styles.help}>{FIT_HELP[fit]}</p>
        </div>
        <Button loading={loading} onClick={() => search(mode, fit)} className={styles.submit}>
          <Icon name="search" /> Find sectors
        </Button>
      </div>

      <div className={searchStyles.results}>
        {loading && <StateMessage tone="loading" title="Searching" />}
        {error && <StateMessage tone="error" title="Something went wrong">{error}</StateMessage>}

        {!loading && shown && <GroupResults data={shown} tryScoredAction={tryScoredAction} onShowStays={setStaysFor} />}
      </div>

      {staysFor && <StaysPanel sector={staysFor} groupCode={group.share_code} onClose={() => setStaysFor(null)} />}
    </section>
  );
}

interface GroupResultsProps {
  data: GroupSearchResponse;
  tryScoredAction: ReactNode;
  onShowStays: (sector: Sector) => void;
}

function GroupResults({ data, tryScoredAction, onShowStays }: GroupResultsProps) {
  if (data.mode === "strict" && !data.common_ground) {
    return (
      <StateMessage tone="notice" title="No common ground" action={tryScoredAction}>
        {data.message}
      </StateMessage>
    );
  }
  if (data.mode === "strict" && data.results.length === 0) {
    return (
      <>
        {data.filters && <GroupFilters filters={data.filters} />}
        <StateMessage tone="empty" title="No sector matches" action={tryScoredAction}>
          {data.message}
        </StateMessage>
      </>
    );
  }
  if (data.results.length === 0) {
    return <StateMessage tone="empty" title="No sectors found">{data.message}</StateMessage>;
  }

  return (
    <>
      {data.mode === "strict" && data.filters && <GroupFilters filters={data.filters} />}
      {data.mode === "scored" && !data.common_ground && (
        <p className={styles.notice}>No sector fits everyone. Best compromises first.</p>
      )}
      <ul className={searchStyles.grid}>
        {data.results.map((match) => (
          <SectorCard key={match.sector.id} sector={match.sector} distanceKm={match.distance_km} onShowStays={onShowStays}>
            <FitSummary match={match} />
          </SectorCard>
        ))}
      </ul>
    </>
  );
}

export default GroupSearch;
