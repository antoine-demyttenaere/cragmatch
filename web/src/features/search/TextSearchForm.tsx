import { useState, type FormEvent } from "react";

import Button from "../../components/Button";
import { ChipButton } from "../../components/Chip";
import Field from "../../components/Field";
import Icon from "../../components/Icon";
import styles from "./Forms.module.css";

interface TextSearchFormProps {
  label: string;
  placeholder: string;
  examples: string[];
  submitLabel: string;
  loading: boolean;
  onSubmit: (query: string) => void;
}

// The shared body of the two AI searches (Describe it, Vibe): a textarea,
// example prompts, an "AI" badge and a submit button.
function TextSearchForm({ label, placeholder, examples, submitLabel, loading, onSubmit }: TextSearchFormProps) {
  const [query, setQuery] = useState("");

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (query.trim()) onSubmit(query.trim());
  }

  return (
    <form onSubmit={handleSubmit} className={styles.form}>
      <span className={styles.badge}><Icon name="sparkle" size={16} /> AI</span>
      <Field label={label}>
        {(fieldProps) => (
          <textarea {...fieldProps} value={query} placeholder={placeholder} onChange={(e) => setQuery(e.target.value)} />
        )}
      </Field>

      <div className={styles.examples}>
        <span className={styles.examplesLabel}>Try one of these</span>
        <div className={styles.chips}>
          {examples.map((example) => (
            <ChipButton key={example} onClick={() => setQuery(example)}>{example}</ChipButton>
          ))}
        </div>
      </div>

      <Button type="submit" loading={loading} disabled={!query.trim()} className={styles.submit}>
        <Icon name="search" /> {submitLabel}
      </Button>
    </form>
  );
}

export default TextSearchForm;
