-- =============================================================================
-- Seed 0014 - CCFP Analysis Environment (GAP-BRD-02)
-- =============================================================================
-- Stands up the environment described in the January 2026 BRD "Data Analysis
-- and Sharing" chapter, with four datasets chosen to exercise every audience
-- rule rather than merely to look populated:
--
--   CRASHES_BY_STATE          NO_PII, State-partitioned    -> Federal + States
--   FATALITIES_BY_STATE_YEAR  NO_PII, State-partitioned    -> Federal + one State
--   LIFECYCLE_PHASE_SUMMARY   DEIDENTIFIED_SUMMARY         -> Federal + PUBLIC
--   COUNTY_SMALL_CELL_DETAIL  PII                          -> Federal ONLY
--
-- The last one is the point of the set. County-level counts over a fatal-crash
-- population produce small cells that are re-identifiable in practice, so it is
-- classified PII — and the database trigger will refuse any attempt to share it
-- to a State or to the public. A demo where every dataset is shareable would
-- not show that the control exists.
--
-- No rows are seeded. The datasets materialize on the first refresh, which the
-- environment triggers itself because next_refresh_due starts NULL — so the
-- seed also demonstrates that the refresh machinery works rather than shipping
-- a pre-baked result that would look identical if it did not.
--
-- ALL data below is synthetic and derived from the fictitious crash records in
-- earlier seeds. Dev/test/demo only.
-- =============================================================================

-- ---------------------------------------------------------------------------
-- The environment. study_id is NULL: Phase 1 runs a single environment across
-- CCFP Aggregated Data as a whole. A future phase can add a study-scoped
-- environment alongside it without a schema change.
-- ---------------------------------------------------------------------------
INSERT INTO analysis_environments (code, name, description, study_id, status, refresh_cadence)
VALUES (
    'CCFP_AE',
    'CCFP Analysis Environment',
    'Authorized analysis tier holding CCFP Aggregated Data and derived views, '
    'refreshed on a daily cadence and shared out to Federal, State and public audiences.',
    NULL,
    'ACTIVE',
    'DAILY'
)
ON CONFLICT (code) DO NOTHING;

-- ---------------------------------------------------------------------------
-- Datasets. `definition` uses the constrained vocabulary validated by
-- app/workers/analysis.py — dimensions/measures/filters drawn from server-side
-- allow-lists, never free-form SQL.
--
-- is_state_partitioned must agree with whether state_code is a dimension; the
-- share trigger reads this column when deciding whether a single State may
-- receive the dataset.
-- ---------------------------------------------------------------------------
INSERT INTO analysis_datasets
    (environment_id, code, name, description, kind, definition, pii_level, is_state_partitioned)
SELECT e.id, d.code, d.name, d.description, d.kind, d.definition::jsonb, d.pii_level, d.state_part
FROM analysis_environments e
CROSS JOIN (VALUES
 (
   'CRASHES_BY_STATE',
   'Crashes by State',
   'CCFP Aggregated Data shared into the Analysis Environment: crash counts, fatalities and vehicles by State.',
   'AGGREGATED_SNAPSHOT',
   '{"dimensions":["state_code"],"measures":["crash_count","sum_fatalities","sum_vehicles"],"filters":[]}',
   'NO_PII',
   TRUE
 ),
 (
   'FATALITIES_BY_STATE_YEAR',
   'Fatalities by State and year',
   'Derived view: fatality counts and per-crash averages by State and crash year, for trend analysis.',
   'DERIVED_VIEW',
   '{"dimensions":["state_code","crash_year"],"measures":["crash_count","sum_fatalities","avg_fatalities"],"filters":[]}',
   'NO_PII',
   TRUE
 ),
 (
   'LIFECYCLE_PHASE_SUMMARY',
   'Program progress by lifecycle phase',
   'De-identified summary: how many crash records sit in each lifecycle phase. Cleared for public release.',
   'DERIVED_VIEW',
   '{"dimensions":["lifecycle_phase"],"measures":["crash_count"],"filters":[]}',
   'DEIDENTIFIED_SUMMARY',
   FALSE
 ),
 (
   'COUNTY_SMALL_CELL_DETAIL',
   'County-level detail (restricted)',
   'County-level counts over a fatal-crash population. Small cells are re-identifiable, so this is '
   'classified PII and may not be shared with States or the public.',
   'DERIVED_VIEW',
   '{"dimensions":["state_code","county"],"measures":["crash_count","sum_fatalities","max_fatalities"],"filters":[]}',
   'PII',
   TRUE
 )
) AS d(code, name, description, kind, definition, pii_level, state_part)
WHERE e.code = 'CCFP_AE'
ON CONFLICT (environment_id, code) DO NOTHING;

-- ---------------------------------------------------------------------------
-- Shares — the BRD's four audiences.
--
-- Every row below is legal under analysis_shares_enforce_pii(). Adding a
-- PARTICIPATING_STATE or PUBLIC share for COUNTY_SMALL_CELL_DETAIL here would
-- abort this seed, which is the intended behaviour: the guard applies to seed
-- files exactly as it applies to the API.
-- ---------------------------------------------------------------------------
INSERT INTO analysis_shares (dataset_id, audience, state_code, refresh_cadence, note)
SELECT ds.id, s.audience, s.state_code, s.cadence, s.note
FROM analysis_datasets ds
JOIN analysis_environments e ON e.id = ds.environment_id AND e.code = 'CCFP_AE'
JOIN (VALUES
 -- Full Aggregated Data view for FMCSA and other Federal partners (BTS/NHTSA/NTSB).
 ('CRASHES_BY_STATE',         'FMCSA_FEDERAL',       NULL, 'DAILY', 'CCFP Project Team and FMCSA HQ.'),
 ('CRASHES_BY_STATE',         'OTHER_FEDERAL',       NULL, 'DAILY', 'BTS, NHTSA and NTSB.'),
 -- State-specific, no PII. Each State sees only its own rows at query time.
 ('CRASHES_BY_STATE',         'PARTICIPATING_STATE', 'KS', 'DAILY', 'Kansas participating-State share.'),
 ('CRASHES_BY_STATE',         'PARTICIPATING_STATE', 'TX', 'DAILY', 'Texas participating-State share.'),
 ('FATALITIES_BY_STATE_YEAR', 'FMCSA_FEDERAL',       NULL, 'DAILY', 'Trend analysis for the CCFP Project Team.'),
 ('FATALITIES_BY_STATE_YEAR', 'PARTICIPATING_STATE', 'KS', 'DAILY', 'Kansas trend view.'),
 -- Summary de-identified data only — the sole dataset cleared for the public.
 ('LIFECYCLE_PHASE_SUMMARY',  'FMCSA_FEDERAL',       NULL, 'DAILY', 'Internal program-progress view.'),
 ('LIFECYCLE_PHASE_SUMMARY',  'PUBLIC',              NULL, 'DAILY', 'Published to the public outputs page.'),
 -- PII: Federal only. The trigger refuses anything wider.
 ('COUNTY_SMALL_CELL_DETAIL', 'FMCSA_FEDERAL',       NULL, 'DAILY', 'Restricted: re-identifiable small cells.')
) AS s(dataset_code, audience, state_code, cadence, note)
  ON s.dataset_code = ds.code
ON CONFLICT DO NOTHING;
