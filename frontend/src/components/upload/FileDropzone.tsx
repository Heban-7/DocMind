"use client";

import { useCallback, useState, useRef } from "react";

interface FileDropzoneProps {
  onUpload: (file: File) => void;
  uploadState: string;
}

export default function FileDropzone({ onUpload, uploadState }: FileDropzoneProps) {
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

  return (
    <div
      className={`border-2 border-dashed rounded-xl p-md text-center transition-all cursor-pointer ${
        isDragging
          ? "border-primary bg-primary/10 scale-[1.02]"
          : "border-outline-variant/40 hover:border-primary/50 hover:bg-surface-container-high/50"
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
          <span className="material-symbols-outlined text-on-surface-variant/50 text-[26px] mb-xs block">
            upload_file
          </span>
          <p className="font-body-sm text-xs font-bold text-on-surface-variant">
            Upload PDF Document
          </p>
          <p className="font-body-sm text-[11px] text-on-surface-variant/60">
            Drag &amp; drop or click to index
          </p>
        </>
      )}

      {(uploadState === "uploading" || uploadState === "processing") && (
        <>
          <span className="material-symbols-outlined text-primary text-[26px] mb-xs block animate-spin">
            progress_activity
          </span>
          <p className="font-body-sm text-xs font-bold text-primary">
            {uploadState === "uploading" ? "Uploading..." : "Indexing PDF..."}
          </p>
        </>
      )}

      {uploadState === "indexed" && (
        <>
          <span className="material-symbols-outlined text-emerald-600 text-[26px] mb-xs block">
            add_circle
          </span>
          <p className="font-body-sm text-xs font-bold text-on-surface">
            Index Another Document
          </p>
        </>
      )}

      {uploadState === "error" && (
        <>
          <span className="material-symbols-outlined text-red-500 text-[26px] mb-xs block">
            error
          </span>
          <p className="font-body-sm text-xs font-bold text-red-500">Upload failed</p>
        </>
      )}
    </div>
  );
}
