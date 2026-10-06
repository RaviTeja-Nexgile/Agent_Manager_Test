-- =============================================================================
-- CCFP IT Solution - Migration 0011: PCR ingestion path (PCR-4)
-- =============================================================================
-- §8.5 (l.289-292): a PCR reaches the platform by one of two structured paths —
-- the MCMIS round-trip (uploaded to the State repository, pushed to SafeSpect,
-- then ingested from MCMIS) or a direct State-repository connection that
-- bypasses the round-trip. Today the path lives only in the free-text
-- `source_repository`. This models it as a native enum captured per PCR record.
-- The live connectors themselves are out of scope — only the path is modelled.
--
-- Native ENUM via the idempotent DO/EXCEPTION pattern (mirrors 0001 l.28-31),
-- then an additive ADD COLUMN IF NOT EXISTS so re-running is safe.
-- =============================================================================

DO $$ BEGIN
    CREATE TYPE ingestion_path AS ENUM ('MCMIS_ROUNDTRIP','DIRECT_STATE');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

ALTER TABLE police_crash_reports
    ADD COLUMN IF NOT EXISTS ingestion_path ingestion_path NOT NULL DEFAULT 'MCMIS_ROUNDTRIP';

COMMENT ON COLUMN police_crash_reports.ingestion_path IS
    'Structured PCR ingestion path: MCMIS_ROUNDTRIP | DIRECT_STATE (PCR-4, §8.5). '
    'Vocabulary mirrored by app.enums.IngestionPath.';
