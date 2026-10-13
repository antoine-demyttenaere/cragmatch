import { useEffect, useId, useRef, type ReactNode } from "react";

import Icon from "./Icon";
import styles from "./Sheet.module.css";

interface SheetProps {
  title: string;
  onClose: () => void;
  children: ReactNode;
}

// Bottom sheet on phones, side panel on wide screens (see the CSS).
function Sheet({ title, onClose, children }: SheetProps) {
  const titleId = useId();
  const panelRef = useRef<HTMLElement>(null);

  // Focus moves into the sheet when it opens and goes back to the button that
  // opened it when it closes.
  useEffect(() => {
    const opener = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    panelRef.current?.focus();
    return () => opener?.focus();
  }, []);

  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

  return (
    <div className={styles.backdrop} onClick={onClose}>
      <aside
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
        className={styles.panel}
        onClick={(e) => e.stopPropagation()}
      >
        <header className={styles.header}>
          <h2 id={titleId} className={styles.title}>{title}</h2>
          <button type="button" className={styles.close} onClick={onClose} aria-label="Close">
            <Icon name="close" />
          </button>
        </header>
        <div className={styles.content}>{children}</div>
      </aside>
    </div>
  );
}

export default Sheet;
