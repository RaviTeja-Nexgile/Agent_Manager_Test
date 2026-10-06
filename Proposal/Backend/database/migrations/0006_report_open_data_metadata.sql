-- =============================================================================
-- CCFP IT Solution - Migration 0006: report open-data metadata (ANAL-9)
-- =============================================================================
-- Federal open-data requirements (spec §14.1; Phase 7) expect published datasets
-- to advertise license, keywords, publisher, point-of-contact, and update
-- cadence, and to be discoverable via a Project-Open-Data data.json catalog.
-- This adds the per-report metadata columns the catalog + public endpoints draw
-- from. All columns are nullable and additive (existing rows unaffected); the
-- feature agent wires these into the existing /public/data.json catalog.
--
-- `keywords` is TEXT[] so it maps to the data.json `keyword` array directly.
-- `update_cadence` corresponds to data.json `accrualPeriodicity`.
--
-- Idempotent / additive: ADD COLUMN IF NOT EXISTS.
-- =============================================================================

ALTER TABLE reports ADD COLUMN IF NOT EXISTS license        TEXT;
ALTER TABLE reports ADD COLUMN IF NOT EXISTS keywords       TEXT[];
ALTER TABLE reports ADD COLUMN IF NOT EXISTS publisher      TEXT;
ALTER TABLE reports ADD COLUMN IF NOT EXISTS contact_name   TEXT;
ALTER TABLE reports ADD COLUMN IF NOT EXISTS contact_email  TEXT;
ALTER TABLE reports ADD COLUMN IF NOT EXISTS update_cadence TEXT;

COMMENT ON COLUMN reports.license IS
    'Open-data license of the published report (data.json `license`) (ANAL-9, §14.1).';
COMMENT ON COLUMN reports.keywords IS
    'Open-data keyword tags (data.json `keyword` array) (ANAL-9, §14.1).';
COMMENT ON COLUMN reports.publisher IS
    'Publishing organization name (data.json `publisher.name`) (ANAL-9, §14.1).';
COMMENT ON COLUMN reports.contact_name IS
    'Point-of-contact name (data.json `contactPoint.fn`) (ANAL-9, §14.1).';
COMMENT ON COLUMN reports.contact_email IS
    'Point-of-contact email (data.json `contactPoint.hasEmail`) (ANAL-9, §14.1).';
COMMENT ON COLUMN reports.update_cadence IS
    'Update cadence / accrual periodicity (data.json `accrualPeriodicity`) (ANAL-9, §14.1).';
