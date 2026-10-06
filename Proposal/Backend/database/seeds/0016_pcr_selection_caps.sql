-- =============================================================================
-- Seed 0016 - HDTS PCR selection caps (GAP-PCR-04)
-- =============================================================================
-- The new form states a selection cap on 28 elements. Each becomes a
-- MULTI_CODE attribute carrying its own `max_selections`, so the cap is DATA,
-- not code -- an administrator can change it per study phase without a release,
-- which is the configurability rule in CLAUDE.md.
--
-- "Check only 1" is modelled as max_selections = 1 rather than as a
-- single-valued CODE, deliberately: the form presents it as a checkbox group
-- with a cap of one, and recording it that way keeps the validation uniform and
-- lets a later phase widen the cap without a type change.
--
-- Two caps in the gap analysis have no existing code to attach to, so they get
-- new attributes here (both flagged in `description`):
--   * "Endorsements (Check up to 5)"          -> P44
--   * "Traffic Control Devices - Signals (5)" -> V37
-- and V17 "Traffic control device type" takes the Signs cap of 4.
--
-- Two caps WIDENED on elements that are otherwise unchanged, which is easy to
-- miss because nothing else about them moved (GAP-PCR-09b):
--   * C11 Weather conditions            2 -> 3
--   * C14 Contributing circumstances    4 -> 6
--
-- Depends on migration 0023 having added the MULTI_CODE enum value in an
-- EARLIER transaction.
-- =============================================================================

-- ---------------------------------------------------------------------------
-- 1. The two elements with no existing code.
-- ---------------------------------------------------------------------------
INSERT INTO data_attributes
    (code, name, category, pcr_section, data_type, sensitivity, repeats_on, applies_to, max_selections, description)
VALUES
 ('P44','Driver license endorsements','Person','PERSON','MULTI_CODE','PII','PERSON','ALL_DRIVERS',5,
  'GAP-PCR-04. "Endorsements (Check up to 5)" on the new form. Distinct from LV01, which records CDL endorsement COMPLIANCE rather than the endorsements held.'),
 ('V37','Traffic control devices - signals','Vehicle','VEHICLE','MULTI_CODE','INTERNAL','VEHICLE',NULL,5,
  'GAP-PCR-04. The new form splits traffic control devices into Signs (up to 4, kept on V17) and Signals (up to 5, here).')
ON CONFLICT (code) DO NOTHING;

-- ---------------------------------------------------------------------------
-- 2. Apply every cap from the new form.
--
-- Written as one VALUES list so the caps are reviewable against the form in a
-- single glance, and so a wrong code fails loudly in the guard below rather
-- than silently applying to nothing.
-- ---------------------------------------------------------------------------
WITH caps(code, cap, form_label) AS (VALUES
    -- Crash Data Elements
    ('C11', 3, 'Weather Conditions (up to 3 -- WIDENED from 2)'),
    ('C12', 1, 'Light Condition (check only 1)'),
    ('C13', 3, 'Roadway Surface Condition (up to 3)'),
    ('C14', 6, 'Roadway Contributing Circumstances (up to 6 -- WIDENED from 4)'),
    ('C15', 3, 'Relation to Junction - Specific Location (up to 3)'),
    ('C07', 1, 'First Harmful Event (check only 1)'),
    -- Fatal Data Elements
    ('F03', 4, 'Drug Test Results (up to 4)'),
    -- Large Vehicle and HM
    ('LV09', 3, 'Cargo Body Type (up to 3)'),
    -- Person Data Elements
    ('P07', 2, 'Seating Position (up to 2)'),
    ('P08', 3, 'Restraint Systems (up to 3)'),
    ('P09', 2, 'Air Bag Deployment Type (up to 2)'),
    ('P14', 6, 'Driver Actions at Time of Crash (up to 6)'),
    ('P15', 5, 'Enforcement Actions - Violations (enter up to 5)'),
    ('P16', 6, 'Driver License Restrictions (up to 6)'),
    ('P18', 2, 'Distracted by Action (up to 2)'),
    ('P19', 6, 'Condition at Time of Crash (up to 6)'),
    ('P33', 4, 'Distracted by Source (up to 4)'),
    ('P44', 5, 'Endorsements (up to 5)'),
    -- Roadway Data Elements
    ('R05', 3, 'Roadway Functional Class (up to 3)'),
    -- Vehicle Data Elements
    ('V17', 4, 'Traffic Control Devices - Signs (up to 4)'),
    ('V19', 3, 'Location of Damaged Area(s) (up to 3)'),
    ('V20', 4, 'Sequence of Events (up to 4)'),
    ('V24', 4, 'Vehicle Contributing Circumstances (up to 4)'),
    ('V37', 5, 'Traffic Control Devices - Signals (up to 5)'),
    -- Non-Motorist Data Elements
    ('NM02', 3, 'Non-Motorist Action/Circumstance Prior (up to 3)'),
    ('NM03', 5, 'Non-Motorist Contributing Action(s) (up to 5)'),
    ('NM05', 5, 'Non-Motorist Safety Equipment (up to 5)')
)
UPDATE data_attributes da
   SET max_selections = caps.cap,
       data_type      = 'MULTI_CODE',
       description    = coalesce(da.description || ' ', '')
                        || 'GAP-PCR-04 cap: ' || caps.form_label || '.',
       updated_at     = now()
  FROM caps
 WHERE da.code = caps.code;

-- Guard: every cap above must have matched a real attribute. A typo would
-- otherwise apply the cap to nothing and be invisible until a value overflowed.
DO $$
DECLARE missing TEXT;
BEGIN
    SELECT string_agg(c, ', ') INTO missing
      FROM unnest(ARRAY['C11','C12','C13','C14','C15','C07','F03','LV09','P07','P08','P09',
                        'P14','P15','P16','P18','P19','P33','P44','R05','V17','V19','V20',
                        'V24','V37','NM02','NM03','NM05']) AS c
     WHERE NOT EXISTS (SELECT 1 FROM data_attributes da
                        WHERE da.code = c AND da.max_selections IS NOT NULL);
    IF missing IS NOT NULL THEN
        RAISE EXCEPTION 'GAP-PCR-04: capped attribute code(s) not found or not updated: %', missing;
    END IF;
END $$;

-- ---------------------------------------------------------------------------
-- 3. The CARDINALITY quality rule.
--
-- Enforcement is BELT AND BRACES: set_attribute rejects an over-cap write at
-- the point of entry (a 400, so the analyst sees it immediately), and this rule
-- re-checks every stored value during QC so data that arrived by any other
-- route -- source ingestion, PCR import, a rule loosened then re-tightened --
-- is still caught.
--
-- Severity ERROR, not CRITICAL: an over-cap selection is a correctable data
-- error, not a reason to block the record from completeness entirely.
-- ---------------------------------------------------------------------------
INSERT INTO data_quality_rules (code, name, rule_type, severity, definition, is_active)
VALUES ('DQ_CARDINALITY',
        'Multi-select attributes within their allowed number of selections',
        'CARDINALITY', 'ERROR',
        '{"check": "cardinality"}'::jsonb, TRUE)
ON CONFLICT (code) DO UPDATE
   SET rule_type  = EXCLUDED.rule_type,
       severity   = EXCLUDED.severity,
       definition = EXCLUDED.definition,
       is_active  = TRUE;
