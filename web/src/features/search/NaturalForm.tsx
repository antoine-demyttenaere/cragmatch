import TextSearchForm from "./TextSearchForm";

const EXAMPLES = [
  "sport 6b to 7a under 2 hours",
  "easy trad climbing close to Barcelona",
  "hard boulder problems within 150 km",
];

interface NaturalFormProps {
  loading: boolean;
  onSubmit: (query: string) => void;
}

function NaturalForm({ loading, onSubmit }: NaturalFormProps) {
  return (
    <TextSearchForm
      label="Describe your ideal climbing day"
      placeholder="Somewhere 6a-7a, 1.5h from Barcelona, sport climbing"
      examples={EXAMPLES}
      submitLabel="Search"
      loading={loading}
      onSubmit={onSubmit}
    />
  );
}

export default NaturalForm;
