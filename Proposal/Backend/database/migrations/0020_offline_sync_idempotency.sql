-- =============================================================================
-- CCFP IT Solution - Migration 0020: offline-sync idempotency keys
-- =============================================================================
-- The SOO requires an "offline-first" client: the MCSAP CMV Inspector completes
-- the Initial Incident Form at the crash scene, frequently with no connectivity,
-- and the device replays queued writes when the signal returns.
--
-- Replay is only safe if create endpoints are idempotent. Before this migration:
--   * PUT  /initial-incident   - upsert keyed on crash_id; already safe.
--   * POST /incident-vehicles  - guarded by the (crash_id, vehicle_number)
--                                natural key; a replay raised 409 rather than
--                                duplicating, so it was duplicate-safe but NOT
--                                idempotent (the client could not distinguish
--                                "my earlier write landed" from "a real clash").
--   * POST /incident-persons   - UNGUARDED. A person has no natural key, so a
--                                replayed sync silently inserted the person twice.
--
-- The duplicate-person case is the dangerous one: incident_persons rows carry
-- `injury` (FATALITY | INJURY | NO_INJURY), and fatality counts feed the
-- qualifying-crash rule (>= 1 fatality, documentation §3.1). A duplicated
-- fatality can therefore change whether a crash is in the study at all.
--
-- Fix: an optional client-generated idempotency key. The offline client mints a
-- UUID per record it creates locally and replays that same key on every attempt;
-- the server returns the already-created row instead of inserting a second one.
--
-- Additive and backward-compatible:
-- * Column is NULLABLE - online callers that send no key behave exactly as
-- before, and every pre-existing row keeps client_uuid IS NULL.
-- * The unique index is PARTIAL (WHERE client_uuid IS NOT NULL) so the many
-- existing NULL rows do not collide with one another.
-- * Scoped per crash, not global: two devices working different crashes can
-- never interfere, and a key only has to be unique within its own crash.
-- =============================================================================

ALTER TABLE incident_persons  ADD COLUMN IF NOT EXISTS client_uuid UUID;
ALTER TABLE incident_vehicles ADD COLUMN IF NOT EXISTS client_uuid UUID;

-- One row per (crash, client key). Partial so pre-existing / online-created rows
-- (client_uuid IS NULL) stay unconstrained. This index is also the concurrency
-- backstop: if two replays race, the second INSERT fails here rather than
-- creating a duplicate, and the endpoint retries the read.
CREATE UNIQUE INDEX IF NOT EXISTS uq_incident_persons_client_uuid
    ON incident_persons(crash_id, client_uuid)
    WHERE client_uuid IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_incident_vehicles_client_uuid
    ON incident_vehicles(crash_id, client_uuid)
    WHERE client_uuid IS NOT NULL;

COMMENT ON COLUMN incident_persons.client_uuid IS
    'Offline-sync idempotency key minted by the client. NULL for '
    'records created online. Unique per crash; a replayed create returns the '
    'existing row instead of inserting a duplicate person.';

COMMENT ON COLUMN incident_vehicles.client_uuid IS
    'Offline-sync idempotency key minted by the client. NULL for '
    'records created online. Unique per crash; complements the existing '
    '(crash_id, vehicle_number) natural-key guard.';
