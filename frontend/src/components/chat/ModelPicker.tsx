"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import { fetchModels, fetchUsage } from "@/lib/api";
import type { ModelCatalog, ModelInfo, UsageReport } from "@/lib/types";

interface ModelPickerProps {
  value: string;
  onChange: (modelId: string) => void;
}

function perMillion(v: number | null | undefined): string {
  if (v == null) return "?";
  // $0.05, $0.075, $0.60, $2.00
  const s = v.toFixed(3);
  return `$${s.endsWith("0") ? s.slice(0, -1) : s}`;
}

function answerCost(m: ModelInfo): string | null {
  if (!m.estimate) return null;
  const usd = m.estimate.usd;
  const shown = usd < 0.01 ? `$${usd.toFixed(5)}` : `$${usd.toFixed(3)}`;
  return `${shown} per answer${m.estimate.basis === "measured" ? "" : " (estimate)"}`;
}

/** What a locked model needs before it can be picked. */
function lockReason(m: ModelInfo, budgetReached: boolean): string | null {
  if (budgetReached) return "Budget reached";
  if (m.available) return null;
  if (m.configured === false) return "Add a key to enable";
  return m.unavailable_reason || "Not available on this server";
}

function trainingNote(m: ModelInfo): string | null {
  if (!m.free_tier) return null;
  const d = (m.data_use || "").toLowerCase();
  const used = !d.startsWith("not used") && /used to improve|used for training|may be used/.test(d);
  return used ? "Free tier, data may be used for training" : "Free tier";
}

/**
 * The model menu: each provider's models with the official name, the price
 * per 1M tokens, what a typical answer costs, its golden-set score, and why a
 * model is locked.
 */
