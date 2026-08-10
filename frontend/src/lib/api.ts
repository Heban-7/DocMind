/* ─── DocMind API Client (with JWT Auth) ─── */
import type {
  HealthResponse,
  ChatRequest,
  ChatResponse,
  UploadResponse,
  HistoryResponse,
  ThreadListResponse,
  DocumentListResponse,
  TokenResponse,
  UserProfile,
} from "./types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

const TOKEN_KEY = "docmind_access_token";

/* ─── Token helpers ─── */

export function getStoredToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(TOKEN_KEY);
}

export function setStoredToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token);
}

export function clearStoredToken(): void {
  localStorage.removeItem(TOKEN_KEY);
}

/* ─── Auth-aware fetch wrapper ─── */

async function authFetch(
  url: string,
  options: RequestInit = {}
): Promise<Response> {
  const token = getStoredToken();
  const headers: Record<string, string> = {
    ...(options.headers as Record<string, string> || {}),
  };
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }
  const res = await fetch(url, { ...options, headers });

  // On 401, clear token and redirect to login
  if (res.status === 401) {
    clearStoredToken();
    if (typeof window !== "undefined" && !window.location.pathname.startsWith("/login")) {
      window.location.href = "/login";
    }
  }
  return res;
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

/* ─── Auth API ─── */

export async function registerUser(email: string, password: string): Promise<UserProfile> {
  const res = await fetch(`${API_BASE}/api/auth/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  if (!res.ok) {
    const data = await res.json().catch(() => null);
    throw new Error(parseApiError(data, res.status, "Registration failed"));
  }
  return res.json();
}

export async function loginUser(email: string, password: string): Promise<TokenResponse> {
  const res = await fetch(`${API_BASE}/api/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  if (!res.ok) {
    const data = await res.json().catch(() => null);
    throw new Error(parseApiError(data, res.status, "Login failed"));
  }
  return res.json();
}

export async function fetchMe(): Promise<UserProfile> {
  const res = await authFetch(`${API_BASE}/api/auth/me`, {
    method: "GET",
    cache: "no-store",
  });
  if (!res.ok) {
    const data = await res.json().catch(() => null);
    throw new Error(parseApiError(data, res.status, "Failed to fetch profile"));
  }
  return res.json();
}

/* ─── Health ─── */
export async function checkHealth(): Promise<HealthResponse> {
  const res = await fetch(`${API_BASE}/health`, {
    method: "GET",
    cache: "no-store",
  });
  if (!res.ok) throw new Error(`Health check failed: ${res.status}`);
  return res.json();
}

/* ─── Upload ─── */
export async function uploadDocument(file: File): Promise<UploadResponse> {
  const formData = new FormData();
  formData.append("file", file);

  const token = getStoredToken();
  const headers: Record<string, string> = {};
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  const res = await fetch(`${API_BASE}/upload`, {
    method: "POST",
    headers,
    body: formData,
  });

  if (!res.ok) {
    // Handle 401 separately
    if (res.status === 401) {
      clearStoredToken();
      if (typeof window !== "undefined" && !window.location.pathname.startsWith("/login")) {
        window.location.href = "/login";
      }
    }
    const data = await res.json().catch(() => null);
    throw new Error(parseApiError(data, res.status, "Upload failed"));
  }
  return res.json();
}

/* ─── Chat ─── */
export async function sendChatMessage(
  payload: ChatRequest
): Promise<ChatResponse> {
  const res = await authFetch(`${API_BASE}/chat`, {
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

export async function sendChatMessageStream(
  payload: ChatRequest,
  onToken: (token: string) => void,
  onDone: (provenance: any[], followUps: string[]) => void,
  onError: (err: Error) => void
): Promise<void> {
  try {
    const res = await authFetch(`${API_BASE}/chat/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    if (!res.ok) {
      const data = await res.json().catch(() => null);
      throw new Error(parseApiError(data, res.status, "Chat stream failed"));
    }

    const reader = res.body?.getReader();
    if (!reader) {
      throw new Error("Stream response body reader unavailable");
    }

    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n\n");
      buffer = lines.pop() || "";

      for (const line of lines) {
        const trimmed = line.trim();
        if (trimmed.startsWith("data: ")) {
          const jsonStr = trimmed.slice(6);
          try {
            const data = JSON.parse(jsonStr);
            if (data.type === "token" && typeof data.token === "string") {
              onToken(data.token);
            } else if (data.type === "done") {
              onDone(data.provenance || [], data.follow_ups || []);
            }
          } catch {
            // Ignore JSON parse error
          }
        }
      }
    }
  } catch (err) {
    onError(err instanceof Error ? err : new Error("Chat stream error"));
  }
}


/* ─── History ─── */
export async function fetchHistory(threadId: string): Promise<HistoryResponse> {
  const res = await authFetch(`${API_BASE}/history/${encodeURIComponent(threadId)}`, {
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
  const res = await authFetch(`${API_BASE}/threads`, {
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
  const res = await authFetch(`${API_BASE}/documents`, {
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
  const token = getStoredToken();
  const baseUrl = `${API_BASE}/documents/${encodeURIComponent(docId)}/pdf`;
  return token ? `${baseUrl}?token=${encodeURIComponent(token)}` : baseUrl;
}
