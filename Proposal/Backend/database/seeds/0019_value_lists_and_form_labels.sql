-- =============================================================================
-- Seed 0019 - Value lists + form-label traceability (GAP-PCR-09b, GAP-PCR-09)
-- ALL data is synthetic / dev-test-demo only.
-- =============================================================================
-- Part A (GAP-PCR-09b) seeds the enumerated value lists the gap analysis names
-- as having CHANGED, in their NEW form -- and records the removed/collapsed old
-- values as RETIRED rows rather than omitting them, so a historical
-- crash_attribute_values row written under the old specification still resolves
-- to a label and can be followed forward to its replacement.
--
-- Only the elements the gap analysis explicitly enumerates are seeded. Seeding
-- a value list for all 175 attributes would be inventing vocabulary the
-- documents do not define; the catalog is built so those can be added as data
-- later, which is the point of making it a table.
--
-- Part B (GAP-PCR-09) records the exact section header and field label text as
-- printed on the form, restoring the traceability the removal of element codes
-- destroyed, and stamps the MMUCC lineage explicitly.
-- =============================================================================

-- ###########################################################################
-- PART A - Value lists (GAP-PCR-09b)
-- ###########################################################################

-- ---------------------------------------------------------------------------
-- Helper shape: (attribute code, value code, label, sort, active, notes)
-- `is_active = FALSE` rows are the values the new form removed.
-- ---------------------------------------------------------------------------
INSERT INTO ref_attribute_values (attribute_id, code, label, sort_order, is_active, spec_version, notes)
SELECT da.id, v.code, v.label, v.sort_order, v.is_active, v.spec_version, v.notes
FROM data_attributes da
JOIN (VALUES
 -- ===== C19 Crash severity =================================================
 -- The MMUCC letter prefixes (K)/(A)/(B)/(C)/(O) are dropped throughout, and
 -- "No Apparent Injury" is dropped AT CRASH LEVEL (it survives at person level
 -- under Injury Status / Injury Severity).
 ('C19','SEV_FATAL',        'Fatal Injury',                 1, TRUE,  'HDTS-PCR-2026', NULL),
 ('C19','SEV_SUSP_SERIOUS', 'Suspected Serious Injury',     2, TRUE,  'HDTS-PCR-2026', NULL),
 ('C19','SEV_SUSP_MINOR',   'Suspected Minor Injury',       3, TRUE,  'HDTS-PCR-2026', NULL),
 ('C19','SEV_POSSIBLE',     'Possible Injury',              4, TRUE,  'HDTS-PCR-2026', NULL),
 ('C19','SEV_NO_APPARENT',  'No Apparent Injury',           5, FALSE, 'KS-WORKSHEET-2025',
   'Removed at crash level by the HDTS PCR data form; retained at person level under Injury Status (P05) / Injury Severity (P34).'),

 -- ===== NMX1 Non-motorist unit type ========================================
 -- Narrowed to four values; "Unknown Type of Non-Motorist" and "Other" removed.
 ('NMX1','NMT_ANIMAL_RIDER','Animal with Rider',            1, TRUE,  'HDTS-PCR-2026', NULL),
 ('NMX1','NMT_BICYCLE',     'Bicycle',                      2, TRUE,  'HDTS-PCR-2026', NULL),
 ('NMX1','NMT_PEDALCYCLE',  'Pedalcycle',                   3, TRUE,  'HDTS-PCR-2026', NULL),
 ('NMX1','NMT_PEDESTRIAN',  'Pedestrian',                   4, TRUE,  'HDTS-PCR-2026', NULL),
 ('NMX1','NMT_UNKNOWN',     'Unknown Type of Non-Motorist', 5, FALSE, 'KS-WORKSHEET-2025',
   'Removed by the HDTS PCR data form; no replacement value.'),
 ('NMX1','NMT_OTHER',       'Other',                        6, FALSE, 'KS-WORKSHEET-2025',
   'Removed by the HDTS PCR data form; no replacement value.'),

 -- ===== LV10 Hazardous materials cargo (release) ===========================
 -- "Unknown if Released" removed; No/Yes per trailer only.
 ('LV10','HM_NO',           'No',                           1, TRUE,  'HDTS-PCR-2026', NULL),
 ('LV10','HM_YES',          'Yes',                          2, TRUE,  'HDTS-PCR-2026', NULL),
 ('LV10','HM_UNKNOWN',      'Unknown if Released',          3, FALSE, 'KS-WORKSHEET-2025',
   'Removed by the HDTS PCR data form; release is now recorded per trailer as No/Yes only.'),

 -- ===== P21 Alcohol test ===================================================
 -- "Not Applicable (Test Not Given)" and "Test given, results pending"
 -- collapse into a single "Pending".
 ('P21','ALC_NONE',         'Test Not Given',               1, TRUE,  'HDTS-PCR-2026', NULL),
 ('P21','ALC_PENDING',      'Pending',                      2, TRUE,  'HDTS-PCR-2026', NULL),
 ('P21','ALC_POSITIVE',     'Positive',                     3, TRUE,  'HDTS-PCR-2026', NULL),
 ('P21','ALC_NEGATIVE',     'Negative',                     4, TRUE,  'HDTS-PCR-2026', NULL),
 ('P21','ALC_NA_OLD',       'Not Applicable (Test Not Given)', 5, FALSE, 'KS-WORKSHEET-2025',
   'Collapsed into Pending by the HDTS PCR data form.'),
 ('P21','ALC_PENDING_OLD',  'Test given, results pending',  6, FALSE, 'KS-WORKSHEET-2025',
   'Collapsed into Pending by the HDTS PCR data form.'),

 -- ===== P23 Drug test ======================================================
 ('P23','DRG_NONE',         'Test Not Given',               1, TRUE,  'HDTS-PCR-2026', NULL),
 ('P23','DRG_PENDING',      'Pending',                      2, TRUE,  'HDTS-PCR-2026', NULL),
 ('P23','DRG_POSITIVE',     'Positive',                     3, TRUE,  'HDTS-PCR-2026', NULL),
 ('P23','DRG_NEGATIVE',     'Negative',                     4, TRUE,  'HDTS-PCR-2026', NULL),
 ('P23','DRG_NA_OLD',       'Not Applicable (Test Not Given)', 5, FALSE, 'KS-WORKSHEET-2025',
   'Collapsed into Pending by the HDTS PCR data form.'),
 ('P23','DRG_PENDING_OLD',  'Test given, results pending',  6, FALSE, 'KS-WORKSHEET-2025',
   'Collapsed into Pending by the HDTS PCR data form.'),

 -- ===== V08 Vehicle body type ==============================================
 -- "Mini-bus", "Large Limo" and "Passenger Car Type" dropped;
 -- "Limousine (Large)" added.
 ('V08','BT_PASSENGER_CAR', 'Passenger Car',                1, TRUE,  'HDTS-PCR-2026', NULL),
 ('V08','BT_LIMO_LARGE',    'Limousine (Large)',            2, TRUE,  'HDTS-PCR-2026',
   'Added by the HDTS PCR data form, replacing the old "Large Limo".'),
 ('V08','BT_TRUCK_TRACTOR', 'Truck Tractor',                3, TRUE,  'HDTS-PCR-2026', NULL),
 ('V08','BT_SINGLE_UNIT',   'Single-Unit Truck',            4, TRUE,  'HDTS-PCR-2026', NULL),
 ('V08','BT_MINIBUS',       'Mini-bus',                     5, FALSE, 'KS-WORKSHEET-2025',
   'Removed by the HDTS PCR data form.'),
 ('V08','BT_LARGE_LIMO',    'Large Limo',                   6, FALSE, 'KS-WORKSHEET-2025',
   'Renamed by the HDTS PCR data form to "Limousine (Large)".'),
 ('V08','BT_PASSENGER_TYPE','Passenger Car Type',           7, FALSE, 'KS-WORKSHEET-2025',
   'Removed by the HDTS PCR data form.'),

 -- ===== V19 Vehicle damage =================================================
 -- "Undercarriage Damaged?" (yes/no) is replaced by "Undercarriage" as one of
 -- the clock-position values.
 ('V19','DMG_UNDERCARRIAGE','Undercarriage',                13, TRUE, 'HDTS-PCR-2026',
   'Now a clock-position value rather than a separate yes/no question.'),
 ('V19','DMG_UNDER_OLD',    'Undercarriage Damaged?',       14, FALSE,'KS-WORKSHEET-2025',
   'Replaced by the "Undercarriage" clock-position value on the HDTS PCR data form.')
) AS v(attr_code, code, label, sort_order, is_active, spec_version, notes)
  ON v.attr_code = da.code
