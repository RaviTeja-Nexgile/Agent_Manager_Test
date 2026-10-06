-- =============================================================================
-- Seed 0015 - Backfill repeat units on pre-existing values (GAP-PCR-02/-03)
-- =============================================================================
-- Seed 0014 declared whole sections as repeating (every Vehicle attribute per
-- VEHICLE, every Person attribute per PERSON, trailer elements per TRAILER).
-- Any crash_attribute_values row written BEFORE that declaration carries a NULL
-- discriminator, because at the time the value model had no concept of units.
--
-- Those rows are now inconsistent with their own attribute's declaration:
--   * the Aggregated Data view files them under the crash-level block rather
--     than under a unit, and
--   * a later write that DOES supply a unit would not supersede them (the
--     supersede predicate matches on the unit), leaving two rows both claiming
--     is_current for the same attribute.
--
-- A value recorded before the repeat model existed necessarily describes the
-- first -- and, in the flat model, only -- unit of its type, so it is assigned
-- to unit 1. This is the only interpretation that preserves the value's meaning
-- and it is idempotent (rows already carrying a unit are untouched).
--
-- Runs as a SEED, not a migration, deliberately: migrations execute before
-- seeds, so as a migration this would run before seed 0014 set repeats_on and
-- silently do nothing on a fresh database.
-- =============================================================================

UPDATE crash_attribute_values cav
   SET unit_type   = da.repeats_on,
       unit_number = 1,
       updated_at  = now()
  FROM data_attributes da
 WHERE da.id = cav.attribute_id
   AND da.repeats_on IS NOT NULL
   AND cav.unit_type IS NULL;

-- Guard: after the backfill no current value may disagree with its attribute's
-- declaration. Fails loudly rather than leaving a silently broken catalog.
DO $$
DECLARE bad INT;
BEGIN
    SELECT count(*) INTO bad
      FROM crash_attribute_values cav
      JOIN data_attributes da ON da.id = cav.attribute_id
     WHERE (da.repeats_on IS NULL) <> (cav.unit_type IS NULL);
    IF bad > 0 THEN
        RAISE EXCEPTION
            'GAP-PCR-02 backfill left % crash_attribute_values row(s) whose unit disagrees with data_attributes.repeats_on', bad;
    END IF;
END $$;
