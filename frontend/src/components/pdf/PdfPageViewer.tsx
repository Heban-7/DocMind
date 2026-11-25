"use client";

// Client only: load with next/dynamic and { ssr: false } (PDF.js needs the browser).
import { useEffect, useMemo, useRef, useState } from "react";
import { Document, Page, pdfjs } from "react-pdf";
import "react-pdf/dist/Page/TextLayer.css";
import "react-pdf/dist/Page/AnnotationLayer.css";

import { documentPdfSource } from "@/lib/api";
import type { PageBox } from "@/lib/types";

// The worker must be set in the module that renders <Document> (react-pdf README).
pdfjs.GlobalWorkerOptions.workerSrc = new URL("pdfjs-dist/build/pdf.worker.min.mjs", import.meta.url).toString();

export interface PdfPageViewerProps {
  docId: string;
  page: number;
  onPageChange: (page: number) => void;
  /** boxes for the page in `boxesPage`, PDF points from the top-left corner */
  boxes?: PageBox[];
  boxesPage?: number;
  onPageCount?: (n: number) => void;
}

/**
 * One PDF page with the cited regions drawn on it. The file is fetched once
 * (with the sign-in header, never a token in the URL); turning pages only
 * renders another page of the loaded document.
 */
export default function PdfPageViewer({ docId, page, onPageChange, boxes = [], boxesPage, onPageCount }: PdfPageViewerProps) {
  const holder = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(640);
  const [pages, setPages] = useState(0);
  const [size, setSize] = useState<{ w: number; h: number } | null>(null);
  const [error, setError] = useState<string | null>(null);

  // the same object for the whole life of the document, or react-pdf reloads it
  const file = useMemo(() => documentPdfSource(docId), [docId]);

  useEffect(() => {
    const el = holder.current;
    if (!el) return;
    const ro = new ResizeObserver(([entry]) => setWidth(Math.max(280, Math.floor(entry.contentRect.width) - 24)));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const shown = boxesPage == null || boxesPage === page ? boxes : [];
  const scale = size ? width / size.w : 1;
  const firstBox = useRef<HTMLDivElement>(null);

  // bring the first box into view once the page is drawn
  useEffect(() => {
    if (size && shown.length) firstBox.current?.scrollIntoView({ block: "center", behavior: "smooth" });
  }, [size, shown.length, page]);

  return (
    <div className="flex flex-col h-full min-h-0">
      <div className="flex items-center justify-center gap-2 py-2 border-b border-slate-200 dark:border-slate-800 shrink-0">
        <button
          type="button"
          aria-label="Previous page"
          disabled={page <= 1}
          onClick={() => onPageChange(Math.max(1, page - 1))}
          className="p-1 rounded hover:bg-slate-200 dark:hover:bg-slate-800 disabled:opacity-30"
        >
          <span className="material-symbols-outlined text-sm" aria-hidden="true">chevron_left</span>
        </button>
        <label className="text-xs text-slate-600 dark:text-slate-300 flex items-center gap-1">
          Page
          <input
            type="number"
            min={1}
            max={pages || undefined}
            value={page}
            onChange={(e) => {
              const n = parseInt(e.target.value, 10);
              if (n >= 1 && (!pages || n <= pages)) onPageChange(n);
            }}
            className="w-14 px-1 py-0.5 rounded border border-slate-300 dark:border-slate-700 bg-transparent text-center"
            aria-label="Page number"
          />
          {pages ? `of ${pages}` : ""}
        </label>
        <button
          type="button"
          aria-label="Next page"
          disabled={pages > 0 && page >= pages}
          onClick={() => onPageChange(pages ? Math.min(pages, page + 1) : page + 1)}
          className="p-1 rounded hover:bg-slate-200 dark:hover:bg-slate-800 disabled:opacity-30"
        >
          <span className="material-symbols-outlined text-sm" aria-hidden="true">chevron_right</span>
        </button>
      </div>

      <div ref={holder} className="flex-1 overflow-auto bg-slate-200/60 dark:bg-slate-900/60 p-3">
        {error ? (
          <p role="alert" className="text-sm text-red-600 p-4 text-center">{error}</p>
        ) : (
          <Document
            file={file}
            onLoadSuccess={(pdf) => {
              setPages(pdf.numPages);
              setError(null);
              onPageCount?.(pdf.numPages);
            }}
            onLoadError={(e) => setError(`The PDF could not be opened: ${e.message}`)}
            loading={<p className="text-sm text-slate-500 p-4 text-center">Loading the PDF…</p>}
          >
            <div className="relative mx-auto shadow-md" style={{ width }}>
              <Page
                pageNumber={page}
                width={width}
                onLoadSuccess={(p) => setSize({ w: p.originalWidth, h: p.originalHeight })}
                loading={<div style={{ width, height: width * 1.3 }} className="bg-white dark:bg-slate-800 animate-pulse" />}
              />
              {size &&
                shown.map((b, i) => (
                  <div
                    key={i}
                    ref={i === 0 ? firstBox : undefined}
                    className={`absolute pointer-events-none rounded-sm ${
                      b.tone === "secondary"
                        ? "border-2 border-amber-500/70 bg-amber-300/15"
                        : "border-2 border-blue-600 bg-blue-500/20 ring-2 ring-blue-600/20"
                    }`}
                    style={{
                      left: (b.x0 - 2) * scale,
                      top: (b.top - 2) * scale,
                      width: Math.max(6, (b.x1 - b.x0 + 4) * scale),
                      height: Math.max(6, (b.bottom - b.top + 4) * scale),
                    }}
                    title={b.label}
                    aria-hidden="true"
                  />
                ))}
            </div>
          </Document>
        )}
      </div>
    </div>
  );
}
