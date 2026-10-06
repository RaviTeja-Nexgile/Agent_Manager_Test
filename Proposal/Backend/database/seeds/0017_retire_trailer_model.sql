-- =============================================================================
-- Seed 0017 - Retire LV05 Trailer Model(s) (GAP-PCR-08)
-- =============================================================================
-- The old KS worksheet carried `LV05. Trailer Model(s)` as a distinct element.
-- The new HDTS PCR data form does NOT: its only trailer-model field is
-- "TRAILER MODEL YEAR(S)", which is the separate element already modelled as
-- LV06. Verified against the new form: no "Trailer Model" occurrence other than
-- "TRAILER MODEL YEAR(S)".
--
-- Deactivated, not deleted -- same reasoning as DV01 (GAP-PCR-01) and PX2
-- (GAP-PCR-02): crash_attribute_values.attribute_id is ON DELETE RESTRICT, so
-- deleting would either fail or orphan values collected under the old
-- specification.
--
-- `superseded_by_code` is deliberately left NULL. LV06 is NOT a replacement for
-- LV05 -- a model year is not a model -- and pointing at it would misrepresent
-- historical values as having migrated somewhere they did not. The element was
-- dropped outright, exactly like DV01.
--
-- Idempotent.
-- =============================================================================

UPDATE data_attributes
   SET is_active   = FALSE,
       description = 'Retired by GAP-PCR-08: the HDTS PCR data form has no Trailer Model element, only TRAILER MODEL YEAR(S) (modelled separately as LV06). Retained so historical values remain resolvable; no replacement attribute.',
       updated_at  = now()
 WHERE code = 'LV05';

-- A retired attribute must not remain a study requirement, or completeness
-- evaluation would keep demanding a value the current form never collects.
UPDATE attribute_requirements
   SET is_required = FALSE, is_optional = FALSE, updated_at = now()
 WHERE attribute_id IN (SELECT id FROM data_attributes WHERE code = 'LV05');

-- Guard: fail loudly if the code ever stops matching (a rename would otherwise
-- make this seed a silent no-op).
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM data_attributes WHERE code = 'LV05' AND NOT is_active) THEN
        RAISE EXCEPTION 'GAP-PCR-08: LV05 was not found or was not deactivated';
    END IF;
END $$;
