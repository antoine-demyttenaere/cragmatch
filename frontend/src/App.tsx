import { useState } from "react";

import GroupPage from "./GroupPage";
import SearchPage from "./SearchPage";


type Tab = "search" | "group";

// A shared invite link looks like http://localhost:5173/?group=ABCD2345
function groupCodeFromUrl(): string | null {
  return new URLSearchParams(window.location.search).get("group");
}

// Keep ?group=CODE in the address bar in sync with the open group, so
// copying the URL shares it. replaceState changes the URL without reloading
// the page or adding a history entry. Defined outside App because it uses
// no state: it's the same function on every render, so GroupPage's effect
// can depend on it without re-running.
function syncGroupCodeToUrl(code: string | null) {
  const url = new URL(window.location.href);
  if (code) url.searchParams.set("group", code);
  else url.searchParams.delete("group");
  window.history.replaceState(null, "", url);
}

function App() {
  // Read the URL once, on first render only: later changes to ?group= are
  // made by us (syncGroupCodeToUrl), not a reason to reload the group.
  const [initialCode] = useState(groupCodeFromUrl);
  const [tab, setTab] = useState<Tab>(initialCode ? "group" : "search");

  return (
    <div>
      <h1>CragMatch</h1>
      <nav style={{ marginBottom: 12 }}>
        <button type="button" onClick={() => setTab("search")} disabled={tab === "search"}>Find crags</button>{" "}
        <button type="button" onClick={() => setTab("group")} disabled={tab === "group"}>Group trip</button>
      </nav>

      {/* Both pages stay mounted and are just hidden, so switching tabs
          doesn't throw away a half-filled form or the last results. */}
      <div hidden={tab !== "search"}><SearchPage /></div>
      <div hidden={tab !== "group"}>
        <GroupPage initialCode={initialCode} onCodeChange={syncGroupCodeToUrl} />
      </div>
    </div>
  );
}

export default App;
