import type { ButtonHTMLAttributes } from "react";

import styles from "./Button.module.css";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "primary" | "secondary" | "ghost";
  loading?: boolean;
}

function Button({ variant = "primary", loading = false, disabled, className, children, type = "button", ...rest }: ButtonProps) {
  const classes = [styles.button, styles[variant], loading ? styles.loading : "", className ?? ""].join(" ");
  return (
    <button type={type} className={classes} disabled={disabled || loading} aria-busy={loading || undefined} {...rest}>
      {loading && <span className={styles.spinner} aria-hidden="true" />}
      {children}
    </button>
  );
}

export default Button;