ON CONFLICT (attribute_id, label) DO NOTHING;

-- ---------------------------------------------------------------------------
-- Point each collapsed/renamed old value at its replacement, so a reader of a
-- historical value can follow it forward. Done as a second pass because the
-- replacement rows must exist first.
-- ---------------------------------------------------------------------------
UPDATE ref_attribute_values old
   SET superseded_by_id = new.id
  FROM ref_attribute_values new
 WHERE old.attribute_id = new.attribute_id
   AND new.is_active
   AND (old.code, new.code) IN (
        ('ALC_NA_OLD','ALC_PENDING'),
        ('ALC_PENDING_OLD','ALC_PENDING'),
        ('DRG_NA_OLD','DRG_PENDING'),
        ('DRG_PENDING_OLD','DRG_PENDING'),
        ('BT_LARGE_LIMO','BT_LIMO_LARGE'),
        ('DMG_UNDER_OLD','DMG_UNDERCARRIAGE')
   );

-- ---------------------------------------------------------------------------
-- The contributing-factor catalog: the new form collapses several motor-vehicle
-- circumstances. The app's seeded vocabulary is synthetic and does not carry
-- the old MMUCC labels, so there is nothing to retire there -- but the three
-- collapsed values ARE added so the catalog matches what the form now offers.
-- ---------------------------------------------------------------------------
INSERT INTO ref_contributing_factor_values (factor_group_id, code, label, sort_order, spec_version, notes)
SELECT g.id, v.code, v.label, v.sort_order, 'HDTS-PCR-2026', v.notes
FROM ref_contributing_factor_groups g
JOIN (VALUES
 ('CC_VEHICLE','CCV_ACCELERATOR','Accelerator', 6,
  'HDTS PCR data form: collapses the old "Accelerator Failure or Defective".'),
 ('CC_VEHICLE','CCV_ENGINE','Engine', 7,
  'HDTS PCR data form: collapses the old "Engine Failure" and "Engine Trouble".'),
 ('CC_VEHICLE','CCV_MECHANICAL','Mechanical', 8,
  'HDTS PCR data form: collapses the old "Mechanical Failure".'),
 ('CC_ROADWAY','CCR_ANIMALS','Animals', 5,
  'HDTS PCR data form: "Animal(s)" is now spelled "Animals". "Obstructed Crosswalks" was removed.')
) AS v(group_code, code, label, sort_order, notes) ON v.group_code = g.code
ON CONFLICT (factor_group_id, label) DO NOTHING;


