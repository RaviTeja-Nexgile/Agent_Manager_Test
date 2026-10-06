-- =============================================================================
-- CCFP IT Solution - Migration 0025: deliver the BTS routing notifications the
-- scope-classification defect swallowed
-- =============================================================================
-- BRD DL1, §5 Phase 2, §8.11.
--
-- Migration 0024 + the `refresh_scope` change fixed the *mechanism*: an in-scope
-- crash submitted from now on notifies both the State CMV Data Analyst and the
-- BTS CIPSEA Agent. Neither repaired the *record*. Crashes whose Initial
-- Incident Form was submitted while the defect was live reached SUBMITTED /
-- ROUTED carrying the provisional UNDETERMINED verdict, matched neither routing
-- branch, and so were announced to nobody at BTS. Re-deriving their scope
-- afterwards corrects the stored classification but emits nothing — the routing
-- notification is tied to the submit/transition event, which is long past.
--
-- The BRD requirement is about the recipient, not the moment: "in-scope crashes
-- would be routed to both the State CMV Data Analyst and BTS CIPSEA Agent."
-- A crash sitting IN_SCOPE with a submitted form and no BTS notification is
-- still in breach of it today, so the notification is delivered here.
--
-- Scope of the repair — deliberately narrow:
--   * only IN_SCOPE, non-supplemental classifications (exactly the branch that
--     routes to BTS in `submit_iif`; supplemental records are retained, not
--     interviewed),
--   * only crashes whose IIF actually reached SUBMITTED / ROUTED, so nothing is
--     announced for a form still being drafted,
--   * only recipients who do not already hold an IN_SCOPE_ROUTING notification
--     for that crash — no duplicate lands in an inbox that was routed correctly.
--
-- Idempotent: the NOT EXISTS guard makes a re-run insert zero rows.
-- =============================================================================

-- The missing notifications, one per (crash, active BTS CIPSEA Agent) pair, each
-- audited by the same statement. Title/message/channel deliberately mirror
-- `submit_iif` verbatim so a recovered notification is indistinguishable from
-- one routed on time. RETURNING feeds the audit insert, so the trail covers
-- exactly the rows this migration created — no timestamp guessing.
WITH delivered AS (
INSERT INTO notifications (
    recipient_user_id, notification_type, crash_id, title, message, channel, status
)
SELECT bts.id,
       'IN_SCOPE_ROUTING',
       c.id,
       'In-scope crash for CIPSEA interview',
       'In-scope crash ' || c.ccfp_identifier || ' routed for confidential interview.',
       'EMAIL',
       'SENT'
  FROM crashes c
  JOIN crash_scope_classifications sc ON sc.crash_id = c.id
  JOIN initial_incident_forms f       ON f.crash_id  = c.id
 CROSS JOIN (
        -- Mirrors app.core.notifications.users_with_role('BTS_CIPSEA_AGENT'):
        -- active holders of the role, unscoped by State (BTS is federal).
        SELECT DISTINCT u.id
          FROM users u
          JOIN user_role_assignments ura ON ura.user_id = u.id
          JOIN roles r                   ON r.id        = ura.role_id
         WHERE r.code = 'BTS_CIPSEA_AGENT'
           AND u.status = 'ACTIVE'
       ) AS bts
 WHERE sc.scope = 'IN_SCOPE'
   AND sc.is_supplemental = false
   AND f.status IN ('SUBMITTED', 'ROUTED')
   AND NOT EXISTS (
           SELECT 1
             FROM notifications n
            WHERE n.crash_id = c.id
              AND n.notification_type = 'IN_SCOPE_ROUTING'
              AND n.recipient_user_id = bts.id
       )
RETURNING id, crash_id
)
-- A delivery the system owes and pays late is still a state-changing action, so
-- it leaves a trail like any other (§8.11). actor_user_id is NULL: the system,
-- not a person, performed it.
INSERT INTO audit_logs (actor_user_id, action, entity_type, entity_id, crash_id, after_state)
SELECT NULL,
       'BACKFILL_BTS_ROUTING',
       'notification',
       d.id,
       d.crash_id,
       jsonb_build_object(
           'notification_type', 'IN_SCOPE_ROUTING',
           'source', 'migration 0025 backfill: BTS routing missed while the scope-classification defect was live'
       )
  FROM delivered d;
