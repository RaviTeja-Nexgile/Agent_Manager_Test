-- =============================================================================
-- CCFP IT Solution - Migration 0024: scope-classification inputs & override flag
-- =============================================================================
-- DL2 / DL8, §3.1, §5. Fixes the crash-scope classification defect in which a
-- crash was classified exactly once — at creation, before any incident vehicle
-- could exist — and never re-derived, leaving every crash stuck at UNDETERMINED
-- and therefore routed to NEITHER the BTS CIPSEA branch NOR the out-of-scope
-- retention branch on IIF submit.
--
-- Two structural gaps are closed here:
--
--  1. incident_vehicles carried no vehicle class and no GVWR, so the Phase 1
--     qualifying criterion ("Class 7/8 heavy-duty truck, GVWR >= 26,001 lbs")
--     could not be evaluated at all — the classifier fell back to the is_cmv
--     checkbox as a proxy. The study parameters that define the criterion
--     (`vehicle_classes`, `min_gvwr_lbs`) were seeded but read by no code.
--     These columns make the configured rule actually evaluable, and keep it
--     configurable for future phases (medium-duty, buses) without a rebuild.
--
--  2. crash_scope_classifications had no way to distinguish a value a human
--     deliberately set (PUT /scope) from one the system derived. Automatic
--     re-derivation must never silently overwrite a human decision, so the
--     override flag is what makes safe auto-refresh possible.
--
-- Idempotent / additive: ADD COLUMN IF NOT EXISTS; no column is dropped.
-- =============================================================================

-- 1. Qualifying-criterion inputs on the Initial Incident Form vehicle record.
ALTER TABLE incident_vehicles ADD COLUMN IF NOT EXISTS vehicle_class TEXT;
ALTER TABLE incident_vehicles ADD COLUMN IF NOT EXISTS gvwr_lbs      NUMERIC;

COMMENT ON COLUMN incident_vehicles.vehicle_class IS
    'FHWA/GVWR vehicle class as recorded on the IIF, e.g. ''7'' or ''8'' (DL2, §3.1). '
    'Evaluated against the study''s configured `vehicle_classes` parameter — NOT '
    'hardcoded to Phase 1. NULL means not yet recorded, in which case the '
    'classifier falls back to gvwr_lbs and then to the is_cmv proxy.';
COMMENT ON COLUMN incident_vehicles.gvwr_lbs IS
    'Gross vehicle weight rating in pounds (DL2, §3.1). Evaluated against the '
    'study''s configured `min_gvwr_lbs` parameter (Phase 1: 26001). Secondary to '
    'vehicle_class when both are recorded.';

-- 2. Manual-override marker on the derived classification.
ALTER TABLE crash_scope_classifications
    ADD COLUMN IF NOT EXISTS is_manual_override BOOLEAN NOT NULL DEFAULT false;

COMMENT ON COLUMN crash_scope_classifications.is_manual_override IS
    'TRUE when a human set this classification through PUT /crashes/{id}/scope. '
    'Automatic re-derivation (on vehicle change, IIF submit, or fatality-count '
    'edit) skips rows flagged here so a deliberate decision is never clobbered. '
    'POST /scope/reclassify clears it — that is an explicit request to re-derive.';

-- Backfill: every classification that already reached a decision predates the
-- automatic re-derivation path, so treat it as intentional and freeze it. Only
-- UNDETERMINED rows — the ones the defect stranded — remain eligible for
-- automatic repair. Without this, applying the fix would retroactively rewrite
-- existing (including seeded/demo) classifications the next time anyone edited
-- a vehicle on those crashes.
UPDATE crash_scope_classifications
   SET is_manual_override = true
 WHERE scope <> 'UNDETERMINED'
   AND is_manual_override = false;
