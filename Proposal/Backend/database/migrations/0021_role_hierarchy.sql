-- =============================================================================
-- CCFP IT Solution - Migration 0021: role hierarchy
-- =============================================================================
-- The SOO requires "Role-based access aligned with the hierarchy of roles
-- established in SafeSpect."
--
-- The application's 12 role codes were derived from the BRD's prose list of
-- users and are FLAT: `role_permissions` is a direct many-to-many, so no role
-- inherits from another. A hierarchy ("a supervisor role has everything the
-- inspector role has, plus more") cannot be expressed at all.
--
-- This migration adds the STRUCTURE only. It deliberately does NOT re-parent any
-- existing role, because the actual SafeSpect hierarchy is not specified in any
-- document currently available (it is Task 2 Discovery work in the SOO). Every
-- role ships with parent_role_id IS NULL, which resolves to exactly today's flat
-- behaviour - so this migration is behaviour-preserving by construction.
--
-- When FMCSA supplies the SafeSpect role hierarchy, mirroring it becomes an
-- UPDATE of parent_role_id values plus a seed change - no schema rebuild and no
-- restructuring of role_permissions.
--
-- Cycle safety: a self-referencing parent chain could loop (A -> B -> A) and
-- hang permission resolution. Two defences:
--   1. A trigger rejects a direct self-parent and any INSERT/UPDATE that would
--      close a cycle, walking the chain with a depth cap.
--   2. app/core/security.py resolves permissions with a visited-set walk, so
--      even a cycle that somehow reached the table cannot spin forever.
-- =============================================================================

ALTER TABLE roles
    ADD COLUMN IF NOT EXISTS parent_role_id UUID REFERENCES roles(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_roles_parent ON roles(parent_role_id);

COMMENT ON COLUMN roles.parent_role_id IS
    'Optional parent role. A role inherits its ancestors'' '
    'permissions and access groups. NULL = no inheritance, which reproduces the '
    'original flat model exactly. Populated once the SafeSpect role hierarchy '
    'is supplied by FMCSA.';

-- --------------------------------------------------------------------------
-- Cycle guard. Rejects self-parenting and any edge that would close a loop.
-- --------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION roles_reject_parent_cycle() RETURNS TRIGGER AS $$
DECLARE
    cursor_id UUID;
    hops      INT := 0;
BEGIN
    IF NEW.parent_role_id IS NULL THEN
        RETURN NEW;
    END IF;

    IF NEW.parent_role_id = NEW.id THEN
        RAISE EXCEPTION 'role % cannot be its own parent', NEW.id
            USING ERRCODE = 'check_violation';
    END IF;

    -- Walk upward from the proposed parent. If we arrive back at NEW.id the
    -- edge would close a cycle. The hop cap is a belt-and-braces stop in case
    -- a pre-existing cycle is already present in the table.
    cursor_id := NEW.parent_role_id;
    WHILE cursor_id IS NOT NULL AND hops < 64 LOOP
        IF cursor_id = NEW.id THEN
            RAISE EXCEPTION 'role parent cycle detected for role %', NEW.id
                USING ERRCODE = 'check_violation';
        END IF;
        SELECT parent_role_id INTO cursor_id FROM roles WHERE id = cursor_id;
        hops := hops + 1;
    END LOOP;

    IF hops >= 64 THEN
        RAISE EXCEPTION 'role hierarchy too deep or already cyclic (role %)', NEW.id
            USING ERRCODE = 'check_violation';
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_roles_reject_parent_cycle ON roles;
CREATE TRIGGER trg_roles_reject_parent_cycle
    BEFORE INSERT OR UPDATE OF parent_role_id ON roles
    FOR EACH ROW EXECUTE FUNCTION roles_reject_parent_cycle();
