import { useState, type FormEvent } from "react";

import { ApiError } from "../../api/client";
import type { PlannerRunStart } from "../../api/types";
import Button from "../../components/Button";
import StateMessage from "../../components/StateMessage";
import forms from "../search/Forms.module.css";
import TripFields, { type TripValues } from "../stays/TripFields";

interface PlannerStartProps {
  memberCount: number;
  // Starts the run; throws when the request fails.
  onStart: (body: PlannerRunStart) => Promise<void>;
}

const FIELDS: (keyof TripValues)[] = ["checkin", "nights", "guests"];

// A whole number, or undefined (the backend then validates or defaults it).
function numberOrUndefined(text: string): number | undefined {
  return text.trim() === "" ? undefined : Number(text);
}

function PlannerStart({ memberCount, onStart }: PlannerStartProps) {
  const [values, setValues] = useState<TripValues>({ checkin: "", nights: "2", guests: "" });
  const [errors, setErrors] = useState<Partial<Record<keyof TripValues, string>>>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setLoading(true);
    setErrors({});
    setFormError(null);
    try {
      // Empty means the backend's default; the backend is the only judge of the rest.
      await onStart({
        nights: numberOrUndefined(values.nights) ?? 2,
        checkin: values.checkin || undefined,
        guests: numberOrUndefined(values.guests),
      });
    } catch (err) {
      const field = err instanceof ApiError ? FIELDS.find((f) => f === err.field) : undefined;
      if (field && err instanceof Error) setErrors({ [field]: err.message });
      else setFormError(err instanceof Error ? err.message : "Something went wrong");
      setLoading(false);
    }
    // On success the parent replaces this form with the run.
  }

  return (
    <form className={forms.form} onSubmit={submit} noValidate>
      <TripFields
        value={values}
        onChange={(patch) => setValues((current) => ({ ...current, ...patch }))}
        errors={errors}
        hints={{ checkin: "Empty: next Saturday", guests: "Empty: one per member" }}
        guestsPlaceholder={String(Math.max(memberCount, 1))}
      />
      <Button type="submit" loading={loading} className={forms.submit}>Plan the trip</Button>
      {formError && <StateMessage tone="error">{formError}</StateMessage>}
    </form>
  );
}

export default PlannerStart;
