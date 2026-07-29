"use client";

import { useCallback, useState, useRef } from "react";

interface FileDropzoneProps {
  onUpload: (file: File) => void;
  uploadState: string;
  fileName?: string;
  strategyTier?: string;
}

export default function FileDropzone({
  onUpload,
  uploadState,
  fileName,
  strategyTier,
}: FileDropzoneProps) {
  const [isDragging, setIsDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setIsDragging(false);
      const file = e.dataTransfer.files[0];
      if (file && file.type === "application/pdf") {
        onUpload(file);
      }
    },
    [onUpload]
  );

  const handleChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (file) onUpload(file);
    },
    [onUpload]
  );

  const tierColors: Record<string, string> = {
    fast: "bg-green-100 text-green-700",
    standard: "bg-blue-100 text-blue-700",
    premium: "bg-purple-100 text-purple-700",
  };

  return (
    <div
      className={`border-2 border-dashed rounded-xl p-md text-center transition-all cursor-pointer ${
        isDragging
          ? "border-primary bg-primary/5"
          : "border-outline-variant/40 hover:border-primary/50"
      }`}
      onDragOver={(e) => {
        e.preventDefault();
        setIsDragging(true);
      }}
      onDragLeave={() => setIsDragging(false)}
      onDrop={handleDrop}
      onClick={() => inputRef.current?.click()}
    >
      <input
        ref={inputRef}
        type="file"
        accept=".pdf"
        className="hidden"
        onChange={handleChange}
      />

      {uploadState === "idle" && (
        <>
          <span className="material-symbols-outlined text-on-surface-variant/50 text-[28px] mb-xs block">
            upload_file
          </span>
          <p className="font-body-sm text-body-sm text-on-surface-variant/60">
            Drop PDF here
          </p>
        </>
      )}

      {(uploadState === "uploading" || uploadState === "processing") && (
        <>
          <span className="material-symbols-outlined text-primary text-[28px] mb-xs block animate-spin">
            progress_activity
          </span>
          <p className="font-body-sm text-body-sm text-primary">
            {uploadState === "uploading" ? "Uploading..." : "Processing..."}
          </p>
        </>
      )}

      {uploadState === "indexed" && fileName && (
        <>
          <span className="material-symbols-outlined text-green-600 text-[28px] mb-xs block">
            check_circle
          </span>
          <p className="font-body-sm text-body-sm text-on-surface-variant truncate">
            {fileName}
          </p>
          <div className="flex items-center justify-center gap-xs mt-xs">
            <span className="font-label-md text-[11px] text-green-600">Indexed</span>
            {strategyTier && (
              <span
                className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${
                  tierColors[strategyTier.toLowerCase()] ||
                  "bg-gray-100 text-gray-700"
                }`}
              >
                {strategyTier}
              </span>
            )}
          </div>
        </>
      )}

      {uploadState === "error" && (
        <>
          <span className="material-symbols-outlined text-red-500 text-[28px] mb-xs block">
            error
          </span>
          <p className="font-body-sm text-body-sm text-red-500">Upload failed</p>
        </>
      )}
    </div>
  );
}
