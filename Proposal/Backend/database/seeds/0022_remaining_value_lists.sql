-- =============================================================================
-- Seed 0022 - Remaining GAP-PCR-09b value-list changes
-- ALL data is synthetic / dev-test-demo only.
-- =============================================================================
-- Seed 0019 covered 7 of the elements the gap analysis enumerates under
-- "Value-list removals and narrowings within retained elements". This closes
-- the rest.
--
-- The gap's table has 13 rows, but they are not all the same KIND of change:
--
--   VALUE changes (need a catalog — seeded here)
--     C03  date decomposition collapsed into a single Date (MM/DD/YY) field
--     C14  "Obstructed Crosswalks" removed; "Animal(s)" respelled "Animals"
--     P16  the "Restriction Compliance?" sub-attribute removed
--     V24  four motor-vehicle circumstances collapsed to three
--     VX1  "Owner Type" removed
--
--   CARDINALITY-ONLY changes (no value list to re-derive — already done)
--     C11  weather cap widened 2 -> 3          -> GAP-PCR-04, seed 0016
--     PX1  Citation Number cap removed          -> GAP-PCR-04; P38 carries no cap
--          and Violations (P15) is capped at 5, which is the actual change
--
-- The second group is deliberately NOT given a catalog. Seeding one would mean
-- inventing an enumerated vocabulary the source documents never state — the
-- same reason seed 0019 stopped at the elements the gap names. A missing
-- catalog is honest; a fabricated one is worse than nothing.
--
-- Idempotent: ON CONFLICT (attribute_id, label) DO NOTHING.
-- =============================================================================

INSERT INTO ref_attribute_values (attribute_id, code, label, sort_order, is_active, spec_version, notes)
SELECT da.id, v.code, v.label, v.sort_order, v.is_active, v.spec_version, v.notes
FROM data_attributes da
JOIN (VALUES
 -- ===== C03 Crash date and time ============================================
 -- The old worksheet decomposed the date into three fields; the new form
 -- collapses them into one. Time Zone survives unchanged.
 ('C03','DT_DATE',       'Date (MM/DD/YY)',  1, TRUE,  'HDTS-PCR-2026', NULL),
 ('C03','DT_TIMEZONE',   'Time Zone',        2, TRUE,  'HDTS-PCR-2026', 'Retained unchanged by the HDTS PCR data form.'),
 ('C03','DT_DAY',        'Day (DD)',         3, FALSE, 'KS-WORKSHEET-2025', 'Collapsed into the single Date (MM/DD/YY) field.'),
 ('C03','DT_MONTH',      'Month (MM)',       4, FALSE, 'KS-WORKSHEET-2025', 'Collapsed into the single Date (MM/DD/YY) field.'),
 ('C03','DT_YEAR',       'Year (YYYY)',      5, FALSE, 'KS-WORKSHEET-2025', 'Collapsed into the single Date (MM/DD/YY) field.'),

 -- ===== C14 Roadway contributing circumstances =============================
 ('C14','RCC_ANIMALS',   'Animals',                 1, TRUE,  'HDTS-PCR-2026',
   'Respelled from the old "Animal(s)".'),
 ('C14','RCC_ANIMALS_OLD','Animal(s)',              2, FALSE, 'KS-WORKSHEET-2025',
   'Respelled to "Animals" by the HDTS PCR data form.'),
 ('C14','RCC_CROSSWALK', 'Obstructed Crosswalks',   3, FALSE, 'KS-WORKSHEET-2025',
   'Removed by the HDTS PCR data form; no replacement value.'),

 -- ===== P16 Driver license restrictions ====================================
 ('P16','DLR_COMPLIANCE','Restriction Compliance?', 1, FALSE, 'KS-WORKSHEET-2025',
   'Sub-attribute removed by the HDTS PCR data form; restrictions are now recorded without a separate compliance flag.'),

 -- ===== V24 Contributing circumstances, motor vehicle ======================
 -- Four failure-mode values collapse to three broader ones.
 ('V24','VCC_ACCELERATOR','Accelerator',                     1, TRUE,  'HDTS-PCR-2026', NULL),
 ('V24','VCC_ENGINE',     'Engine',                          2, TRUE,  'HDTS-PCR-2026', NULL),
 ('V24','VCC_MECHANICAL', 'Mechanical',                      3, TRUE,  'HDTS-PCR-2026', NULL),
 ('V24','VCC_ACCEL_OLD',  'Accelerator Failure or Defective',4, FALSE, 'KS-WORKSHEET-2025',
   'Collapsed into "Accelerator" by the HDTS PCR data form.'),
 ('V24','VCC_ENGFAIL_OLD','Engine Failure',                  5, FALSE, 'KS-WORKSHEET-2025',
   'Collapsed into "Engine" by the HDTS PCR data form.'),
 ('V24','VCC_ENGTROU_OLD','Engine Trouble',                  6, FALSE, 'KS-WORKSHEET-2025',
   'Collapsed into "Engine" by the HDTS PCR data form.'),
 ('V24','VCC_MECHFAIL_OLD','Mechanical Failure',             7, FALSE, 'KS-WORKSHEET-2025',
   'Collapsed into "Mechanical" by the HDTS PCR data form.'),

 -- ===== VX1 Vehicle owner ==================================================
 ('VX1','VO_OWNER_TYPE', 'Owner Type',              1, FALSE, 'KS-WORKSHEET-2025',
   'Removed by the HDTS PCR data form; no replacement value.')
) AS v(attr_code, code, label, sort_order, is_active, spec_version, notes)
  ON v.attr_code = da.code
