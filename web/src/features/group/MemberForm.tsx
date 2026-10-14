import { useState, type FormEvent } from "react";

import { ApiError, apiRequest } from "../../api/client";
import type { Member, MemberInput } from "../../api/types";
import Button from "../../components/Button";
import { ChipButton } from "../../components/Chip";
import Field from "../../components/Field";
import StateMessage from "../../components/StateMessage";
import { GRADES, STYLES, styleLabel } from "../../constants";
import styles from "../search/Forms.module.css";

interface MemberFormProps {
  groupCode: string;
  // Set when editing; the form then starts from this member and saves with PUT.
  member?: Member;
  onSaved: () => void;
  onCancel?: () => void;
}

interface FormError {
  field: string | null;
  message: string;
}

// An empty number box means "no limit", which the backend stores as null.
function numberOrNull(text: string): number | null {
  return text.trim() === "" ? null : Number(text);
}

function MemberForm({ groupCode, member, onSaved, onCancel }: MemberFormProps) {
  const [name, setName] = useState(member?.name ?? "");
  const [gradeMin, setGradeMin] = useState(member?.grade_min ?? "");
  const [gradeMax, setGradeMax] = useState(member?.grade_max ?? "");
  const [maxDistance, setMaxDistance] = useState(member?.max_distance_km?.toString() ?? "");
  const [maxWalk, setMaxWalk] = useState(member?.max_approach_minutes?.toString() ?? "");
  const [memberStyles, setMemberStyles] = useState<string[]>(member?.styles ?? []);
  const [error, setError] = useState<FormError | null>(null);
  const [saving, setSaving] = useState(false);

  function toggleStyle(style: string) {
    setMemberStyles((current) => (current.includes(style) ? current.filter((s) => s !== style) : [...current, style]));
  }

  function clear() {
    setName("");
    setGradeMin("");
    setGradeMax("");
    setMaxDistance("");
    setMaxWalk("");
    setMemberStyles([]);
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    const body: MemberInput = {
      name,
      grade_min: gradeMin || null,
      grade_max: gradeMax || null,
      max_distance_km: numberOrNull(maxDistance),
      max_approach_minutes: numberOrNull(maxWalk),
      styles: memberStyles,
    };
    const path = member ? `/groups/${groupCode}/members/${member.id}` : `/groups/${groupCode}/members`;

    setSaving(true);
    setError(null);
    try {
      await apiRequest(path, { method: member ? "PUT" : "POST", body: JSON.stringify(body) });
      if (!member) clear();
      onSaved();
    } catch (err) {
      setError({
        field: err instanceof ApiError ? err.field : null,
        message: err instanceof Error ? err.message : "Something went wrong",
      });
    } finally {
      setSaving(false);
    }
  }

  // The message goes under the field it is about; anything else goes under the form.
  const errorFor = (field: string) => (error?.field === field ? error.message : null);
  const knownFields = ["name", "grade_min", "grade_max", "max_distance_km", "max_approach_minutes", "styles"];
  const formError = error && (error.field === null || !knownFields.includes(error.field)) ? error : null;

  return (
    // noValidate: the browser's own checks would hide the backend's messages.
    <form onSubmit={handleSubmit} noValidate className={styles.form}>
      <Field label="Name" error={errorFor("name")}>
        {(fieldProps) => (
          <input {...fieldProps} value={name} onChange={(e) => setName(e.target.value)} placeholder="Ana" autoComplete="off" />
        )}
      </Field>

      <div className={styles.row}>
        <Field label="Easiest grade" error={errorFor("grade_min")}>
          {(fieldProps) => (
            <select {...fieldProps} value={gradeMin} onChange={(e) => setGradeMin(e.target.value)}>
              <option value="">Any</option>
              {GRADES.map((g) => <option key={g} value={g}>{g}</option>)}
            </select>
          )}
        </Field>
        <Field label="Hardest grade" error={errorFor("grade_max")}>
          {(fieldProps) => (
            <select {...fieldProps} value={gradeMax} onChange={(e) => setGradeMax(e.target.value)}>
              <option value="">Any</option>
              {GRADES.map((g) => <option key={g} value={g}>{g}</option>)}
            </select>
          )}
        </Field>
      </div>

      <div className={styles.row}>
        <Field label="Max distance (km)" error={errorFor("max_distance_km")}>
          {(fieldProps) => (
            <input {...fieldProps} type="number" inputMode="decimal" placeholder="Any" value={maxDistance} onChange={(e) => setMaxDistance(e.target.value)} />
          )}
        </Field>
        <Field label="Max walk-in (min)" error={errorFor("max_approach_minutes")}>
          {(fieldProps) => (
            <input {...fieldProps} type="number" inputMode="numeric" placeholder="Any" value={maxWalk} onChange={(e) => setMaxWalk(e.target.value)} />
          )}
        </Field>
      </div>

      <Field label="Styles" hint="None selected = any style" error={errorFor("styles")}>
        {(fieldProps) => (
          <div {...fieldProps} role="group" aria-label="Styles" className={styles.chips}>
            {STYLES.map((s) => (
              <ChipButton key={s} selected={memberStyles.includes(s)} onClick={() => toggleStyle(s)}>
                {styleLabel(s)}
              </ChipButton>
            ))}
          </div>
        )}
      </Field>

      <div className={styles.chips}>
        <Button type="submit" loading={saving}>{member ? "Save" : "Add member"}</Button>
        {onCancel && <Button variant="ghost" onClick={onCancel}>Cancel</Button>}
      </div>

      {formError && <StateMessage tone="error">{formError.message}</StateMessage>}
    </form>
  );
}

export default MemberForm;
