"use client";

import { useState } from "react";
import type { ProvenanceCitation } from "@/lib/types";
import PDFViewerModal from "./PDFViewerModal";

interface ProvenanceBadgeProps {
  citation: ProvenanceCitation;
}

export default function ProvenanceBadge({ citation }: ProvenanceBadgeProps) {
  const [isModalOpen, setIsModalOpen] = useState(false);

  const fileName = citation.source_file || (citation as any).document_name || "Document.pdf";
  const docId =
    (citation as any).doc_id ||
    (citation as any).document_id ||
    (typeof citation.chunk_id === "string" && citation.chunk_id.includes("_") ? citation.chunk_id.split("_")[0] : undefined) ||
    (typeof citation.source_file === "string" && citation.source_file.includes("_") ? citation.source_file.split("_")[0] : undefined) ||
    (typeof (citation as any).document_name === "string" && (citation as any).document_name.includes("_") ? (citation as any).document_name.split("_")[0] : undefined);
  const page = citation.page_number ?? 1;

  const hash = citation.content_hash;

  const rawBbox = citation.bbox;
  const bboxArray: number[] | undefined = Array.isArray(rawBbox)
    ? rawBbox
    : typeof rawBbox === "string"
    ? (rawBbox as string)
        .split(",")
        .map((s) => parseFloat(s.trim()))
        .filter((n) => !isNaN(n))
    : undefined;

  const bboxStr = bboxArray && bboxArray.length > 0 ? bboxArray.join(", ") : null;
  const chunkText = citation.chunk_text as string | undefined;

  return (
    <>
      <button
        onClick={() => setIsModalOpen(true)}
        className="inline-flex items-center gap-xs bg-surface-container-lowest border border-outline-variant/30 hover:border-primary px-3 py-1.5 rounded-lg transition-all group"
        title={
          hash
            ? `Click to view source PDF evidence.\nContent hash: ${hash}${bboxStr ? `\nBBox: [${bboxStr}]` : ""}`
            : "Click to view source PDF evidence"
        }
      >
        <span className="material-symbols-outlined text-primary text-sm">
          description
        </span>
        <span className="font-body-sm text-body-sm text-on-surface-variant group-hover:text-primary">
          📄 {fileName}
          {page != null && ` — Page ${page}`}{" "}
          <span className="font-bold text-green-600 ml-1">[Verified]</span>
        </span>
        <span className="material-symbols-outlined text-xs text-on-surface-variant/40 group-hover:text-primary">
          visibility
        </span>
      </button>

      <PDFViewerModal
        isOpen={isModalOpen}
        onClose={() => setIsModalOpen(false)}
        docId={docId}
        fileName={fileName}
        pageNumber={page}
        bbox={bboxArray}
        chunkText={chunkText}
      />
    </>
  );
}
