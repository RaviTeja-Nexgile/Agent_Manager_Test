-- =============================================================================
-- Seed 0023 - QC rules for GAP-PCR-06 and GAP-PCR-07
-- ALL data is synthetic / dev-test-demo only.
-- =============================================================================
-- GAP-PCR-06 asks for "a QC rule warning when the public narrative is empty on
-- a complete record". The point is disclosure safety, not tidiness: the new
-- form separates the Public Narrative (C31, PUBLIC) from the internal Crash
-- Description (CX1, SENSITIVE) precisely so the former can be released without
-- redaction. If C31 is missing, the only narrative available is the sensitive
-- one, and publishing that would be a disclosure incident. The rule makes that
-- absence visible before publication rather than after.
--
-- GAP-PCR-07 asks for "a CROSS_FIELD QC rule that flags disagreement with the
-- SafeSpect-sourced post_crash_inspections row". The new form repeats
-- inspection identifiers that already arrive from SafeSpect, so the same fact
-- has two sources and can silently diverge. Treating the PCR block as a
-- cross-reference only works if divergence is surfaced.
--
-- Severities are deliberate:
--   DQ_PUBLIC_NARRATIVE      WARNING — an early-lifecycle crash legitimately
--                            has no public narrative yet; this must not block a
--                            record from ever reaching completeness.
--   DQ_PCR_INSPECTION_XREF   ERROR   — two authoritative sources stating
--                            different facts about the same inspection is a
--                            correctness problem someone must resolve, not a
--                            stylistic nag. Still not CRITICAL: it should not
--                            by itself bar the record.
--
-- Idempotent.
-- =============================================================================

INSERT INTO data_quality_rules (code, name, rule_type, severity, definition, is_active)
VALUES
 ('DQ_PUBLIC_NARRATIVE',
  'Public narrative missing — the internal description must not be published in its place',
  'MISSING', 'WARNING', '{"check": "public_narrative"}'::jsonb, TRUE),
 ('DQ_PCR_INSPECTION_XREF',
  'PCR-reported inspection details disagree with the SafeSpect record',
  'CROSS_FIELD', 'ERROR', '{"check": "pcr_inspection_xref"}'::jsonb, TRUE)
ON CONFLICT (code) DO UPDATE
   SET name       = EXCLUDED.name,
       rule_type  = EXCLUDED.rule_type,
       severity   = EXCLUDED.severity,
       definition = EXCLUDED.definition,
       is_active  = TRUE;

-- ---------------------------------------------------------------------------
-- Demonstration data for the cross-reference rule.
--
-- One crash is given a SafeSpect inspection that AGREES with its PCR-reported
-- block, and another is given one that DISAGREES, so both outcomes are
-- observable in the demo rather than only the happy path. Values mirror the
-- C33-C37 attributes seeded for those crashes below.
-- ---------------------------------------------------------------------------
INSERT INTO crash_attribute_values
    (crash_id, attribute_id, value_text, source_system, confidence, is_current, is_edited)
SELECT c.id, da.id, v.value_text, 'PCR', 95, TRUE, FALSE
  FROM (VALUES
    ('CCFP-2026-KS-000105','C33','Kansas Highway Patrol'),
    ('CCFP-2026-KS-000105','C34','KS-INSP-88214'),
    ('CCFP-2026-KS-000105','C35','Trooper D. Halloran'),
    ('CCFP-2026-KS-000105','C36','Vehicle'),
    ('CCFP-2026-KS-000105','C37','No'),
    ('CCFP-2026-CA-000115','C33','California Highway Patrol'),
    ('CCFP-2026-CA-000115','C34','CA-INSP-40771'),
    ('CCFP-2026-CA-000115','C36','Driver'),
    ('CCFP-2026-CA-000115','C37','Yes')
  ) AS v(ident, code, value_text)
  JOIN crashes c ON c.ccfp_identifier = v.ident
  JOIN data_attributes da ON da.code = v.code AND da.is_active
 WHERE NOT EXISTS (
        SELECT 1 FROM crash_attribute_values x
         WHERE x.crash_id = c.id AND x.attribute_id = da.id AND x.is_current
           AND x.unit_type IS NULL);

-- Matching SafeSpect record for KS (agrees) and CA (disagrees on type + OOS).
INSERT INTO post_crash_inspections
    (crash_id, source_system, inspection_number, inspection_date, inspector_name,
     inspection_type, driver_oos, violations_count, defects_count)
SELECT c.id, 'SafeSpect', v.num, v.dt::date, v.officer, v.itype, v.oos, v.viol, v.def
  FROM (VALUES
    ('CCFP-2026-KS-000105','KS-INSP-88214','2026-03-22','Trooper D. Halloran','Vehicle', FALSE, 2, 1),
    -- Deliberately divergent: SafeSpect says Vehicle / not OOS, the PCR says
    -- Driver / OOS. Exercises the FAIL branch.
    ('CCFP-2026-CA-000115','CA-INSP-40771','2026-04-26','Officer R. Nakashima','Vehicle', FALSE, 5, 3)
  ) AS v(ident, num, dt, officer, itype, oos, viol, def)
  JOIN crashes c ON c.ccfp_identifier = v.ident
 WHERE NOT EXISTS (
        SELECT 1 FROM post_crash_inspections p
         WHERE p.crash_id = c.id AND p.inspection_number = v.num);

DO $$
DECLARE n INT;
BEGIN
    SELECT count(*) INTO n FROM data_quality_rules
     WHERE code IN ('DQ_PUBLIC_NARRATIVE','DQ_PCR_INSPECTION_XREF') AND is_active;
    IF n <> 2 THEN
        RAISE EXCEPTION 'GAP-PCR-06/07: expected 2 active rules, found %', n;
    END IF;
END $$;