export default function ModelPicker({ value, onChange }: ModelPickerProps) {
  const [catalog, setCatalog] = useState<ModelCatalog | null>(null);
  const [usage, setUsage] = useState<UsageReport | null>(null);
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  const button = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    fetchModels()
      .then((c) => {
        setCatalog(c);
        if (!value && c.default) onChange(c.default);
      })
      .catch(() => setCatalog({ default: null, prices_checked_on: null, models: [] }));
    fetchUsage().then(setUsage).catch(() => setUsage(null));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!open) return;
    const outside = (e: MouseEvent) => {
      if (box.current && !box.current.contains(e.target as Node) && !button.current?.contains(e.target as Node)) setOpen(false);
    };
    const esc = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setOpen(false);
        button.current?.focus();
      }
    };
    document.addEventListener("mousedown", outside);
    document.addEventListener("keydown", esc);
    box.current?.querySelector<HTMLElement>("button:not([disabled])")?.focus();
    return () => {
      document.removeEventListener("mousedown", outside);
      document.removeEventListener("keydown", esc);
    };
  }, [open]);

  const models = useMemo(() => catalog?.models ?? [], [catalog]);
  const providers = Array.from(new Set(models.map((m) => m.provider)));
  const budgetReached = !!usage && (usage.spent_usd >= usage.cap_usd || usage.service_spent_usd >= usage.service_cap_usd);

  // badges come from the golden-set results, among the models that ran it
  const { best, fastest } = useMemo(() => {
    const ran = models.filter((m) => m.benchmark?.correct_pct != null);
    const best = ran.length > 1 ? ran.reduce((a, b) => ((b.benchmark!.correct_pct! > a.benchmark!.correct_pct!) ? b : a)).id : null;
    const timed = models.filter((m) => m.benchmark?.first_token_p50_s != null);
    const fastest = timed.length > 1 ? timed.reduce((a, b) => ((b.benchmark!.first_token_p50_s! < a.benchmark!.first_token_p50_s!) ? b : a)).id : null;
    return { best, fastest };
  }, [models]);

  const active = models.find((m) => m.id === value);

  return (
    <div className="relative shrink-0">
      <button
        ref={button}
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-haspopup="true"
        aria-expanded={open}
        className="flex items-center gap-xs px-2.5 py-1 text-slate-700 dark:text-slate-300 hover:text-primary dark:hover:text-white transition-colors rounded-lg hover:bg-slate-200/50 dark:hover:bg-white/10 border border-slate-300 dark:border-slate-700 bg-slate-100 dark:bg-slate-800/60"
        title="Choose the model that writes the answer"
      >
        <span className="material-symbols-outlined text-[16px] text-primary" aria-hidden="true">smart_toy</span>
        <span className="font-label-md text-[12px] font-bold text-slate-900 dark:text-white">{active?.label || "Default model"}</span>
        <span className="material-symbols-outlined text-[14px]" aria-hidden="true">{open ? "expand_less" : "expand_more"}</span>
      </button>

      {open && (
        <div
          ref={box}
          role="dialog"
          aria-label="Choose a model"
          className="absolute bottom-12 left-0 w-[23rem] max-h-[65vh] overflow-y-auto bg-white dark:bg-[#0e1329] border border-slate-200 dark:border-slate-800 rounded-2xl p-3 shadow-2xl z-50 fade-in"
        >
          <div className="flex items-center justify-between pb-2 mb-2 border-b border-slate-200 dark:border-slate-800">
            <span className="text-xs uppercase font-bold text-slate-500">Model for answers</span>
            <span className="text-[10px] px-2 py-0.5 rounded bg-primary/10 text-primary font-bold">
              {budgetReached ? "budget reached" : `${models.filter((m) => m.available).length} available`}
            </span>
          </div>
          {budgetReached && usage && (
            <p className="text-[11px] text-amber-700 dark:text-amber-400 mb-2">
              This month&apos;s spending (${usage.spent_usd.toFixed(2)} of ${usage.cap_usd.toFixed(2)}) has reached its cap; answers resume next month.
            </p>
          )}
          {providers.length === 0 && <p className="text-[11px] text-slate-500 px-1">Using the server&apos;s default model.</p>}

          {providers.map((provider) => (
            <section key={provider} className="mb-3 last:mb-0" aria-label={provider}>
              <h3 className="text-[11px] font-bold text-slate-400 uppercase tracking-wider px-1 mb-1">{provider}</h3>
              <ul className="space-y-1">
                {models
                  .filter((m) => m.provider === provider)
                  .map((m) => {
                    const lock = lockReason(m, budgetReached);
                    const selected = value === m.id;
                    const free = trainingNote(m);
                    const cost = answerCost(m);
                    return (
                      <li key={m.id}>
                        <button
                          type="button"
                          disabled={!!lock}
                          aria-pressed={selected}
                          title={m.data_use || undefined}
                          onClick={() => {
                            onChange(m.id);
                            setOpen(false);
                            button.current?.focus();
                          }}
                          className={`w-full text-left px-2 py-1.5 rounded-xl transition-colors ${
                            selected
                              ? "bg-primary/10 text-primary"
                              : lock
                                ? "opacity-60 cursor-not-allowed"
                                : "hover:bg-slate-100 dark:hover:bg-slate-800/70"
                          }`}
                        >
                          <span className="flex items-center gap-1 flex-wrap">
                            <span className="text-xs font-bold text-slate-900 dark:text-white">{m.label}</span>
                            {m.default && <Badge tone="green">Default</Badge>}
                            {m.id === best && <Badge tone="blue">Best score</Badge>}
                            {m.id === fastest && <Badge tone="blue">Fastest</Badge>}
                            {free && <Badge tone="amber">{free}</Badge>}
                            {lock && <Badge tone="gray">{lock}</Badge>}
                            {selected && <span className="material-symbols-outlined text-sm ml-auto" aria-hidden="true">check</span>}
                          </span>
                          <span className="block text-[10px] text-slate-500 dark:text-slate-400">
                            {m.price.input_per_m == null || m.price.output_per_m == null
                              ? m.price.note || "price not published"
                              : `${perMillion(m.price.input_per_m)} in / ${perMillion(m.price.output_per_m)} out per 1M tokens`}
                            {cost ? ` · ${cost}` : ""}
                          </span>
                          {m.benchmark?.correct_pct != null && (
                            <span className="block text-[10px] text-slate-500 dark:text-slate-400">
                              {m.benchmark.correct_pct}% right on the 142 test questions
                              {m.benchmark.first_token_p50_s != null ? ` · first words in ${m.benchmark.first_token_p50_s} s` : ""}
                            </span>
                          )}
                        </button>
                      </li>
                    );
                  })}
              </ul>
            </section>
          ))}
          {catalog?.prices_checked_on && (
            <p className="text-[10px] text-slate-400 px-1 pt-1 border-t border-slate-200 dark:border-slate-800">
              Prices as of {catalog.prices_checked_on}, from each provider&apos;s pricing page.
              {catalog.typical_answer_tokens
                ? ` A typical answer reads ${catalog.typical_answer_tokens.input.toLocaleString()} tokens and writes ${catalog.typical_answer_tokens.output}.`
                : ""}
            </p>
          )}
        </div>
      )}
    </div>
  );
}

function Badge({ tone, children }: { tone: "green" | "blue" | "amber" | "gray"; children: React.ReactNode }) {
  const cls = {
    green: "bg-emerald-500/10 text-emerald-700 dark:text-emerald-400 border-emerald-500/30",
    blue: "bg-blue-500/10 text-blue-700 dark:text-blue-300 border-blue-500/30",
    amber: "bg-amber-500/10 text-amber-700 dark:text-amber-400 border-amber-500/30",
    gray: "bg-slate-500/10 text-slate-600 dark:text-slate-300 border-slate-500/30",
  }[tone];
  return <span className={`text-[9px] px-1.5 rounded font-bold border ${cls}`}>{children}</span>;
}
