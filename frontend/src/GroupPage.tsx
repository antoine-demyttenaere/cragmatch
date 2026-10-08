import { useEffect, useState } from "react";

import { apiRequest } from "./api";
import MemberForm from "./MemberForm";
import StaysPanel from "./StaysPanel";
import type { Group, GroupSearchResponse, Member, MemberInput, Sector } from "./types";


interface GroupPageProps {
  initialCode: string | null;
  // Tells the parent which group is open, so it can put ?group=CODE in the URL.
  onCodeChange: (code: string | null) => void;
}

function describePrefs(m: Member): string {
  const grades = m.grade_min ? `${m.grade_min}–${m.grade_max}` : "any grade";
  const distance = m.max_distance_km ? `≤${m.max_distance_km} km` : "any distance";
  const walk = m.max_approach_minutes ? `≤${m.max_approach_minutes} min walk` : "any walk-in";
  const styles = m.styles.length ? m.styles.join("/") : "any style";
  return `${grades}, ${distance}, ${walk}, ${styles}`;
}

function GroupPage({ initialCode, onCodeChange }: GroupPageProps) {
  const [group, setGroup] = useState<Group | null>(null);
  const [newGroupName, setNewGroupName] = useState("");
  const [joinCode, setJoinCode] = useState(initialCode ?? "");
  const [editingId, setEditingId] = useState<number | null>(null);
  const [mode, setMode] = useState<"scored" | "strict">("scored");
  const [fit, setFit] = useState<"overlap" | "cover">("overlap");
  const [search, setSearch] = useState<GroupSearchResponse | null>(null);
  const [staysFor, setStaysFor] = useState<Sector | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  async function loadGroup(code: string) {
    try {
      const loaded = await apiRequest<Group>(`/groups/${encodeURIComponent(code.trim())}`);
      // Cleared after the await (not before it): this runs inside an effect
      // on first load, and React's lint rule forbids synchronous setState there.
      setError(null);
      setGroup(loaded);
      onCodeChange(loaded.share_code);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    }
  }

  // Opening a shared link (?group=CODE) loads that group straight away.
  // State is only updated inside the promise callbacks, never synchronously
  // in the effect body (React's set-state-in-effect rule).
  useEffect(() => {
    if (!initialCode) return;
    let cancelled = false;
    apiRequest<Group>(`/groups/${encodeURIComponent(initialCode)}`)
      .then((loaded) => {
        if (cancelled) return;
        setGroup(loaded);
        onCodeChange(loaded.share_code);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : "Something went wrong");
      });
    return () => {
      cancelled = true;
    };
  }, [initialCode, onCodeChange]);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      const created = await apiRequest<Group>("/groups/", {
        method: "POST",
        body: JSON.stringify({ name: newGroupName.trim() }),
      });
      setGroup(created);
      onCodeChange(created.share_code);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    }
  }

  // After any member change: reload the group and drop the old results,
  // which were computed for a different set of members.
  async function afterMembersChanged() {
    if (!group) return;
    setSearch(null);
    setStaysFor(null);
    await loadGroup(group.share_code);
  }

  async function addMember(input: MemberInput) {
    await apiRequest(`/groups/${group!.share_code}/members`, { method: "POST", body: JSON.stringify(input) });
    await afterMembersChanged();
  }

  async function updateMember(id: number, input: MemberInput) {
    await apiRequest(`/groups/${group!.share_code}/members/${id}`, { method: "PUT", body: JSON.stringify(input) });
    setEditingId(null);
    await afterMembersChanged();
  }

  async function removeMember(member: Member) {
    if (!window.confirm(`Remove ${member.name} from the group?`)) return;
    try {
      await apiRequest(`/groups/${group!.share_code}/members/${member.id}`, { method: "DELETE" });
      await afterMembersChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    }
  }

  async function runSearch() {
    if (!group) return;
    setLoading(true);
    setError(null);
    setStaysFor(null);
    try {
      const params = new URLSearchParams({ mode, fit });
      setSearch(await apiRequest<GroupSearchResponse>(`/groups/${group.share_code}/search?${params}`));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setLoading(false);
    }
  }

  async function copyLink() {
    if (!group) return;
    await navigator.clipboard.writeText(`${window.location.origin}${window.location.pathname}?group=${group.share_code}`);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  function leaveGroup() {
    setGroup(null);
    setSearch(null);
    setStaysFor(null);
    setJoinCode("");
    onCodeChange(null);
  }

  // --- No group open: create one or join with a code -----------------------
  if (!group) {
    return (
      <div>
        <h2>Plan a trip with friends</h2>
        <form onSubmit={handleCreate}>
          <label>
            New group: <input value={newGroupName} onChange={(e) => setNewGroupName(e.target.value)}
              placeholder="Siurana weekend" required />
          </label>{" "}
          <button type="submit">Create</button>
        </form>
        <form onSubmit={(e) => { e.preventDefault(); loadGroup(joinCode); }}>
          <label>
            Or join with a code: <input value={joinCode} onChange={(e) => setJoinCode(e.target.value)}
              placeholder="ABCD2345" required />
          </label>{" "}
          <button type="submit">Join</button>
        </form>
        {error && <p style={{ color: "red" }}>Error: {error}</p>}
      </div>
    );
  }

  // --- A group is open ------------------------------------------------------
  return (
    <div>
      <h2>
        {group.name} <small>code <code>{group.share_code}</code></small>{" "}
        <button type="button" onClick={copyLink}>{copied ? "Link copied!" : "Copy invite link"}</button>{" "}
        <button type="button" onClick={leaveGroup}>Leave</button>
      </h2>

      <h3>Members ({group.members.length})</h3>
      <ul>
        {group.members.map((m) => (
          <li key={m.id}>
            {editingId === m.id ? (
              <MemberForm initial={m} onSubmit={(input) => updateMember(m.id, input)} onCancel={() => setEditingId(null)} />
            ) : (
              <>
                <strong>{m.name}</strong>: {describePrefs(m)}{" "}
                <button type="button" onClick={() => setEditingId(m.id)}>Edit</button>{" "}
                <button type="button" onClick={() => removeMember(m)}>Remove</button>
              </>
            )}
          </li>
        ))}
      </ul>
      <MemberForm onSubmit={addMember} />

      <h3>Find sectors for the group</h3>
      <label>
        Mode:
        <select value={mode} onChange={(e) => setMode(e.target.value as "scored" | "strict")}>
          <option value="scored">Scored: everything, ranked by who it fits</option>
          <option value="strict">Strict: only what fits everyone</option>
        </select>
      </label>{" "}
      <label>
        A sector fits someone if its grades:
        <select value={fit} onChange={(e) => setFit(e.target.value as "overlap" | "cover")}>
          <option value="overlap">overlap their range</option>
          <option value="cover">cover their whole range</option>
        </select>
      </label>{" "}
      <button type="button" onClick={runSearch} disabled={loading}>Search</button>

      {loading && <p>Searching...</p>}
      {error && <p style={{ color: "red" }}>Error: {error}</p>}

      {search && (
        <>
          {search.filters && (
            <p>
              Everyone agrees on: {search.filters.grade_min}–{search.filters.grade_max}
              {search.filters.max_distance_km !== null && `, ≤${search.filters.max_distance_km} km`}
              {search.filters.max_approach_minutes !== null && `, ≤${search.filters.max_approach_minutes} min walk`}
              {search.filters.styles && `, ${search.filters.styles.join("/")}`}
            </p>
          )}
          {search.message && <p><em>{search.message}</em></p>}
          {search.mode === "scored" && !search.common_ground && search.results.length > 0 && (
            <p><em>No sector fits everyone. Best compromises first:</em></p>
          )}
          <ol>
            {search.results.map((r) => (
              <li key={r.sector.id} style={{ marginBottom: 6 }}>
                <strong>{r.sector.name}</strong> ({r.sector.crag.name}) — {r.sector.style},{" "}
                {r.sector.grade_min}–{r.sector.grade_max} — {r.distance_km} km —{" "}
                {r.sector.approach_minutes !== null ? `${r.sector.approach_minutes} min walk-in` : "approach unknown"} —{" "}
                fits {r.fit_count} of {r.member_count}{" "}
                <button type="button" onClick={() => setStaysFor(r.sector)}>Stays nearby</button>
                <div>
                  {r.fits.length > 0 && <span style={{ color: "green" }}>✓ {r.fits.join(", ")} </span>}
                  {r.misfits.map((m) => (
                    <span key={m.name} style={{ color: "#b00", marginRight: 8 }}>✗ {m.name} ({m.reason})</span>
                  ))}
                </div>
              </li>
            ))}
          </ol>
        </>
      )}

      {staysFor && <StaysPanel sector={staysFor} groupCode={group.share_code} onClose={() => setStaysFor(null)} />}
    </div>
  );
}

export default GroupPage;
