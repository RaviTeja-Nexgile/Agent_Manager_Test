-- =============================================================================
-- CCFP IT Solution - Migration 0020: CCFP Aggregated Data external links
-- (BRD January 2026)
-- =============================================================================
-- The January 2026 BRD promotes "CCFP Aggregated Data" from an incidental view
-- into a defined term with a glossary entry and a named owner:
--
--   "Linked CCFP crash data (e.g., data from post-crash inspections, PCRs,
--    post-crash investigations, and crash reconstructions), AND DATA FROM
--    EXTERNAL SYSTEMS (e.g., SafeSpect Inspections, Drug and Alcohol
--    Clearinghouse, etc.) that are related to a specific crash."
--
-- ...carrying the system requirement "Create CCFP Aggregated Data by linking raw
-- CCFP crash data and data from external systems ... associated with a specific
-- crash", assigned to the CCFP Database Administrator with Create/Update/Read.
--
-- The platform already models the CCFP-collected half: source_records registers
-- each ingested record and crash_attribute_values holds canonical values with
-- per-value provenance. What is absent is the OTHER half of the definition --
-- the linkage to the Appendix D external systems. This migration adds it:
--
--   1. ref_external_systems  - the Appendix D vocabulary held as DATA, not code.
--      A new source is a row insert, so the BRD's own forward-compatibility note
--      ("some information may shift to Motus ... as FMCSA works to modernize its
--      legacy IT systems") and later study phases are absorbed without a rebuild
--      (§3.4 Adaptability / §11.1).
--   2. crash_external_links  - one row per (crash -> external system record)
--      correspondence, recording HOW the match was made (link_method), WHAT it
--      was matched on (matched_on), how confident it is, and by whom.
--
-- Provenance is retained rather than destroyed. Unlinking flips is_current to
-- FALSE instead of deleting the row -- the same append-only pattern already used
-- for crash_attribute_values (uq_cav_current) and required by the standing rule
-- that provenance is retained on every source value. Uniqueness is therefore a
-- PARTIAL unique index over current rows only, which additionally allows a
-- previously removed reference to be re-linked later.
--
-- Idempotent / additive: IF NOT EXISTS throughout; no existing table is altered
-- and no existing row is touched.
-- =============================================================================

-- How a crash was matched to an external system record. Native ENUM via the
-- idempotent DO/EXCEPTION pattern (mirrors 0001 l.28-31 and 0011).
DO $$ BEGIN
    CREATE TYPE external_link_method AS ENUM ('MANUAL','AUTO','RULE');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- ---------------------------------------------------------------------------
-- Appendix D external-source catalog
-- ---------------------------------------------------------------------------
-- Deliberately a reference TABLE keyed on a TEXT code rather than a native ENUM:
-- the BRD expects this list to grow (Motus, later phases, additional partner
-- systems) and a reference row can be added by an administrator, whereas an
-- ENUM value requires a migration. Rows are retired with is_active = FALSE so
-- historical links stay resolvable.
CREATE TABLE IF NOT EXISTS ref_external_systems (
    code           TEXT PRIMARY KEY,
    name           TEXT NOT NULL,
    owner          TEXT,
    is_fmcsa_owned BOOLEAN NOT NULL DEFAULT TRUE,
    relevant_data  TEXT,
    sort_order     INT NOT NULL DEFAULT 0,
    is_active      BOOLEAN NOT NULL DEFAULT TRUE
);

COMMENT ON TABLE ref_external_systems IS
    'Appendix D external data sources available for CCFP Aggregated Data linkage '
    '. Held as data so new sources (e.g. the BRD''s "may shift to '
    'Motus" note) are row inserts, not code changes. Retire with is_active=FALSE '
    'rather than deleting so historical crash_external_links stay resolvable.';

-- ---------------------------------------------------------------------------
-- Crash -> external system record linkage
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS crash_external_links (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    crash_id      UUID NOT NULL REFERENCES crashes(id) ON DELETE CASCADE,
    source_system TEXT NOT NULL REFERENCES ref_external_systems(code) ON DELETE RESTRICT,
    external_ref  TEXT NOT NULL,
    link_method   external_link_method NOT NULL DEFAULT 'MANUAL',
    matched_on    JSONB,
    confidence    NUMERIC(5,2),
    notes         TEXT,
    linked_by     UUID REFERENCES users(id) ON DELETE SET NULL,
    linked_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    is_current    BOOLEAN NOT NULL DEFAULT TRUE,
    unlinked_by   UUID REFERENCES users(id) ON DELETE SET NULL,
    unlinked_at   TIMESTAMPTZ,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_cel_confidence CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 100))
);

-- One CURRENT link per (crash, system, external reference). Partial on
-- is_current so unlinking retains history and a later re-link is permitted --
-- the same shape as uq_cav_current on crash_attribute_values.
CREATE UNIQUE INDEX IF NOT EXISTS uq_cel_current
    ON crash_external_links (crash_id, source_system, external_ref)
    WHERE is_current;

CREATE INDEX IF NOT EXISTS idx_crash_external_links_crash
    ON crash_external_links (crash_id);
CREATE INDEX IF NOT EXISTS idx_crash_external_links_system
    ON crash_external_links (source_system);

COMMENT ON TABLE crash_external_links IS
    'CCFP Aggregated Data linkage to Appendix D external systems ('
    'BRD Jan-2026 "Create CCFP Aggregated Data by linking raw CCFP crash data '
    'and data from external systems"). Append-only: unlink sets is_current=FALSE '
    'so the linkage history is retained; uq_cel_current enforces one live link '
    'per (crash, system, external_ref). Owned by the CCFP Database Administrator '
    'via the aggregated:link permission.';

COMMENT ON COLUMN crash_external_links.external_ref IS
    'The identifier of the record in the external system (e.g. an MCMIS report '
    'number, a DACH query id, a SafeSpect inspection number). Opaque to CCFP.';
COMMENT ON COLUMN crash_external_links.link_method IS
    'MANUAL (a DBA linked it), AUTO (an adapter matched it), or RULE (a '
    'deterministic matching rule produced it). Vocabulary mirrored by '
    'app.enums.LinkMethod.';
COMMENT ON COLUMN crash_external_links.matched_on IS
    'The identifiers the match was made on (e.g. {"dot_number":"1234567", '
    '"crash_date":"2026-05-01"}), retained as evidence for the linkage.';