ON CONFLICT (attribute_id, label) DO NOTHING;

-- ---------------------------------------------------------------------------
-- Point each collapsed/respelled value at its replacement so a historical value
-- can be followed forward. Second pass: the replacements must exist first.
-- ---------------------------------------------------------------------------
UPDATE ref_attribute_values old
   SET superseded_by_id = new.id
  FROM ref_attribute_values new
 WHERE old.attribute_id = new.attribute_id
   AND new.is_active
   AND (old.code, new.code) IN (
        ('DT_DAY','DT_DATE'), ('DT_MONTH','DT_DATE'), ('DT_YEAR','DT_DATE'),
        ('RCC_ANIMALS_OLD','RCC_ANIMALS'),
        ('VCC_ACCEL_OLD','VCC_ACCELERATOR'),
        ('VCC_ENGFAIL_OLD','VCC_ENGINE'), ('VCC_ENGTROU_OLD','VCC_ENGINE'),
        ('VCC_MECHFAIL_OLD','VCC_MECHANICAL')
   );

-- ---------------------------------------------------------------------------
-- Guards.
-- ---------------------------------------------------------------------------
DO $$
DECLARE missing TEXT; n INT;
BEGIN
    -- Every element the gap names as having a VALUE change must now have a catalog.
    SELECT string_agg(c, ', ') INTO missing
      FROM unnest(ARRAY['C03','C14','C19','LV10','NMX1','P16','P21','P23','V08','V19','V24','VX1']) AS c
     WHERE NOT EXISTS (SELECT 1 FROM ref_attribute_values v
                         JOIN data_attributes da ON da.id = v.attribute_id
                        WHERE da.code = c);
    IF missing IS NOT NULL THEN
        RAISE EXCEPTION 'GAP-PCR-09b: element(s) still without a value catalog: %', missing;
    END IF;

    -- Every value the gap describes as COLLAPSED or RESPELLED must name where it went.
    SELECT count(*) INTO n FROM ref_attribute_values
     WHERE code IN ('DT_DAY','DT_MONTH','DT_YEAR','RCC_ANIMALS_OLD','VCC_ACCEL_OLD',
                    'VCC_ENGFAIL_OLD','VCC_ENGTROU_OLD','VCC_MECHFAIL_OLD')
       AND superseded_by_id IS NULL;
    IF n > 0 THEN
        RAISE EXCEPTION 'GAP-PCR-09b: % collapsed value(s) name no replacement', n;
    END IF;
END $$;
