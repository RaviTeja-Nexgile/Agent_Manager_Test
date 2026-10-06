-- =============================================================================
-- CCFP IT Solution - Migration 0008: full-text + trigram search (SEAR-2)
-- =============================================================================
-- §9.2 / §15 / §8.10: cross-entity search must find crashes, people, carriers,
-- reports and the unstructured content of source documents. This replaces the
-- substring-only search with PostgreSQL-native full-text (to_tsvector /
-- websearch_to_tsquery) plus pg_trgm fuzzy matching, broadens the searched
-- columns, and adds an extracted-text column on documents so document content
-- becomes searchable. Stays entirely inside PostgreSQL (no external engine).
--
-- Forward-only runner: all DDL is idempotent (IF NOT EXISTS) so re-running is
-- safe. pg_trgm ships with PostgreSQL — enabling it is in-stack, not new infra.
-- =============================================================================

CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- Nullable extracted/plain-text content for document content search. NULL for
-- binary seed docs (they remain findable by file_name); written wherever plain
-- text is available. No OCR/ingestion pipeline here.
ALTER TABLE documents ADD COLUMN IF NOT EXISTS content_text TEXT;

-- --- Full-text (GIN over to_tsvector) indexes ------------------------------
CREATE INDEX IF NOT EXISTS idx_crashes_fts ON crashes USING gin (
    to_tsvector('english',
        coalesce(ccfp_identifier,'') || ' ' || coalesce(local_report_number,'') || ' ' ||
        coalesce(city,'') || ' ' || coalesce(county,'') || ' ' || coalesce(street_highway,''))
);

CREATE INDEX IF NOT EXISTS idx_incident_persons_fts ON incident_persons USING gin (
    to_tsvector('english', coalesce(full_name,''))
);

CREATE INDEX IF NOT EXISTS idx_incident_vehicles_fts ON incident_vehicles USING gin (
    to_tsvector('english',
        coalesce(carrier_name,'') || ' ' || coalesce(make,'') || ' ' || coalesce(us_dot_number,''))
);

CREATE INDEX IF NOT EXISTS idx_reports_fts ON reports USING gin (
    to_tsvector('english', coalesce(name,'') || ' ' || coalesce(description,''))
);

CREATE INDEX IF NOT EXISTS idx_documents_fts ON documents USING gin (
    to_tsvector('english', coalesce(file_name,'') || ' ' || coalesce(content_text,''))
);

-- --- Trigram (gin_trgm_ops) indexes for fuzzy id/name fallback -------------
CREATE INDEX IF NOT EXISTS idx_crashes_ccfp_trgm ON crashes USING gin (ccfp_identifier gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_crashes_local_report_trgm ON crashes USING gin (local_report_number gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_incident_persons_name_trgm ON incident_persons USING gin (full_name gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_incident_vehicles_carrier_trgm ON incident_vehicles USING gin (carrier_name gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_incident_vehicles_dot_trgm ON incident_vehicles USING gin (us_dot_number gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_reports_name_trgm ON reports USING gin (name gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_documents_filename_trgm ON documents USING gin (file_name gin_trgm_ops);

COMMENT ON COLUMN documents.content_text IS
    'Extracted/plain text for full-text document content search (SEAR-2, §8.10). '
    'NULL for binary docs; searched wherever plain text is stored. No OCR here.';
