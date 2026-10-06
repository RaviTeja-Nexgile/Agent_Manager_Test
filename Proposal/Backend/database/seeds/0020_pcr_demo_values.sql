-- =============================================================================
-- Seed 0020 - Demonstration PCR values across repeating units
-- ALL data is synthetic / dev-test-demo only. No real PII.
-- =============================================================================
-- The PCR gap work (GAP-PCR-02/-03/-04) gave the model the ability to express
-- per-vehicle, per-person and per-trailer values with selection caps — but the
-- demo database had almost no `crash_attribute_values` at all: 6 crashes out of
-- 45 held any value, and the only per-unit rows anywhere were ad-hoc ones
-- written during verification. So the Aggregated Data tab rendered EMPTY on
-- essentially every crash, which reads as "the feature does not work" rather
-- than "there is nothing to show".
--
-- This populates three crashes — one per participating State — with a coherent
-- heavy-duty-truck record: a tractor with two trailers, a passenger vehicle,
-- the people involved, and the crash-level conditions. Chosen so the reader
-- sees the SHAPE the new form describes: whole sections repeating per unit.
--
-- Every value respects the model the earlier migrations put in place:
--   * unit_type/unit_number are set together and match the attribute's own
--     `repeats_on` (a DB CHECK enforces the pairing; set_attribute enforces the
--     match), so nothing here could be written through the API either.
--   * Capped attributes stay within `max_selections` — C11 weather ≤3,
--     C12 light =1, C13 surface ≤3, V19 damage ≤3, P07 seating ≤2.
--   * Coded values reuse the labels seeded into `ref_attribute_values` where a
--     catalog exists (C19, V08, V19), so the demo data and the data dictionary
--     agree rather than drifting apart.
--
-- Idempotent via NOT EXISTS on the same key the partial unique index uses.
-- =============================================================================

