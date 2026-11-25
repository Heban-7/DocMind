"use client";

import dynamic from "next/dynamic";
import { useSearchParams } from "next/navigation";
import { Suspense, use, useCallback, useEffect, useMemo, useState } from "react";

import AppShell, { Card, ErrorNote } from "@/components/layout/AppShell";
import { formatValue, ReviewActions, StatusChip } from "@/components/fields/FieldRow";
import {
  downloadExport,
  fetchDocumentStatus,
  fetchFields,
  fetchLedger,
  fetchSchemas,
  requestFields,
} from "@/lib/api";
import { displayFileName, fieldBox } from "@/lib/boxes";
import type { DocumentInfo, DocumentLedger, ExtractedField, FieldExtraction, SchemaInfo } from "@/lib/types";

const PdfPageViewer = dynamic(() => import("@/components/pdf/PdfPageViewer"), {
  ssr: false,
  loading: () => <p className="text-sm text-slate-500 p-4 text-center">Loading the viewer…</p>,
});

export default function DocumentPage({ params }: { params: Promise<{ docId: string }> }) {
  const { docId } = use(params);
  return (
    <Suspense>
      <DocumentView docId={docId} />
    </Suspense>
  );
}

function DocumentView({ docId }: { docId: string }) {
  const search = useSearchParams();
  const [doc, setDoc] = useState<DocumentInfo | null>(null);
  const [schemas, setSchemas] = useState<SchemaInfo[]>([]);
  const [schema, setSchema] = useState<string>(search.get("schema") || "");
  const [extraction, setExtraction] = useState<FieldExtraction | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [ledger, setLedger] = useState<DocumentLedger | null>(null);
  const [tab, setTab] = useState<"fields" | "pages">(search.get("tab") === "pages" ? "pages" : "fields");
  const [selected, setSelected] = useState<string | null>(search.get("field"));
  const [page, setPage] = useState(1);
  const [error, setError] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);

  useEffect(() => {
    fetchDocumentStatus(docId).then(setDoc).catch((e) => setError(e.message));
    fetchSchemas()
      .then((s) => {
        setSchemas(s);
        setSchema((cur) => cur || s[0]?.name || "");
      })
      .catch((e) => setError(e.message));
  }, [docId]);

  // the newest extraction of any schema first; then the chosen schema's
  const load = useCallback(
    async (name?: string) => {
      try {
        const ex = await fetchFields(docId, name);
        setExtraction(ex);
        return ex;
      } catch (e) {
        setError((e as Error).message);
        return null;
      }
    },
    [docId],
  );

  useEffect(() => {
    const wanted = search.get("field");
    let live = true;
    fetchFields(docId, search.get("schema") || undefined)
      .then((ex) => {
        if (!live) return;
        setExtraction(ex);
        if (ex) setSchema(ex.schema);
        const f = ex?.fields.find((x) => x.field === wanted);
        if (f?.page) setPage(f.page);
      })
      .catch((e) => live && setError((e as Error).message))
      .finally(() => live && setLoaded(true));
    return () => {
      live = false;
    };
  }, [docId, search]);

  // while the worker reads the fields, ask again every two seconds
  const running = extraction?.status === "queued" || extraction?.status === "running";
  useEffect(() => {
    if (!running) return;
    const t = setInterval(() => load(extraction?.schema), 2000);
    return () => clearInterval(t);
  }, [running, load, extraction?.schema]);

  useEffect(() => {
    if (tab !== "pages" || ledger) return;
    fetchLedger(docId)
      .then(setLedger)
      .catch((e) => setError(e.message));
  }, [tab, ledger, docId]);

  const field = useMemo(() => extraction?.fields.find((f) => f.field === selected) || null, [extraction, selected]);

  const start = async () => {
    if (!schema) return;
    setStarting(true);
    setError(null);
    try {
      await requestFields(docId, schema);
      await load(schema);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setStarting(false);
    }
  };

  const update = (f: ExtractedField) =>
    setExtraction((ex) => (ex ? { ...ex, fields: ex.fields.map((x) => (x.field === f.field ? { ...x, ...f } : x)) } : ex));

  const fileName = displayFileName(doc?.file_name);
  const sameSchema = extraction && extraction.schema === schema;

  return (
    <AppShell
      title={fileName}
      actions={
        <div className="flex items-center gap-2 text-sm text-slate-500">
          {doc && <span>{doc.page_count} pages · {doc.status === "indexed" ? "ready" : doc.status}</span>}
        </div>
      }
    >
      <ErrorNote message={error} />
      <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)] gap-4">
        <Card className="h-[78vh] !p-0 overflow-hidden">
          <PdfPageViewer
            docId={docId}
            page={page}
            onPageChange={setPage}
            boxes={field ? fieldBox(field.bbox, field.label, field.grounded !== false) : []}
            boxesPage={field?.page ?? undefined}
          />
        </Card>

        <div className="space-y-4 min-w-0">
          <div role="tablist" aria-label="Document views" className="flex gap-1">
            {(["fields", "pages"] as const).map((t) => (
              <button
                key={t}
                role="tab"
                type="button"
                aria-selected={tab === t}
                onClick={() => setTab(t)}
                className={`px-3 py-1.5 rounded-lg text-sm ${tab === t ? "bg-primary/10 text-primary font-bold" : "hover:bg-slate-100 dark:hover:bg-slate-800"}`}
              >
                {t === "fields" ? "Fields" : "How each page was read"}
              </button>
            ))}
          </div>

          {tab === "fields" && (
            <Card>
              <div className="flex flex-wrap items-end gap-2 mb-3">
                <label className="text-xs text-slate-500 flex flex-col gap-1">
                  Schema
                  <select
                    value={schema}
                    onChange={(e) => {
                      setSchema(e.target.value);
                      load(e.target.value);
                    }}
                    className="px-2 py-1.5 rounded-lg border border-slate-300 dark:border-slate-700 bg-transparent text-sm text-slate-900 dark:text-white"
                  >
                    {schemas.map((s) => (
                      <option key={s.name} value={s.name}>{s.label}</option>
                    ))}
                  </select>
                </label>
                <button
                  type="button"
                  onClick={start}
                  disabled={!schema || starting || running || doc?.status !== "indexed"}
                  className="px-3 py-1.5 rounded-lg bg-primary text-white text-sm font-bold disabled:opacity-40"
                  title={doc?.status !== "indexed" ? "The document is still being read" : undefined}
                >
                  {running ? "Reading the fields…" : sameSchema ? "Read again" : "Read the fields"}
                </button>
                {sameSchema && extraction.status === "done" && (
                  <div className="ml-auto flex gap-1">
                    <button type="button" onClick={() => downloadExport(schema, "csv", [docId]).catch((e) => setError(e.message))} className="px-2 py-1.5 rounded-lg border border-slate-300 dark:border-slate-700 text-xs">
                      CSV
                    </button>
                    <button type="button" onClick={() => downloadExport(schema, "xlsx", [docId]).catch((e) => setError(e.message))} className="px-2 py-1.5 rounded-lg border border-slate-300 dark:border-slate-700 text-xs">
                      Excel
                    </button>
                  </div>
                )}
              </div>
              <p className="text-xs text-slate-500 mb-3">{schemas.find((s) => s.name === schema)?.description}</p>

              {!loaded ? (
                <p className="text-sm text-slate-500">Loading…</p>
              ) : !sameSchema ? (
                <p className="text-sm text-slate-500">No fields read with this schema yet.</p>
              ) : extraction.status === "failed" ? (
                <p role="alert" className="text-sm text-red-600">Reading the fields failed: {extraction.error}</p>
              ) : running ? (
                <p className="text-sm text-slate-500" role="status">The worker is reading the statement pages; this takes about ten seconds.</p>
              ) : (
                <FieldsTable
                  docId={docId}
                  extraction={extraction}
                  selected={selected}
                  onSelect={(f) => {
                    setSelected(f.field);
                    if (f.page) setPage(f.page);
                  }}
                  onSaved={update}
                />
              )}
            </Card>
          )}

          {tab === "pages" && (
            <Card>
              {!ledger ? (
                <p className="text-sm text-slate-500">Loading…</p>
              ) : (
                <LedgerTable ledger={ledger} onOpen={setPage} />
              )}
            </Card>
          )}
        </div>
      </div>
    </AppShell>
  );
}

