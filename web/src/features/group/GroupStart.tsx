import { useState, type FormEvent } from "react";

import { apiRequest } from "../../api/client";
import type { Group } from "../../api/types";
import Button from "../../components/Button";
import Card from "../../components/Card";
import Field from "../../components/Field";
import StateMessage from "../../components/StateMessage";
import styles from "./GroupStart.module.css";
import { readRecentGroups } from "./recentGroups";

interface GroupStartProps {
  onCreated: (group: Group) => void;
  // Open an existing group by its code (typed or from the recent list).
  onOpenCode: (code: string) => void;
}

function GroupStart({ onCreated, onOpenCode }: GroupStartProps) {
  const [name, setName] = useState("");
  const [code, setCode] = useState("");
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);
  // Read once: this screen remounts each time a group is left, so it is fresh.
  const [recent] = useState(readRecentGroups);

  async function create(e: FormEvent) {
    e.preventDefault();
    setCreating(true);
    setCreateError(null);
    try {
      // The trailing slash matters: /groups answers with a redirect.
      onCreated(await apiRequest<Group>("/groups/", { method: "POST", body: JSON.stringify({ name }) }));
    } catch (err) {
      setCreateError(err instanceof Error ? err.message : "Something went wrong");
      setCreating(false);
    }
  }

  function join(e: FormEvent) {
    e.preventDefault();
    if (code.trim()) onOpenCode(code.trim());
  }

  return (
    <div className={styles.start}>
      <div className={styles.cards}>
        <Card as="section">
          <form onSubmit={create} noValidate className={styles.form}>
            <h2 className={styles.title}>Start a group trip</h2>
            <Field label="Group name" error={createError}>
              {(fieldProps) => (
                <input {...fieldProps} value={name} onChange={(e) => setName(e.target.value)} placeholder="Siurana weekend" autoComplete="off" />
              )}
            </Field>
            <Button type="submit" loading={creating}>Create group</Button>
          </form>
        </Card>

        <Card as="section">
          <form onSubmit={join} className={styles.form}>
            <h2 className={styles.title}>Join with a code</h2>
            <Field label="Group code">
              {(fieldProps) => (
                <input {...fieldProps} value={code} onChange={(e) => setCode(e.target.value)} placeholder="ABCD2345" autoComplete="off" />
              )}
            </Field>
            <Button type="submit" variant="secondary" disabled={!code.trim()}>Join group</Button>
          </form>
        </Card>
      </div>

      {recent.length > 0 ? (
        <section aria-label="Your recent groups" className={styles.recent}>
          <h2 className={styles.title}>Your recent groups</h2>
          <ul className={styles.recentList}>
            {recent.map((group) => (
              <li key={group.code}>
                <button type="button" className={styles.recentButton} onClick={() => onOpenCode(group.code)}>
                  <span className={styles.recentName}>{group.name}</span>
                  <span className={styles.recentCode}>{group.code}</span>
                </button>
              </li>
            ))}
          </ul>
        </section>
      ) : (
        <StateMessage tone="empty" title="No groups yet">
          Create a group, then share its link so friends can add their preferences.
        </StateMessage>
      )}
    </div>
  );
}

export default GroupStart;