WITH v(ident, code, unit_type, unit_number, value_text, value_json) AS (VALUES
  -- ═══ CCFP-2026-KS-000105 · tractor + 2 trailers vs passenger car ═══════════
  ('CCFP-2026-KS-000105','C11',  NULL,     NULL, NULL,                       '["Rain","Fog"]'),
  ('CCFP-2026-KS-000105','C12',  NULL,     NULL, NULL,                       '["Dark - Lighted"]'),
  ('CCFP-2026-KS-000105','C13',  NULL,     NULL, NULL,                       '["Wet"]'),
  ('CCFP-2026-KS-000105','C19',  NULL,     NULL, 'Fatal Injury',             NULL),
  ('CCFP-2026-KS-000105','C24',  NULL,     NULL, '1',                        NULL),
  ('CCFP-2026-KS-000105','C31',  NULL,     NULL, 'A combination truck and a passenger vehicle collided at a rural junction during evening rain. One person died at the scene.', NULL),
  ('CCFP-2026-KS-000105','LV07', NULL,     NULL, 'US DOT 2214477',           NULL),
  -- vehicle 1: the CMV tractor
  ('CCFP-2026-KS-000105','V01',  'VEHICLE', 1,   '1XKAD49X2MJ371882',        NULL),
  ('CCFP-2026-KS-000105','V05',  'VEHICLE', 1,   'Kenworth',                 NULL),
  ('CCFP-2026-KS-000105','V06',  'VEHICLE', 1,   '2021',                     NULL),
  ('CCFP-2026-KS-000105','V08',  'VEHICLE', 1,   'Truck Tractor',            NULL),
  ('CCFP-2026-KS-000105','V19',  'VEHICLE', 1,   NULL,                       '["Undercarriage"]'),
  ('CCFP-2026-KS-000105','V29',  'VEHICLE', 1,   '80000',                    NULL),
  ('CCFP-2026-KS-000105','V30',  'VEHICLE', 1,   'true',                     NULL),
  ('CCFP-2026-KS-000105','LV16', 'VEHICLE', 1,   'Loaded',                   NULL),
  -- vehicle 2: the passenger car
  ('CCFP-2026-KS-000105','V01',  'VEHICLE', 2,   '2HGFC2F59MH553104',        NULL),
  ('CCFP-2026-KS-000105','V05',  'VEHICLE', 2,   'Honda',                    NULL),
  ('CCFP-2026-KS-000105','V06',  'VEHICLE', 2,   '2019',                     NULL),
  ('CCFP-2026-KS-000105','V08',  'VEHICLE', 2,   'Passenger Car',            NULL),
  ('CCFP-2026-KS-000105','V29',  'VEHICLE', 2,   '4200',                     NULL),
  ('CCFP-2026-KS-000105','V30',  'VEHICLE', 2,   'false',                    NULL),
  -- trailers 1 and 2 on the tractor
  ('CCFP-2026-KS-000105','LV02', 'TRAILER', 1,   'KS-TRL-4471',              NULL),
  ('CCFP-2026-KS-000105','LV03', 'TRAILER', 1,   '1JJV532W1PL118401',        NULL),
  ('CCFP-2026-KS-000105','LV06', 'TRAILER', 1,   '2019',                     NULL),
  ('CCFP-2026-KS-000105','LV12', 'TRAILER', 1,   'Prairie Line Leasing LLC', NULL),
  ('CCFP-2026-KS-000105','LV02', 'TRAILER', 2,   'KS-TRL-8820',              NULL),
  ('CCFP-2026-KS-000105','LV03', 'TRAILER', 2,   '1GRAA0620XW102338',        NULL),
  ('CCFP-2026-KS-000105','LV06', 'TRAILER', 2,   '2021',                     NULL),
  ('CCFP-2026-KS-000105','LV12', 'TRAILER', 2,   'Prairie Line Leasing LLC', NULL),
  -- people
  ('CCFP-2026-KS-000105','P01',  'PERSON',  1,   'Alvarez, Marisol',         NULL),
  ('CCFP-2026-KS-000105','P04',  'PERSON',  1,   'Driver',                   NULL),
  ('CCFP-2026-KS-000105','P05',  'PERSON',  1,   'No Injury',                NULL),
  ('CCFP-2026-KS-000105','P07',  'PERSON',  1,   NULL,                       '["Front Left"]'),
  ('CCFP-2026-KS-000105','P01',  'PERSON',  2,   'Whitcombe, Reginald',      NULL),
  ('CCFP-2026-KS-000105','P04',  'PERSON',  2,   'Driver',                   NULL),
  ('CCFP-2026-KS-000105','P05',  'PERSON',  2,   'Fatal',                    NULL),
  ('CCFP-2026-KS-000105','P34',  'PERSON',  2,   'Fatal',                    NULL),
  ('CCFP-2026-KS-000105','P07',  'PERSON',  2,   NULL,                       '["Front Left"]'),
  ('CCFP-2026-KS-000105','P01',  'PERSON',  3,   'Whitcombe, Delia',         NULL),
  ('CCFP-2026-KS-000105','P04',  'PERSON',  3,   'Occupant',                 NULL),
  ('CCFP-2026-KS-000105','P05',  'PERSON',  3,   'Injury',                   NULL),
  ('CCFP-2026-KS-000105','P34',  'PERSON',  3,   'Serious',                  NULL),
  ('CCFP-2026-KS-000105','P07',  'PERSON',  3,   NULL,                       '["Front Right"]'),

  -- ═══ CCFP-2026-CA-000115 · 3 vehicles, single trailer ══════════════════════
  ('CCFP-2026-CA-000115','C11',  NULL,     NULL, NULL,                       '["Clear"]'),
  ('CCFP-2026-CA-000115','C12',  NULL,     NULL, NULL,                       '["Daylight"]'),
  ('CCFP-2026-CA-000115','C13',  NULL,     NULL, NULL,                       '["Dry"]'),
  ('CCFP-2026-CA-000115','C19',  NULL,     NULL, 'Fatal Injury',             NULL),
  ('CCFP-2026-CA-000115','C24',  NULL,     NULL, '2',                        NULL),
  ('CCFP-2026-CA-000115','C31',  NULL,     NULL, 'A multi-vehicle collision involving a combination truck occurred on an interstate in clear daylight conditions.', NULL),
  ('CCFP-2026-CA-000115','V01',  'VEHICLE', 1,   '3AKJHHDR9LSLP4021',        NULL),
  ('CCFP-2026-CA-000115','V05',  'VEHICLE', 1,   'Freightliner',             NULL),
  ('CCFP-2026-CA-000115','V06',  'VEHICLE', 1,   '2020',                     NULL),
  ('CCFP-2026-CA-000115','V08',  'VEHICLE', 1,   'Truck Tractor',            NULL),
  ('CCFP-2026-CA-000115','V29',  'VEHICLE', 1,   '79500',                    NULL),
  ('CCFP-2026-CA-000115','V30',  'VEHICLE', 1,   'true',                     NULL),
  ('CCFP-2026-CA-000115','LV16', 'VEHICLE', 1,   'Partially Loaded',         NULL),
  ('CCFP-2026-CA-000115','V01',  'VEHICLE', 2,   '5TDZA23C13S012947',        NULL),
  ('CCFP-2026-CA-000115','V05',  'VEHICLE', 2,   'Toyota',                   NULL),
  ('CCFP-2026-CA-000115','V08',  'VEHICLE', 2,   'Passenger Car',            NULL),
  ('CCFP-2026-CA-000115','V30',  'VEHICLE', 2,   'false',                    NULL),
  ('CCFP-2026-CA-000115','V01',  'VEHICLE', 3,   '1FTFW1ET5DFC10312',        NULL),
  ('CCFP-2026-CA-000115','V05',  'VEHICLE', 3,   'Ford',                     NULL),
  ('CCFP-2026-CA-000115','V08',  'VEHICLE', 3,   'Single-Unit Truck',        NULL),
  ('CCFP-2026-CA-000115','V30',  'VEHICLE', 3,   'false',                    NULL),
  ('CCFP-2026-CA-000115','LV02', 'TRAILER', 1,   'CA-TRL-2290',              NULL),
  ('CCFP-2026-CA-000115','LV03', 'TRAILER', 1,   '1UYVS2530M2298744',        NULL),
  ('CCFP-2026-CA-000115','LV06', 'TRAILER', 1,   '2021',                     NULL),
  ('CCFP-2026-CA-000115','LV12', 'TRAILER', 1,   'Golden State Haulage Inc', NULL),
  ('CCFP-2026-CA-000115','P01',  'PERSON',  1,   'Okonkwo, Chidiebere',      NULL),
  ('CCFP-2026-CA-000115','P04',  'PERSON',  1,   'Driver',                   NULL),
  ('CCFP-2026-CA-000115','P05',  'PERSON',  1,   'No Injury',                NULL),
  ('CCFP-2026-CA-000115','P01',  'PERSON',  2,   'Bergström, Annika',        NULL),
  ('CCFP-2026-CA-000115','P04',  'PERSON',  2,   'Driver',                   NULL),
  ('CCFP-2026-CA-000115','P05',  'PERSON',  2,   'Fatal',                    NULL),
  ('CCFP-2026-CA-000115','P34',  'PERSON',  2,   'Fatal',                    NULL),

  -- ═══ CCFP-2026-TX-000109 · tractor + 3 trailers (Rocky Mountain double) ════
  ('CCFP-2026-TX-000109','C11',  NULL,     NULL, NULL,                       '["Clear","Wind"]'),
  ('CCFP-2026-TX-000109','C12',  NULL,     NULL, NULL,                       '["Dawn"]'),
  ('CCFP-2026-TX-000109','C19',  NULL,     NULL, 'Fatal Injury',             NULL),
  ('CCFP-2026-TX-000109','C24',  NULL,     NULL, '1',                        NULL),
  ('CCFP-2026-TX-000109','C31',  NULL,     NULL, 'A combination vehicle departed the roadway at dawn in high wind. One fatality was reported.', NULL),
  ('CCFP-2026-TX-000109','V01',  'VEHICLE', 1,   '1XPBDP9X1MD742119',        NULL),
  ('CCFP-2026-TX-000109','V05',  'VEHICLE', 1,   'Peterbilt',                NULL),
  ('CCFP-2026-TX-000109','V08',  'VEHICLE', 1,   'Truck Tractor',            NULL),
  ('CCFP-2026-TX-000109','V19',  'VEHICLE', 1,   NULL,                       '["Undercarriage"]'),
  ('CCFP-2026-TX-000109','V29',  'VEHICLE', 1,   '80000',                    NULL),
  ('CCFP-2026-TX-000109','V30',  'VEHICLE', 1,   'true',                     NULL),
  ('CCFP-2026-TX-000109','LV02', 'TRAILER', 1,   'TX-TRL-5512',              NULL),
  ('CCFP-2026-TX-000109','LV06', 'TRAILER', 1,   '2018',                     NULL),
  ('CCFP-2026-TX-000109','LV02', 'TRAILER', 2,   'TX-TRL-5513',              NULL),
  ('CCFP-2026-TX-000109','LV06', 'TRAILER', 2,   '2018',                     NULL),
  ('CCFP-2026-TX-000109','LV02', 'TRAILER', 3,   'TX-TRL-5514',              NULL),
  ('CCFP-2026-TX-000109','LV06', 'TRAILER', 3,   '2020',                     NULL),
  ('CCFP-2026-TX-000109','P01',  'PERSON',  1,   'Nakamura, Haruki',         NULL),
  ('CCFP-2026-TX-000109','P04',  'PERSON',  1,   'Driver',                   NULL),
  ('CCFP-2026-TX-000109','P05',  'PERSON',  1,   'Fatal',                    NULL),
  ('CCFP-2026-TX-000109','P34',  'PERSON',  1,   'Fatal',                    NULL)
)
INSERT INTO crash_attribute_values
    (crash_id, attribute_id, unit_type, unit_number, value_text, value_json,
     source_system, confidence, is_current, is_edited)
