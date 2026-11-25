-- Schema field extraction and its review queue (M8).
--
-- A field extraction runs in the background (a job of kind 'extract_fields')
-- and writes one row per schema field: the normalised value, the printed
-- text, the page and box it was read from, a confidence, and a status:
--   auto          grounded, above the threshold, no broken rule
--   needs_review  a person should look (the review queue)
--   missing       an optional field the document does not print
--   confirmed     a person checked the machine's value
--   corrected     a person replaced it (machine_value keeps the original)
--   rejected      a person said the document does not have it

ALTER TABLE jobs DROP CONSTRAINT jobs_kind_check;
ALTER TABLE jobs ADD CONSTRAINT jobs_kind_check CHECK (kind IN ('ingest', 'extract_fields'));
ALTER TABLE jobs ADD COLUMN payload jsonb NOT NULL DEFAULT '{}'::jsonb;

CREATE TABLE field_extractions (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       uuid NOT NULL DEFAULT app_tenant(),
    document_id     uuid NOT NULL,
    schema_name     text NOT NULL,
    schema_version  integer NOT NULL,
    status          text NOT NULL DEFAULT 'queued' CHECK (status IN ('queued', 'running', 'done', 'failed')),
    model           text,
    pages_read      integer[] NOT NULL DEFAULT '{}',
    rules           jsonb NOT NULL DEFAULT '[]'::jsonb,
    cost_usd        numeric(14, 8) NOT NULL DEFAULT 0,
    seconds         real,
    error           text,
    requested_by    uuid,
    created_at      timestamptz NOT NULL DEFAULT now(),
    finished_at     timestamptz,
    UNIQUE (tenant_id, id),
    FOREIGN KEY (tenant_id, document_id) REFERENCES documents (tenant_id, id) ON DELETE CASCADE
);
CREATE INDEX field_extractions_document ON field_extractions (tenant_id, document_id, schema_name, created_at DESC);

CREATE TABLE extracted_fields (
    id              bigserial PRIMARY KEY,
    tenant_id       uuid NOT NULL DEFAULT app_tenant(),
    extraction_id   uuid NOT NULL,
    document_id     uuid NOT NULL,
    schema_name     text NOT NULL,
    field           text NOT NULL,
    value           jsonb,
    printed         text,
    unit            text,
    page_number     integer,
    ref             text,
    bbox            jsonb,
    confidence      real NOT NULL DEFAULT 0,
    grounded        boolean NOT NULL DEFAULT false,
    status          text NOT NULL CHECK (status IN ('auto', 'needs_review', 'missing', 'confirmed', 'corrected', 'rejected')),
    reasons         text[] NOT NULL DEFAULT '{}',
    alternatives    jsonb NOT NULL DEFAULT '[]'::jsonb,
    machine_value   jsonb,
    reviewed_by     uuid,
    reviewed_at     timestamptz,
    UNIQUE (extraction_id, field),
    FOREIGN KEY (tenant_id, extraction_id) REFERENCES field_extractions (tenant_id, id) ON DELETE CASCADE
);
CREATE INDEX extracted_fields_review ON extracted_fields (tenant_id, status) WHERE status = 'needs_review';

ALTER TABLE field_extractions ENABLE ROW LEVEL SECURITY;
ALTER TABLE field_extractions FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON field_extractions USING (tenant_id = app_tenant()) WITH CHECK (tenant_id = app_tenant());
ALTER TABLE extracted_fields ENABLE ROW LEVEL SECURITY;
ALTER TABLE extracted_fields FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON extracted_fields USING (tenant_id = app_tenant()) WITH CHECK (tenant_id = app_tenant());

GRANT SELECT, INSERT, UPDATE, DELETE ON field_extractions, extracted_fields TO docmind_app;
GRANT USAGE ON SEQUENCE extracted_fields_id_seq TO docmind_app;
