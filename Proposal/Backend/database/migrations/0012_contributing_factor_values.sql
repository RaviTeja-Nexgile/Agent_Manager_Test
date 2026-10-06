-- =============================================================================
-- CCFP IT Solution - Migration 0012: contributing-factor value catalog (DATA-7)
-- =============================================================================
-- §5 Phase 6 (l.174-176): the analyst's top-three primary contributing factors
-- must be chosen from a structured per-group catalog, not free text, so values
-- aggregate cleanly. The factor *group* is already a reference table
-- (ref_contributing_factor_groups); this adds a per-group value catalog so each
-- group exposes a fixed vocabulary of allowed values.
--
-- Configurable for future phases/groups: new values are added as rows, not code.
-- Idempotent / additive: IF NOT EXISTS.
-- =============================================================================

CREATE TABLE IF NOT EXISTS ref_contributing_factor_values (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    factor_group_id UUID NOT NULL REFERENCES ref_contributing_factor_groups(id) ON DELETE CASCADE,
    code            TEXT,
    label           TEXT NOT NULL,
    sort_order      INT NOT NULL DEFAULT 0,
    UNIQUE (factor_group_id, label)
);
CREATE INDEX IF NOT EXISTS idx_ref_factor_values_group
    ON ref_contributing_factor_values (factor_group_id);

COMMENT ON TABLE ref_contributing_factor_values IS
    'Per-group catalog of allowed contributing-factor values (DATA-7, §5 Phase 6). '
    'Keyed to ref_contributing_factor_groups; new values add rows, not code.';
