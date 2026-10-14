import { useState } from "react";

import type { PlannerSector } from "../../api/types";
import Button from "../../components/Button";
import Field from "../../components/Field";
import StateMessage from "../../components/StateMessage";
import PlannerSectorCard from "./PlannerSectorCard";
import styles from "./RunView.module.css";

interface ProposalPanelProps {
  proposal: PlannerSector;
  // Throws when the answer fails; the panel shows the message.
  onAnswer: (approved: boolean, reason: string | null) => Promise<void>;
}

type Busy = "approve" | "reject" | null;

function ProposalPanel({ proposal, onAnswer }: ProposalPanelProps) {
  const [rejecting, setRejecting] = useState(false);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState<Busy>(null);
  const [error, setError] = useState<string | null>(null);

  async function send(approved: boolean) {
    setBusy(approved ? "approve" : "reject");
    setError(null);
    try {
      await onAnswer(approved, approved ? null : reason.trim() || null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
      setBusy(null);
    }
    // On success the parent shows the next state and this panel goes away.
  }

  return (
    <section aria-labelledby="proposal-title" className={styles.run}>
      <h3 id="proposal-title" className={styles.heading}>Proposed sector</h3>
      <PlannerSectorCard sector={proposal}>
        {rejecting ? (
          <div className={styles.reasonForm}>
            <Field label="Why not? (optional)">
              {(fieldProps) => (
                <textarea {...fieldProps} rows={2} value={reason} onChange={(e) => setReason(e.target.value)} />
              )}
            </Field>
            <div className={styles.actions}>
              <Button loading={busy === "reject"} disabled={busy !== null} onClick={() => send(false)}>Send</Button>
              <Button variant="ghost" disabled={busy !== null} onClick={() => setRejecting(false)}>Cancel</Button>
            </div>
          </div>
        ) : (
          <div className={styles.actions}>
            <Button loading={busy === "approve"} disabled={busy !== null} onClick={() => send(true)}>Approve</Button>
            <Button variant="secondary" disabled={busy !== null} onClick={() => setRejecting(true)}>Not this one</Button>
          </div>
        )}
      </PlannerSectorCard>
      {error && <StateMessage tone="error">{error}</StateMessage>}
    </section>
  );
}

export default ProposalPanel;
