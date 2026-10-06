-- =============================================================================
-- Seed 0009 - ELD global default mappings (RECO-5)
-- ALL data is synthetic / dev-test-demo only.
-- =============================================================================
-- Reproduces the CURRENT parser (app/workers/tasks.py) as the GLOBAL DEFAULT
-- (study_id = NULL, provider = NULL) so existing CSVs parse identically once the
-- parser reads its mapping from configuration:
--   * eld_duty_code_mappings  <- _DUTY_MAP (each source_code -> canonical_duty).
--   * eld_field_mappings      <- the inline header alias lists in parse_eld_file
--                                (each canonical_field -> each source_header).
-- These tables carry no UNIQUE constraint, so each INSERT is guarded with a
-- NOT EXISTS predicate to stay idempotent across re-runs.
-- =============================================================================

-- ---------------------------------------------------------------------------
-- Duty-status code map (mirrors tasks._DUTY_MAP).
-- ---------------------------------------------------------------------------
INSERT INTO eld_duty_code_mappings (study_id, provider, source_code, canonical_duty)
SELECT NULL, NULL, m.source_code, m.canonical_duty
FROM (VALUES
 ('off_duty','OFF_DUTY'),
 ('off','OFF_DUTY'),
 ('sleeper','SLEEPER_BERTH'),
 ('sleeper_berth','SLEEPER_BERTH'),
 ('sb','SLEEPER_BERTH'),
 ('driving','DRIVING'),
 ('d','DRIVING'),
 ('on_duty','ON_DUTY_NOT_DRIVING'),
 ('on_duty_not_driving','ON_DUTY_NOT_DRIVING'),
 ('on','ON_DUTY_NOT_DRIVING')
) AS m(source_code, canonical_duty)
WHERE NOT EXISTS (
    SELECT 1 FROM eld_duty_code_mappings d
    WHERE d.study_id IS NULL AND d.provider IS NULL
      AND d.source_code = m.source_code
      AND d.canonical_duty = m.canonical_duty
);

-- ---------------------------------------------------------------------------
-- Header -> canonical-field aliases (mirrors the inline lookups in
-- parse_eld_file). Headers are stored normalized (lowercase/underscored), the
-- same shape tasks._norm produces before lookup.
-- ---------------------------------------------------------------------------
INSERT INTO eld_field_mappings (study_id, provider, canonical_field, source_header, priority)
SELECT NULL, NULL, m.canonical_field, m.source_header, 0
FROM (VALUES
 ('event_sequence','sequence'),
 ('event_sequence','event_sequence'),
 ('event_timestamp','timestamp'),
 ('event_timestamp','event_timestamp'),
 ('duty','duty'),
 ('duty','duty_status'),
 ('event_type','event_type'),
 ('event_type','type'),
 ('location','location'),
 ('latitude','latitude'),
 ('latitude','lat'),
 ('latitude','gps_lat'),
 ('longitude','longitude'),
 ('longitude','lon'),
 ('longitude','lng'),
 ('longitude','long'),
 ('longitude','gps_lng'),
 ('longitude','gps_lon'),
 ('miles_driven','miles_driven'),
 ('miles_driven','miles'),
 ('engine_hours','engine_hours'),
 ('ignition_status','ignition_status'),
 ('ignition_status','ignition')
) AS m(canonical_field, source_header)
WHERE NOT EXISTS (
    SELECT 1 FROM eld_field_mappings f
    WHERE f.study_id IS NULL AND f.provider IS NULL
      AND f.canonical_field = m.canonical_field
      AND f.source_header = m.source_header
);
