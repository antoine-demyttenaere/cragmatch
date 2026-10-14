import { useRef, useState } from "react";

import Button from "../../components/Button";
import { shareLinkFor } from "./groupLink";
import styles from "./ShareLink.module.css";

type CopyState = "idle" | "copied" | "failed";

function ShareLink({ code }: { code: string }) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [copy, setCopy] = useState<CopyState>("idle");
  const link = shareLinkFor(code);

  async function copyLink() {
    try {
      await navigator.clipboard.writeText(link);
      setCopy("copied");
      setTimeout(() => setCopy("idle"), 2000);
    } catch {
      // No clipboard (plain-HTTP address) or permission refused: let the user copy by hand.
      setCopy("failed");
      inputRef.current?.select();
    }
  }

  return (
    <div className={styles.share}>
      <label htmlFor="share-link" className={styles.label}>Share link</label>
      <div className={styles.row}>
        <input id="share-link" ref={inputRef} readOnly value={link} onFocus={(e) => e.currentTarget.select()} />
        <Button variant="secondary" onClick={copyLink}>{copy === "copied" ? "Copied" : "Copy link"}</Button>
      </div>
      <p role="status" className={styles.note}>
        {copy === "failed" ? "Couldn't copy, select the link and copy it" : ""}
      </p>
    </div>
  );
}

export default ShareLink;
