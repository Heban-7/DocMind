"use client";

import { useState, useCallback, useRef } from "react";
import { fetchHistory, sendChatMessageStream } from "@/lib/api";
import type { ChatMessageUI } from "@/lib/types";

export function useChat() {
  const [messages, setMessages] = useState<ChatMessageUI[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const threadIdRef = useRef<string>(crypto.randomUUID());
  const threadDocMapRef = useRef<Record<string, string>>({});

  const threadId = threadIdRef.current;
  const activeDocId = threadDocMapRef.current[threadId];

  const send = useCallback(
    async (
      text: string,
      documentId?: string | null,
      options?: { federatedSearch?: boolean; auditMode?: boolean; model?: string }
    ) => {
      const currentThreadId = threadIdRef.current;

      if (documentId) {
        threadDocMapRef.current[currentThreadId] = documentId;
      }

      const effectiveDocId = options?.federatedSearch
        ? undefined
        : (documentId || threadDocMapRef.current[currentThreadId]);

      const userMsg: ChatMessageUI = {
        id: crypto.randomUUID(),
        role: "user",
        content: text,
        timestamp: Date.now(),
      };

      const aiMsgId = crypto.randomUUID();
      const initialAiMsg: ChatMessageUI = {
        id: aiMsgId,
        role: "ai",
        content: "",
        provenance: [],
        timestamp: Date.now(),
      };

      setMessages((prev) => [...prev, userMsg, initialAiMsg]);
      setIsLoading(true);
      setError(null);

      await sendChatMessageStream(
        {
          message: text,
          thread_id: currentThreadId,
          document_id: effectiveDocId,
          federated_search: options?.federatedSearch,
          audit_mode: options?.auditMode,
          model: options?.model,
        },
        (token) => {
          setMessages((prev) =>
            prev.map((msg) =>
              msg.id === aiMsgId ? { ...msg, content: msg.content + token } : msg
            )
          );
        },
        (provenance) => {
          setMessages((prev) =>
            prev.map((msg) =>
              msg.id === aiMsgId ? { ...msg, provenance } : msg
            )
          );
          setIsLoading(false);
        },
        (err) => {
          setError(err.message || "Streaming response failed");
          setIsLoading(false);
        }
      );
    },
    []
  );

  const loadThread = useCallback(async (targetThreadId: string) => {
    setIsLoading(true);
    setError(null);
    try {
      threadIdRef.current = targetThreadId;
      const res = await fetchHistory(targetThreadId);
      if (res.document_id) {
        threadDocMapRef.current[targetThreadId] = res.document_id;
      }
      const uiMsgs: ChatMessageUI[] = res.messages.map((m) => ({
        id: crypto.randomUUID(),
        role: m.role === "human" || m.role === "user" ? "user" : "ai",
        content: m.content,
        timestamp: Date.now(),
      }));
      setMessages(uiMsgs);
      return res;
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load thread history");
      return null;
    } finally {
      setIsLoading(false);
    }
  }, []);

  const newChat = useCallback(() => {
    threadIdRef.current = crypto.randomUUID();
    setMessages([]);
    setError(null);
  }, []);

  return { messages, isLoading, error, threadId, activeDocId, send, loadThread, newChat };
}
