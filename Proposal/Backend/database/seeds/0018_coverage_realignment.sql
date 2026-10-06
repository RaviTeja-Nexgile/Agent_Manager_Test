-- =============================================================================
-- Seed 0018 - Per-State coverage realignment (GAP-PCR-05)
-- =============================================================================
-- Three things to fix, in order of how wrong they were:
--
-- 1. STALE STORED COUNTS. `state_pcr_coverage` still held the old KS worksheet
--    denominators -- CRASH 202, PERSON 294, VEHICLE 378 and so on, counted in
--    attribute-VALUES. The catalog now holds attributes (CRASH 40, PERSON 44,
--    VEHICLE 37), so the stored numbers were out by roughly 5x and made the
--    Study Coverage percentages meaningless.
--
--    The GET endpoint already DERIVES its counts from `attribute_requirements`
--    (so the displayed figures were never actually wrong), but the stored rows
--    are still writable through POST /studies/{id}/pcr-coverage and are still
--    what a State "reports it collects". Leaving 202 in place would have the
--    next reporter overwrite a number they could not reconcile. They are zeroed
--    and stamped with the specification they now belong to.
--
-- 2. MISSING SECTION. The reported (State, section) pairs are driven by the
--    rows in this table. PRIMARY_CONTRIBUTING_FACTORS was registered as a
--    section by GAP-PCR-01 but has no coverage rows, so it never appeared in
--    the report. One row per participating State is added.
--
-- 3. OPTIONAL TIER. The old worksheet had 50 optional attribute-values. The new
--    form has NO optional tier -- everything shown on it is CCFP-required. The
--    optional columns are zeroed here and hidden in the UI. The columns stay in
--    the schema because a future phase may reintroduce the tier, per the gap
--    analysis; they are simply not reported against a source that no longer
--    defines them.
--
-- The pre-change numbers are preserved in `state_pcr_coverage_archive` so the
-- pilot can explain the step change (see the note at the end).
-- =============================================================================

-- ---------------------------------------------------------------------------
-- 0. Archive the pre-realignment numbers before touching them.
--    (GAP-PCR-01 already archived the DYNAMIC rows; this captures the rest.)
-- ---------------------------------------------------------------------------
INSERT INTO state_pcr_coverage_archive (
    id, study_id, state_code, pcr_section_code, required_collected, total_required,
    optional_collected, total_optional, completion_pct, archived_reason, spec_version)
SELECT id, study_id, state_code, pcr_section_code, required_collected, total_required,
       optional_collected, total_optional, completion_pct,
       'GAP-PCR-05: denominators re-derived for the HDTS PCR data form; counts not comparable across specifications',
       'KS-WORKSHEET-2025'
  FROM state_pcr_coverage
 WHERE total_required > 0 OR total_optional > 0
ON CONFLICT (id) DO NOTHING;

-- ---------------------------------------------------------------------------
-- 1. Register PRIMARY_CONTRIBUTING_FACTORS for every State already reported on,
--    so the new section appears in coverage alongside the others.
-- ---------------------------------------------------------------------------
INSERT INTO state_pcr_coverage (study_id, state_code, pcr_section_code, spec_version)
SELECT DISTINCT c.study_id, c.state_code, 'PRIMARY_CONTRIBUTING_FACTORS', 'HDTS-PCR-2026'
  FROM state_pcr_coverage c
ON CONFLICT (study_id, state_code, pcr_section_code) DO NOTHING;

-- ---------------------------------------------------------------------------
-- 2. Zero the stale reported counts and stamp the specification.
--
--    Zero, not "recomputed": these columns record what a STATE REPORTS it
--    collects, which is a statement only the State can make. Deriving them from
--    our own data would silently turn a State's declaration into a copy of our
--    observation. The GET endpoint derives the live figures separately; these
--    stay empty until a State reports under the new form.
-- ---------------------------------------------------------------------------
UPDATE state_pcr_coverage
   SET required_collected = 0,
       total_required     = 0,
       optional_collected = 0,
       total_optional     = 0,
       spec_version       = 'HDTS-PCR-2026',
       updated_at         = now();

-- ---------------------------------------------------------------------------
-- 3. Guards.
-- ---------------------------------------------------------------------------
DO $$
DECLARE n_stale INT; n_pcf INT;
BEGIN
    SELECT count(*) INTO n_stale FROM state_pcr_coverage WHERE total_required > 0;
    IF n_stale > 0 THEN
        RAISE EXCEPTION 'GAP-PCR-05: % coverage row(s) still carry old-worksheet denominators', n_stale;
    END IF;

    SELECT count(*) INTO n_pcf FROM state_pcr_coverage
     WHERE pcr_section_code = 'PRIMARY_CONTRIBUTING_FACTORS';
    IF n_pcf = 0 THEN
        RAISE EXCEPTION 'GAP-PCR-05: PRIMARY_CONTRIBUTING_FACTORS has no coverage rows';
    END IF;

    -- Every live coverage row must name a section that still exists and is active.
    IF EXISTS (
        SELECT 1 FROM state_pcr_coverage c
          JOIN ref_pcr_sections s ON s.code = c.pcr_section_code
         WHERE NOT s.is_active
    ) THEN
        RAISE EXCEPTION 'GAP-PCR-05: a coverage row references a retired PCR section';
    END IF;
END $$;
