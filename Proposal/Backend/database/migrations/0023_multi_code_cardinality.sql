-- =============================================================================
-- CCFP IT Solution - Migration 0023: MULTI_CODE data type (GAP-PCR-04)
-- =============================================================================
-- The old KS worksheet mentioned selection caps only sporadically ("Select up
-- to 5" on DV01). The new HDTS PCR data form states them pervasively and
-- precisely -- "Check only 1", "Check up to 2/3/4/5/6", "Enter up to 5" -- on
-- 28 elements.
--
-- Two things were missing to express that:
--   1. A data type for a capped multi-select. `attribute_data_type` had only
--      single-valued types plus JSON, so multi-valued data would land in
--      value_json with no declared cardinality at all.
--   2. A rule type that checks cardinality. `data_quality_rules.rule_type` is
--      free TEXT (documented as MISSING | FORMAT | COMPLIANCE | CROSS_FIELD),
--      none of which is a count check -- so no DDL is needed for CARDINALITY,
--      only the evaluator and the seeded rule (seed 0016).
--
-- `data_attributes.max_selections` already exists (migration 0020, added
-- alongside the repeat discriminator); this migration only adds the type.
--
-- NOTE ON TRANSACTIONS: PostgreSQL forbids using a newly added enum value in
-- the SAME transaction that adds it. migrate.py runs each file in its own
-- transaction, so the value is added here and first USED in seed 0016. Do not
-- merge the two.
-- =============================================================================

ALTER TYPE attribute_data_type ADD VALUE IF NOT EXISTS 'MULTI_CODE';

COMMENT ON COLUMN data_quality_rules.rule_type IS
    'MISSING | FORMAT | COMPLIANCE | CROSS_FIELD | CARDINALITY. CARDINALITY checks that a capped multi-select attribute holds no more values than data_attributes.max_selections allows (GAP-PCR-04).';
