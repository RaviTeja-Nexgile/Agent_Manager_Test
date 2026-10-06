-- =============================================================================
-- Seed 0021 - ELD Appendix E: FMCSA-standard mappings + upload grant
-- ALL data is synthetic / dev-test-demo only.
-- =============================================================================
-- BRD Jan-2026 Appendix E, requirement 1:
--   "Ability to allow the MCSAP CMV Inspector AND ANALYSTS ON THE CCFP PROJECT
--    TEAM to upload ELD output files to the associated crash record."
-- `eld:upload` was granted only to MCSAP_INSPECTOR and STATE_CMV_ANALYST, so a
-- CCFP Project Team analyst — named explicitly in the requirement — got a 403.
--
-- Appendix E, requirement 2 ("Ability to extract data from ELD output file so
-- the data can be analyzed"): the parser's data-driven mapping tables only knew
-- the simplified column names of a hand-built CSV. The real ELD output file
-- (49 CFR 395 Appendix A to Subpart B) names its columns "Event Sequence ID
-- Number", "Accumulated Vehicle Miles", "Elapsed Engine Hours", ... and encodes
-- duty status as the numeric event codes 1-4. Those are added here as GLOBAL
-- DEFAULTS (study_id / provider NULL) so the flat-CSV path also recognizes a
-- standard event-list export, and so an administrator can see and override the
-- standard vocabulary as data (§3.4 configurability).
--
-- The sectioned FMCSA layout itself is handled structurally in
-- app/workers/eld_format.py; these rows serve a file that carries ONLY the
-- event-list table with its standard headers.
--
-- Idempotent: every INSERT is guarded (NOT EXISTS / ON CONFLICT DO NOTHING).
-- =============================================================================

-- ---------------------------------------------------------------------------
-- BRD Appendix E: the CCFP Project Team can upload ELD output files.
-- ---------------------------------------------------------------------------
-- Read access to the extracted data already comes from source_data:read, which
-- the role holds; this adds only the upload/reparse capability the requirement
-- names. SYSTEM_ADMIN already holds every permission via seed 0002's CROSS JOIN.
INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id
FROM roles r
JOIN permissions p ON p.code = 'eld:upload'
WHERE r.code = 'CCFP_PROJECT_TEAM'
ON CONFLICT DO NOTHING;

-- Re-run the blanket SYSTEM_ADMIN grant so the System Administrator keeps every
-- permission even if one was added after seed 0002 ran (cheap drift guard).
INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id FROM roles r CROSS JOIN permissions p
WHERE r.code = 'SYSTEM_ADMIN'
ON CONFLICT DO NOTHING;

-- ---------------------------------------------------------------------------
-- Duty-status abbreviations used by vendor exports.
-- ---------------------------------------------------------------------------
-- The standard's NUMERIC duty codes (Event Type 1 with Event Code 1 = off duty,
-- 2 = sleeper berth, 3 = driving, 4 = on duty not driving) are deliberately NOT
-- seeded here. Those digits only mean a duty status *in the context of event
-- type 1* — under event type 3 a code of 1 means personal conveyance, under
-- type 6 it means engine power-up. app/workers/eld_format.py therefore resolves
-- them structurally, with the event type in hand. Seeding a bare '3' -> DRIVING
-- global default would misread every other event type's code column.
--
-- What IS safe to map as data are the unambiguous textual abbreviations.
INSERT INTO eld_duty_code_mappings (study_id, provider, source_code, canonical_duty)
SELECT NULL, NULL, m.source_code, m.canonical_duty
FROM (VALUES
 ('od','OFF_DUTY'),
 ('off_duty_not_driving','OFF_DUTY'),
 ('sb','SLEEPER_BERTH'),
 ('sleeper_berth_resting','SLEEPER_BERTH'),
 ('dr','DRIVING'),
 ('drive','DRIVING'),
 ('driving_cmv','DRIVING'),
 ('on','ON_DUTY_NOT_DRIVING'),
 ('onduty','ON_DUTY_NOT_DRIVING'),
 ('on_duty_nd','ON_DUTY_NOT_DRIVING'),
 ('ond','ON_DUTY_NOT_DRIVING'),
 -- Personal conveyance is recorded off duty; a yard move is on-duty not driving.
 ('pc','OFF_DUTY'),
 ('personal_conveyance','OFF_DUTY'),
 ('ym','ON_DUTY_NOT_DRIVING'),
 ('yard_move','ON_DUTY_NOT_DRIVING'),
 ('yard_moves','ON_DUTY_NOT_DRIVING')
) AS m(source_code, canonical_duty)
WHERE NOT EXISTS (
    SELECT 1 FROM eld_duty_code_mappings d
    WHERE d.study_id IS NULL AND d.provider IS NULL
      AND d.source_code = m.source_code
);

-- ---------------------------------------------------------------------------
-- ELD output-file column names -> canonical fields.
-- ---------------------------------------------------------------------------
-- Headers are stored NORMALIZED (lowercase, non-alphanumeric runs collapsed to
-- '_'), which is the shape app/workers/eld_format.norm produces before lookup —
-- so "Accumulated Vehicle Miles" is stored as accumulated_vehicle_miles.
-- priority 5 keeps these above the seed-0009 simplified defaults (priority 0)
-- without displacing a study/provider-specific override, which scores higher on
-- specificity regardless of priority.
INSERT INTO eld_field_mappings (study_id, provider, canonical_field, source_header, priority)
SELECT NULL, NULL, m.canonical_field, m.source_header, 5
FROM (VALUES
 ('event_sequence','event_sequence_id_number'),
 ('event_sequence','event_sequence_id'),
 ('event_sequence','sequence_number'),
 ('event_sequence','seq_no'),
 ('event_timestamp','event_timestamp'),
 ('event_timestamp','date_time'),
 ('duty','duty_status_code'),
 ('duty','driver_status'),
 ('event_type','event_type'),
 ('location','event_location_description'),
 ('location','location_description'),
 ('location','geo_location'),
 ('latitude','event_latitude'),
 ('longitude','event_longitude'),
 ('miles_driven','accumulated_vehicle_miles'),
 ('miles_driven','total_vehicle_miles'),
 ('miles_driven','vehicle_miles'),
 ('miles_driven','odometer'),
 ('engine_hours','elapsed_engine_hours'),
 ('engine_hours','total_engine_hours'),
 ('ignition_status','power_state')
) AS m(canonical_field, source_header)
WHERE NOT EXISTS (
    SELECT 1 FROM eld_field_mappings f
    WHERE f.study_id IS NULL AND f.provider IS NULL
      AND f.canonical_field = m.canonical_field
      AND f.source_header = m.source_header
);
