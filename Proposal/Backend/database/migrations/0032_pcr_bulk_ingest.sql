-- =============================================================================
-- CCFP IT Solution - Migration 0032: PCR bulk-ingest column mappings (GAP-SOO-05)
-- =============================================================================
-- The SOO requires the "capability to import/ingest CCFP-required police crash
-- report (PCR) data elements and attributes from States' existing PCRs, with a
-- primary goal of minimizing data sharing burden to the States".
--
-- Neither the BRD nor the SOO specifies the file format any State's PCR system
-- exports, and they never will: there are 50 of them and the whole point of
-- "minimizing burden" is that a State keeps its existing form and export. So
-- this deliberately does NOT define a CCFP PCR file format for States to conform
-- to — that would move the burden onto them, which is the opposite of the
-- requirement.
--
-- Instead the format becomes DATA. This table maps a State's own export column
-- headers to CCFP data attributes, exactly as `eld_field_mappings` does for ELD
-- provider CSVs (RECO-5). A State sends whatever its system already produces;
-- an administrator configures the header mapping once; every subsequent file
-- ingests with no code change. A new State is onboarded by inserting rows here.
--
-- `pcr_field_mapping` (migration 0019) is a per-REPORT record of provenance —
-- which field on one filed report corresponded to which attribute. This is the
-- per-STATE ingest rule applied before any report exists. Related, not the same:
-- one documents what was mapped, the other decides what to map.
--
-- Precedence mirrors the ELD resolver: a study+state row beats a state-only row
-- beats a global default (NULL study, NULL state), with `priority` breaking ties.
-- =============================================================================

CREATE TABLE IF NOT EXISTS pcr_column_mappings (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    study_id        UUID REFERENCES studies(id) ON DELETE CASCADE,
    -- NULL state_code = a default that applies to every State, so a header the
    -- whole country happens to share ("Crash Date") is configured once.
    state_code      CHAR(2) REFERENCES ref_us_states(code),
    -- The header exactly as it appears in the State's export. Normalised on
    -- comparison (lower-case, non-alphanumeric runs collapsed) so trivial
    -- punctuation differences do not require a second row.
    source_header   TEXT NOT NULL,
    -- The CCFP attribute the column lands in. RESTRICT: a mapping must not be
    -- silently orphaned by deleting the attribute it targets.
    attribute_id    UUID NOT NULL REFERENCES data_attributes(id) ON DELETE RESTRICT,
    priority        INTEGER NOT NULL DEFAULT 0,
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    notes           TEXT,
    created_by      UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- One active rule per (scope, header, attribute). Partial index so superseded
-- rows can be retained as history by flipping is_active rather than deleting.
CREATE UNIQUE INDEX IF NOT EXISTS ux_pcr_column_mappings_active
    ON pcr_column_mappings (
        COALESCE(study_id, '00000000-0000-0000-0000-000000000000'::uuid),
        COALESCE(state_code, '--'),
        lower(source_header),
        attribute_id
    ) WHERE is_active;

CREATE INDEX IF NOT EXISTS ix_pcr_column_mappings_lookup
    ON pcr_column_mappings (state_code, study_id) WHERE is_active;
