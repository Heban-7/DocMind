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
  mode?: "concise" | "balanced" | "detailed";
  model?: string;
}

/** The answer footer: which model wrote it, how long it took, what it cost. */
export interface AnswerUsage {
  model: string;
  provider: string;
  llm_calls: number;
  input_tokens: number;
  output_tokens: number;
  cost_usd: number;
  seconds: number;
  first_token_s?: number | null;
  /** seconds per stage: understand, retrieve, answer, check */
  stages?: Record<string, number>;
  /** USD per kind of call: plan, embed, answer */
  cost_by_purpose?: Record<string, number>;
}

/** One entry of GET /models. Prices are USD per 1M tokens, as checked on `checked_on`. */
export interface ModelInfo {
  id: string;
  label: string;
  provider: string;
  available: boolean;
  unavailable_reason?: string | null;
  /** the server has this provider's API key */
  configured?: boolean;
  default: boolean;
  status: string;
  price: {
    input_per_m: number | null;
    cached_input_per_m?: number | null;
    output_per_m: number | null;
    checked_on: string | null;
    source?: string | null;
    note?: string | null;
  };
  capabilities: { vision: boolean; reasoning: boolean; streaming: boolean; context_window?: number | null };
  free_tier: boolean;
  data_use?: string | null;
  benchmark?: {
    correct_pct?: number;
    first_token_p50_s?: number;
    latency_p50_s?: number;
    cost_per_question_usd?: number;
    input_tokens_mean?: number;
    output_tokens_mean?: number;
    run?: string;
  } | null;
  /** cost of a typical answer: measured on the golden set, or from the price */
  estimate?: { usd: number; basis: "measured" | "price" } | null;
  tested?: boolean;
}

export interface ModelCatalog {
  default: string | null;
  prices_checked_on: string | null;
  typical_answer_tokens?: { input: number; output: number; model: string } | null;
  models: ModelInfo[];
}



/** A box on a PDF page in PDF points, origin at the BOTTOM-LEFT corner (PDF convention). */
export interface PdfBox {
  x0: number;
  y0: number;
  x1: number;
  y1: number;
  page_width?: number | null;
  page_height?: number | null;
}

/** One citation of an answer (the API's Citation model). */
export interface ProvenanceCitation {
  document_name?: string;
  doc_id?: string | null;
  page_number?: number;
  printed_page?: string | null;
  bbox?: PdfBox;
  /** the regions that print the claim; empty when only the page is known */
  boxes?: PdfBox[];
  /** fact | cell | block | page */
  box_kind?: string;
  content_hash?: string;
  chunk_id?: string | null;
  excerpt?: string;
  [key: string]: unknown;
}

/** A box to draw on a page: PDF points from the TOP-LEFT corner. */
export interface PageBox {
  x0: number;
  top: number;
  x1: number;
  bottom: number;
  /** primary (the value) or secondary (its row label, a passage) */
  tone?: "primary" | "secondary";
  label?: string;
}

export interface ChatResponse {
  response: string;
  thread_id: string;
  provenance: ProvenanceCitation[];
}

/** Live processing state of a document (the worker reads it in the background). */
export interface DocumentProgress {
  /** queued | processing | indexed | failed */
  status: string;
  /** queued | reading | layout | indexing | done | retrying | failed */
  stage?: string;
  pages_done?: number;
  /** 0-1 */
  progress?: number;
  /** questions can already use the document */
  searchable?: boolean;
  error?: string | null;
}

export interface UploadResponse extends DocumentProgress {
  document_id: string;
  file_name: string;
  page_count: number;
  strategy_tier: string;
  deduplicated?: boolean;
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

export interface DocumentInfo extends DocumentProgress {
  document_id: string;
  file_name: string;
  page_count: number;
  strategy_tier: string;
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
  status?: string;
  usage?: AnswerUsage;
  followUps?: string[];
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

/* ─── Schema fields (M8) ─── */

export interface SchemaField {
  name: string;
  label: string;
  type: string;
  required: boolean;
  description: string;
  columns?: Record<string, string> | null;
}

export interface SchemaInfo {
  name: string;
  label: string;
  description: string;
  version: number;
  fields: SchemaField[];
  rules: string[];
}

export type FieldStatus = "auto" | "needs_review" | "missing" | "confirmed" | "corrected" | "rejected";

export interface ExtractedField {
  field: string;
  label?: string;
  type?: string | null;
  value: unknown;
  /** the text as printed on the page */
  printed?: string | null;
  unit?: string | null;
  page?: number | null;
  /** the block or cell id the value was read from */
  ref?: string | null;
  /** [x0, top, x1, bottom], PDF points from the top-left corner */
  bbox?: number[] | null;
  confidence: number;
  grounded?: boolean;
  status: FieldStatus;
  reasons: string[];
  alternatives?: unknown[];
  /** the machine's value, kept when a person corrects it */
  machine_value?: unknown;
  reviewed_at?: string | null;
}

export interface RuleCheck {
  name: string;
  passed: boolean;
  soft?: boolean;
  detail?: string;
  fields?: string[];
}

export interface FieldExtraction {
  extraction_id: string;
  document_id: string;
  file_name: string;
  schema: string;
  schema_version?: number;
  /** queued | running | done | failed */
  status: string;
  error?: string | null;
  model?: string | null;
  pages_read: number[];
  rules?: RuleCheck[] | null;
  cost_usd: number;
  seconds?: number | null;
  created_at: string;
  finished_at?: string | null;
  fields: ExtractedField[];
  needs_review: string[];
}

export interface ReviewItem extends ExtractedField {
  document_id: string;
  file_name: string;
  schema: string;
}

/* ─── Usage and the page ledger ─── */

export interface UsageReport {
  month: string;
  spent_usd: number;
  cap_usd: number;
  service_spent_usd: number;
  service_cap_usd: number;
  by_model: { provider: string; model: string; kind: string; calls: number; input_tokens: number; output_tokens: number; cost_usd: number }[];
  by_purpose: { purpose: string; calls: number; cost_usd: number }[];
  by_provider: { provider: string; calls: number; cost_usd: number }[];
  by_day: { day: string; calls: number; cost_usd: number }[];
  questions: number;
  cost_per_question_usd: number | null;
  documents: { document_id: string; file_name: string; page_count: number; ingest_usd: number; fields_usd: number; calls: number }[];
  latest: { created_at: string; purpose: string; provider: string; model: string; input_tokens: number; output_tokens: number; cost_usd: number; latency_ms: number; ok: boolean; error_kind: string | null }[];
}

export interface LedgerPage {
  page: number;
  engine: string;
  attempts: string[];
  confidence: number;
  seconds: number;
  cost_usd: number;
  flags: string[];
  needs_review: boolean;
  blocks: number;
  tables: number;
}

export interface DocumentLedger {
  document_id: string;
  file_name: string;
  pages: LedgerPage[];
  engines: Record<string, number>;
  seconds: number;
  cost_usd: number;
  needs_review: number;
}
