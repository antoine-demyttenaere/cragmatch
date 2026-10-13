import { useId, type ReactNode } from "react";

import styles from "./SegmentedControl.module.css";

interface Option<T extends string> {
  value: T;
  label: ReactNode;
}

interface SegmentedControlProps<T extends string> {
  label: string;
  options: Option<T>[];
  value: T;
  onChange: (value: T) => void;
}

// Radio buttons underneath, so arrow keys move between options for free.
function SegmentedControl<T extends string>({ label, options, value, onChange }: SegmentedControlProps<T>) {
  const name = useId();
  return (
    <div role="radiogroup" aria-label={label} className={styles.group}>
      {options.map((option) => (
        <label key={option.value} className={styles.option}>
          <input
            type="radio"
            name={name}
            value={option.value}
            checked={option.value === value}
            onChange={() => onChange(option.value)}
            className={styles.input}
          />
          <span className={styles.text}>{option.label}</span>
        </label>
      ))}
    </div>
  );
}

export default SegmentedControl;
