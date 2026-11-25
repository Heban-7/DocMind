/* ─── DocMind API Client (with JWT Auth) ─── */
import type {
  HealthResponse,
  ChatRequest,
  ChatResponse,
  UploadResponse,
  HistoryResponse,
  ThreadListResponse,
  DocumentInfo,
  DocumentListResponse,
  TokenResponse,
  UserProfile,
  AnswerUsage,
  ModelCatalog,
  SchemaInfo,
  FieldExtraction,
  ExtractedField,
  ReviewItem,
  UsageReport,
  DocumentLedger,
  ProvenanceCitation,
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

type ApiErrorBody = { detail?: unknown } | null;

function parseApiError(data: ApiErrorBody, status: number, defaultMsg: string): string {
  if (!data) return `${defaultMsg}: ${status}`;
  if (typeof data.detail === "string") return data.detail;
  if (Array.isArray(data.detail)) {
    return data.detail
      .map((e: { msg?: string; message?: string } | string) =>
        typeof e === "string" ? e : e.msg || e.message || JSON.stringify(e),
      )
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

/** Current status and progress of one document. */
export async function fetchDocumentStatus(docId: string): Promise<DocumentInfo> {
  const token = getStoredToken();
  const res = await fetch(`${API_BASE}/documents/${encodeURIComponent(docId)}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!res.ok) {
    const data = await res.json().catch(() => null);
    throw new Error(parseApiError(data, res.status, "Status check failed"));
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

export interface StreamDone {
  answer: string;
  provenance: ProvenanceCitation[];
  followUps: string[];
  status: string;
  usage?: AnswerUsage;
}

/**
 * POST /chat/stream. `onToken` gets the answer as the model writes it; `onDone`
 * gets the checked answer, which replaces the streamed text (the verifier may
 * have removed a sentence it could not match to the evidence).
 */
export async function sendChatMessageStream(
  payload: ChatRequest,
  onToken: (token: string) => void,
  onDone: (done: StreamDone) => void,
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
    let finished = false;

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n\n");
      buffer = lines.pop() || "";

      for (const line of lines) {
        const trimmed = line.trim();
        if (!trimmed.startsWith("data: ")) continue;
        let data: {
          type?: string;
          token?: string;
          answer?: string;
          provenance?: ProvenanceCitation[];
          follow_ups?: string[];
          status?: string;
          usage?: AnswerUsage;
          message?: string;
        };
        try {
          data = JSON.parse(trimmed.slice(6));
        } catch {
          continue;
        }
        if (data.type === "token" && typeof data.token === "string") {
          onToken(data.token);
        } else if (data.type === "done") {
          finished = true;
          onDone({
            answer: data.answer ?? "",
            provenance: data.provenance || [],
            followUps: data.follow_ups || [],
            status: data.status || "answered",
            usage: data.usage,
          });
        } else if (data.type === "error") {
          // a provider failure is an error, not "not found in the document"
          throw new Error(data.message || "The answer failed");
        }
      }
    }
    if (!finished) {
      // the connection closed before the server sent the checked answer
      throw new Error("The connection closed before the answer finished. Please ask again.");
    }
  } catch (err) {
    const e = err instanceof Error ? err : new Error("Chat stream error");
    if (e.name === "TypeError" && /fetch|network/i.test(e.message)) {
      onError(new Error("The server could not be reached. Check that the API is running, then ask again."));
    } else {
      onError(e);
    }
  }
}

/* ─── Models ─── */
export async function fetchModels(): Promise<ModelCatalog> {
  const res = await authFetch(`${API_BASE}/models`, { method: "GET", cache: "no-store" });
  if (!res.ok) {
    const data = await res.json().catch(() => null);
    throw new Error(parseApiError(data, res.status, "Failed to load models"));
  }
  return res.json();
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

/** The PDF's URL and the header that opens it (the viewer fetches with it; no token in the URL). */
export function documentPdfSource(docId: string): { url: string; httpHeaders: Record<string, string> } {
  const token = getStoredToken();
  return {
    url: `${API_BASE}/documents/${encodeURIComponent(docId)}/pdf`,
    httpHeaders: token ? { Authorization: `Bearer ${token}` } : {},
  };
}

/** A ten-minute link to the PDF, for opening it in a new tab. */
export async function fetchPdfLink(docId: string): Promise<string> {
  const res = await authFetch(`${API_BASE}/documents/${encodeURIComponent(docId)}/link`, { method: "POST" });
  const data = await res.json().catch(() => null);
  if (!res.ok) throw new Error(parseApiError(data, res.status, "Could not open the PDF"));
  return `${API_BASE}${data.url}`;
}

async function getJson<T>(path: string, what: string, init: RequestInit = {}): Promise<T> {
  const res = await authFetch(`${API_BASE}${path}`, { cache: "no-store", ...init });
  const data = await res.json().catch(() => null);
  if (!res.ok) {
    const err = new Error(parseApiError(data, res.status, what)) as Error & { status?: number };
    err.status = res.status;
    throw err;
  }
  return data as T;
}

/* ─── Schema fields ─── */

export async function fetchSchemas(): Promise<SchemaInfo[]> {
  const data = await getJson<{ schemas: SchemaInfo[] }>("/schemas", "Could not load the schemas");
  return data.schemas;
}

export async function requestFields(docId: string, schema: string): Promise<{ extraction_id: string; status: string }> {
  return getJson(`/documents/${encodeURIComponent(docId)}/fields`, "Could not start reading the fields", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ schema }),
  });
}

/** The latest extraction, or null when the document has none for this schema. */
export async function fetchFields(docId: string, schema?: string): Promise<FieldExtraction | null> {
  const q = schema ? `?schema=${encodeURIComponent(schema)}` : "";
  try {
    return await getJson<FieldExtraction>(`/documents/${encodeURIComponent(docId)}/fields${q}`, "Could not load the fields");
  } catch (e) {
    if ((e as { status?: number }).status === 404 && !/document not found/i.test((e as Error).message)) return null;
    throw e;
  }
}

export async function reviewField(
  docId: string,
  field: string,
  action: "confirm" | "correct" | "reject",
  opts: { value?: unknown; schema?: string } = {},
): Promise<ExtractedField> {
  return getJson(`/documents/${encodeURIComponent(docId)}/fields/${encodeURIComponent(field)}`, "Could not save the review", {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ action, value: opts.value, schema: opts.schema }),
  });
}

export async function fetchReviewQueue(): Promise<ReviewItem[]> {
  const data = await getJson<{ fields: ReviewItem[] }>("/review", "Could not load the review queue");
  return data.fields;
}

/** Download a schema's table (one row per document) as CSV or Excel. */
export async function downloadExport(schema: string, fmt: "csv" | "xlsx", documentIds?: string[]): Promise<void> {
  const q = (documentIds || []).map((d) => `document_id=${encodeURIComponent(d)}`).join("&");
  const res = await authFetch(`${API_BASE}/exports/${encodeURIComponent(schema)}.${fmt}${q ? `?${q}` : ""}`);
  if (!res.ok) {
    const data = await res.json().catch(() => null);
    throw new Error(parseApiError(data, res.status, "Export failed"));
  }
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `docmind-${schema}.${fmt}`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

/* ─── Usage and the page ledger ─── */

export async function fetchUsage(): Promise<UsageReport> {
  return getJson<UsageReport>("/usage", "Could not load usage");
}

export async function fetchLedger(docId: string): Promise<DocumentLedger> {
  return getJson<DocumentLedger>(`/documents/${encodeURIComponent(docId)}/ledger`, "Could not load the page ledger");
}
