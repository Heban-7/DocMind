-- Cost ledger and spending caps (M7).
--
-- Every model and embedding call writes one row: who asked (tenant, user,
-- thread, document), what for (plan, answer, ingest, ...), which model, the
-- tokens, the cost in USD and how long it took. A tenant sees only its own
-- rows (RLS), like every other table.
--
-- The monthly cap across all tenants needs a total that no tenant's RLS
-- view can give, so the running total per month is kept in llm_spend_monthly:
-- one number per month, no tenant data.

CREATE TABLE llm_usage (
    id             bigserial PRIMARY KEY,
    tenant_id      uuid NOT NULL DEFAULT app_tenant(),
    user_id        uuid,
    thread_id      text,
    document_id    uuid,
    purpose        text NOT NULL DEFAULT 'other',
    kind           text NOT NULL DEFAULT 'llm' CHECK (kind IN ('llm', 'embed')),
    provider       text NOT NULL DEFAULT '',
    model          text NOT NULL DEFAULT '',
    input_tokens   integer NOT NULL DEFAULT 0,
    output_tokens  integer NOT NULL DEFAULT 0,
    cost_usd       numeric(14, 8) NOT NULL DEFAULT 0,
    latency_ms     integer NOT NULL DEFAULT 0,
    first_token_ms integer,
    ok             boolean NOT NULL DEFAULT true,
    error_kind     text,
    created_at     timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (tenant_id) REFERENCES tenants (id) ON DELETE CASCADE
);
CREATE INDEX llm_usage_tenant_time ON llm_usage (tenant_id, created_at);

ALTER TABLE llm_usage ENABLE ROW LEVEL SECURITY;
ALTER TABLE llm_usage FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON llm_usage USING (tenant_id = app_tenant()) WITH CHECK (tenant_id = app_tenant());
GRANT SELECT, INSERT ON llm_usage TO docmind_app;
GRANT USAGE ON SEQUENCE llm_usage_id_seq TO docmind_app;

CREATE TABLE llm_spend_monthly (
    month     date PRIMARY KEY,  -- first day of the month (UTC)
    cost_usd  numeric(14, 8) NOT NULL DEFAULT 0,
    calls     integer NOT NULL DEFAULT 0
);
GRANT SELECT, INSERT, UPDATE ON llm_spend_monthly TO docmind_app;
