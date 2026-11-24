-- Typed facts and a read-only role for numeric queries (M5).
--
-- A fact now carries what it measures (row label, section row, column label,
-- table title), the scale and currency the document states for it, and where
-- it is printed (table, row, column, box). value_abs = value * scale is what
-- the database computes with.
--
-- Numeric questions run as SQL compiled from a checked spec, under the role
-- docmind_reader: SELECT on facts and documents only, so a query can never
-- change data. Row-level security applies to it like to every other role.

CREATE EXTENSION IF NOT EXISTS pg_trgm;

ALTER TABLE facts
    ADD COLUMN row_label     text NOT NULL DEFAULT '',
    ADD COLUMN row_group     text NOT NULL DEFAULT '',
    ADD COLUMN column_label  text NOT NULL DEFAULT '',
    ADD COLUMN table_title   text NOT NULL DEFAULT '',
    ADD COLUMN scale         double precision NOT NULL DEFAULT 1,
    ADD COLUMN currency      text NOT NULL DEFAULT '',
    ADD COLUMN table_id      text NOT NULL DEFAULT '',
    ADD COLUMN row_index     integer,
    ADD COLUMN col_index     integer,
    ADD COLUMN bbox          real[],
    ADD COLUMN source        text NOT NULL DEFAULT 'text' CHECK (source IN ('table', 'text')),
    ADD COLUMN confidence    real NOT NULL DEFAULT 1,
    ADD COLUMN period_key    text NOT NULL DEFAULT '',
    ADD COLUMN value_abs     double precision GENERATED ALWAYS AS (value * scale) STORED,
    ADD COLUMN search_text   text GENERATED ALWAYS AS (
        lower(row_group || ' ' || metric || ' ' || column_label || ' ' || table_title)
    ) STORED;

CREATE INDEX facts_search_trgm ON facts USING gin (search_text gin_trgm_ops);
CREATE INDEX facts_period ON facts (tenant_id, document_id, period_key);

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'docmind_reader') THEN
        CREATE ROLE docmind_reader NOLOGIN;
    END IF;
END
$$;
GRANT USAGE ON SCHEMA public TO docmind_reader;
GRANT SELECT ON facts, documents TO docmind_reader;
GRANT EXECUTE ON FUNCTION app_tenant() TO docmind_reader;
GRANT docmind_reader TO docmind_app;
