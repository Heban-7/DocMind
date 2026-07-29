"use client";

import { useState, useEffect, useCallback } from "react";
import { checkHealth } from "@/lib/api";
import type { HealthResponse } from "@/lib/types";

export function useHealth(pollIntervalMs = 30_000) {
  const [isOnline, setIsOnline] = useState(false);
  const [version, setVersion] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const poll = useCallback(async () => {
    try {
      const data: HealthResponse = await checkHealth();
      setIsOnline(data.status === "ok");
      setVersion(data.version);
      setError(null);
    } catch (err) {
      setIsOnline(false);
      setError(err instanceof Error ? err.message : "Health check failed");
    }
  }, []);

  useEffect(() => {
    poll();
    const id = setInterval(poll, pollIntervalMs);
    return () => clearInterval(id);
  }, [poll, pollIntervalMs]);

  return { isOnline, version, error, refresh: poll };
}
