"use client";

import { useState } from "react";

import { reviewField } from "@/lib/api";
import type { ExtractedField, FieldStatus } from "@/lib/types";

export function formatValue(f: Pick<ExtractedField, "value" | "type" | "unit">): string {
  const v = f.value;
  if (v == null || v === "") return "—";
  if (Array.isArray(v)) return `${v.length} line${v.length === 1 ? "" : "s"}`;
  if (typeof v === "number") {
    const s = v.toLocaleString(undefined, { maximumFractionDigits: 2 });
    return f.unit ? `${s} ${f.unit}` : s;
  }
  if (typeof v === "object") return JSON.stringify(v);
  return String(v);
}

export const STATUS: Record<FieldStatus, { label: string; cls: string }> = {
  auto: { label: "Accepted", cls: "bg-emerald-500/10 text-emerald-700 dark:text-emerald-400 border-emerald-500/30" },
  needs_review: { label: "Needs review", cls: "bg-amber-500/10 text-amber-700 dark:text-amber-400 border-amber-500/30" },
  missing: { label: "Not found", cls: "bg-slate-500/10 text-slate-600 dark:text-slate-300 border-slate-500/30" },
  confirmed: { label: "Confirmed", cls: "bg-blue-500/10 text-blue-700 dark:text-blue-300 border-blue-500/30" },
  corrected: { label: "Corrected", cls: "bg-blue-500/10 text-blue-700 dark:text-blue-300 border-blue-500/30" },
  rejected: { label: "Rejected", cls: "bg-red-500/10 text-red-700 dark:text-red-300 border-red-500/30" },
};

export function StatusChip({ status }: { status: FieldStatus }) {
  const s = STATUS[status] || STATUS.missing;
  return <span className={`text-[10px] px-1.5 py-0.5 rounded border font-bold whitespace-nowrap ${s.cls}`}>{s.label}</span>;
}

interface ReviewActionsProps {
  docId: string;
  field: ExtractedField;
  schema?: string;
  onSaved: (f: ExtractedField) => void;
}

/** Confirm, correct or reject one field; the machine's value is kept when corrected. */
export function ReviewActions({ docId, field, schema, onSaved }: ReviewActionsProps) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const isList = field.type === "list";

  const act = async (action: "confirm" | "correct" | "reject", value?: unknown) => {
    setBusy(true);
    setError(null);
    try {
      const saved = await reviewField(docId, field.field, action, { value, schema });
      onSaved({ ...field, ...saved });
      setEditing(false);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  if (editing) {
    return (
      <form
        className="flex flex-wrap items-center gap-1"
        onSubmit={(e) => {
          e.preventDefault();
          if (draft.trim()) act("correct", draft.trim());
        }}
      >
        <label className="sr-only" htmlFor={`fix-${field.field}`}>Correct value for {field.label || field.field}</label>
        <input
          id={`fix-${field.field}`}
          autoFocus
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder={field.type === "date" ? "2023-06-30" : field.type === "money" ? "1,234,567" : "value"}
          className="w-36 px-2 py-1 text-xs rounded border border-slate-300 dark:border-slate-700 bg-transparent"
          onKeyDown={(e) => {
            if (e.key === "Escape") {
              e.stopPropagation();
              setEditing(false);
            }
          }}
        />
        <button type="submit" disabled={busy || !draft.trim()} className="text-xs px-2 py-1 rounded bg-primary text-white disabled:opacity-40">
          Save
        </button>
        <button type="button" onClick={() => setEditing(false)} className="text-xs px-2 py-1 rounded hover:bg-slate-100 dark:hover:bg-slate-800">
          Cancel
        </button>
        {error && <span role="alert" className="text-[11px] text-red-600 w-full">{error}</span>}
      </form>
    );
  }

  return (
    <div className="flex flex-wrap items-center gap-1">
      <button
        type="button"
        disabled={busy || field.value == null}
        onClick={() => act("confirm")}
        className="text-xs px-2 py-1 rounded border border-slate-300 dark:border-slate-700 hover:border-emerald-500 hover:text-emerald-700 disabled:opacity-40"
        aria-label={`Confirm ${field.label || field.field}`}
      >
        Confirm
      </button>
      {!isList && (
        <button
          type="button"
          disabled={busy}
          onClick={() => {
            setDraft(field.value == null || typeof field.value === "object" ? "" : String(field.value));
            setEditing(true);
          }}
          className="text-xs px-2 py-1 rounded border border-slate-300 dark:border-slate-700 hover:border-primary hover:text-primary disabled:opacity-40"
          aria-label={`Correct ${field.label || field.field}`}
        >
          Correct
        </button>
      )}
      <button
        type="button"
        disabled={busy}
        onClick={() => act("reject")}
        className="text-xs px-2 py-1 rounded border border-slate-300 dark:border-slate-700 hover:border-red-500 hover:text-red-600 disabled:opacity-40"
        aria-label={`Reject ${field.label || field.field}`}
      >
        Reject
      </button>
      {error && <span role="alert" className="text-[11px] text-red-600 w-full">{error}</span>}
    </div>
  );
}
