-- =============================================================================
-- CCFP IT Solution - Migration 0007: access groups (AUTH-3)
-- =============================================================================
-- §4 (l.140-142): authorization by data sensitivity, layered over operational
-- roles as first-class access groups (Federal/PII, State/No-PII, Public, plus a
-- CIPSEA group). Today PII/CIPSEA visibility is derived from a hardcoded set of
-- permission codes in app/core/security.py; this models the groups as data so
-- backend sensitivity logic and the frontend can read a single source of truth.
--
-- `data_sensitivity_max` carries the highest DataSensitivity a group may view as
-- plain TEXT (vocabulary governed by app.enums.DataSensitivity) — no native PG
-- enum, to keep the vocabulary configurable per phase without a rebuild.
--
-- Idempotent / additive: IF NOT EXISTS on table/index creation.
-- =============================================================================

CREATE TABLE IF NOT EXISTS access_groups (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    code                TEXT NOT NULL UNIQUE,
    name                TEXT NOT NULL,
    data_sensitivity_max TEXT NOT NULL,   -- highest DataSensitivity the group may view
    description         TEXT,
    is_active           BOOLEAN NOT NULL DEFAULT TRUE,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS role_access_groups (
    role_id   UUID NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
    group_id  UUID NOT NULL REFERENCES access_groups(id) ON DELETE CASCADE,
    PRIMARY KEY (role_id, group_id)
);

COMMENT ON TABLE access_groups IS
    'First-class access groups (AUTH-3, §4 l.142) — PII / NOPII / CIPSEA / PUBLIC. '
    'data_sensitivity_max is the highest DataSensitivity the group may view.';
COMMENT ON TABLE role_access_groups IS
    'Role -> access-group membership (AUTH-3). Mirrors role_permissions.';