-- ###########################################################################
-- PART B - Form-label traceability (GAP-PCR-09)
-- ###########################################################################

-- Section header text exactly as printed on the form, applied by section so it
-- stays correct as the catalog grows.
UPDATE data_attributes da
   SET form_section = s.name
  FROM ref_pcr_sections s
 WHERE s.code = da.pcr_section AND s.is_active AND da.form_section IS NULL;

-- MMUCC lineage: every code matching the MMUCC-aligned pattern descends from
-- MMUCC. The ad-hoc `*X*` pseudo-codes the app invented for the worksheet's
-- un-numbered entries do not, and are left NULL rather than asserted.
UPDATE data_attributes
   SET mmucc_code = code
 WHERE mmucc_code IS NULL
   AND code ~ '^(C|F|LV|NM|P|R|V)[0-9]{2}$';

-- Field labels for the elements whose form wording differs materially from the
-- internal attribute name -- the cases where a State mapping its own PCR could
-- not otherwise find the right CCFP attribute. Attributes whose name already
-- matches the form label are left to the fallback in the data-dictionary view.
UPDATE data_attributes da
   SET form_label = v.form_label
  FROM (VALUES
    ('C03','DATE (MM/DD/YY)'),
    ('C11','WEATHER CONDITIONS'),
    ('C12','LIGHT CONDITION'),
    ('C13','ROADWAY SURFACE CONDITION'),
    ('C14','ROADWAY CONTRIBUTING CIRCUMSTANCES'),
    ('C15','RELATION TO JUNCTION - SPECIFIC LOCATION'),
    ('C19','CRASH SEVERITY'),
    ('C27','CASE/REPORT NUMBER'),
    ('C31','PUBLIC NARRATIVE (WRITTEN FOR AND AVAILABLE TO THE PUBLIC)'),
    ('C37','DRIVER OUT OF SERVICE (OOS)?'),
    ('CX1','CRASH DESCRIPTION'),
    ('LV09','CARGO BODY TYPE'),
    ('LV10','HAZARDOUS MATERIALS RELEASE'),
    ('LV12','TRAILER OWNER NAME'),
    ('LV20','NUMBER OF TRAILING UNITS'),
    ('P14','DRIVER ACTIONS AT TIME OF CRASH'),
    ('P15','ENFORCEMENT ACTIONS - VIOLATIONS'),
    ('P16','DRIVER LICENSE RESTRICTIONS'),
    ('P18','DISTRACTED BY ACTION'),
    ('P19','CONDITION AT TIME OF CRASH'),
    ('P33','DISTRACTED BY SOURCE'),
    ('P34','INJURY SEVERITY'),
    ('P43','SEQUENTIAL IDENTIFYING NUMBER'),
    ('P44','ENDORSEMENTS'),
    ('R05','ROADWAY FUNCTIONAL CLASS'),
    ('R14','WARNING DEVICE TYPE'),
    ('V17','TRAFFIC CONTROL DEVICES - SIGNS'),
    ('V19','LOCATION OF DAMAGED AREA(S)'),
    ('V20','SEQUENCE OF EVENTS'),
    ('V24','VEHICLE CONTRIBUTING CIRCUMSTANCES'),
    ('V29','VEHICLE SIZE AND GVWR'),
    ('V30','CMV?'),
    ('V37','TRAFFIC CONTROL DEVICES - SIGNALS'),
    ('NM02','NON-MOTORIST ACTION/CIRCUMSTANCE PRIOR'),
    ('NM03','NON-MOTORIST CONTRIBUTING ACTION(S)'),
    ('NM05','NON-MOTORIST SAFETY EQUIPMENT'),
    ('NMX1','NON-MOTORIST UNIT TYPE')
  ) AS v(code, form_label)
 WHERE da.code = v.code;

