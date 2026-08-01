"use client";

import { useState, useCallback } from "react";
import { uploadDocument } from "@/lib/api";
import type { UploadedDocument, UploadState } from "@/lib/types";

export function useUpload() {
  const [uploadState, setUploadState] = useState<UploadState>("idle");
  const [document, setDocument] = useState<UploadedDocument | null>(null);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);

  const upload = useCallback(async (file: File) => {
    setSelectedFile(file);
    setUploadState("uploading");
    setError(null);

    try {
      setUploadState("processing");
      const res = await uploadDocument(file);

      const doc: UploadedDocument = {
        document_id: res.document_id,
        file_name: res.file_name,
        page_count: res.page_count,
        strategy_tier: res.strategy_tier,
        status: res.status,
        uploadedAt: Date.now(),
      };

      setDocument(doc);
      setUploadState("indexed");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed");
      setUploadState("error");
    }
  }, []);

  const reset = useCallback(() => {
    setUploadState("idle");
    setDocument(null);
    setSelectedFile(null);
    setError(null);
  }, []);

  return { uploadState, document, selectedFile, error, upload, reset };
}

