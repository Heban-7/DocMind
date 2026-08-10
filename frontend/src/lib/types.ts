/* ─── TypeScript interfaces mirroring FastAPI Pydantic schemas ─── */

/* ─── Auth types ─── */

export interface UserRegister {
  email: string;
  password: string;
}

export interface UserLogin {
  email: string;
  password: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
}

export interface UserProfile {
  id: string;
  email: string;
}

/* ─── API types ─── */

export interface HealthResponse {
  status: string;
  version: string;
}

export interface ChatRequest {
  message: string;
  thread_id: string;
  document_id?: string | null;
  federated_search?: boolean;
  audit_mode?: boolean;
  model?: string;
}



export interface ProvenanceCitation {
  source_file?: string;
  page_number?: number;
  bbox?: number[];
  content_hash?: string;
  chunk_text?: string;
  [key: string]: unknown;
}

export interface ChatResponse {
  response: string;
  thread_id: string;
  provenance: ProvenanceCitation[];
}

export interface UploadResponse {
  document_id: string;
  file_name: string;
  page_count: number;
  strategy_tier: string;
  status: string;
}

export interface HistoryMessage {
  role: "human" | "ai" | string;
  content: string;
}

export interface HistoryResponse {
  thread_id: string;
  messages: HistoryMessage[];
  document_id?: string;
  document_info?: DocumentInfo;
}

export interface ThreadSummary {
  thread_id: string;
  title: string;
  message_count: number;
  document_id?: string;
  document_info?: DocumentInfo;
}

export interface ThreadListResponse {
  threads: ThreadSummary[];
}

export interface DocumentInfo {
  document_id: string;
  file_name: string;
  page_count: number;
  strategy_tier: string;
  status: string;
}

export interface DocumentListResponse {
  documents: DocumentInfo[];
}


/* ─── Frontend-only UI types ─── */

export interface ChatMessageUI {
  id: string;
  role: "user" | "ai";
  content: string;
  provenance?: ProvenanceCitation[];
  timestamp: number;
}

export interface UploadedDocument {
  document_id: string;
  file_name: string;
  page_count: number;
  strategy_tier: string;
  status: string;
  uploadedAt: number;
}

export type UploadState = "idle" | "uploading" | "processing" | "indexed" | "error";
