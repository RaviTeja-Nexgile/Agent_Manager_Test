-- =============================================================================
-- Seed 0024 - Accuracy (internal-consistency and range) QC rules
-- ALL data is synthetic / dev-test-demo only.
-- =============================================================================
-- The SOO requires "data validations for the completeness AND ACCURACY of
-- reports". Every rule in the catalogue before this one answers one of:
--
--   MISSING       is the value present?          (DQ_MISSING_*, DQ_PUBLIC_NARRATIVE)
--   FORMAT        is it well-formed?             (DQ_DOT_FORMAT)
--   COMPLIANCE    does an external source agree? (DQ_DOT_SAFESPECT, DQ_CDLIS_CHECK)
--   CROSS_FIELD   do two sources of the same fact agree? (DQ_PCR_INSPECTION_XREF)
--
-- None asks whether the record contradicts ITSELF, or whether a value is in a
-- possible range. Those are the accuracy failures that survive collection
-- undetected, precisely because every field is individually present, well-formed
-- and unchallenged by any other system — a crash with 4 fatalities among 2
-- persons, or dated next week, passes the entire existing catalogue.
--
--   DQ_COUNTS_CONSISTENT  ERROR   — fatalities exceeding persons, more attached
--                         vehicle records than declared, or injured occupants
--                         exceeding occupants. A self-contradicting record is a
--                         correctness defect someone must resolve; it corrupts
--                         any count-based analysis downstream. Not CRITICAL: it
--                         should not by itself bar the record from existing.
--
--   DQ_DATE_PLAUSIBLE     WARNING — a future crash date is impossible and a date
--                         more than ten years old is almost always a mistyped
--                         year. WARNING rather than ERROR because the ten-year
--                         arm is a prompt to verify, not a statement of fault,
--                         and because study scope is the classifier's job, not
--                         this rule's.
--
-- Both are evaluated by definition-driven dispatch (`check` keys) in
-- app/workers/tasks.py, so neither needs a code-keyed fallback branch.
--
-- Idempotent.
-- =============================================================================

INSERT INTO data_quality_rules (code, name, rule_type, severity, definition, is_active)
VALUES
 ('DQ_COUNTS_CONSISTENT',
  'Crash record contradicts itself (fatalities, vehicles, or injured occupants)',
  'CROSS_FIELD', 'ERROR', '{"check": "counts_consistent"}'::jsonb, TRUE),
 ('DQ_DATE_PLAUSIBLE',
  'Crash date is in the future or implausibly old',
  'FORMAT', 'WARNING', '{"check": "date_plausible"}'::jsonb, TRUE)
ON CONFLICT (code) DO UPDATE
   SET name       = EXCLUDED.name,
       rule_type  = EXCLUDED.rule_type,
       severity   = EXCLUDED.severity,
       definition = EXCLUDED.definition,
       is_active  = TRUE;
