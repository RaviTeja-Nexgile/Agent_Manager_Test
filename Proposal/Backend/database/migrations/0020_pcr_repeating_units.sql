-- =============================================================================
-- CCFP IT Solution - Migration 0020: PCR repeating units (GAP-PCR-03)
-- =============================================================================
-- The new HDTS Police Crash Report data form makes multiplicity STRUCTURAL:
--   * Trailers 1/2/3 -- every trailer element repeats per position (plate, VIN,
--     model year, owner name/address/city/zip, GVWR, length, type, HM release,
--     axles).
--   * The whole Vehicle section repeats, keyed by Vehicle Sequential Number.
--   * The whole Person section repeats, keyed by Sequential Identifying Number,
--     with the occupant's Vehicle Number as the link.
--   * Person fields apply to different populations (All Persons Involved / All
--     Occupants / All Drivers / CMV Drivers / All Drivers and Non-Motorists /
--     All Injured) -- a conditional-visibility + validation spec.
--   * Bounded repeats: "Violations (Enter up to 5)", "Endorsements (up to 5)".
--
-- crash_attribute_values previously enforced ONE current value per
-- (crash_id, attribute_id) via the partial unique index uq_cav_current, so it
-- was architecturally incapable of holding "Trailer 2 GVWR" separately from
-- "Trailer 1 GVWR", or Vehicle 3's damage separately from Vehicle 1's.
--
-- This migration adds a repeat discriminator (unit_type, unit_number) and
-- widens the uniqueness key to include it. NULL/NULL means "crash-level value"
-- -- exactly what every existing row is -- so this is purely ADDITIVE: no
-- existing row changes and no backfill is required.
--
-- Follows the convention established by migration 0016 (PCI repeating
-- structures): repeat positions are an index column, NOT fixed numbered
-- columns, and the unit vocabulary lives in a reference table rather than a PG
-- enum so it stays configurable for future phases (no hardcoded Phase-1 maxima
-- or unit set as DB constraints).
--
-- Idempotent / additive: IF NOT EXISTS throughout.
-- =============================================================================

-- ---------------------------------------------------------------------------
-- Repeat-unit vocabulary. A reference table (not a PG enum) so a future phase
-- can add a unit -- e.g. CARGO or AXLE -- without an ALTER TYPE.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ref_repeat_units (
    code        TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    description TEXT,
    sort_order  INT NOT NULL DEFAULT 0
);

INSERT INTO ref_repeat_units (code, name, description, sort_order) VALUES
 ('VEHICLE','Vehicle','Vehicle section, keyed by Vehicle Sequential Number',1),
 ('PERSON','Person','Person section, keyed by Sequential Identifying Number',2),
 ('TRAILER','Trailer','Trailer position 1..n on a large vehicle',3),
 ('NON_MOTORIST','Non-motorist','Non-motorist unit involved in the crash',4)
ON CONFLICT (code) DO NOTHING;

-- ---------------------------------------------------------------------------
-- data_attributes: declare which unit an attribute repeats on, how many values
-- may be selected, and which person population it applies to.
--
--   repeats_on     NULL = crash-level (single value per crash). Non-NULL = the
--                  attribute is captured once per unit of that type.
--   max_selections NULL = single-valued. N = capped multi-select ("Check up to
--                  N"); seeded and enforced by GAP-PCR-04.
--   applies_to     NULL = applies to every row of its unit. Non-NULL names the
--                  conditional population from the new PCR Person section.
-- ---------------------------------------------------------------------------
ALTER TABLE data_attributes
    ADD COLUMN IF NOT EXISTS repeats_on     TEXT REFERENCES ref_repeat_units(code),
    ADD COLUMN IF NOT EXISTS max_selections INT,
    ADD COLUMN IF NOT EXISTS applies_to     TEXT;

DO $$ BEGIN
    ALTER TABLE data_attributes
        ADD CONSTRAINT ck_data_attributes_max_selections
        CHECK (max_selections IS NULL OR max_selections >= 1);
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

CREATE INDEX IF NOT EXISTS idx_data_attributes_repeats_on
    ON data_attributes(repeats_on) WHERE repeats_on IS NOT NULL;

COMMENT ON COLUMN data_attributes.repeats_on IS
    'Repeat unit this attribute is captured per (ref_repeat_units.code). NULL = crash-level.';
COMMENT ON COLUMN data_attributes.max_selections IS
    'Cap for a multi-select attribute ("Check up to N"). NULL = single-valued.';
COMMENT ON COLUMN data_attributes.applies_to IS
    'Conditional population from the PCR Person section (ALL_PERSONS, ALL_OCCUPANTS, ALL_DRIVERS, CMV_DRIVERS, DRIVERS_AND_NON_MOTORISTS, ALL_INJURED). NULL = all rows of the unit.';

-- ---------------------------------------------------------------------------
-- crash_attribute_values: the repeat discriminator.
--
-- Both columns NULL together = a crash-level value (every pre-existing row).
-- Both set together = "this attribute, for unit #N of that type".
-- ---------------------------------------------------------------------------
ALTER TABLE crash_attribute_values
    ADD COLUMN IF NOT EXISTS unit_type   TEXT REFERENCES ref_repeat_units(code),
    ADD COLUMN IF NOT EXISTS unit_number INT;

-- unit_type and unit_number are meaningful only together: a unit_number with no
-- unit_type is unattributable, and a unit_type with no number cannot be ordered
-- against its siblings. Reject both halves of that.
DO $$ BEGIN
    ALTER TABLE crash_attribute_values
        ADD CONSTRAINT ck_cav_unit_pairing
        CHECK ((unit_type IS NULL) = (unit_number IS NULL));
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- Unit positions are 1-based (Trailer 1, Vehicle 1, Person 1) -- matching the
-- form's own numbering. No upper bound: Phase 1 caps trailers at 3, but that is
-- a study rule, not a schema rule.
DO $$ BEGIN
    ALTER TABLE crash_attribute_values
        ADD CONSTRAINT ck_cav_unit_number_positive
        CHECK (unit_number IS NULL OR unit_number >= 1);
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- ---------------------------------------------------------------------------
-- Replace the uniqueness key: one current value per (crash, attribute, unit).
--
-- coalesce() collapses the NULL discriminator to a sentinel so crash-level rows
-- still collide with each other exactly as before -- preserving the original
-- guarantee for every existing row -- while per-unit rows are now distinct.
-- Both expressions are IMMUTABLE, which a unique index requires.
--
-- Dropped and recreated (not created alongside) because keeping the old
-- two-column index would defeat the whole change: it would still reject a
-- second trailer's value.
-- ---------------------------------------------------------------------------
DROP INDEX IF EXISTS uq_cav_current;

CREATE UNIQUE INDEX IF NOT EXISTS uq_cav_current
    ON crash_attribute_values (
        crash_id,
        attribute_id,
        coalesce(unit_type, ''),
        coalesce(unit_number, 0)
    )
    WHERE is_current;

-- Supports "give me every attribute for Vehicle 2 of this crash", the read the
-- unit-grouped Aggregated Data view issues.
CREATE INDEX IF NOT EXISTS idx_cav_unit
    ON crash_attribute_values (crash_id, unit_type, unit_number)
    WHERE unit_type IS NOT NULL;

COMMENT ON COLUMN crash_attribute_values.unit_type IS
    'Repeat unit this value belongs to (ref_repeat_units.code). NULL = crash-level value.';
COMMENT ON COLUMN crash_attribute_values.unit_number IS
    '1-based position of the unit (Trailer 1, Vehicle 2, ...). NULL = crash-level value.';
