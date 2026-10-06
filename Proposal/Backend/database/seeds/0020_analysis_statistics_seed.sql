-- =============================================================================
-- Seed 0020 - Statistical analysis cohorts and investigations
-- =============================================================================
-- Seeds the populations the January 2026 BRD's statistical methods run over, and
-- one saved investigation per method family so every path is exercised.
--
-- THE COHORT SET IS THE POINT OF THIS SEED.
--
-- The BRD makes risk modelling conditional: "statistical risk modeling (given
-- the availability of control such as non-fatal crashes)". The reading that
-- kills the requirement is "Phase 1 collects fatal crashes, so no control
-- exists". These cohorts show that reading is wrong using data already present:
--
--   FATAL_INSCOPE     CASE     num_fatalities >= 1, scope = IN_SCOPE
--                              -- the Phase 1 study population
--   NONFATAL_CONTROL  CONTROL  num_fatalities = 0
--                              -- crashes recorded and then classified out.
--                                 This is the BRD's "non-fatal crashes",
--                                 literally.
--   OUTOFSCOPE_CONTROL CONTROL scope = OUT_OF_SCOPE
--                              -- qualifying crashes from non-participating
--                                 States: a second, larger comparison arm for
--                                 when the non-fatal set is too thin.
--   ALL_CRASHES       GENERAL  no filters -- the descriptive denominator.
--   KS_FATAL          GENERAL  Kansas fatal crashes, for State comparison.
--
-- The two CONTROL cohorts are deliberately different in size and in what they
-- control for. Neither is asserted to be the right control for CCFP; that is an
-- FMCSA determination in discovery. What is demonstrated is that the platform
-- can express, materialize, designate and use one -- so whichever population
-- FMCSA confirms becomes a row here and nothing else changes.
--
-- Honest caveat, and the reason the API returns caveats at all: at Phase 1 seed
-- volumes these cohorts are tiny (tens of crashes), so every risk estimate they
-- produce has an interval far too wide to be a finding. The methods report that
-- themselves rather than leaving it to be noticed.
--
-- ALL data below is synthetic, derived from the fictitious crash records in
-- earlier seeds. Dev/test/demo only.
-- =============================================================================

-- ---------------------------------------------------------------------------
-- Cohorts
-- ---------------------------------------------------------------------------
INSERT INTO analysis_cohorts (environment_id, code, name, description, cohort_role, definition)
SELECT e.id, v.code, v.name, v.description, v.cohort_role, v.definition::jsonb
FROM analysis_environments e
CROSS JOIN (VALUES
 ('FATAL_INSCOPE', 'Fatal in-scope crashes (cases)',
  'Phase 1 study population: crashes with at least one fatality that were classified in scope. This is the case arm of every risk model.',
  'CASE',
  '{"filters":[{"column":"num_fatalities","op":"gte","value":1},{"column":"scope","op":"eq","value":"IN_SCOPE"}]}'),

 ('NONFATAL_CONTROL', 'Non-fatal crashes (control)',
  'Crashes recorded in CCFP with no fatality. The BRD names non-fatal crashes as the example control population for statistical risk modeling.',
  'CONTROL',
  '{"filters":[{"column":"num_fatalities","op":"lte","value":0}]}'),

 ('OUTOFSCOPE_CONTROL', 'Out-of-scope crashes (control)',
  'Crashes classified out of the Phase 1 study -- chiefly qualifying crashes in non-participating States. A second comparison arm when the non-fatal set is too small to support an estimate.',
  'CONTROL',
  '{"filters":[{"column":"scope","op":"eq","value":"OUT_OF_SCOPE"}]}'),

 ('ALL_CRASHES', 'All recorded crashes',
  'Every crash in the environment, regardless of scope or outcome. The descriptive denominator and the widest base for thematic analysis.',
  'GENERAL',
  '{"filters":[]}'),

 ('KS_FATAL', 'Kansas fatal crashes',
  'Fatal crashes in Kansas. Paired with another State cohort this supports the comparative analysis the BRD expects of analysts.',
  'GENERAL',
  '{"filters":[{"column":"state_code","op":"eq","value":"KS"},{"column":"num_fatalities","op":"gte","value":1}]}'),

 ('TX_FATAL', 'Texas fatal crashes',
  'Fatal crashes in Texas, the comparison arm for KS_FATAL.',
  'GENERAL',
  '{"filters":[{"column":"state_code","op":"eq","value":"TX"},{"column":"num_fatalities","op":"gte","value":1}]}')
) AS v(code, name, description, cohort_role, definition)
WHERE e.code = 'CCFP_AE'
ON CONFLICT (environment_id, code) DO NOTHING;

