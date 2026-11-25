"use client";

import dynamic from "next/dynamic";
import { useState } from "react";

import Modal from "@/components/ui/Modal";
import { fetchPdfLink } from "@/lib/api";
import type { PageBox } from "@/lib/types";

const PdfPageViewer = dynamic(() => import("@/components/pdf/PdfPageViewer"), {
  ssr: false,
  loading: () => <p className="text-sm text-slate-500 p-4 text-center">Loading the viewer…</p>,
});

interface PDFViewerModalProps {
  isOpen: boolean;
  onClose: () => void;
  docId?: string | null;
  fileName?: string;
  pageNumber?: number;
  /** the printed page label, when it differs from the PDF page */
  printedPage?: string | null;
  boxes?: PageBox[];
  /** what the boxes mark, in words */
  note?: string;
  excerpt?: string;
}

export default function PDFViewerModal({
  isOpen,
  onClose,
  docId,
  fileName = "Document.pdf",
  pageNumber = 1,
  printedPage,
  boxes = [],
  note,
  excerpt,
}: PDFViewerModalProps) {
  // the page a reader turned to; the cited page whenever the dialog opens
  const [turned, setTurned] = useState<number | null>(null);
  const [linkError, setLinkError] = useState<string | null>(null);
  const page = turned ?? pageNumber;

  const close = () => {
    setTurned(null);
    setLinkError(null);
    onClose();
  };

  const openInTab = async () => {
    if (!docId) return;
    // a ten-minute link for this document only; the sign-in token never goes in a URL
    const tab = window.open("", "_blank");
    try {
      const url = await fetchPdfLink(docId);
      if (tab) tab.location.href = `${url}#page=${page}`;
      else window.location.href = `${url}#page=${page}`;
    } catch (e) {
      tab?.close();
      setLinkError((e as Error).message);
    }
  };

  return (
    <Modal open={isOpen} onClose={close} title={`${fileName}, page ${pageNumber}`} hideTitle className="w-full max-w-6xl h-[88vh] flex flex-col overflow-hidden">
      <div className="px-4 py-3 border-b border-slate-200 dark:border-slate-800 flex items-center justify-between gap-3">
        <div className="min-w-0">
          <p className="font-bold text-sm text-slate-900 dark:text-white truncate" title={fileName}>{fileName}</p>
          <p className="text-xs text-slate-500 dark:text-slate-400">
            Cited on page {pageNumber}
            {printedPage && printedPage !== String(pageNumber) ? ` (printed page ${printedPage})` : ""}
          </p>
        </div>
        <div className="flex items-center gap-1 shrink-0">
          {docId && (
            <button
              type="button"
              onClick={openInTab}
              className="p-2 text-slate-500 hover:text-primary hover:bg-slate-100 dark:hover:bg-slate-800 rounded-lg"
              aria-label="Open the PDF in a new tab"
              title="Open the PDF in a new tab"
            >
              <span className="material-symbols-outlined text-[20px]" aria-hidden="true">open_in_new</span>
            </button>
          )}
          <button
            type="button"
            onClick={close}
            className="p-2 text-slate-500 hover:text-red-600 hover:bg-slate-100 dark:hover:bg-slate-800 rounded-lg"
            aria-label="Close"
          >
            <span className="material-symbols-outlined text-[20px]" aria-hidden="true">close</span>
          </button>
        </div>
      </div>

      <div className="flex-1 flex flex-col md:flex-row min-h-0">
        <div className="flex-1 min-h-0 min-w-0">
          {docId ? (
            <PdfPageViewer docId={docId} page={page} onPageChange={setTurned} boxes={boxes} boxesPage={pageNumber} />
          ) : (
            <p className="p-6 text-center text-sm text-slate-500">The PDF of this document is not available.</p>
          )}
        </div>
        <aside className="w-full md:w-80 p-4 border-t md:border-t-0 md:border-l border-slate-200 dark:border-slate-800 overflow-y-auto space-y-4">
          <div>
            <h3 className="text-[11px] uppercase font-bold tracking-wider text-slate-500 mb-1">On the page</h3>
            <p className="text-sm text-slate-700 dark:text-slate-200 flex items-start gap-2">
              {boxes.length > 0 && <span className="mt-1 inline-block w-3 h-3 rounded-sm border-2 border-blue-600 bg-blue-500/20 shrink-0" aria-hidden="true" />}
              <span>{note || (boxes.length ? "The region the citation points at." : "This citation points at the whole page.")}</span>
            </p>
            {turned != null && turned !== pageNumber && (
              <button type="button" onClick={() => setTurned(null)} className="mt-2 text-xs text-primary hover:underline">
                Back to the cited page
              </button>
            )}
          </div>
          {excerpt && (
            <div>
              <h3 className="text-[11px] uppercase font-bold tracking-wider text-slate-500 mb-1">Evidence the answer used</h3>
              <p className="p-3 rounded-xl bg-slate-50 dark:bg-slate-900/60 border border-slate-200 dark:border-slate-800 text-[13px] leading-relaxed text-slate-800 dark:text-slate-200 whitespace-pre-wrap">
                {excerpt}
              </p>
            </div>
          )}
          {linkError && <p role="alert" className="text-xs text-red-600">{linkError}</p>}
        </aside>
      </div>
    </Modal>
  );
}
