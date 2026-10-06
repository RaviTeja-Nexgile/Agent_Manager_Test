-- =============================================================================
-- CCFP IT Solution - Migration 0022: attribute supersession (GAP-PCR-02)
-- =============================================================================
-- The application's catalog grew from the old KS worksheet, which used
-- un-numbered pseudo-codes (`CX.`, `FX.`, `LVX.`, `NMX.`, `PX.`, `RX.`, `VX.`,
-- `AAA.`) alongside the MMUCC-aligned ones. The app rendered those as CX1,
-- FX1, LVX1 ... -- ad-hoc codes with no external authority.
--
-- The new HDTS PCR data form decomposes some of them. `PX2 Person address`, for
-- example, is now four separate fields (City / State / ZIP / Country). Those
-- coarse codes cannot simply be renamed: historical crash_attribute_values rows
-- point at them, so they must stay resolvable.
--
-- This adds the supersession pointer the gap analysis calls "aliasing": a
-- retired code names the attribute that replaces it, so a reader of an old
-- value can follow the chain forward. It is intentionally MANY-retired-to-ONE
-- replacement (not one-to-many): where the new form splits one old code into
-- several, each new code carries the pointer back is not possible, so the old
-- code points at the primary replacement and the rest are discoverable by
-- section. Recorded in `description` where the split matters.
--
-- Idempotent / additive.
-- =============================================================================

ALTER TABLE data_attributes
    ADD COLUMN IF NOT EXISTS superseded_by_code TEXT REFERENCES data_attributes(code);

COMMENT ON COLUMN data_attributes.superseded_by_code IS
    'For a retired attribute (is_active = FALSE), the code that replaces it under the current specification. NULL for live attributes and for retirements with no replacement (e.g. DV01, whose section was removed outright).';

CREATE INDEX IF NOT EXISTS idx_data_attributes_superseded_by
    ON data_attributes(superseded_by_code) WHERE superseded_by_code IS NOT NULL;

-- An attribute cannot supersede itself.
DO $$ BEGIN
    ALTER TABLE data_attributes
        ADD CONSTRAINT ck_data_attributes_no_self_supersede
        CHECK (superseded_by_code IS NULL OR superseded_by_code <> code);
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