SELECT c.id, da.id, v.unit_type, v.unit_number, v.value_text, v.value_json::jsonb,
       'PCR', 95, TRUE, FALSE
  FROM v
  JOIN crashes c ON c.ccfp_identifier = v.ident
  JOIN data_attributes da ON da.code = v.code AND da.is_active
 WHERE NOT EXISTS (
        SELECT 1 FROM crash_attribute_values x
         WHERE x.crash_id = c.id AND x.attribute_id = da.id AND x.is_current
           AND coalesce(x.unit_type,'') = coalesce(v.unit_type,'')
           AND coalesce(x.unit_number,0) = coalesce(v.unit_number,0));

-- ---------------------------------------------------------------------------
-- Coverage rows for the OTHER participating States. Only KS had rows, so the
-- PCR Coverage report showed a single State however many were onboarded.
-- Counts stay 0: they record what a STATE REPORTS, which only the State can
-- state (GAP-PCR-05). The GET endpoint derives live figures separately.
-- ---------------------------------------------------------------------------
INSERT INTO state_pcr_coverage (study_id, state_code, pcr_section_code, spec_version)
SELECT ss.study_id, ss.state_code, s.code, 'HDTS-PCR-2026'
  FROM study_states ss
  JOIN studies st ON st.id = ss.study_id AND st.code = 'PHASE1-HDT'
  CROSS JOIN ref_pcr_sections s
 WHERE ss.is_participating AND s.is_active
