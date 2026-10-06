-- =============================================================================
-- CCFP IT Solution - Migration 0021: PCR section set realignment (GAP-PCR-01)
-- =============================================================================
-- The old KS Sample Study Inclusion worksheet and the new HDTS Police Crash
-- Report data form carry DIFFERENT section sets:
--
--   REMOVED  "Dynamic Data Elements" and its sole element
--            DV01 Motor Vehicle Automated Driving System(s) (21 required
--            attribute-values in the old worksheet). Verified absent from the
--            new form: zero occurrences of "Dynamic" or "Automated".
--
--   ADDED    "Primary Contributing Factors" -- now a form section carrying
--            Primary Contributing Factor 1/2/3, with the five BRD source
--            sections named on the form itself.
--
--   RENAMED  every section ("... Section" -> "... Data Elements") and the
--            section ORDER changed.
--
-- DEACTIVATION, NOT DELETION. `ref_pcr_sections` and `data_attributes` are
-- referenced by historical rows (crash_attribute_values.attribute_id is
-- ON DELETE RESTRICT; state_pcr_coverage.pcr_section_code is a FK). Deleting
-- DYNAMIC/DV01 would either fail or orphan collected history from crashes
-- recorded under the old specification. Instead they are flagged inactive so
-- they stop being offered for new collection while remaining resolvable.
--
-- The contributing-factor tables (ref_contributing_factor_groups,
-- ref_contributing_factor_values, contributing_factor_selections) already model
-- the top-three prompt correctly and are NOT restructured here -- this only
-- registers Primary Contributing Factors as a PCR *section* so it appears in
-- the section catalog and coverage reporting alongside the others.
--
-- Idempotent / additive.
-- =============================================================================

-- ---------------------------------------------------------------------------
-- Sections gain a lifecycle flag so a retired section survives for history
-- without being offered for new collection.
-- ---------------------------------------------------------------------------
ALTER TABLE ref_pcr_sections
    ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE;

COMMENT ON COLUMN ref_pcr_sections.is_active IS
    'FALSE = retired by a later specification; retained so historical values and coverage rows stay resolvable, but not offered for new collection.';

-- ---------------------------------------------------------------------------
-- Register the new section. The Primary Contributing Factor 1/2/3 selections
-- themselves continue to live in contributing_factor_selections (rank 1..3).
-- ---------------------------------------------------------------------------
INSERT INTO ref_pcr_sections (code, name, sort_order) VALUES
 ('PRIMARY_CONTRIBUTING_FACTORS','Primary Contributing Factors',8)
ON CONFLICT (code) DO NOTHING;

-- ---------------------------------------------------------------------------
-- Rename + reorder to the new form's section list and order:
--   Crash · Fatal · Large Vehicle and HM · Person · Vehicle · Non-Motorist ·
--   Roadway · Primary Contributing Factors
-- Codes are the stable internal keys and are deliberately NOT renamed -- they
-- are referenced by data_attributes.pcr_section and state_pcr_coverage.
-- ---------------------------------------------------------------------------
UPDATE ref_pcr_sections SET name = 'Crash Data Elements',                                   sort_order = 1 WHERE code = 'CRASH';
UPDATE ref_pcr_sections SET name = 'Fatal Data Elements',                                   sort_order = 2 WHERE code = 'FATAL';
UPDATE ref_pcr_sections SET name = 'Large Vehicle and Hazardous Material (HM) Data Elements', sort_order = 3 WHERE code = 'LARGE_VEH_HAZMAT';
UPDATE ref_pcr_sections SET name = 'Person Data Elements',                                  sort_order = 4 WHERE code = 'PERSON';
UPDATE ref_pcr_sections SET name = 'Vehicle Data Elements',                                 sort_order = 5 WHERE code = 'VEHICLE';
UPDATE ref_pcr_sections SET name = 'Non-Motorist Data Elements',                             sort_order = 6 WHERE code = 'NON_MOTORIST';
UPDATE ref_pcr_sections SET name = 'Roadway Data Elements',                                 sort_order = 7 WHERE code = 'ROADWAY';
UPDATE ref_pcr_sections SET name = 'Primary Contributing Factors',                           sort_order = 8 WHERE code = 'PRIMARY_CONTRIBUTING_FACTORS';

-- ---------------------------------------------------------------------------
-- Retire the Dynamic Data Elements section and its sole element.
-- sort_order is pushed past the live sections so any ordered listing that does
-- surface retired rows keeps them last.
-- ---------------------------------------------------------------------------
UPDATE ref_pcr_sections
   SET name = 'Dynamic Data Elements (retired)', is_active = FALSE, sort_order = 99
 WHERE code = 'DYNAMIC';

UPDATE data_attributes SET is_active = FALSE WHERE code = 'DV01';

-- A retired attribute must not remain a study requirement, or completeness
-- evaluation would keep demanding a value the new form no longer collects.
UPDATE attribute_requirements
   SET is_required = FALSE, is_optional = FALSE, updated_at = now()
 WHERE attribute_id IN (SELECT id FROM data_attributes WHERE code = 'DV01');

-- ---------------------------------------------------------------------------
-- Archive the DYNAMIC per-State coverage rows.
--
-- Their denominator (21 attribute-values from the old worksheet) no longer
-- corresponds to anything in the new specification, so leaving them in place
-- would drag every State's completion_pct down against a section that is no
-- longer collected. Rows are copied to an archive table first -- the numbers
-- are a record of what a State reported under the old spec, which the pilot
-- may need to explain a change in coverage.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS state_pcr_coverage_archive (
    id                 UUID PRIMARY KEY,
    study_id           UUID NOT NULL,
    state_code         CHAR(2) NOT NULL,
    pcr_section_code   TEXT NOT NULL,
    required_collected INT NOT NULL,
    total_required     INT NOT NULL,
    optional_collected INT NOT NULL,
    total_optional     INT NOT NULL,
    completion_pct     NUMERIC(5,2),
    archived_reason    TEXT NOT NULL,
    archived_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

INSERT INTO state_pcr_coverage_archive (
    id, study_id, state_code, pcr_section_code, required_collected, total_required,
    optional_collected, total_optional, completion_pct, archived_reason)
SELECT id, study_id, state_code, pcr_section_code, required_collected, total_required,
       optional_collected, total_optional, completion_pct,
       'GAP-PCR-01: Dynamic Data Elements section removed by the HDTS PCR data form'
  FROM state_pcr_coverage
 WHERE pcr_section_code = 'DYNAMIC'
ON CONFLICT (id) DO NOTHING;

DELETE FROM state_pcr_coverage WHERE pcr_section_code = 'DYNAMIC';
