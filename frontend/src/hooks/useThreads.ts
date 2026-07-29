"use client";

import { useState, useEffect, useCallback } from "react";
import { fetchThreads } from "@/lib/api";
import type { ThreadSummary } from "@/lib/types";

export function useThreads() {
  const [threads, setThreads] = useState<ThreadSummary[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await fetchThreads();
      setThreads(data.threads || []);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load threads");
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return { threads, isLoading, error, refresh };
}