ON CONFLICT (study_id, state_code, pcr_section_code) DO NOTHING;

-- ---------------------------------------------------------------------------
-- Guards: fail loudly rather than seeding a half-populated demo.
-- ---------------------------------------------------------------------------
DO $$
DECLARE n INT;
BEGIN
    SELECT count(DISTINCT crash_id) INTO n
      FROM crash_attribute_values WHERE unit_type IS NOT NULL AND is_current;
    IF n < 3 THEN
        RAISE EXCEPTION 'demo seed: expected per-unit values on at least 3 crashes, got %', n;
    END IF;

    -- No stored value may exceed its attribute's cap.
    SELECT count(*) INTO n
      FROM crash_attribute_values cav JOIN data_attributes da ON da.id = cav.attribute_id
     WHERE cav.is_current AND da.max_selections IS NOT NULL
       AND jsonb_typeof(cav.value_json) = 'array'
       AND jsonb_array_length(cav.value_json) > da.max_selections;
    IF n > 0 THEN
        RAISE EXCEPTION 'demo seed: % value(s) exceed their selection cap', n;
    END IF;

    -- Every value's unit must agree with its attribute's declaration.
    SELECT count(*) INTO n
      FROM crash_attribute_values cav JOIN data_attributes da ON da.id = cav.attribute_id
     WHERE cav.is_current AND (da.repeats_on IS NULL) <> (cav.unit_type IS NULL);
    IF n > 0 THEN
        RAISE EXCEPTION 'demo seed: % value(s) disagree with data_attributes.repeats_on', n;
    END IF;
END $$;
