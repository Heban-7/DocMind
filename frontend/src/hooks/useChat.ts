"use client";

import { useState, useCallback, useRef } from "react";
import { fetchHistory, sendChatMessage } from "@/lib/api";
import type { ChatMessageUI } from "@/lib/types";

export function useChat() {
  const [messages, setMessages] = useState<ChatMessageUI[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const threadIdRef = useRef<string>(crypto.randomUUID());

  const threadId = threadIdRef.current;

  const send = useCallback(
    async (text: string, documentId?: string | null) => {
      const userMsg: ChatMessageUI = {
        id: crypto.randomUUID(),
        role: "user",
        content: text,
        timestamp: Date.now(),
      };

      setMessages((prev) => [...prev, userMsg]);
      setIsLoading(true);
      setError(null);

      try {
        const res = await sendChatMessage({
          message: text,
          thread_id: threadIdRef.current,
          document_id: documentId ?? undefined,
        });

        const aiMsg: ChatMessageUI = {
          id: crypto.randomUUID(),
          role: "ai",
          content: res.response,
          provenance: res.provenance,
          timestamp: Date.now(),
        };

        setMessages((prev) => [...prev, aiMsg]);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Chat failed");
      } finally {
        setIsLoading(false);
      }
    },
    []
  );

  const loadThread = useCallback(async (targetThreadId: string) => {
    setIsLoading(true);
    setError(null);
    try {
      threadIdRef.current = targetThreadId;
      const res = await fetchHistory(targetThreadId);
      const uiMsgs: ChatMessageUI[] = res.messages.map((m) => ({
        id: crypto.randomUUID(),
        role: m.role === "human" || m.role === "user" ? "user" : "ai",
        content: m.content,
        timestamp: Date.now(),
      }));
      setMessages(uiMsgs);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load thread history");
    } finally {
      setIsLoading(false);
    }
  }, []);

  const newChat = useCallback(() => {
    threadIdRef.current = crypto.randomUUID();
    setMessages([]);
    setError(null);
  }, []);

  return { messages, isLoading, error, threadId, send, loadThread, newChat };
}

