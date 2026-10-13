import type { ButtonHTMLAttributes, ReactNode } from "react";

import styles from "./Chip.module.css";

interface ChipProps {
  tone?: "neutral" | "grade" | "style" | "highlight";
  children: ReactNode;
}

// A read-only label.
function Chip({ tone = "neutral", children }: ChipProps) {
  return <span className={`${styles.chip} ${styles[tone]}`}>{children}</span>;
}

interface ChipButtonProps extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, "type"> {
  selected?: boolean;
}

// A clickable chip: a filter toggle or an example prompt.
export function ChipButton({ selected = false, children, ...rest }: ChipButtonProps) {
  return (
    <button type="button" className={`${styles.chip} ${styles.button} ${selected ? styles.selected : ""}`} aria-pressed={selected} {...rest}>
      {children}
    </button>
  );
}

export default Chip;
