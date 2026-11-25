import Footer from "@/components/layout/Footer";
import Navbar from "@/components/layout/Navbar";
import data from "@/lib/benchmarks.json";

export const metadata = {
  title: "Benchmarks · DocMind",
  description: "How DocMind scores on its golden set, milestone by milestone.",
};

const REPO = "https://github.com/Heban-7/DocMind/blob/main/";

type Milestone = (typeof data.milestones)[number] & Record<string, unknown>;

function pct(v: unknown): string {
  return typeof v === "number" ? `${v}%` : "—";
}
function num(v: unknown, digits = 2): string {
  return typeof v === "number" ? v.toFixed(digits) : "—";
}
function usd(v: unknown): string {
  return typeof v === "number" ? `$${v.toFixed(5)}` : "—";
}

const ROWS: { key: string; label: string; fmt: (v: unknown) => string; better: "up" | "down" }[] = [
  { key: "correct_pct", label: "Questions answered right", fmt: pct, better: "up" },
  { key: "false_refusal_pct", label: "Said “not found” when it was there", fmt: pct, better: "down" },
  { key: "unanswerable_refused_pct", label: "Refused questions the document can't answer", fmt: pct, better: "up" },
  { key: "citation_precision_mean", label: "Citations on the right page", fmt: (v) => num(v), better: "up" },
  { key: "citation_support_mean", label: "Citations on a page that prints the answer", fmt: (v) => num(v), better: "up" },
  { key: "box_on_figure_pct", label: "Citation box on the printed figure", fmt: pct, better: "up" },
  { key: "retrieval_hit_at_5_pct", label: "Right page in the top 5 search results", fmt: pct, better: "up" },
  { key: "figures_intact_pct", label: "Key figures read intact", fmt: pct, better: "up" },
  { key: "fact_correct_pct", label: "Facts stored with the right value", fmt: pct, better: "up" },
  { key: "pages_silently_missing", label: "Pages lost without a warning", fmt: (v) => (typeof v === "number" ? String(v) : "—"), better: "down" },
  { key: "first_token_p50_s", label: "First words of an answer (median, s)", fmt: (v) => num(v, 1), better: "down" },
  { key: "cost_per_question_usd", label: "Cost per question", fmt: usd, better: "down" },
];

