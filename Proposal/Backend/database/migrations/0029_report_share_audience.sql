-- =============================================================================
-- CCFP IT Solution - Migration 0026: audience on report shares
-- =============================================================================
-- The January 2026 BRD reassigns every outward-sharing row from the CCFP
-- Project Team to the CCFP Database Administrator (FMCSA CTO Resource):
--
--   Share ... with the CCFP Project Team ............ DBA   C,R,U,D
--   Share ... with Other Federal Users (BTS, NHTSA, NTSB) .. DBA  Create, Read
--   Share ... with participating States (State-specific, no PII) .. DBA  C,R
--   Share ... with the Public (no PII, summary de-identified only) . DBA  C,R
--
-- The Project Team keeps creating derived views and sharing dashboards; the DBA
-- owns the DATA-sharing pipeline. Enforcing that split needs the share row to
-- record WHICH AUDIENCE it targets — report_shares only recorded a user, role or
-- organization, so "who is this being released to" was unanswerable and the
-- restriction was unenforceable.
--
-- The gap analysis preferred modelling audience on the share row rather than
-- widening reports.visibility. analysis_dataset_shares does not
-- exist yet and belongs to another work item, so the same idea is applied to the
-- share table that does exist. When BRD-02 lands, its dataset shares need this
-- identical audience + authorization rule.
--
-- The original CHECK required at least one of user/role/org. An audience-only
-- share is now a legitimate target, so the constraint is widened to accept it —
-- located by catalog lookup because it was created unnamed.
--
-- Idempotent / additive: IF NOT EXISTS throughout; existing shares get NULL
-- audience and keep behaving exactly as before.
-- =============================================================================

-- A brand-new type, so creating and using it in one transaction is safe (unlike
-- ALTER TYPE ... ADD VALUE, which is why migration 0025 is separate).
DO $$ BEGIN
    CREATE TYPE share_audience AS ENUM
        ('FMCSA_FEDERAL','OTHER_FEDERAL','STATE','PUBLIC');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

ALTER TABLE report_shares
    ADD COLUMN IF NOT EXISTS audience share_audience;

-- carries through: a STATE-audience share must say which State.
ALTER TABLE report_shares
    ADD COLUMN IF NOT EXISTS audience_state_code CHAR(2) REFERENCES ref_us_states(code);

-- Widen the "must have a target" CHECK to accept an audience-only share. The
-- original constraint was unnamed, so find it by definition rather than guessing
-- PostgreSQL's generated name.
DO $$
DECLARE
    conname_found TEXT;
BEGIN
    SELECT c.conname INTO conname_found
      FROM pg_constraint c
      JOIN pg_class t ON t.oid = c.conrelid
     WHERE t.relname = 'report_shares'
       AND c.contype = 'c'
       AND pg_get_constraintdef(c.oid) LIKE '%shared_with_user_id%'
     LIMIT 1;
    IF conname_found IS NOT NULL THEN
        EXECUTE format('ALTER TABLE report_shares DROP CONSTRAINT %I', conname_found);
    END IF;
END $$;

ALTER TABLE report_shares
    DROP CONSTRAINT IF EXISTS ck_report_shares_target;
ALTER TABLE report_shares
    ADD CONSTRAINT ck_report_shares_target CHECK (
        shared_with_user_id IS NOT NULL
        OR shared_with_role_id IS NOT NULL
        OR shared_with_org_id IS NOT NULL
        OR audience IS NOT NULL
    );

-- A State-specific share is meaningless without the State, and a State code on
-- any other audience is a mistake worth rejecting at the boundary.
ALTER TABLE report_shares
    DROP CONSTRAINT IF EXISTS ck_report_shares_audience_state;
ALTER TABLE report_shares
    ADD CONSTRAINT ck_report_shares_audience_state CHECK (
        (audience = 'STATE' AND audience_state_code IS NOT NULL)
        OR (audience IS DISTINCT FROM 'STATE' AND audience_state_code IS NULL)
        OR audience IS NULL
    );

CREATE INDEX IF NOT EXISTS idx_report_shares_audience
    ON report_shares (audience)
    WHERE audience IS NOT NULL;

COMMENT ON COLUMN report_shares.audience IS
    'Audience tier this share releases the report to (BRD Jan-2026). '
    'NULL = a directed user/role/org share, the only kind that existed before. '
    'Only the CCFP Database Administrator may create OTHER_FEDERAL, STATE or '
    'PUBLIC shares; the CCFP Project Team is limited to FMCSA_FEDERAL.';
COMMENT ON COLUMN report_shares.audience_state_code IS
    'Which State a STATE-audience share targets. '
    'Required for STATE, forbidden otherwise.';