-- ---------------------------------------------------------------------------
-- Guards.
-- ---------------------------------------------------------------------------
DO $$
DECLARE n INT;
BEGIN
    SELECT count(*) INTO n FROM ref_attribute_values;
    IF n < 30 THEN
        RAISE EXCEPTION 'GAP-PCR-09b: expected the named value lists to seed, got % rows', n;
    END IF;

    -- Every retired value that the gap says was COLLAPSED must name where it went.
    SELECT count(*) INTO n FROM ref_attribute_values
     WHERE code IN ('ALC_NA_OLD','ALC_PENDING_OLD','DRG_NA_OLD','DRG_PENDING_OLD',
                    'BT_LARGE_LIMO','DMG_UNDER_OLD')
       AND superseded_by_id IS NULL;
    IF n > 0 THEN
        RAISE EXCEPTION 'GAP-PCR-09b: % collapsed value(s) do not name a replacement', n;
    END IF;

    -- No active attribute in a live section should be missing its form section.
    SELECT count(*) INTO n FROM data_attributes da
      JOIN ref_pcr_sections s ON s.code = da.pcr_section
     WHERE da.is_active AND s.is_active AND da.form_section IS NULL;
    IF n > 0 THEN
        RAISE EXCEPTION 'GAP-PCR-09: % active attribute(s) have no form_section', n;
    END IF;
END $$;
