"use client";

import { useState } from "react";

import { boxNote, citationBoxes, displayFileName } from "@/lib/boxes";
import type { ProvenanceCitation } from "@/lib/types";
import PDFViewerModal from "./PDFViewerModal";

interface ProvenanceBadgeProps {
  citation: ProvenanceCitation;
  /** the citation's number in the answer ([1], [2], ...) */
  index?: number;
}

function shortName(name: string): string {
  if (name.length <= 26) return name;
  const dot = name.lastIndexOf(".");
  const ext = dot > 0 ? name.slice(dot) : "";
  return `${name.slice(0, 20)}…${ext}`;
}

const KIND: Record<string, string> = { fact: "cell", cell: "cell", block: "passage" };

export default function ProvenanceBadge({ citation, index }: ProvenanceBadgeProps) {
  const [open, setOpen] = useState(false);
  const fileName = displayFileName(citation.document_name);
  const page = citation.page_number ?? 1;
  const boxes = citationBoxes(citation);
  const kind = boxes.length ? KIND[citation.box_kind || ""] || "region" : "page";
  const printed = citation.printed_page && citation.printed_page !== String(page) ? ` (p. ${citation.printed_page})` : "";

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="w-full flex items-center gap-1.5 bg-surface-container-lowest border border-outline-variant/30 hover:border-primary px-3 py-1.5 rounded-xl transition-all group cursor-pointer min-w-0 text-left"
        aria-label={`Open ${fileName} at page ${page}${boxes.length ? ", with the cited " + kind + " marked" : ""}`}
        title={citation.content_hash ? `Evidence hash ${citation.content_hash.slice(0, 12)}…` : undefined}
      >
        {index != null && <span className="text-[11px] font-bold text-primary shrink-0">[{index}]</span>}
        <span className="material-symbols-outlined text-primary text-sm shrink-0" aria-hidden="true">description</span>
        <span className="text-xs text-on-surface-variant group-hover:text-primary font-medium truncate">
          {shortName(fileName)}, page {page}
          {printed}
        </span>
        <span className="ml-auto text-[10px] px-1.5 py-0.5 rounded bg-slate-100 dark:bg-slate-800 text-slate-500 dark:text-slate-400 shrink-0">
          {kind}
        </span>
      </button>

      <PDFViewerModal
        isOpen={open}
        onClose={() => setOpen(false)}
        docId={citation.doc_id}
        fileName={fileName}
        pageNumber={page}
        printedPage={citation.printed_page}
        boxes={boxes}
        note={boxNote(citation.box_kind, boxes.length)}
        excerpt={citation.excerpt}
      />
    </>
  );
}
