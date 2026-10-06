-- =============================================================================
-- CCFP IT Solution - Migration 0025: versioned attribute value catalog (GAP-PCR-09b)
-- =============================================================================
-- The new HDTS PCR data form does not only add and remove ELEMENTS -- it also
-- removes and narrows the enumerated VALUES inside elements that were otherwise
-- retained. From the gap analysis:
--
--   C19 Crash severity      "No Apparent Injury" dropped at crash level; the
--                           MMUCC letter prefixes (K)/(A)/(B)/(C)/(O) dropped
--   NMX1 Non-motorist type  narrowed to 4 values; "Unknown" and "Other" removed
--   LV10 HazMat release     "Unknown if Released" removed -- now No/Yes only
--   P21/P23 Alcohol/Drug    "Not Applicable (Test Not Given)" and "Test given,
--                           results pending" collapsed into "Pending"
--   V08 Vehicle body type   "Mini-bus", "Large Limo", "Passenger Car Type"
--                           dropped; "Limousine (Large)" added
--   V19 Vehicle damage      "Undercarriage Damaged?" yes/no replaced by
--                           "Undercarriage" as a clock-position value
--
-- The application could not express any of this: apart from the
-- contributing-factor groups, NO attribute had an enumerated value list at all.
-- A CODE attribute simply accepted any string. So there was nothing to
-- re-derive, and no way for the data dictionary (GAP-PCR-09) to carry a value
-- list.
--
-- This adds that catalog, versioned from the outset. The versioning is the
-- point: a value removed by a later specification must stop being offered for
-- new collection WITHOUT orphaning the historical rows that already use it, so
-- values are retired and optionally point at what replaced them, exactly as
-- data_attributes.superseded_by_code does for whole attributes.
--
-- Idempotent / additive.
-- =============================================================================

-- ---------------------------------------------------------------------------
-- Per-attribute enumerated values.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ref_attribute_values (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    attribute_id  UUID NOT NULL REFERENCES data_attributes(id) ON DELETE CASCADE,
    code          TEXT,
    label         TEXT NOT NULL,
    sort_order    INT NOT NULL DEFAULT 0,
    -- Which specification introduced / retired this value. `is_active = FALSE`
    -- means "collected under an earlier spec, still resolvable, not offered".
    spec_version  TEXT NOT NULL DEFAULT 'HDTS-PCR-2026',
    is_active     BOOLEAN NOT NULL DEFAULT TRUE,
    -- Where a retired value went, when the new form collapsed several old
    -- values into one (e.g. "Engine Failure"/"Engine Trouble" -> "Engine").
    -- NULL when the value was dropped outright with no successor.
    superseded_by_id UUID REFERENCES ref_attribute_values(id) ON DELETE SET NULL,
    notes         TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (attribute_id, label)
);
CREATE INDEX IF NOT EXISTS idx_ref_attribute_values_attr
    ON ref_attribute_values (attribute_id);
CREATE INDEX IF NOT EXISTS idx_ref_attribute_values_active
    ON ref_attribute_values (attribute_id) WHERE is_active;

DO $$ BEGIN
    ALTER TABLE ref_attribute_values
        ADD CONSTRAINT ck_ref_attribute_values_no_self_supersede
        CHECK (superseded_by_id IS NULL OR superseded_by_id <> id);
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

COMMENT ON TABLE ref_attribute_values IS
    'Enumerated values allowed for a CODE / MULTI_CODE attribute, versioned by specification (GAP-PCR-09b). A value removed by a later spec is deactivated, never deleted, so historical crash_attribute_values rows stay resolvable.';

-- ---------------------------------------------------------------------------
-- The contributing-factor catalog gains the same lifecycle, for the same
-- reason: contributing_factor_selections references these values, and the new
-- form collapses several of them (e.g. the motor-vehicle circumstances
-- "Accelerator Failure or Defective" / "Engine Failure" / "Engine Trouble" /
-- "Mechanical Failure" -> "Accelerator" / "Engine" / "Mechanical").
-- ---------------------------------------------------------------------------
ALTER TABLE ref_contributing_factor_values
    ADD COLUMN IF NOT EXISTS spec_version     TEXT NOT NULL DEFAULT 'HDTS-PCR-2026',
    ADD COLUMN IF NOT EXISTS is_active        BOOLEAN NOT NULL DEFAULT TRUE,
    ADD COLUMN IF NOT EXISTS superseded_by_id UUID REFERENCES ref_contributing_factor_values(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS notes            TEXT;

DO $$ BEGIN
    ALTER TABLE ref_contributing_factor_values
        ADD CONSTRAINT ck_ref_factor_values_no_self_supersede
        CHECK (superseded_by_id IS NULL OR superseded_by_id <> id);
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

COMMENT ON COLUMN ref_contributing_factor_values.is_active IS
    'FALSE = retired by a later specification. Retained so existing contributing_factor_selections stay resolvable (GAP-PCR-09b).';

-- updated_at trigger, reusing the existing function.
DO $$ BEGIN
    CREATE TRIGGER trg_ref_attribute_values_updated_at
        BEFORE UPDATE ON ref_attribute_values
        FOR EACH ROW EXECUTE FUNCTION set_updated_at();
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
