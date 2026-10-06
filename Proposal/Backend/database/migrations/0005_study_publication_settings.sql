-- =============================================================================
-- CCFP IT Solution - Migration 0005: study publication settings (STUD-5)
-- =============================================================================
-- Publication policy must be configurable PER STUDY (spec §8.1; §5 Phase 7 —
-- Publication & Data Sharing): each study sets its de-identification policy and
-- the scope of what is shared publicly. Today a Study has no publication
-- settings at all. This adds nullable/defaulted settings columns to `studies`.
--
-- Columns stay plain TEXT (no native PG ENUM) to preserve per-study/phase
-- configurability without a rebuild (§3.4/§11.1); the constrained vocabulary
-- lives in Python (_Str enums DeidentificationPolicy / PublicScope in
-- app/enums.py). NOT NULL DEFAULT so existing rows backfill cleanly and StudyOut
-- never returns null. Settings only — no publication pipeline / de-id engine.
--
-- Idempotent / additive: ADD COLUMN IF NOT EXISTS.
-- =============================================================================

ALTER TABLE studies ADD COLUMN IF NOT EXISTS deidentification_policy TEXT NOT NULL DEFAULT 'STANDARD';
ALTER TABLE studies ADD COLUMN IF NOT EXISTS public_scope            TEXT NOT NULL DEFAULT 'AGGREGATE_ONLY';
ALTER TABLE studies ADD COLUMN IF NOT EXISTS publication_enabled     BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE studies ADD COLUMN IF NOT EXISTS publication_notes       TEXT;

COMMENT ON COLUMN studies.deidentification_policy IS
    'Per-study de-identification policy (e.g. STANDARD / STRICT). Plain TEXT; '
    'vocabulary governed by app.enums.DeidentificationPolicy (STUD-5, §8.1).';
COMMENT ON COLUMN studies.public_scope IS
    'Scope of data shared publicly: NONE / AGGREGATE_ONLY / DEIDENTIFIED_RECORDS. '
    'Plain TEXT; vocabulary governed by app.enums.PublicScope (STUD-5, §5 Phase 7).';
COMMENT ON COLUMN studies.publication_enabled IS
    'Per-study master toggle for whether published outputs are shared (STUD-5).';
COMMENT ON COLUMN studies.publication_notes IS
    'Free-text notes about the study publication policy (STUD-5).';