function FieldsTable({
  docId,
  extraction,
  selected,
  onSelect,
  onSaved,
}: {
  docId: string;
  extraction: FieldExtraction;
  selected: string | null;
  onSelect: (f: ExtractedField) => void;
  onSaved: (f: ExtractedField) => void;
}) {
  const broken = (extraction.rules || []).filter((r) => !r.passed);
  return (
    <>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-xs text-slate-500 border-b border-slate-200 dark:border-slate-800">
              <th className="py-2 pr-2 font-semibold">Field</th>
              <th className="py-2 pr-2 font-semibold">Value</th>
              <th className="py-2 pr-2 font-semibold">Page</th>
              <th className="py-2 pr-2 font-semibold">Status</th>
              <th className="py-2 font-semibold"><span className="sr-only">Review</span></th>
            </tr>
          </thead>
          <tbody>
            {extraction.fields.map((f) => (
              <tr
                key={f.field}
                className={`border-b border-slate-100 dark:border-slate-800/60 align-top ${selected === f.field ? "bg-primary/5" : ""}`}
              >
                <td className="py-2 pr-2">
                  <button
                    type="button"
                    onClick={() => onSelect(f)}
                    disabled={!f.page}
                    className="text-left font-medium hover:text-primary disabled:hover:text-inherit"
                    aria-label={f.page ? `${f.label || f.field}: show on page ${f.page}` : f.label || f.field}
                  >
                    {f.label || f.field}
                  </button>
                  {f.reasons.length > 0 && <p className="text-[11px] text-amber-700 dark:text-amber-400">{f.reasons.join("; ")}</p>}
                </td>
                <td className="py-2 pr-2 tabular-nums">
                  {formatValue(f)}
                  {f.printed && String(f.printed) !== formatValue(f) && (
                    <span className="block text-[11px] text-slate-400">printed “{f.printed}”</span>
                  )}
                </td>
                <td className="py-2 pr-2">{f.page ?? "—"}</td>
                <td className="py-2 pr-2">
                  <StatusChip status={f.status} />
                  <span className="block text-[10px] text-slate-400 mt-0.5">{Math.round(f.confidence * 100)}% sure</span>
                </td>
                <td className="py-2">
                  <ReviewActions docId={docId} field={f} schema={extraction.schema} onSaved={onSaved} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="mt-3 text-xs text-slate-500 space-y-1">
        {broken.length ? (
          broken.map((r) => (
            <p key={r.name} className="text-amber-700 dark:text-amber-400">
              Check failed: {r.name.replaceAll("_", " ")}{r.detail ? ` (${r.detail})` : ""}{r.soft ? ", a soft check" : ""}
            </p>
          ))
        ) : (
          <p>Every check of the schema holds ({(extraction.rules || []).length} checks).</p>
        )}
        <p>
          Read by {extraction.model || "the server model"} from pages {extraction.pages_read.join(", ") || "—"} in{" "}
          {extraction.seconds != null ? `${extraction.seconds.toFixed(1)} s` : "—"} for ${extraction.cost_usd.toFixed(4)}.
        </p>
      </div>
    </>
  );
}

function LedgerTable({ ledger, onOpen }: { ledger: DocumentLedger; onOpen: (p: number) => void }) {
  return (
    <>
      <p className="text-xs text-slate-500 mb-3">
        {Object.entries(ledger.engines)
          .map(([e, n]) => `${n} page${n === 1 ? "" : "s"} by ${e.replace("_", " ")}`)
          .join(" · ")}
        {` · ${ledger.seconds.toFixed(1)} s · $${ledger.cost_usd.toFixed(4)} in model calls · ${ledger.needs_review} flagged`}
      </p>
      <div className="overflow-auto max-h-[60vh]">
        <table className="w-full text-sm">
          <thead className="sticky top-0 bg-white dark:bg-[#0c1021]">
            <tr className="text-left text-xs text-slate-500 border-b border-slate-200 dark:border-slate-800">
              <th className="py-2 pr-2 font-semibold">Page</th>
              <th className="py-2 pr-2 font-semibold">Read by</th>
              <th className="py-2 pr-2 font-semibold">Confidence</th>
              <th className="py-2 pr-2 font-semibold">Time</th>
              <th className="py-2 pr-2 font-semibold">Cost</th>
              <th className="py-2 font-semibold">Flags</th>
            </tr>
          </thead>
          <tbody>
            {ledger.pages.map((p) => (
              <tr key={p.page} className={`border-b border-slate-100 dark:border-slate-800/60 ${p.needs_review ? "bg-amber-500/5" : ""}`}>
                <td className="py-1.5 pr-2">
                  <button type="button" onClick={() => onOpen(p.page)} className="hover:text-primary underline-offset-2 hover:underline" aria-label={`Show page ${p.page}`}>
                    {p.page}
                  </button>
                </td>
                <td className="py-1.5 pr-2">{p.engine.replace("_", " ")}</td>
                <td className="py-1.5 pr-2 tabular-nums">{Math.round(p.confidence * 100)}%</td>
                <td className="py-1.5 pr-2 tabular-nums">{p.seconds.toFixed(1)} s</td>
                <td className="py-1.5 pr-2 tabular-nums">{p.cost_usd ? `$${p.cost_usd.toFixed(4)}` : "—"}</td>
                <td className="py-1.5 text-xs text-amber-700 dark:text-amber-400">{p.flags.join("; ")}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
