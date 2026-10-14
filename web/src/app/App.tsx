import { useState } from "react";

import Icon from "../components/Icon";
import GroupPage from "../features/group/GroupPage";
import { groupCodeFromUrl } from "../features/group/groupLink";
import SearchPage from "../features/search/SearchPage";
import styles from "./App.module.css";

type Tab = "search" | "group";

const TABS: { id: Tab; label: string }[] = [
  { id: "search", label: "Find crags" },
  { id: "group", label: "Group trip" },
];

function App() {
  // Read the URL once, on first render only.
  const [groupCode] = useState(groupCodeFromUrl);
  const [tab, setTab] = useState<Tab>(groupCode ? "group" : "search");

  return (
    <div className={styles.app}>
      <header className={styles.header}>
        <div className={`${styles.inner} ${styles.bar}`}>
          <span className={styles.wordmark}>
            <Icon name="pin" size={22} /> CragMatch
          </span>
          <nav aria-label="Main" className={styles.nav}>
            {TABS.map(({ id, label }) => (
              <button
                key={id}
                type="button"
                className={`${styles.tab} ${tab === id ? styles.active : ""}`}
                aria-current={tab === id ? "page" : undefined}
                onClick={() => setTab(id)}
              >
                {label}
              </button>
            ))}
          </nav>
        </div>
      </header>

      {/* Both sections stay mounted and are just hidden, so switching tabs
          doesn't throw away a half-filled form or the last results. */}
      <main className={`${styles.inner} ${styles.main}`}>
        <div hidden={tab !== "search"}><SearchPage /></div>
        <div hidden={tab !== "group"}><GroupPage initialCode={groupCode} /></div>
      </main>
    </div>
  );
}

export default App;
