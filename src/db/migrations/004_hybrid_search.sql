-- Retrieval v2 (M6): each chunk carries its context (document title,
-- section path), which is embedded with the text and searched by keyword.
--
-- tsv now covers context + text with the 'english' configuration (stems
-- "expenses" and "expense" alike; Amharic words pass through unchanged).
-- embed_hash identifies the exact text that was embedded, so re-indexing
-- reuses a vector only when that text is unchanged.

ALTER TABLE chunks ADD COLUMN context text NOT NULL DEFAULT '';
ALTER TABLE chunks ADD COLUMN embed_hash text NOT NULL DEFAULT '';
ALTER TABLE chunks DROP COLUMN tsv;
ALTER TABLE chunks ADD COLUMN tsv tsvector
    GENERATED ALWAYS AS (to_tsvector('english', context || ' ' || text)) STORED;
CREATE INDEX chunks_tsv ON chunks USING gin (tsv);
