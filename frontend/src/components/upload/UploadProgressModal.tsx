"use client";

import { useEffect, useState } from "react";
import type { UploadedDocument, UploadState } from "@/lib/types";

interface UploadProgressModalProps {
  isOpen: boolean;
  onClose: () => void;
  uploadState: UploadState;
  document: UploadedDocument | null;
  error?: string | null;
  file?: File | null;
}

export default function UploadProgressModal({
  isOpen,
  onClose,
  uploadState,
  document,
  error,
  file,
}: UploadProgressModalProps) {
  const [currentStep, setCurrentStep] = useState<number>(1);

  useEffect(() => {
    if (uploadState === "uploading") {
      setCurrentStep(1);
    } else if (uploadState === "processing") {
      const timer = setTimeout(() => setCurrentStep(2), 1200);
      return () => clearTimeout(timer);
    } else if (uploadState === "indexed") {
      setCurrentStep(3);
    }
  }, [uploadState]);

  if (!isOpen) return null;

  const fileName = document?.file_name || file?.name || "Document.pdf";
  const fileSizeMb = file ? (file.size / (1024 * 1024)).toFixed(2) : null;
  const pageCount = document?.page_count;
  const strategyTier = document?.strategy_tier || "standard";

  const tierBadges: Record<string, { label: string; color: string; desc: string }> = {
    fast: {
      label: "Fast Tier (Direct Text Parsing)",
      color: "bg-emerald-500/10 text-emerald-600 border-emerald-500/30",
      desc: "Native digital PDF processed via rapid heuristic extraction.",
    },
    standard: {
      label: "Standard Tier (Layout & Table Extraction)",
      color: "bg-indigo-500/10 text-indigo-600 border-indigo-500/30",
      desc: "Multi-column layout structure with cell-level table extraction.",
    },
    premium: {
      label: "Premium Tier (Vision-Language OCR)",
      color: "bg-purple-500/10 text-purple-600 border-purple-500/30",
      desc: "Scanned document processed with high-precision multimodal VLM OCR.",
    },
  };

  const currentTierInfo = tierBadges[strategyTier.toLowerCase()] || tierBadges.standard;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-md bg-black/60 backdrop-blur-md fade-in">
      <div className="bg-surface-container-lowest border border-outline-variant/30 rounded-2xl w-full max-w-lg p-xl shadow-2xl relative overflow-hidden">
        {/* Glow */}
        <div className="absolute top-0 right-0 w-32 h-32 bg-primary/10 rounded-full blur-2xl pointer-events-none" />

        {/* Modal Header */}
        <div className="flex items-center justify-between mb-lg pb-md border-b border-outline-variant/20">
          <div className="flex items-center gap-sm">
            <div className="w-10 h-10 rounded-xl bg-primary/10 flex items-center justify-center text-primary">
              <span className="material-symbols-outlined text-[24px]">description</span>
            </div>
            <div>
              <h3 className="font-headline-md text-base font-bold text-on-surface truncate max-w-[260px]">
                {fileName}
              </h3>
              <p className="font-body-sm text-xs text-on-surface-variant/70">
                {fileSizeMb ? `${fileSizeMb} MB` : "PDF Document"}{" "}
                {pageCount ? `• ${pageCount} pages` : ""}
              </p>
            </div>
          </div>

          <button
            onClick={onClose}
            className="p-2 hover:bg-surface-container rounded-lg text-on-surface-variant transition-colors"
          >
            <span className="material-symbols-outlined text-[20px]">close</span>
          </button>
        </div>

        {/* Processing Pipeline Stages */}
        <div className="space-y-md mb-xl">
          {/* Stage 1: Triage */}
          <div className="flex items-start gap-md">
            <div
              className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold transition-all ${
                currentStep > 1
                  ? "bg-emerald-500 text-white"
                  : currentStep === 1
                  ? "bg-primary text-white animate-pulse"
                  : "bg-surface-container text-on-surface-variant/40"
              }`}
            >
              {currentStep > 1 ? (
                <span className="material-symbols-outlined text-sm">check</span>
              ) : (
                "1"
              )}
            </div>
            <div className="flex-1">
              <h4 className="font-label-md text-xs font-bold text-on-surface">
                Phase 1: Automated Triage & Cost Classification
              </h4>
              <p className="font-body-sm text-[11px] text-on-surface-variant/70">
                Analyzing PDF layout complexity, origin, and optimal routing tier.
              </p>
            </div>
          </div>

          {/* Stage 2: Extraction & Chunking */}
          <div className="flex items-start gap-md">
            <div
              className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold transition-all ${
                currentStep > 2
                  ? "bg-emerald-500 text-white"
                  : currentStep === 2
                  ? "bg-primary text-white animate-pulse"
                  : "bg-surface-container text-on-surface-variant/40"
              }`}
            >
              {currentStep > 2 ? (
                <span className="material-symbols-outlined text-sm">check</span>
              ) : (
                "2"
              )}
            </div>
            <div className="flex-1">
              <h4 className="font-label-md text-xs font-bold text-on-surface">
                Phase 2 & 3: Layout Extraction & Logical Semantic Chunking
              </h4>
              <p className="font-body-sm text-[11px] text-on-surface-variant/70">
                Extracting multi-column reading order, tables, and creating LDU fragments.
              </p>
            </div>
          </div>

          {/* Stage 3: Indexing */}
          <div className="flex items-start gap-md">
            <div
              className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold transition-all ${
                uploadState === "indexed"
                  ? "bg-emerald-500 text-white"
                  : currentStep === 3
                  ? "bg-primary text-white animate-pulse"
                  : "bg-surface-container text-on-surface-variant/40"
              }`}
            >
              {uploadState === "indexed" ? (
                <span className="material-symbols-outlined text-sm">check</span>
              ) : (
                "3"
              )}
            </div>
            <div className="flex-1">
              <h4 className="font-label-md text-xs font-bold text-on-surface">
                Phase 4: PageIndex Tree & Vector Embeddings
              </h4>
              <p className="font-body-sm text-[11px] text-on-surface-variant/70">
                Indexing structural hierarchy into Chroma DB and SQLite PageMap store.
              </p>
            </div>
          </div>
        </div>

        {/* Assigned Strategy Badge */}
        {uploadState === "indexed" && (
          <div className="p-md rounded-xl bg-surface-container-low border border-outline-variant/30 mb-lg">
            <div className="flex items-center justify-between mb-xs">
              <span className="font-label-md text-[11px] uppercase font-bold text-on-surface-variant/60">
                Assigned Refinery Strategy
              </span>
              <span
                className={`px-2 py-0.5 rounded-full text-[10px] font-bold border ${currentTierInfo.color}`}
              >
                {currentTierInfo.label}
              </span>
            </div>
            <p className="font-body-sm text-xs text-on-surface-variant">
              {currentTierInfo.desc}
            </p>
          </div>
        )}

        {/* Error Display */}
        {uploadState === "error" && error && (
          <div className="p-md rounded-xl bg-red-500/10 border border-red-500/30 text-red-600 text-xs mb-lg">
            <div className="flex items-center gap-xs font-bold mb-1">
              <span className="material-symbols-outlined text-sm">error</span>
              <span>Ingestion Failed</span>
            </div>
            <p>{error}</p>
          </div>
        )}

        {/* Footer Action */}
        <div className="flex justify-end gap-sm pt-md border-t border-outline-variant/20">
          <button
            onClick={onClose}
            className="px-lg py-2 rounded-xl bg-primary text-white font-label-md text-xs font-bold hover:bg-primary-container transition-all"
          >
            {uploadState === "indexed" ? "Done & Ready for Q&A" : "Dismiss"}
          </button>
        </div>
      </div>
    </div>
  );
}
