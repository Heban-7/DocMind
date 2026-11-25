"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import AppShell, { Card, ErrorNote } from "@/components/layout/AppShell";
import { formatValue, ReviewActions } from "@/components/fields/FieldRow";
import { downloadExport, fetchReviewQueue, fetchSchemas } from "@/lib/api";
import { displayFileName } from "@/lib/boxes";
import type { ExtractedField, ReviewItem, SchemaInfo } from "@/lib/types";

/** Every field the extractor was unsure of, across the account's documents. */
export default function ReviewPage() {
  const [items, setItems] = useState<ReviewItem[] | null>(null);
  const [schemas, setSchemas] = useState<SchemaInfo[]>([]);
  const [done, setDone] = useState<Record<string, ExtractedField["status"]>>({});
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchReviewQueue().then(setItems).catch((e) => setError(e.message));
    fetchSchemas().then(setSchemas).catch(() => setSchemas([]));
  }, []);

  const byDoc = useMemo(() => {
    const out = new Map<string, ReviewItem[]>();
    for (const it of items || []) out.set(it.document_id, [...(out.get(it.document_id) || []), it]);
    return Array.from(out.values());
  }, [items]);

  const left = (items || []).filter((i) => !done[`${i.document_id}/${i.field}`]).length;
  const label = (name: string) => schemas.find((s) => s.name === name)?.label || name;

  return (
    <AppShell
      title="Review"
      actions={
        <div className="flex flex-wrap items-center gap-2">
          {schemas.map((s) => (
            <div key={s.name} className="flex items-center gap-1 text-xs">
              <span className="text-slate-500">{s.label}:</span>
              <button type="button" onClick={() => downloadExport(s.name, "csv").catch((e) => setError(e.message))} className="px-2 py-1 rounded-lg border border-slate-300 dark:border-slate-700">
                CSV
              </button>
              <button type="button" onClick={() => downloadExport(s.name, "xlsx").catch((e) => setError(e.message))} className="px-2 py-1 rounded-lg border border-slate-300 dark:border-slate-700">
                Excel
              </button>
            </div>
          ))}
        </div>
      }
    >
      <ErrorNote message={error} />
      <p className="text-sm text-slate-600 dark:text-slate-300 mb-4">
        {items == null
          ? "Loading…"
          : left
            ? `${left} value${left === 1 ? "" : "s"} to check. Open one to see where it was read on the page; the exports mark these cells yellow until they are checked.`
            : "Nothing to check. Every value the extractor read is accepted, confirmed or corrected."}
      </p>
      <div className="space-y-4">
        {byDoc.map((fields) => {
          const d = fields[0];
          return (
            <Card key={d.document_id} title={`${displayFileName(d.file_name)} · ${label(d.schema)}`}>
              <ul className="divide-y divide-slate-100 dark:divide-slate-800">
                {fields.map((f) => {
                  const key = `${f.document_id}/${f.field}`;
                  const status = done[key];
                  return (
                    <li key={key} className="py-2 flex flex-wrap items-start gap-3">
                      <div className="min-w-[12rem] flex-1">
                        <p className="font-medium text-sm">{schemas.find((s) => s.name === f.schema)?.fields.find((x) => x.name === f.field)?.label || f.field}</p>
                        <p className="text-sm tabular-nums">
                          {formatValue(f)}
                          {f.printed ? <span className="text-xs text-slate-400"> · printed “{f.printed}”</span> : null}
                        </p>
                        {f.reasons.length > 0 && <p className="text-[11px] text-amber-700 dark:text-amber-400">{f.reasons.join("; ")}</p>}
                      </div>
                      <Link
                        href={`/documents/${f.document_id}?schema=${encodeURIComponent(f.schema)}&field=${encodeURIComponent(f.field)}`}
                        className="text-xs text-primary hover:underline self-center"
                      >
                        {f.page ? `See page ${f.page}` : "Open the document"}
                      </Link>
                      <div className="self-center">
                        {status ? (
                          <span className="text-xs text-slate-500" role="status">{status === "confirmed" ? "Confirmed" : status === "corrected" ? "Corrected" : "Rejected"}</span>
                        ) : (
                          <ReviewActions
                            docId={f.document_id}
                            field={{ ...f, type: schemas.find((s) => s.name === f.schema)?.fields.find((x) => x.name === f.field)?.type }}
                            schema={f.schema}
                            onSaved={(saved) => setDone((m) => ({ ...m, [key]: saved.status }))}
                          />
                        )}
                      </div>
                    </li>
                  );
                })}
              </ul>
            </Card>
          );
        })}
      </div>
    </AppShell>
  );
}
