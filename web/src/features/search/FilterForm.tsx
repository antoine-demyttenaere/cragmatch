import { useState, type FormEvent } from "react";

import Button from "../../components/Button";
import { ChipButton } from "../../components/Chip";
import Field from "../../components/Field";
import Icon from "../../components/Icon";
import { GRADES, STYLES, styleLabel, type ClimbingStyle } from "../../constants";
import styles from "./Forms.module.css";

export interface FilterValues {
  minGrade: string;
  maxGrade: string;
  style: ClimbingStyle | "";
  maxDistanceKm: number;
}

interface FilterFormProps {
  loading: boolean;
  onSubmit: (values: FilterValues) => void;
}

function FilterForm({ loading, onSubmit }: FilterFormProps) {
  const [minGrade, setMinGrade] = useState("6a");
  const [maxGrade, setMaxGrade] = useState("7a");
  const [style, setStyle] = useState<ClimbingStyle | "">("");
  const [maxDistanceKm, setMaxDistanceKm] = useState(120);

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    onSubmit({ minGrade, maxGrade, style, maxDistanceKm });
  }

  return (
    <form onSubmit={handleSubmit} className={styles.form}>
      <div className={styles.row}>
        <Field label="Easiest grade">
          {(fieldProps) => (
            <select {...fieldProps} value={minGrade} onChange={(e) => setMinGrade(e.target.value)}>
              {GRADES.map((g) => <option key={g} value={g}>{g}</option>)}
            </select>
          )}
        </Field>
        <Field label="Hardest grade">
          {(fieldProps) => (
            <select {...fieldProps} value={maxGrade} onChange={(e) => setMaxGrade(e.target.value)}>
              {GRADES.map((g) => <option key={g} value={g}>{g}</option>)}
            </select>
          )}
        </Field>
      </div>

      <div role="group" aria-label="Style" className={styles.chips}>
        <ChipButton selected={style === ""} onClick={() => setStyle("")}>Any style</ChipButton>
        {STYLES.map((s) => (
          <ChipButton key={s} selected={style === s} onClick={() => setStyle(s)}>{styleLabel(s)}</ChipButton>
        ))}
      </div>

      <Field label={`Max distance from Barcelona: ${maxDistanceKm} km`}>
        {(fieldProps) => (
          <input
            {...fieldProps}
            type="range"
            min={10}
            max={300}
            step={10}
            value={maxDistanceKm}
            onChange={(e) => setMaxDistanceKm(Number(e.target.value))}
          />
        )}
      </Field>

      <Button type="submit" loading={loading} className={styles.submit}>
        <Icon name="search" /> Search
      </Button>
    </form>
  );
}

export default FilterForm;
