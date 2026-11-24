-- Background ingest jobs and per-page progress (M4).
--
-- An upload stores the PDF, creates the document as 'queued' and adds a job.
-- A separate worker process claims jobs with FOR UPDATE SKIP LOCKED, so any
-- number of workers can run, and a job whose worker died is claimed again
-- once its lease runs out.
--
-- Workers must see every tenant's queue, so the jobs table has a second
-- policy for a connection that has set app.worker = 'on'. Jobs hold ids and
-- status only, never document content; the worker then reads and writes the
-- document's data inside that document's own tenant.

ALTER TABLE documents DROP CONSTRAINT documents_status_check;
ALTER TABLE documents ADD CONSTRAINT documents_status_check
    CHECK (status IN ('uploaded', 'queued', 'processing', 'ready', 'failed'));

-- Progress the UI shows while a document is processed, and whether its
-- chunks may already be searched (a quick text-layer index is built first).
ALTER TABLE documents
    ADD COLUMN stage        text    NOT NULL DEFAULT '',
    ADD COLUMN pages_done   integer NOT NULL DEFAULT 0,
    ADD COLUMN searchable   boolean NOT NULL DEFAULT false;
UPDATE documents SET searchable = true, pages_done = page_count, stage = 'done' WHERE status = 'ready';

CREATE TABLE jobs (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id     uuid NOT NULL DEFAULT app_tenant(),
    document_id   uuid NOT NULL,
    kind          text NOT NULL DEFAULT 'ingest' CHECK (kind IN ('ingest')),
    status        text NOT NULL DEFAULT 'queued' CHECK (status IN ('queued', 'running', 'done', 'failed')),
    attempts      integer NOT NULL DEFAULT 0,
    max_attempts  integer NOT NULL DEFAULT 3,
    run_after     timestamptz NOT NULL DEFAULT now(),
    locked_by     text,
    locked_until  timestamptz,
    error         text,
    created_at    timestamptz NOT NULL DEFAULT now(),
    started_at    timestamptz,
    finished_at   timestamptz,
    FOREIGN KEY (tenant_id, document_id) REFERENCES documents (tenant_id, id) ON DELETE CASCADE
);
CREATE INDEX jobs_claimable ON jobs (run_after) WHERE status IN ('queued', 'running');
CREATE INDEX jobs_document ON jobs (tenant_id, document_id);

ALTER TABLE jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE jobs FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON jobs USING (tenant_id = app_tenant()) WITH CHECK (tenant_id = app_tenant());
CREATE POLICY worker_queue ON jobs USING (current_setting('app.worker', true) = 'on');

GRANT SELECT, INSERT, UPDATE, DELETE ON jobs TO docmind_app;