-- ---------------------------------------------------------------------------
-- Saved investigations -- one per method family, so every code path in
-- POST /analysis-investigations/{id}/run is exercised by the seed rather than
-- only by whatever an operator happens to click.
--
-- Parameters carry cohort ids, which are generated above, so each row resolves
-- its own references by code.
-- ---------------------------------------------------------------------------
INSERT INTO analysis_investigations (environment_id, code, name, description, method, parameters, visibility)
SELECT e.id, v.code, v.name, v.description, v.method, v.parameters::jsonb, 'TEAM'
FROM analysis_environments e
CROSS JOIN LATERAL (VALUES
 ('FATALITIES_DESCRIPTIVE', 'Fatalities per crash - central tendency and dispersion',
  'Descriptive statistics for the number of fatalities across the Phase 1 case population.',
  'DESCRIPTIVE',
  json_build_object(
    'cohort_id', (SELECT c.id::text FROM analysis_cohorts c WHERE c.environment_id = e.id AND c.code = 'FATAL_INSCOPE'),
    'variable', 'num_fatalities',
    'confidence', 0.95
  )::text),

 ('STATE_DISTRIBUTION', 'Crash distribution by State',
  'Frequency distribution of the case population across participating States.',
  'DISTRIBUTION',
  json_build_object(
    'cohort_id', (SELECT c.id::text FROM analysis_cohorts c WHERE c.environment_id = e.id AND c.code = 'FATAL_INSCOPE'),
    'variable', 'state_code'
  )::text),

 ('FACTOR_THEMES', 'Contributing-factor themes and co-occurrence',
  'Which contributing factors recur across all recorded crashes, and which appear together more often than chance.',
  'THEMATIC',
  json_build_object(
    'cohort_id', (SELECT c.id::text FROM analysis_cohorts c WHERE c.environment_id = e.id AND c.code = 'ALL_CRASHES'),
    'min_support', 1,
    'top_n', 25
  )::text),

 ('FATAL_TREND', 'Fatal crashes by year',
  'Trend in fatal crash counts over time, with an ordinary-least-squares fit.',
  'TREND',
  json_build_object(
    'cohort_id', (SELECT c.id::text FROM analysis_cohorts c WHERE c.environment_id = e.id AND c.code = 'FATAL_INSCOPE'),
    'period', 'YEAR',
    'measure', 'crash_count'
  )::text),

 ('KS_TX_COMPARISON', 'Kansas vs Texas - fatalities per crash',
  'Comparative analysis of two State crash populations using Welch''s t-test.',
  'COMPARATIVE',
  json_build_object(
    'cohort_a_id', (SELECT c.id::text FROM analysis_cohorts c WHERE c.environment_id = e.id AND c.code = 'KS_FATAL'),
    'cohort_b_id', (SELECT c.id::text FROM analysis_cohorts c WHERE c.environment_id = e.id AND c.code = 'TX_FATAL'),
    'variable', 'num_fatalities',
    'confidence', 0.95
  )::text)
) AS v(code, name, description, method, parameters)
WHERE e.code = 'CCFP_AE'
ON CONFLICT (environment_id, code) DO NOTHING;

-- The risk model is seeded separately: it is only valid if a contributing factor
-- actually exists to use as the exposure, and seeding it against a factor that
-- appears on no crash would produce an all-zero table that looks like a bug.
-- The most frequently recorded factor is chosen from the data itself.
INSERT INTO analysis_investigations (environment_id, code, name, description, method, parameters, visibility)
SELECT e.id,
       'TOP_FACTOR_RISK',
       'Risk model - most frequent contributing factor',
       'Case-control risk model for the most frequently recorded contributing factor, comparing fatal in-scope crashes against the out-of-scope control population.',
       'RISK_MODEL',
       json_build_object(
         'case_cohort_id',    (SELECT c.id::text FROM analysis_cohorts c WHERE c.environment_id = e.id AND c.code = 'FATAL_INSCOPE'),
         'control_cohort_id', (SELECT c.id::text FROM analysis_cohorts c WHERE c.environment_id = e.id AND c.code = 'OUTOFSCOPE_CONTROL'),
         'exposure_factor',   (SELECT s.factor_value FROM contributing_factor_selections s
                                GROUP BY s.factor_value ORDER BY count(*) DESC, s.factor_value LIMIT 1),
         'confidence', 0.95
       )::jsonb,
       'TEAM'
FROM analysis_environments e
WHERE e.code = 'CCFP_AE'
  AND EXISTS (SELECT 1 FROM contributing_factor_selections)
ON CONFLICT (environment_id, code) DO NOTHING;

-- Cohorts materialize on the next environment refresh, which the environment
-- triggers itself when an analyst opens the page. Nothing is pre-baked here, so
-- the seed exercises the refresh machinery rather than hiding a failure in it.
