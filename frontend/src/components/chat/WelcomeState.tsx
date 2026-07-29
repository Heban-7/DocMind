interface WelcomeStateProps {
  onSuggestionClick: (text: string) => void;
}

const suggestions = [
  "What was Q3 Net Revenue?",
  "Compare risk factors in 2023 vs 2024",
  "Summarize ESG metrics",
];

export default function WelcomeState({ onSuggestionClick }: WelcomeStateProps) {
  return (
    <div className="mb-xl" id="welcome-state">
      <h2 className="font-display text-display text-on-surface mb-lg">
        What would you like to verify today?
      </h2>
      <div className="flex flex-wrap gap-sm">
        {suggestions.map((s) => (
          <button
            key={s}
            onClick={() => onSuggestionClick(s)}
            className="px-4 py-2 border border-outline-variant rounded-full font-label-md text-label-md text-on-surface-variant hover:border-primary hover:text-primary transition-all"
          >
            {s}
          </button>
        ))}
      </div>
    </div>
  );
}
