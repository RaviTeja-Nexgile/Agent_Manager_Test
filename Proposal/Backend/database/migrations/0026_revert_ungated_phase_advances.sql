-- =============================================================================
-- CCFP IT Solution - Migration 0026: revert lifecycle advances that bypassed the
-- QC & Completeness gate
-- =============================================================================
-- BRD DL5, DL6, DA11, §5.
--
-- The lifecycle had no gate: `advance_phase` compared two phase ordinals and
-- nothing else, so saving contributing factors carried a crash straight from
-- Quality Control into Analysis & Reporting even with an open Critical QC
-- failure and an INCOMPLETE record. The code gate (`phase_gate_blockers`) closes
-- that for every future advance. It cannot move a record that already went
-- through — those crashes are still sitting in a phase they were never eligible
-- to enter, and the UI offers "Advance to Publish" on them.
--
-- WHAT THIS REPAIRS — and what it deliberately does not.
--
-- Records were separated by evidence, not by guesswork, using the application's
-- own gate evaluation (`phase_gate_blockers`) against live data:
--
--   * 4 crashes are unfit AND carry an ADVANCE_PHASE audit row recording the
--     runtime move into their current phase. Those moves are the defect's doing
--     and are reverted here.
--   * 7 further crashes are unfit but have NO advance audit row — they were
--     seeded directly into ANALYSIS / PUBLICATION as demo state. Rewriting them
--     would silently gut the publication and reporting demos, so they are left
--     alone. They are demo fixtures, not damage.
--
-- Each record returns to the phase its own audit row says it came FROM, so this
-- reverts exactly the illegitimate transition rather than assuming a
-- destination. Nothing is deleted: the original ADVANCE_PHASE audit row stays,
-- and a REVERT_UNGATED_ADVANCE row is added beside it.
--
-- These records are not stuck. Once the missing IIF / required attributes /
-- inspection are supplied and the Critical QC failure clears, the normal
-- advance path moves them forward again — now legitimately.
--
-- Idempotent and environment-safe: every crash is matched by CCFP identifier and
-- only moved while it is still parked on the phase the audited advance put it
-- in. A re-run, or an environment without these records, updates zero rows.
-- =============================================================================

WITH ungated AS (
    -- The audited advance that put each crash where it now sits, with the phase
    -- it came from. DISTINCT ON keeps the most recent such move per crash.
    SELECT DISTINCT ON (c.id)
           c.id                                AS crash_id,
           c.lifecycle_phase                   AS current_phase,
           a.after_state ->> 'from'            AS revert_to
      FROM crashes c
      JOIN audit_logs a
        ON a.crash_id = c.id
       AND a.action = 'ADVANCE_PHASE'
       AND a.after_state ->> 'to' = c.lifecycle_phase::text
     WHERE c.ccfp_identifier IN (
               -- Identified by running the application's gate evaluation; see header.
               'CCFP-2026-KS-000008',   -- DATA_COLLECTION -> ANALYSIS, 2026-06-03
               'CCFP-2026-KS-000010',   -- QUALITY_CONTROL -> ANALYSIS, 2026-06-03
               'CCFP-2026-KS-000329',   -- QUALITY_CONTROL -> ANALYSIS, 2026-06-03
               'CCFP-2026-TX-000114'    -- QUALITY_CONTROL -> ANALYSIS, 2026-08-01 (the reported repro)
           )
       AND c.lifecycle_phase IN ('ANALYSIS', 'PUBLICATION')
       AND a.after_state ->> 'from' IS NOT NULL
     ORDER BY c.id, a.occurred_at DESC
),
reverted AS (
    UPDATE crashes c
       SET lifecycle_phase = u.revert_to::crash_lifecycle_phase
      FROM ungated u
     WHERE c.id = u.crash_id
    RETURNING c.id, u.current_phase, u.revert_to
)
-- Reverting a lifecycle phase is a state change and is audited like any other
-- (§8.11). actor_user_id is NULL: the system, not a person, performed it.
INSERT INTO audit_logs (actor_user_id, action, entity_type, entity_id, crash_id,
                        before_state, after_state)
SELECT NULL,
       'REVERT_UNGATED_ADVANCE',
       'crash',
       r.id,
       r.id,
       jsonb_build_object('lifecycle_phase', r.current_phase),
       jsonb_build_object(
           'lifecycle_phase', r.revert_to,
           'source', 'migration 0026: advance bypassed the QC & Completeness gate (DL5, DL6, DA11)'
       )
  FROM reverted r;
