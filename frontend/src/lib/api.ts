/* ─── DocMind API Client ─── */
import type {
  HealthResponse,
  ChatRequest,
  ChatResponse,
  UploadResponse,
  HistoryResponse,
  ThreadListResponse,
  DocumentListResponse,
} from "./types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

/* ─── Health ─── */
export async function checkHealth(): Promise<HealthResponse> {
  const res = await fetch(`${API_BASE}/health`, {
    method: "GET",
    cache: "no-store",
  });
  if (!res.ok) throw new Error(`Health check failed: ${res.status}`);
  return res.json();
}

function parseApiError(data: any, status: number, defaultMsg: string): string {
  if (!data) return `${defaultMsg}: ${status}`;
  if (typeof data.detail === "string") return data.detail;
  if (Array.isArray(data.detail)) {
    return data.detail
      .map((e: any) => e.msg || e.message || (typeof e === "string" ? e : JSON.stringify(e)))
      .join("; ");
  }
  if (data.detail && typeof data.detail === "object") {
    return JSON.stringify(data.detail);
  }
  return `${defaultMsg}: ${status}`;
}

/* ─── Upload ─── */
export async function uploadDocument(file: File): Promise<UploadResponse> {
  const formData = new FormData();
  formData.append("file", file);

  const res = await fetch(`${API_BASE}/upload`, {
    method: "POST",
    body: formData,
  });

  if (!res.ok) {
    const data = await res.json().catch(() => null);
    throw new Error(parseApiError(data, res.status, "Upload failed"));
  }
  return res.json();
}

/* ─── Chat ─── */
export async function sendChatMessage(
  payload: ChatRequest
): Promise<ChatResponse> {
  const res = await fetch(`${API_BASE}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  if (!res.ok) {
    const data = await res.json().catch(() => null);
    throw new Error(parseApiError(data, res.status, "Chat query failed"));
  }
  return res.json();
}


/* ─── History ─── */
export async function fetchHistory(threadId: string): Promise<HistoryResponse> {
  const res = await fetch(`${API_BASE}/history/${encodeURIComponent(threadId)}`, {
    method: "GET",
    cache: "no-store",
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(detail.detail || `History fetch failed: ${res.status}`);
  }
  return res.json();
}

/* ─── Threads ─── */
export async function fetchThreads(): Promise<ThreadListResponse> {
  const res = await fetch(`${API_BASE}/threads`, {
    method: "GET",
    cache: "no-store",
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(detail.detail || `Threads fetch failed: ${res.status}`);
  }
  return res.json();
}

/* ─── Documents ─── */
export async function fetchDocuments(): Promise<DocumentListResponse> {
  const res = await fetch(`${API_BASE}/documents`, {
    method: "GET",
    cache: "no-store",
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(detail.detail || `Documents fetch failed: ${res.status}`);
  }
  return res.json();
}

export function getDocumentPdfUrl(docId: string): string {
  return `${API_BASE}/documents/${encodeURIComponent(docId)}/pdf`;
}

