-- =============================================================================
-- CCFP IT Solution - Seed 0018: BTS routing consistency for seeded crashes
-- =============================================================================
-- BRD DL1, §5 Phase 2. Seed-phase counterpart to migration
-- `0025_backfill_bts_routing_notifications.sql`.
--
-- Why both: `migrate.py up` applies every migration BEFORE any seed. On a fresh
-- database 0025 therefore runs against an empty schema and inserts nothing, and
-- the demo crashes that arrive moments later in the seed phase — several of
-- which are IN_SCOPE with a submitted Initial Incident Form — would land with no
-- BTS CIPSEA routing notification. That is the exact signature of the defect
-- 0025 exists to repair, so a freshly seeded environment would reproduce the
-- reported symptom and the next tester would file it again.
--
-- Running the same rule here closes that window. The statement is identical to
-- 0025's and equally idempotent (the NOT EXISTS guard), so applying it in both
-- phases is safe: whichever runs second inserts nothing.
--
-- This does NOT invent demo data. It only gives an already-seeded in-scope,
-- already-submitted crash the notification the BRD says it must have; seeded
-- crashes that are out-of-scope, supplemental, or whose form is still a draft
-- are untouched, as are the crashes whose routing notification the seeds
-- already provide.
-- =============================================================================

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
INSERT INTO audit_logs (actor_user_id, action, entity_type, entity_id, crash_id, after_state)
SELECT NULL,
       'BACKFILL_BTS_ROUTING',
       'notification',
       d.id,
       d.crash_id,
       jsonb_build_object(
           'notification_type', 'IN_SCOPE_ROUTING',
           'source', 'seed 0018: BTS routing consistency for seeded in-scope crashes'
       )
  FROM delivered d;