export default function BenchmarksPage() {
  const ms = data.milestones as Milestone[];
  const fields = data.fields as Record<string, unknown>[];
  return (
    <div className="min-h-screen bg-slate-50 dark:bg-[#03050f] text-slate-900 dark:text-white transition-colors">
      <Navbar />
      <main className="pt-28 pb-16 px-4 md:px-8 max-w-[1200px] mx-auto min-h-screen">
        <h1 className="text-3xl font-bold mb-2">Benchmarks</h1>
        <p className="text-slate-600 dark:text-slate-300 max-w-3xl mb-8">
          Every milestone is scored on the same golden set: {data.golden_set.documents} documents ({data.golden_set.pages.toLocaleString()} pages) of
          Ethiopian annual reports, audited statements, scans and Amharic forms, with {data.golden_set.questions} questions. Scores are deterministic: no
          model judges an answer, so each pass or fail can be traced to a page. {data.golden_set.note}
        </p>

        <section aria-labelledby="qa" className="mb-10">
          <h2 id="qa" className="text-xl font-bold mb-3">Answers, milestone by milestone</h2>
          <div className="overflow-x-auto rounded-2xl border border-slate-200 dark:border-slate-800">
            <table className="w-full text-sm">
              <thead className="bg-slate-50 dark:bg-slate-900/60">
                <tr>
                  <th scope="col" className="text-left p-3 font-semibold">Measure</th>
                  {ms.map((m) => (
                    <th key={m.milestone} scope="col" className="text-right p-3 font-semibold">
                      <a href={REPO + m.report} className="hover:text-primary" title={m.change}>
                        {m.milestone}
                      </a>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {ROWS.filter((r) => ms.some((m) => typeof m[r.key] === "number")).map((r) => (
                  <tr key={r.key} className="border-t border-slate-200 dark:border-slate-800">
                    <th scope="row" className="text-left p-3 font-normal">
                      {r.label} <span className="text-slate-400 text-xs">({r.better === "up" ? "higher is better" : "lower is better"})</span>
                    </th>
                    {ms.map((m) => (
                      <td key={m.milestone} className="text-right p-3 tabular-nums">{r.fmt(m[r.key])}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <ul className="mt-3 text-xs text-slate-500 space-y-0.5">
            {ms.map((m) => (
              <li key={m.milestone}>
                <a href={REPO + m.report} className="font-bold hover:text-primary">{m.milestone}</a>: {m.change}
              </li>
            ))}
          </ul>
        </section>

        <section aria-labelledby="fields" className="mb-10">
          <h2 id="fields" className="text-xl font-bold mb-3">Schema fields (M8)</h2>
          <div className="grid md:grid-cols-2 gap-4">
            {fields.map((f) => (
              <div key={String(f.set)} className="rounded-2xl border border-slate-200 dark:border-slate-800 p-4">
                <h3 className="font-bold mb-1">
                  <a href={REPO + String(f.report)} className="hover:text-primary">{String(f.set)}</a>
                </h3>
                <p className="text-3xl font-bold tabular-nums">{pct(f.f1_pct)}</p>
                <p className="text-sm text-slate-500 mb-2">field F1 over {String(f.documents)} documents</p>
                <ul className="text-sm space-y-0.5">
                  <li>{pct(f.auto_rate_pct)} of values accepted without review, {pct(f.auto_precision_pct)} of them right</li>
                  <li>
                    {typeof f.errors_flagged === "number" ? `${Math.round(f.errors_flagged * 100)}%` : "—"} of the {String(f.wrong_values ?? "—")} wrong
                    values sent to review
                  </li>
                  <li>
                    {usd(f.cost_per_document_usd)} and {num(f.seconds_p50, 1)} s per document (median)
                  </li>
                </ul>
              </div>
            ))}
          </div>
        </section>

        {data.models.length > 0 && (
          <section aria-labelledby="models" className="mb-10">
            <h2 id="models" className="text-xl font-bold mb-3">Answer models</h2>
            <div className="overflow-x-auto rounded-2xl border border-slate-200 dark:border-slate-800">
              <table className="w-full text-sm">
                <thead className="bg-slate-50 dark:bg-slate-900/60">
                  <tr>
                    <th scope="col" className="text-left p-3 font-semibold">Model</th>
                    <th scope="col" className="text-right p-3 font-semibold">Right</th>
                    <th scope="col" className="text-right p-3 font-semibold">First words</th>
                    <th scope="col" className="text-right p-3 font-semibold">Cost per question</th>
                  </tr>
                </thead>
                <tbody>
                  {(data.models as Record<string, unknown>[]).map((m) => (
                    <tr key={String(m.model)} className="border-t border-slate-200 dark:border-slate-800">
                      <th scope="row" className="text-left p-3 font-normal">
                        <a href={REPO + String(m.report)} className="hover:text-primary">{String(m.model)}</a>
                      </th>
                      <td className="text-right p-3 tabular-nums">{pct(m.correct_pct)}</td>
                      <td className="text-right p-3 tabular-nums">{num(m.first_token_p50_s, 1)} s</td>
                      <td className="text-right p-3 tabular-nums">{usd(m.cost_per_question_usd)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        )}

        {data.speed.length > 0 && (
          <section aria-labelledby="speed">
            <h2 id="speed" className="text-xl font-bold mb-3">Reading speed on 2 CPU cores (M4)</h2>
            <div className="overflow-x-auto rounded-2xl border border-slate-200 dark:border-slate-800">
              <table className="w-full text-sm">
                <thead className="bg-slate-50 dark:bg-slate-900/60">
                  <tr>
                    <th scope="col" className="text-left p-3 font-semibold">Document</th>
                    <th scope="col" className="text-right p-3 font-semibold">Pages</th>
                    <th scope="col" className="text-right p-3 font-semibold">Before (min)</th>
                    <th scope="col" className="text-right p-3 font-semibold">After (min)</th>
                    <th scope="col" className="text-right p-3 font-semibold">First searchable (s)</th>
                  </tr>
                </thead>
                <tbody>
                  {(data.speed as Record<string, unknown>[]).map((s) => (
                    <tr key={String(s.document)} className="border-t border-slate-200 dark:border-slate-800">
                      <th scope="row" className="text-left p-3 font-normal">{String(s.document)}</th>
                      <td className="text-right p-3 tabular-nums">{String(s.pages)}</td>
                      <td className="text-right p-3 tabular-nums">{num(s.before_min, 1)}</td>
                      <td className="text-right p-3 tabular-nums">{num(s.after_min, 1)}</td>
                      <td className="text-right p-3 tabular-nums">{num(s.first_searchable_s, 1)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        )}
      </main>
      <Footer />
    </div>
  );
}
