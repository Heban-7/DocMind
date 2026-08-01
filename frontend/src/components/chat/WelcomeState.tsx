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
      <h2 className="font-display text-3xl sm:text-4xl font-bold text-slate-900 dark:text-white mb-lg">
        What would you like to verify today?
      </h2>
      <div className="flex flex-wrap gap-sm">
        {suggestions.map((s) => (
          <button
            key={s}
            onClick={() => onSuggestionClick(s)}
            className="px-4 py-2 border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900/60 rounded-full font-label-md text-xs sm:text-sm text-slate-700 dark:text-slate-300 hover:border-primary hover:text-primary transition-all shadow-sm"
          >
            {s}
          </button>
        ))}
      </div>
    </div>
  );
}

