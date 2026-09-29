import { useState } from "react";

import { GRADES, STYLES } from "./constants";
import type { Member, MemberInput } from "./types";


interface MemberFormProps {
  initial?: Member;           // set = editing an existing member
  onSubmit: (input: MemberInput) => Promise<void>;
  onCancel?: () => void;
}

// Every preference is optional: a member can join first and fill them in
// later. The backend validates everything (real grades, min <= max, both
// grades or neither) and its message is shown if something's off.
function MemberForm({ initial, onSubmit, onCancel }: MemberFormProps) {
  const [name, setName] = useState(initial?.name ?? "");
  const [gradeMin, setGradeMin] = useState(initial?.grade_min ?? "");
  const [gradeMax, setGradeMax] = useState(initial?.grade_max ?? "");
  const [maxDistance, setMaxDistance] = useState(initial?.max_distance_km?.toString() ?? "");
  const [styles, setStyles] = useState<string[]>(initial?.styles ?? []);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  function toggleStyle(style: string) {
    setStyles((current) => current.includes(style) ? current.filter((s) => s !== style) : [...current, style]);
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setError(null);
    try {
      await onSubmit({
        name: name.trim(),
        grade_min: gradeMin || null,
        grade_max: gradeMax || null,
        max_distance_km: maxDistance === "" ? null : Number(maxDistance),
        styles,
      });
      if (!initial) {
        // Clear the form after adding, ready for the next friend.
        setName(""); setGradeMin(""); setGradeMax(""); setMaxDistance(""); setStyles([]);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setSaving(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} style={{ border: "1px dashed #aaa", padding: 8, margin: "8px 0" }}>
      <label>
        Name: <input value={name} onChange={(e) => setName(e.target.value)} required />
      </label>{" "}
      <label>
        Grades:
        <select value={gradeMin} onChange={(e) => setGradeMin(e.target.value)}>
          <option value="">—</option>
          {GRADES.map((g) => <option key={g} value={g}>{g}</option>)}
        </select>
        to
        <select value={gradeMax} onChange={(e) => setGradeMax(e.target.value)}>
          <option value="">—</option>
          {GRADES.map((g) => <option key={g} value={g}>{g}</option>)}
        </select>
      </label>{" "}
      <label>
        Max distance (km):
        <input type="number" min={1} value={maxDistance} placeholder="any"
          onChange={(e) => setMaxDistance(e.target.value)} style={{ width: 70 }} />
      </label>
      <div>
        Styles (none ticked = any):{" "}
        {STYLES.map((s) => (
          <label key={s} style={{ marginRight: 8 }}>
            <input type="checkbox" checked={styles.includes(s)} onChange={() => toggleStyle(s)} /> {s}
          </label>
        ))}
      </div>
      <button type="submit" disabled={saving}>{initial ? "Save" : "Add member"}</button>
      {onCancel && <button type="button" onClick={onCancel}>Cancel</button>}
      {error && <p style={{ color: "red" }}>Error: {error}</p>}
    </form>
  );
}

export default MemberForm;
