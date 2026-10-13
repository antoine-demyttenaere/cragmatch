import TextSearchForm from "./TextSearchForm";

const EXAMPLES = [
  "quiet crag, short approach",
  "big views and a relaxed atmosphere",
  "shady sectors for a hot day",
];

interface VibeFormProps {
  loading: boolean;
  onSubmit: (query: string) => void;
}

function VibeForm({ loading, onSubmit }: VibeFormProps) {
  return (
    <TextSearchForm
      label="Describe the vibe you're after"
      placeholder="Quiet crag, short approach"
      examples={EXAMPLES}
      submitLabel="Find similar"
      loading={loading}
      onSubmit={onSubmit}
    />
  );
}

export default VibeForm;
