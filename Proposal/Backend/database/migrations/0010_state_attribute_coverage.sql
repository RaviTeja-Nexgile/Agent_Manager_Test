-- =============================================================================
-- CCFP IT Solution - Migration 0010: per-attribute State coverage (PCR-3)
-- =============================================================================
-- §8.5 (l.294): the per-State PCR form must colour-code each attribute into one
-- of three states — required-and-collected, required-and-not-collected, or
-- optional-and-not-collected. Today coverage is tracked only at PCR-section
-- granularity (state_pcr_coverage). This adds a per-State, per-attribute
-- "is collected" flag so the documented three-way per-attribute status can be
-- derived and rendered.
--
-- Idempotent / additive: IF NOT EXISTS on table/index creation.
-- =============================================================================

CREATE TABLE IF NOT EXISTS state_attribute_coverage (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    study_id      UUID NOT NULL REFERENCES studies(id) ON DELETE CASCADE,
    state_code    CHAR(2) NOT NULL REFERENCES ref_us_states(code),
    attribute_id  UUID NOT NULL REFERENCES data_attributes(id) ON DELETE CASCADE,
    is_collected  BOOLEAN NOT NULL DEFAULT FALSE,
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (study_id, state_code, attribute_id)
);
CREATE INDEX IF NOT EXISTS idx_state_attribute_coverage_study_state
    ON state_attribute_coverage (study_id, state_code);

COMMENT ON TABLE state_attribute_coverage IS
    'Per-State, per-attribute collection flag (PCR-3, §8.5). Drives the three-way '
    'per-attribute colour status on the PCR coverage view.';
