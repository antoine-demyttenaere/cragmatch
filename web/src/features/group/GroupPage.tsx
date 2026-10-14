import { useEffect, useState } from "react";

import { ApiError, apiRequest } from "../../api/client";
import type { Group } from "../../api/types";
import Button from "../../components/Button";
import Chip from "../../components/Chip";
import StateMessage from "../../components/StateMessage";
import GroupSearch from "./GroupSearch";
import GroupStart from "./GroupStart";
import styles from "./GroupPage.module.css";
import { syncGroupCodeToUrl } from "./groupLink";
import MemberList from "./MemberList";
import { forgetGroup, rememberGroup } from "./recentGroups";
import ShareLink from "./ShareLink";

// What the page shows. Only one of these is true at a time.
type View =
  | { state: "idle" } // no group open: the start screen
  | { state: "loading" }
  | { state: "open"; group: Group }
  | { state: "notFound"; code: string }
  | { state: "error"; message: string; code: string };

// Never throws: a failed load is just another view.
async function loadGroup(code: string): Promise<View> {
  try {
    return { state: "open", group: await apiRequest<Group>(`/groups/${encodeURIComponent(code)}`) };
  } catch (err) {
    if (err instanceof ApiError && err.status === 404) return { state: "notFound", code };
    return { state: "error", code, message: err instanceof Error ? err.message : "Something went wrong" };
  }
}

// The side effects of a group opening or turning out not to exist.
function settle(view: View): View {
  if (view.state === "open") {
    syncGroupCodeToUrl(view.group.share_code);
    rememberGroup({ code: view.group.share_code, name: view.group.name });
  }
  if (view.state === "notFound") forgetGroup(view.code);
  return view;
}

function GroupPage({ initialCode }: { initialCode: string | null }) {
  const [view, setView] = useState<View>(initialCode ? { state: "loading" } : { state: "idle" });

  // Load the group from a shared link. State is set only after the await
  // (react-hooks forbids a synchronous update at the start of an effect).
  useEffect(() => {
    if (!initialCode) return;
    let cancelled = false;
    (async () => {
      const next = await loadGroup(initialCode);
      if (!cancelled) setView(settle(next));
    })();
    return () => {
      cancelled = true;
    };
  }, [initialCode]);

  async function openCode(code: string) {
    setView({ state: "loading" });
    setView(settle(await loadGroup(code)));
  }

  // After a member change: re-read the group so the list and count are the
  // backend's. No "loading" view, which would unmount the forms.
  async function refresh(code: string) {
    setView(settle(await loadGroup(code)));
  }

  function backToStart() {
    syncGroupCodeToUrl(null);
    setView({ state: "idle" });
  }

  if (view.state === "idle") {
    return <GroupStart onCreated={(group) => setView(settle({ state: "open", group }))} onOpenCode={openCode} />;
  }

  if (view.state === "loading") return <StateMessage tone="loading" title="Loading group" />;

  if (view.state === "notFound") {
    return (
      <StateMessage
        tone="notice"
        title="Group not found"
        action={<Button onClick={backToStart}>Create a group</Button>}
      >
        No group has the code {view.code}. Check the link, or start a new group.
      </StateMessage>
    );
  }

  if (view.state === "error") {
    const { code } = view;
    return (
      <StateMessage
        tone="error"
        title="Couldn't open the group"
        action={
          <>
            <Button onClick={() => openCode(code)}>Try again</Button>
            <Button variant="ghost" onClick={backToStart}>Back</Button>
          </>
        }
      >
        {view.message}
      </StateMessage>
    );
  }

  const { group } = view;
  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <div className={styles.titleRow}>
          <h1 className={styles.name}>{group.name}</h1>
          <Chip>Code {group.share_code}</Chip>
        </div>
        <Button variant="ghost" onClick={backToStart}>Leave group</Button>
      </header>

      <ShareLink code={group.share_code} />
      <MemberList groupCode={group.share_code} members={group.members} onChanged={() => refresh(group.share_code)} />
      <GroupSearch group={group} />
    </div>
  );
}

export default GroupPage;
