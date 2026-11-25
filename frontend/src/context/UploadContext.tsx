"use client";

import React, { createContext, useContext, useState, useCallback, useMemo } from "react";
import { fetchDocumentStatus, uploadDocument } from "@/lib/api";
import type { UploadedDocument, UploadState, DocumentInfo } from "@/lib/types";
import { useAuth } from "@/context/AuthContext";

const LOCAL_STORAGE_KEY_PREFIX = "docmind_thread_docs_";

interface UploadContextType {
  uploadState: UploadState;
  uploadingThreadId: string | null;
  selectedFile: File | null;
  error: string | null;
  /** Real progress reported by the server while the document is read (0-1). */
  progress: number;
  /** e.g. "Reading page 40 of 161" */
  progressLabel: string;
  threadDocMap: Record<string, UploadedDocument>;
  upload: (file: File, threadId?: string) => Promise<UploadedDocument | null>;
  setThreadDocument: (threadId: string, doc: UploadedDocument | DocumentInfo) => void;
  getThreadDocument: (threadId: string) => UploadedDocument | null;
  reset: () => void;
}

const UploadContext = createContext<UploadContextType | undefined>(undefined);

export function UploadProvider({ children }: { children: React.ReactNode }) {
  const { user } = useAuth();
  const storageKey = user ? `${LOCAL_STORAGE_KEY_PREFIX}${user.id}` : null;

  const [uploadState, setUploadState] = useState<UploadState>("idle");
  const [uploadingThreadId, setUploadingThreadId] = useState<string | null>(null);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [progress, setProgress] = useState<number>(0);
  const [progressLabel, setProgressLabel] = useState<string>("");
  // the documents bound to chat threads, per account (saved in localStorage)
  const [maps, setMaps] = useState<Record<string, Record<string, UploadedDocument>>>({});
  const threadDocMap = useMemo<Record<string, UploadedDocument>>(() => {
    if (!storageKey) return {};
    if (maps[storageKey]) return maps[storageKey];
    try {
      const saved = typeof window === "undefined" ? null : localStorage.getItem(storageKey);
      return saved ? JSON.parse(saved) : {};
    } catch {
      return {};
    }
  }, [maps, storageKey]);

  // Sync to localStorage on threadDocMap change
  const persistThreadDocs = useCallback((map: Record<string, UploadedDocument>) => {
    if (!storageKey) return;
    try {
      localStorage.setItem(storageKey, JSON.stringify(map));
    } catch {
      // Ignore localStorage write errors
    }
  }, [storageKey]);

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
    if (!storageKey) return;
    const next = { ...threadDocMap, [threadId]: uploadedDoc };
    persistThreadDocs(next);
    setMaps((m) => ({ ...m, [storageKey]: next }));
  }, [persistThreadDocs, storageKey, threadDocMap]);

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
      setProgress(0);
      setProgressLabel("Uploading");
      const res = await uploadDocument(file);
      setUploadState("processing");

      // The upload returns at once; the worker reads the PDF in the background.
      let info = res as { status: string; stage?: string; pages_done?: number; page_count: number; progress?: number; error?: string | null; strategy_tier: string };
      const started = Date.now();
      while (info.status !== "indexed" && info.status !== "failed") {
        const stage = info.stage || info.status;
        setProgress(info.progress ?? 0);
        setProgressLabel(
          stage === "queued" ? "Waiting for a worker" :
          stage === "reading" ? `Reading page ${info.pages_done ?? 0} of ${info.page_count}` :
          stage === "layout" ? `Tables and scans: ${info.pages_done ?? 0} of ${info.page_count} pages` :
          stage === "indexing" ? "Indexing" :
          stage === "retrying" ? "Retrying after an error" : "Processing"
        );
        if (Date.now() - started > 60 * 60 * 1000) throw new Error("Processing is taking longer than an hour");
        await new Promise((r) => setTimeout(r, 1500));
        info = await fetchDocumentStatus(res.document_id);
      }
      if (info.status === "failed") {
        throw new Error(info.error || "The document could not be processed");
      }
      setProgress(1);
      setProgressLabel("Ready");

      const doc: UploadedDocument = {
        document_id: res.document_id,
        file_name: res.file_name,
        page_count: info.page_count,
        strategy_tier: info.strategy_tier,
        status: info.status,
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
        progress,
        progressLabel,
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
