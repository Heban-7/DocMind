"use client";

import React, { createContext, useContext, useState, useEffect, useCallback } from "react";
import { uploadDocument } from "@/lib/api";
import type { UploadedDocument, UploadState, DocumentInfo } from "@/lib/types";

const LOCAL_STORAGE_KEY = "docmind_thread_docs_v1";

interface UploadContextType {
  uploadState: UploadState;
  uploadingThreadId: string | null;
  selectedFile: File | null;
  error: string | null;
  threadDocMap: Record<string, UploadedDocument>;
  upload: (file: File, threadId?: string) => Promise<UploadedDocument | null>;
  setThreadDocument: (threadId: string, doc: UploadedDocument | DocumentInfo) => void;
  getThreadDocument: (threadId: string) => UploadedDocument | null;
  reset: () => void;
}

const UploadContext = createContext<UploadContextType | undefined>(undefined);

export function UploadProvider({ children }: { children: React.ReactNode }) {
  const [uploadState, setUploadState] = useState<UploadState>("idle");
  const [uploadingThreadId, setUploadingThreadId] = useState<string | null>(null);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [threadDocMap, setThreadDocMap] = useState<Record<string, UploadedDocument>>({});

  // Load persisted thread documents on mount
  useEffect(() => {
    try {
      const saved = localStorage.getItem(LOCAL_STORAGE_KEY);
      if (saved) {
        setThreadDocMap(JSON.parse(saved));
      }
    } catch {
      // Ignore localStorage read errors
    }
  }, []);

  // Sync to localStorage on threadDocMap change
  const persistThreadDocs = useCallback((map: Record<string, UploadedDocument>) => {
    try {
      localStorage.setItem(LOCAL_STORAGE_KEY, JSON.stringify(map));
    } catch {
      // Ignore localStorage write errors
    }
  }, []);

  const setThreadDocument = useCallback((threadId: string, doc: UploadedDocument | DocumentInfo) => {
    if (!threadId || !doc) return;
    const uploadedDoc: UploadedDocument = {
      document_id: doc.document_id,
      file_name: doc.file_name,
      page_count: doc.page_count,
      strategy_tier: doc.strategy_tier,
      status: doc.status,
      uploadedAt: (doc as UploadedDocument).uploadedAt || Date.now(),
    };
    setThreadDocMap((prev) => {
      const next = { ...prev, [threadId]: uploadedDoc };
      persistThreadDocs(next);
      return next;
    });
  }, [persistThreadDocs]);

  const getThreadDocument = useCallback((threadId: string): UploadedDocument | null => {
    if (!threadId) return null;
    return threadDocMap[threadId] || null;
  }, [threadDocMap]);

  const upload = useCallback(async (file: File, threadId?: string): Promise<UploadedDocument | null> => {
    setSelectedFile(file);
    setUploadState("uploading");
    if (threadId) setUploadingThreadId(threadId);
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

      if (threadId) {
        setThreadDocument(threadId, doc);
      }

      setUploadState("indexed");
      return doc;
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed");
      setUploadState("error");
      return null;
    }
  }, [setThreadDocument]);

  const reset = useCallback(() => {
    setUploadState("idle");
    setUploadingThreadId(null);
    setSelectedFile(null);
    setError(null);
  }, []);

  return (
    <UploadContext.Provider
      value={{
        uploadState,
        uploadingThreadId,
        selectedFile,
        error,
        threadDocMap,
        upload,
        setThreadDocument,
        getThreadDocument,
        reset,
      }}
    >
      {children}
    </UploadContext.Provider>
  );
}

export function useUploadContext() {
  const ctx = useContext(UploadContext);
  if (!ctx) {
    throw new Error("useUploadContext must be used within an UploadProvider");
  }
  return ctx;
}
