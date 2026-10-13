import type { ReactNode } from "react";

import Icon, { type IconName } from "./Icon";
import styles from "./StateMessage.module.css";

type Tone = "loading" | "empty" | "notice" | "error";

const ICONS: Record<Exclude<Tone, "loading">, IconName> = {
  empty: "search",
  notice: "info",
  error: "alert",
};

interface StateMessageProps {
  tone: Tone;
  title?: string;
  children?: ReactNode;
  action?: ReactNode;
}

function StateMessage({ tone, title, children, action }: StateMessageProps) {
  if (tone === "loading") {
    return (
      <div role="status" aria-live="polite" className={styles.skeletons}>
        <span className={styles.srOnly}>{title ?? "Loading"}</span>
        {[0, 1, 2].map((n) => <div key={n} className={styles.skeleton} aria-hidden="true" />)}
      </div>
    );
  }

  return (
    <div role={tone === "error" ? "alert" : "status"} className={`${styles.message} ${styles[tone]}`}>
      <span className={styles.icon}><Icon name={ICONS[tone]} size={24} /></span>
      <div className={styles.body}>
        {title && <h3 className={styles.title}>{title}</h3>}
        {children && <p className={styles.text}>{children}</p>}
        {action && <div className={styles.action}>{action}</div>}
      </div>
    </div>
  );
}

export default StateMessage;
