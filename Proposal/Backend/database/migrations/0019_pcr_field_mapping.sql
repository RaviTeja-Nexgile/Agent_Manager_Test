-- =============================================================================
-- CCFP IT Solution - Migration 0019: PCR field mapping (PCR-1)
-- =============================================================================
-- §8.5 / §19.4: a State maps the fields on its EXISTING Police Crash Report to
-- the CCFP attribute model WITHOUT changing the State form. Today only a PCR
-- header row exists (police_crash_reports) and the "Map" action merely flips
-- mapping_status to MAPPED. This adds the missing relation: one row per
-- (State PCR field -> CCFP attribute) correspondence, recorded against the
-- existing MMUCC-aligned data_attributes catalog.
--
-- The State PCR form itself is NOT modified — this only records a mapping FROM
-- the State's existing fields TO CCFP attribute codes. No live State-repository
-- connector (out of scope; PCR-4 owns the path enum).
--
-- Idempotent / additive: IF NOT EXISTS on table/index creation.
-- =============================================================================

CREATE TABLE IF NOT EXISTS pcr_field_mapping (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pcr_id               UUID NOT NULL REFERENCES police_crash_reports(id) ON DELETE CASCADE,
    state_field_name     TEXT NOT NULL,
    state_field_position TEXT,
    attribute_id         UUID NOT NULL REFERENCES data_attributes(id) ON DELETE RESTRICT,
    notes                TEXT,
    mapped_by            UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (pcr_id, attribute_id)
);
CREATE INDEX IF NOT EXISTS idx_pcr_field_mapping_pcr
    ON pcr_field_mapping (pcr_id);

COMMENT ON TABLE pcr_field_mapping IS
    'State PCR field -> CCFP attribute mapping (PCR-1, §8.5/§19.4). One row per '
    'mapped attribute on a police_crash_reports record; the State form is never '
    'altered. UNIQUE(pcr_id, attribute_id) keeps one mapping per attribute per PCR.';
