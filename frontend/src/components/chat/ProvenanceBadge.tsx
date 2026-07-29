"use client";

import type { ProvenanceCitation } from "@/lib/types";

interface ProvenanceBadgeProps {
  citation: ProvenanceCitation;
}

export default function ProvenanceBadge({ citation }: ProvenanceBadgeProps) {
  const fileName = citation.source_file || "Document.pdf";
  const page = citation.page_number;
  const hash = citation.content_hash;

  return (
    <button
      className="inline-flex items-center gap-xs bg-surface-container-lowest border border-outline-variant/30 hover:border-primary px-3 py-1.5 rounded-lg transition-all group"
      title={
        hash
          ? `Content hash: ${hash}${citation.bbox ? `\nBBox: [${citation.bbox.join(", ")}]` : ""}`
          : undefined
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
      <span className="material-symbols-outlined text-xs text-on-surface-variant/40">
        open_in_new
      </span>
    </button>
  );
}
