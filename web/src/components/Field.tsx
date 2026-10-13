import { useId, type ReactElement } from "react";

import styles from "./Field.module.css";

interface FieldProps {
  label: string;
  hint?: string;
  error?: string | null;
  // Receives the id to put on the input/select/textarea, so the label is linked.
  children: (props: { id: string; "aria-describedby": string | undefined; "aria-invalid": boolean }) => ReactElement;
}

function Field({ label, hint, error, children }: FieldProps) {
  const id = useId();
  const noteId = hint || error ? `${id}-note` : undefined;
  return (
    <div className={styles.field}>
      <label htmlFor={id} className={styles.label}>{label}</label>
      {children({ id, "aria-describedby": noteId, "aria-invalid": Boolean(error) })}
      {error ? (
        <p id={noteId} className={styles.error}>{error}</p>
      ) : hint ? (
        <p id={noteId} className={styles.hint}>{hint}</p>
      ) : null}
    </div>
  );
}

export default Field;
