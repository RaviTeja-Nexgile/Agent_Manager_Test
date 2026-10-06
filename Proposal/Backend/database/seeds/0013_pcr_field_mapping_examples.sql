-- =============================================================================
-- Seed 0013 - example KS PCR field mappings (PCR-1)
-- ALL data is synthetic / dev-test-demo only.
-- =============================================================================
-- A couple of example State-field -> CCFP-attribute mappings on the seeded KS
-- PCR (pcr_number 'KS-PCR-2026-558210', crash CCFP-2026-KS-000101) so the
-- "Map fields" UI shows data out of the box. The PCR is resolved by its
-- pcr_number and each attribute by its code, so no generated UUIDs are hardcoded.
--
-- Idempotent: each INSERT is guarded with NOT EXISTS (the table's
-- UNIQUE(pcr_id, attribute_id) would also reject a duplicate on re-run).
-- =============================================================================

INSERT INTO pcr_field_mapping (pcr_id, state_field_name, state_field_position, attribute_id, notes, mapped_by)
SELECT pcr.id, m.state_field_name, m.state_field_position, da.id, m.notes,
       (SELECT id FROM users WHERE email = 'victor.delacruz@ccfp.gov')
FROM (VALUES
 ('ACCIDENT_KEY',   'Page 1, Box 1',  'C01', 'KARS primary crash key maps to the CCFP crash identifier.'),
 ('ACCIDENT_DATE',  'Page 1, Box 3',  'C03', 'KARS crash date/time field.'),
 ('COUNTY_NAME',    'Page 1, Box 7',  'C04', 'KARS county-of-crash field.')
) AS m(state_field_name, state_field_position, attribute_code, notes)
JOIN police_crash_reports pcr ON pcr.pcr_number = 'KS-PCR-2026-558210'
JOIN data_attributes da ON da.code = m.attribute_code
WHERE NOT EXISTS (
    SELECT 1 FROM pcr_field_mapping x
    WHERE x.pcr_id = pcr.id AND x.attribute_id = da.id
);
