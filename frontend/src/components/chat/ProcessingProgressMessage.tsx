"use client";

import { useEffect, useState } from "react";

interface ProcessingProgressMessageProps {
  fileName: string;
  fileSizeMb?: string | null;
  uploadState: "idle" | "uploading" | "processing" | "indexed" | "error";
  strategyTier?: string;
  onComplete?: () => void;
}

export default function ProcessingProgressMessage({
  fileName,
  fileSizeMb,
  uploadState,
  strategyTier,
}: ProcessingProgressMessageProps) {
  const [progressPercent, setProgressPercent] = useState<number>(15);
  const [currentStep, setCurrentStep] = useState<number>(1);

  useEffect(() => {
    if (uploadState === "uploading") {
      setProgressPercent(25);
      setCurrentStep(1);
    } else if (uploadState === "processing") {
      setProgressPercent(45);
      setCurrentStep(2);
      const timer1 = setTimeout(() => {
        setProgressPercent(75);
        setCurrentStep(3);
      }, 1000);
      return () => clearTimeout(timer1);
    } else if (uploadState === "indexed") {
      setProgressPercent(100);
      setCurrentStep(4);
    } else if (uploadState === "error") {
      setProgressPercent(0);
    }
  }, [uploadState]);

  // SVG Circular Ring calculation
  const radius = 28;
  const circumference = 2 * Math.PI * radius;
  const strokeDashoffset = circumference - (progressPercent / 100) * circumference;

  const steps = [
    { id: 1, label: "Uploading & Validating PDF File" },
    { id: 2, label: "Automated Triage & Cost Classification" },
    { id: 3, label: "Multi-Column Layout Extraction & Table Chunking" },
    { id: 4, label: "PageIndex Tree & Vector Indexing in ChromaDB" },
  ];

  return (
    <div className="w-full max-w-[800px] my-md fade-in">
      <div className="bg-surface-container-lowest dark:bg-[#0c1021] border border-outline-variant/30 dark:border-slate-800/80 rounded-2xl p-md shadow-md glass-card flex flex-col md:flex-row items-start md:items-center gap-md relative overflow-hidden">
        {/* Subtle Ambient Background Gradient */}
        <div className="absolute top-0 right-0 w-48 h-48 bg-primary/5 rounded-full blur-xl pointer-events-none" />

        {/* Circular Progress Ring around PDF Icon */}
        <div className="relative w-20 h-20 flex items-center justify-center shrink-0 mx-auto md:mx-0">
          <svg className="w-20 h-20 -rotate-90" viewBox="0 0 70 70">
            {/* Background Track Circle */}
            <circle
              cx="35"
              cy="35"
              r={radius}
              className="stroke-surface-container-high dark:stroke-slate-800"
              strokeWidth="5"
              fill="transparent"
            />
            {/* Animated Progress Circle */}
            <circle
              cx="35"
              cy="35"
              r={radius}
              className="stroke-primary transition-all duration-500 ease-out"
              strokeWidth="5"
              strokeDasharray={circumference}
              strokeDashoffset={strokeDashoffset}
              strokeLinecap="round"
              fill="transparent"
            />
          </svg>

          {/* Center PDF Icon */}
          <div className="absolute inset-0 flex flex-col items-center justify-center text-primary">
            <span className="material-symbols-outlined text-[24px]">description</span>
            <span className="font-label-md text-[10px] font-bold text-on-surface">
              {progressPercent}%
            </span>
          </div>
        </div>

        {/* Details & Pipeline Checklist */}
        <div className="flex-1 w-full space-y-xs">
          {/* File Header */}
          <div className="flex items-center justify-between">
            <div className="truncate max-w-[280px] sm:max-w-[400px]">
              <h4 className="font-headline-md text-sm font-bold text-on-surface truncate">
                {fileName}
              </h4>
              <p className="font-body-sm text-[11px] text-on-surface-variant/70">
                {fileSizeMb ? `${fileSizeMb} MB` : "Document Ingestion"}
                {strategyTier ? ` • Tier: ${strategyTier}` : ""}
              </p>
            </div>

            {/* Status Badge */}
            <div>
              {uploadState === "indexed" ? (
                <span className="px-2.5 py-1 rounded-full text-[11px] font-bold bg-emerald-500/10 text-emerald-600 border border-emerald-500/30 flex items-center gap-1">
                  <span className="material-symbols-outlined text-[14px]">check_circle</span>
                  <span>Indexed</span>
                </span>
              ) : uploadState === "error" ? (
                <span className="px-2.5 py-1 rounded-full text-[11px] font-bold bg-red-500/10 text-red-600 border border-red-500/30 flex items-center gap-1">
                  <span className="material-symbols-outlined text-[14px]">error</span>
                  <span>Failed</span>
                </span>
              ) : (
                <span className="px-2.5 py-1 rounded-full text-[11px] font-bold bg-primary/10 text-primary border border-primary/30 flex items-center gap-1 animate-pulse">
                  <span className="material-symbols-outlined text-[14px] animate-spin">
                    progress_activity
                  </span>
                  <span>Processing</span>
                </span>
              )}
            </div>
          </div>

          {/* Progress Steps List */}
          <div className="space-y-1 pt-xs border-t border-outline-variant/20">
            {steps.map((step) => {
              const isDone = currentStep > step.id || uploadState === "indexed";
              const isCurrent = currentStep === step.id && uploadState !== "indexed";

              return (
                <div key={step.id} className="flex items-center gap-xs text-[11px]">
                  <span
                    className={`w-3.5 h-3.5 rounded-full flex items-center justify-center text-[9px] font-bold ${
                      isDone
                        ? "bg-emerald-500 text-white"
                        : isCurrent
                        ? "bg-primary text-white animate-pulse"
                        : "bg-surface-container text-on-surface-variant/40"
                    }`}
                  >
                    {isDone ? "✓" : step.id}
                  </span>
                  <span
                    className={`font-body-sm ${
                      isDone
                        ? "text-on-surface font-medium"
                        : isCurrent
                        ? "text-primary font-bold"
                        : "text-on-surface-variant/50"
                    }`}
                  >
                    {step.label}
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}
