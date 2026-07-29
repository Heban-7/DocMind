"use client";

import { useState } from "react";
import { getDocumentPdfUrl } from "@/lib/api";

interface PDFViewerModalProps {
  isOpen: boolean;
  onClose: () => void;
  docId?: string;
  fileName?: string;
  pageNumber?: number;
  bbox?: number[];
  chunkText?: string;
}

export default function PDFViewerModal({
  isOpen,
  onClose,
  docId,
  fileName = "Document.pdf",
  pageNumber = 1,
  bbox,
  chunkText,
}: PDFViewerModalProps) {
  const [currentPage, setCurrentPage] = useState(pageNumber);

  if (!isOpen) return null;

  const pdfBaseUrl = docId ? getDocumentPdfUrl(docId) : null;
  const pdfUrlWithPage = pdfBaseUrl ? `${pdfBaseUrl}#page=${currentPage}` : null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-md bg-black/60 backdrop-blur-sm fade-in">
      <div className="bg-surface-container-lowest border border-outline-variant/30 rounded-2xl w-full max-w-5xl h-[85vh] flex flex-col shadow-2xl overflow-hidden relative">
        {/* Header */}
        <div className="px-lg py-md border-b border-outline-variant/20 flex items-center justify-between bg-surface-container-low/50">
          <div className="flex items-center gap-sm">
            <div className="w-8 h-8 rounded-lg bg-primary/10 flex items-center justify-center text-primary">
              <span className="material-symbols-outlined">description</span>
            </div>
            <div>
              <h3 className="font-headline-md text-body-md font-bold text-on-surface">
                {fileName}
              </h3>
              <p className="font-body-sm text-[12px] text-on-surface-variant">
                Page {currentPage} {bbox ? `• BBox [${bbox.join(", ")}]` : ""}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-md">
            {/* Page navigation */}
            <div className="flex items-center gap-xs bg-surface-container px-2 py-1 rounded-lg">
              <button
                disabled={currentPage <= 1}
                onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
                className="p-1 hover:bg-surface-container-high rounded disabled:opacity-30"
              >
                <span className="material-symbols-outlined text-sm">chevron_left</span>
              </button>
              <span className="font-label-md text-xs px-2">Page {currentPage}</span>
              <button
                onClick={() => setCurrentPage((p) => p + 1)}
                className="p-1 hover:bg-surface-container-high rounded"
              >
                <span className="material-symbols-outlined text-sm">chevron_right</span>
              </button>
            </div>

            {/* External link */}
            {pdfUrlWithPage && (
              <a
                href={pdfUrlWithPage}
                target="_blank"
                rel="noreferrer"
                className="p-2 text-on-surface-variant hover:text-primary hover:bg-surface-container rounded-lg transition-colors"
                title="Open raw PDF in new tab"
              >
                <span className="material-symbols-outlined text-[20px]">open_in_new</span>
              </a>
            )}

            {/* Close button */}
            <button
              onClick={onClose}
              className="p-2 text-on-surface-variant hover:text-error hover:bg-error-container/20 rounded-lg transition-colors"
            >
              <span className="material-symbols-outlined text-[20px]">close</span>
            </button>
          </div>
        </div>

        {/* Body content */}
        <div className="flex-1 flex flex-col md:flex-row overflow-hidden">
          {/* Main PDF Viewer Iframe */}
          <div className="flex-1 bg-surface-container-high/30 relative flex items-center justify-center border-r border-outline-variant/20">
            {pdfUrlWithPage ? (
              <iframe
                src={pdfUrlWithPage}
                className="w-full h-full border-none"
                title={fileName}
              />
            ) : (
              <div className="p-xl text-center text-on-surface-variant">
                <span className="material-symbols-outlined text-[48px] opacity-40 mb-sm block">
                  find_in_page
                </span>
                <p className="font-body-md">PDF document source file not available.</p>
              </div>
            )}
          </div>

          {/* Side Panel: Cited Snippet & Metadata */}
          <div className="w-full md:w-80 p-lg bg-surface-container-lowest flex flex-col gap-md overflow-y-auto">
            <div>
              <span className="font-label-md text-[11px] text-primary uppercase font-bold tracking-wider block mb-xs">
                Verified Provenance Citation
              </span>
              <div className="p-md rounded-xl bg-surface-container-low border border-outline-variant/30 text-on-surface font-body-sm text-[13px] leading-relaxed">
                {chunkText || "Source chunk text provided by provenance trace."}
              </div>
            </div>

            {bbox && bbox.length >= 4 && (
              <div>
                <span className="font-label-md text-[11px] text-on-surface-variant/70 uppercase font-bold tracking-wider block mb-xs">
                  Spatial Bounding Box (PDF Points)
                </span>
                <div className="grid grid-cols-2 gap-xs font-code text-xs">
                  <div className="p-2 bg-surface-container rounded border border-outline-variant/20">
                    <span className="text-on-surface-variant/60 block text-[10px]">X0 / Y0</span>
                    [{bbox[0]}, {bbox[1]}]
                  </div>
                  <div className="p-2 bg-surface-container rounded border border-outline-variant/20">
                    <span className="text-on-surface-variant/60 block text-[10px]">X1 / Y1</span>
                    [{bbox[2]}, {bbox[3]}]
                  </div>
                </div>
              </div>
            )}

            <div className="mt-auto pt-md border-t border-outline-variant/20">
              <div className="flex items-center gap-xs text-green-600 font-label-md text-xs font-bold">
                <span className="material-symbols-outlined text-[16px]">verified</span>
                <span>Zero-Trust Grounded Evidence</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
