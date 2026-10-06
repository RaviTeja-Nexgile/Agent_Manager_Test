-- =============================================================================
-- CCFP IT Solution - Migration 0003: audit_logs immutability (COMP-3)
-- =============================================================================
-- Enforces append-only audit_logs at the DATABASE level (spec §14.2 "Immutable
-- audit logs for state-changing actions"; §11.1 audit_logs = "Immutable audit
-- event records"). Application code (app/core/audit.py:record_audit) already only
-- appends, but the app connects as the schema owner (dot_ccfp_user) and could
-- otherwise UPDATE/DELETE. A BEFORE UPDATE OR DELETE trigger raises an exception
-- as the primary guard; REVOKE on the app role + PUBLIC is layered defense.
--
-- Idempotent / re-runnable: CREATE OR REPLACE FUNCTION, DROP TRIGGER IF EXISTS
-- then CREATE TRIGGER, and REVOKE (a no-op if already revoked). Safe under
-- `python migrate.py up`. INSERT is deliberately untouched.
-- =============================================================================

CREATE OR REPLACE FUNCTION ccfp_block_audit_mutation() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'audit_logs is append-only: % is not permitted', TG_OP
        USING ERRCODE = 'restrict_violation';
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_audit_immutable ON audit_logs;
CREATE TRIGGER trg_audit_immutable
    BEFORE UPDATE OR DELETE ON audit_logs
    FOR EACH ROW EXECUTE FUNCTION ccfp_block_audit_mutation();

-- Defense-in-depth. The trigger is the authoritative guard because the table
-- owner (dot_ccfp_user) retains its privileges even after REVOKE; these lines
-- still block any non-owner role from mutating audit rows.
REVOKE UPDATE, DELETE, TRUNCATE ON audit_logs FROM PUBLIC;
REVOKE UPDATE, DELETE, TRUNCATE ON audit_logs FROM dot_ccfp_user;
