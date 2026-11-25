"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import AppShell, { Card, ErrorNote } from "@/components/layout/AppShell";
import { fetchUsage } from "@/lib/api";
import { displayFileName } from "@/lib/boxes";
import type { UsageReport } from "@/lib/types";

function usd(v: number | null | undefined, digits = 4): string {
  if (v == null) return "—";
  return `$${v.toFixed(v > 0 && v < 0.001 ? 5 : digits)}`;
}

const PURPOSE: Record<string, string> = {
  answer: "Answers",
  plan: "Planning a question",
  embed: "Search (embeddings)",
  ingest: "Reading documents",
  fields: "Schema fields",
  other: "Other",
};

function Meter({ label, spent, cap }: { label: string; spent: number; cap: number }) {
  const pct = cap > 0 ? Math.min(100, (100 * spent) / cap) : 0;
  return (
    <div>
      <div className="flex justify-between text-sm mb-1">
        <span>{label}</span>
        <span className="tabular-nums">
          {usd(spent, 2)} of {usd(cap, 2)}
        </span>
      </div>
      <div
        className="h-2.5 rounded-full bg-slate-200 dark:bg-slate-800 overflow-hidden"
        role="meter"
        aria-label={label}
        aria-valuemin={0}
        aria-valuemax={cap}
        aria-valuenow={spent}
      >
        <div className={`h-full ${pct >= 90 ? "bg-red-500" : pct >= 70 ? "bg-amber-500" : "bg-primary"}`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

export default function UsagePage() {
  const [u, setU] = useState<UsageReport | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchUsage().then(setU).catch((e) => setError(e.message));
  }, []);

  const month = u ? new Date(u.month).toLocaleDateString(undefined, { month: "long", year: "numeric" }) : "";
  const maxDay = Math.max(0.000001, ...(u?.by_day || []).map((d) => d.cost_usd));

  return (
    <AppShell title={u ? `Usage, ${month}` : "Usage"}>
      <ErrorNote message={error} />
      {!u ? (
        !error && <p className="text-sm text-slate-500">Loading…</p>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          <Card title="Spending caps" className="lg:col-span-1">
            <div className="space-y-4">
              <Meter label="Your account" spent={u.spent_usd} cap={u.cap_usd} />
              <Meter label="The whole server" spent={u.service_spent_usd} cap={u.service_cap_usd} />
              <p className="text-xs text-slate-500">
                Model calls stop when a cap is reached and start again next month. The caps are set on the server
                (DOCMIND_TENANT_MONTHLY_BUDGET_USD and DOCMIND_MONTHLY_BUDGET_USD).
              </p>
            </div>
          </Card>

          <Card title="Per question" className="lg:col-span-1">
            <p className="text-3xl font-bold tabular-nums">{usd(u.cost_per_question_usd, 5)}</p>
            <p className="text-sm text-slate-500">
              on average, over {u.questions.toLocaleString()} question{u.questions === 1 ? "" : "s"} this month (planning, search and the answer)
            </p>
          </Card>

          <Card title="By provider" className="lg:col-span-1">
            {u.by_provider.length === 0 ? (
              <p className="text-sm text-slate-500">No model calls this month.</p>
            ) : (
              <ul className="text-sm space-y-1">
                {u.by_provider.map((p) => (
                  <li key={p.provider} className="flex justify-between">
                    <span className="capitalize">{p.provider}</span>
                    <span className="tabular-nums">
                      {usd(p.cost_usd)} · {p.calls.toLocaleString()} calls
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </Card>

          <Card title="Spending by day" className="lg:col-span-2">
            {u.by_day.length === 0 ? (
              <p className="text-sm text-slate-500">No spending yet this month.</p>
            ) : (
              <figure>
                <div className="flex items-end gap-1 h-40" aria-hidden="true">
                  {u.by_day.map((d) => (
                    <div key={d.day} className="flex-1 min-w-[6px] flex flex-col justify-end h-full group relative">
                      <div className="bg-primary/80 rounded-t" style={{ height: `${Math.max(2, (100 * d.cost_usd) / maxDay)}%` }} />
                      <span className="hidden group-hover:block absolute bottom-full left-1/2 -translate-x-1/2 mb-1 text-[10px] whitespace-nowrap bg-slate-900 text-white px-1.5 py-0.5 rounded">
                        {d.day}: {usd(d.cost_usd)}
                      </span>
                    </div>
                  ))}
                </div>
                <figcaption className="flex justify-between text-[10px] text-slate-400 mt-1">
                  <span>{u.by_day[0].day}</span>
                  <span>{u.by_day[u.by_day.length - 1].day}</span>
                </figcaption>
                <table className="sr-only">
                  <caption>Spending by day</caption>
                  <tbody>
                    {u.by_day.map((d) => (
                      <tr key={d.day}>
                        <td>{d.day}</td>
                        <td>{usd(d.cost_usd)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </figure>
            )}
          </Card>

          <Card title="By kind of call">
            <ul className="text-sm space-y-1">
              {u.by_purpose.map((p) => (
                <li key={p.purpose} className="flex justify-between gap-2">
                  <span>{PURPOSE[p.purpose] || p.purpose}</span>
                  <span className="tabular-nums">
                    {usd(p.cost_usd)} · {p.calls.toLocaleString()}
                  </span>
                </li>
              ))}
            </ul>
          </Card>

          <Card title="By model" className="lg:col-span-3">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-xs text-slate-500 border-b border-slate-200 dark:border-slate-800">
                    <th className="py-2 pr-2 font-semibold">Model</th>
                    <th className="py-2 pr-2 font-semibold">Calls</th>
                    <th className="py-2 pr-2 font-semibold">Tokens in</th>
                    <th className="py-2 pr-2 font-semibold">Tokens out</th>
                    <th className="py-2 font-semibold">Cost</th>
                  </tr>
                </thead>
                <tbody>
                  {u.by_model.map((m) => (
                    <tr key={`${m.provider}/${m.model}/${m.kind}`} className="border-b border-slate-100 dark:border-slate-800/60">
                      <td className="py-1.5 pr-2">
                        {m.provider}/{m.model}
                        {m.kind === "embed" ? " (search)" : ""}
                      </td>
                      <td className="py-1.5 pr-2 tabular-nums">{m.calls.toLocaleString()}</td>
                      <td className="py-1.5 pr-2 tabular-nums">{Number(m.input_tokens || 0).toLocaleString()}</td>
                      <td className="py-1.5 pr-2 tabular-nums">{Number(m.output_tokens || 0).toLocaleString()}</td>
                      <td className="py-1.5 tabular-nums">{usd(m.cost_usd)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>

          <Card title="Reading documents" className="lg:col-span-3">
            {u.documents.length === 0 ? (
              <p className="text-sm text-slate-500">No document needed a model call to be read (pages with a text layer and OCR are free).</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-left text-xs text-slate-500 border-b border-slate-200 dark:border-slate-800">
                      <th className="py-2 pr-2 font-semibold">Document</th>
                      <th className="py-2 pr-2 font-semibold">Pages</th>
                      <th className="py-2 pr-2 font-semibold">Reading</th>
                      <th className="py-2 pr-2 font-semibold">Schema fields</th>
                      <th className="py-2 font-semibold"><span className="sr-only">Ledger</span></th>
                    </tr>
                  </thead>
                  <tbody>
                    {u.documents.map((d) => (
                      <tr key={d.document_id} className="border-b border-slate-100 dark:border-slate-800/60">
                        <td className="py-1.5 pr-2">{displayFileName(d.file_name)}</td>
                        <td className="py-1.5 pr-2 tabular-nums">{d.page_count}</td>
                        <td className="py-1.5 pr-2 tabular-nums">{usd(d.ingest_usd)}</td>
                        <td className="py-1.5 pr-2 tabular-nums">{usd(d.fields_usd)}</td>
                        <td className="py-1.5">
                          <Link href={`/documents/${d.document_id}?tab=pages`} className="text-xs text-primary hover:underline">
                            Each page
                          </Link>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>
        </div>
      )}
    </AppShell>
  );
}
