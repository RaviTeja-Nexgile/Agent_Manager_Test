-- =============================================================================
-- CCFP IT Solution - Migration 0024: coverage spec version (GAP-PCR-05)
-- =============================================================================
-- The per-State coverage numbers were seeded from the old KS Sample Study
-- Inclusion worksheet, which quantified readiness per section (636/1,194
-- required collected, 53.27%, plus a 50-item optional tier).
--
-- The new HDTS PCR data form contains NO per-State quantification, NO optional
-- tier, and no colour coding -- everything on it is CCFP-required. The
-- required/optional distinction now lives entirely in the CCFP IT Solution's
-- own `attribute_requirements` configuration, which an administrator manages
-- per study.
--
-- Consequence: a coverage percentage computed under the old worksheet is NOT
-- comparable with one computed under the new form. The denominators changed
-- (the CRASH section went from 202 required attribute-VALUES to 40 attributes),
-- the DYNAMIC section disappeared, and the optional tier has no source.
-- Presenting the two side by side without saying so would read as a State's
-- readiness collapsing or leaping when nothing about the State changed.
--
-- `spec_version` stamps which specification a row's numbers belong to, so the
-- pilot can explain a step change rather than having to reconstruct it.
--
-- Idempotent / additive.
-- =============================================================================

ALTER TABLE state_pcr_coverage
    ADD COLUMN IF NOT EXISTS spec_version TEXT NOT NULL DEFAULT 'HDTS-PCR-2026';

COMMENT ON COLUMN state_pcr_coverage.spec_version IS
    'The PCR specification a row''s reported counts were recorded against. KS-WORKSHEET-2025 = the old KS Sample Study Inclusion worksheet; HDTS-PCR-2026 = the HDTS Police Crash Report data form. Percentages are NOT comparable across versions (GAP-PCR-05).';

ALTER TABLE state_pcr_coverage_archive
    ADD COLUMN IF NOT EXISTS spec_version TEXT;

COMMENT ON COLUMN state_pcr_coverage_archive.spec_version IS
    'Specification the archived counts were recorded against (GAP-PCR-05).';
