import { useState } from "react";

import { apiRequest } from "../../api/client";
import type { Member } from "../../api/types";
import Button from "../../components/Button";
import Card from "../../components/Card";
import Chip from "../../components/Chip";
import StateMessage from "../../components/StateMessage";
import MemberForm from "./MemberForm";
import styles from "./MemberList.module.css";
import { describeMember } from "./memberSummary";

interface MemberListProps {
  groupCode: string;
  members: Member[];
  // Called after any change, so the group is re-read from the backend.
  onChanged: () => void;
}

function MemberRow({ member, onEdit, onRemove }: { member: Member; onEdit: () => void; onRemove: () => void }) {
  const labels = describeMember(member);
  return (
    <li className={styles.member}>
      <div className={styles.info}>
        <p className={styles.name}>{member.name}</p>
        <div className={styles.chips}>
          <Chip tone="grade">{labels.grades}</Chip>
          <Chip>{labels.distance}</Chip>
          <Chip>{labels.walkIn}</Chip>
          {labels.styles.length > 0
            ? labels.styles.map((s) => <Chip key={s} tone="style">{s}</Chip>)
            : <Chip tone="style">Any style</Chip>}
        </div>
      </div>
      <div className={styles.actions}>
        <Button variant="ghost" onClick={onEdit} aria-label={`Edit ${member.name}`}>Edit</Button>
        <Button variant="ghost" onClick={onRemove} aria-label={`Remove ${member.name}`}>Remove</Button>
      </div>
    </li>
  );
}

function MemberList({ groupCode, members, onChanged }: MemberListProps) {
  const [editingId, setEditingId] = useState<number | null>(null);
  const [removeError, setRemoveError] = useState<string | null>(null);

  async function remove(member: Member) {
    if (!window.confirm(`Remove ${member.name} from the group?`)) return;
    setRemoveError(null);
    try {
      await apiRequest(`/groups/${groupCode}/members/${member.id}`, { method: "DELETE" });
      onChanged();
    } catch (err) {
      setRemoveError(err instanceof Error ? err.message : "Something went wrong");
    }
  }

  function saved() {
    setEditingId(null);
    onChanged();
  }

  return (
    <Card as="section">
      <div id="members" className={styles.section}>
        <h2 className={styles.title}>Members ({members.length})</h2>

        {members.length === 0 && <p className={styles.empty}>No one has joined yet. Add everyone's preferences below.</p>}

        {members.length > 0 && (
          <ul className={styles.list}>
            {members.map((member) =>
              editingId === member.id ? (
                <li key={member.id} className={styles.member}>
                  <MemberForm groupCode={groupCode} member={member} onSaved={saved} onCancel={() => setEditingId(null)} />
                </li>
              ) : (
                <MemberRow
                  key={member.id}
                  member={member}
                  onEdit={() => setEditingId(member.id)}
                  onRemove={() => remove(member)}
                />
              ),
            )}
          </ul>
        )}

        {removeError && <StateMessage tone="error">{removeError}</StateMessage>}

        <h3 className={styles.addTitle}>Add a member</h3>
        <MemberForm groupCode={groupCode} onSaved={onChanged} />
      </div>
    </Card>
  );
}

export default MemberList;
