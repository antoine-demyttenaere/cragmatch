import Field from "../../components/Field";
import styles from "./TripFields.module.css";

// The raw text of the three inputs, so a field can be emptied and retyped.
export interface TripValues {
  checkin: string;
  nights: string;
  guests: string;
}

type PerField = Partial<Record<keyof TripValues, string>>;

interface TripFieldsProps {
  value: TripValues;
  // Only the field the user changed, so a caller never sends what it didn't before.
  onChange: (patch: Partial<TripValues>) => void;
  errors?: PerField;
  hints?: PerField;
  guestsPlaceholder?: string;
}

// Check-in, nights and guests: shared by the stays panel and the trip planner.
function TripFields({ value, onChange, errors, hints, guestsPlaceholder }: TripFieldsProps) {
  return (
    <div className={styles.trip}>
      <Field label="Check-in" error={errors?.checkin} hint={hints?.checkin}>
        {(fieldProps) => (
          <input {...fieldProps} type="date" value={value.checkin} onChange={(e) => onChange({ checkin: e.target.value })} />
        )}
      </Field>
      <Field label="Nights" error={errors?.nights} hint={hints?.nights}>
        {(fieldProps) => (
          <input {...fieldProps} type="number" min={1} max={30} value={value.nights} onChange={(e) => onChange({ nights: e.target.value })} />
        )}
      </Field>
      <Field label="Guests" error={errors?.guests} hint={hints?.guests}>
        {(fieldProps) => (
          <input
            {...fieldProps}
            type="number"
            min={1}
            max={30}
            placeholder={guestsPlaceholder}
            value={value.guests}
            onChange={(e) => onChange({ guests: e.target.value })}
          />
        )}
      </Field>
    </div>
  );
}

export default TripFields;
