-- DocMind schema v1: one Postgres database for documents, pages, chunks with
-- vectors and full-text, facts, page indexes, chat threads and users.
--
-- Isolation: every tenant table has tenant_id and row-level security keyed on
-- the per-transaction setting app.tenant_id. The application runs as the
-- non-superuser role docmind_app (superusers bypass RLS), so a query without a
-- tenant set sees nothing. Foreign-key checks do not apply RLS, so every link
-- between tenant rows is a composite key on (tenant_id, id): a row can only
-- point at a parent of its own tenant.

CREATE EXTENSION IF NOT EXISTS vector;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'docmind_app') THEN
        CREATE ROLE docmind_app NOLOGIN;
    END IF;
END
$$;

CREATE OR REPLACE FUNCTION app_tenant() RETURNS uuid
    LANGUAGE sql STABLE AS
$$ SELECT nullif(current_setting('app.tenant_id', true), '')::uuid $$;

CREATE TABLE tenants (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name        text NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now()
);

-- Users are looked up by email at login, before any tenant is known, so this
-- table is reached only through the auth code path and carries no RLS.
CREATE TABLE users (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id        uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    email            text NOT NULL UNIQUE,
    hashed_password  text NOT NULL,
    role             text NOT NULL DEFAULT 'owner',
    created_at       timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, id)
);

CREATE TABLE documents (
    id                    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id             uuid NOT NULL DEFAULT app_tenant() REFERENCES tenants(id) ON DELETE CASCADE,
    sha256                text NOT NULL,
    file_name             text NOT NULL,
    page_count            integer NOT NULL DEFAULT 0,
    status                text NOT NULL DEFAULT 'uploaded'
                          CHECK (status IN ('uploaded', 'processing', 'ready', 'failed')),
    storage_key           text NOT NULL,
    model_key             text,
    pages_needing_review  integer NOT NULL DEFAULT 0,
    domain_hint           text NOT NULL DEFAULT '',
    stats                 jsonb NOT NULL DEFAULT '{}',
    error                 text,
    created_by            uuid,
    created_at            timestamptz NOT NULL DEFAULT now(),
    updated_at            timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, sha256),
    UNIQUE (tenant_id, id),
    FOREIGN KEY (tenant_id, created_by) REFERENCES users (tenant_id, id) ON DELETE SET NULL (created_by)
);

-- The per-page extraction ledger.
CREATE TABLE pages (
    tenant_id     uuid NOT NULL DEFAULT app_tenant(),
    document_id   uuid NOT NULL,
    number        integer NOT NULL,
    engine        text NOT NULL,
    confidence    real NOT NULL,
    flags         jsonb NOT NULL DEFAULT '[]',
    needs_review  boolean NOT NULL DEFAULT false,
    seconds       real NOT NULL DEFAULT 0,
    cost_usd      real NOT NULL DEFAULT 0,
    PRIMARY KEY (document_id, number),
    FOREIGN KEY (tenant_id, document_id) REFERENCES documents (tenant_id, id) ON DELETE CASCADE
);

CREATE TABLE chunks (
    id             uuid PRIMARY KEY,
    tenant_id      uuid NOT NULL DEFAULT app_tenant(),
    document_id    uuid NOT NULL,
    ordinal        integer NOT NULL,
    text           text NOT NULL,
    chunk_type     text NOT NULL DEFAULT 'prose',
    section_path   text[] NOT NULL DEFAULT '{}',
    page_numbers   integer[] NOT NULL DEFAULT '{}',
    content_hash   text NOT NULL,
    word_count     integer NOT NULL DEFAULT 0,
    embedding      vector(1536),
    tsv            tsvector GENERATED ALWAYS AS (to_tsvector('simple', text)) STORED,
    FOREIGN KEY (tenant_id, document_id) REFERENCES documents (tenant_id, id) ON DELETE CASCADE
);
CREATE INDEX chunks_tenant_document ON chunks (tenant_id, document_id);
CREATE INDEX chunks_embedding ON chunks USING hnsw (embedding vector_cosine_ops);
CREATE INDEX chunks_tsv ON chunks USING gin (tsv);

CREATE TABLE facts (
    id              uuid PRIMARY KEY,
    tenant_id       uuid NOT NULL DEFAULT app_tenant(),
    document_id     uuid NOT NULL,
    metric          text NOT NULL,
    value           double precision,
    value_text      text NOT NULL,
    unit            text NOT NULL DEFAULT '',
    period          text NOT NULL DEFAULT '',
    page_number     integer NOT NULL DEFAULT 1,
    content_hash    text NOT NULL DEFAULT '',
    chunk_id        text NOT NULL DEFAULT '',
    source_excerpt  text NOT NULL DEFAULT '',
    extractor       text NOT NULL DEFAULT 'heuristic',
    created_at      timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (tenant_id, document_id) REFERENCES documents (tenant_id, id) ON DELETE CASCADE
);
CREATE INDEX facts_tenant_document ON facts (tenant_id, document_id);

CREATE TABLE page_indexes (
    document_id  uuid PRIMARY KEY,
    tenant_id    uuid NOT NULL DEFAULT app_tenant(),
    tree         jsonb NOT NULL,
    FOREIGN KEY (tenant_id, document_id) REFERENCES documents (tenant_id, id) ON DELETE CASCADE
);

-- A chat thread belongs to one user; its LangGraph checkpoints live in the
-- checkpointer's own tables and are reached only after this row is checked.
-- Thread ids come from the client, so they are unique per tenant only; the
-- checkpointer key is "<tenant_id>:<thread_id>".
CREATE TABLE threads (
    id             text NOT NULL CHECK (length(id) BETWEEN 1 AND 128),
    tenant_id      uuid NOT NULL DEFAULT app_tenant(),
    user_id        uuid NOT NULL,
    document_id    uuid,
    title          text NOT NULL DEFAULT '',
    message_count  integer NOT NULL DEFAULT 0,
    created_at     timestamptz NOT NULL DEFAULT now(),
    updated_at     timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, id),
    FOREIGN KEY (tenant_id, user_id) REFERENCES users (tenant_id, id) ON DELETE CASCADE,
    FOREIGN KEY (tenant_id, document_id) REFERENCES documents (tenant_id, id) ON DELETE SET NULL (document_id)
);
CREATE INDEX threads_user ON threads (tenant_id, user_id, updated_at DESC);

DO $$
DECLARE t text;
BEGIN
    FOREACH t IN ARRAY ARRAY['documents', 'pages', 'chunks', 'facts', 'page_indexes', 'threads'] LOOP
        EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t);
        EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', t);
        EXECUTE format(
            'CREATE POLICY tenant_isolation ON %I USING (tenant_id = app_tenant()) WITH CHECK (tenant_id = app_tenant())',
            t
        );
    END LOOP;
END
$$;

GRANT USAGE ON SCHEMA public TO docmind_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON documents, pages, chunks, facts, page_indexes, threads TO docmind_app;
GRANT SELECT, INSERT, UPDATE ON tenants, users TO docmind_app;
GRANT EXECUTE ON FUNCTION app_tenant() TO docmind_app;
