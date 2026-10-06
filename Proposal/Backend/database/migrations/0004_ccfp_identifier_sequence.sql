-- =============================================================================
-- CCFP IT Solution - Migration 0004: race-safe CCFP identifier sequence (CRAS-7)
-- =============================================================================
-- Every crash gets one stable CCFP identifier (spec §3.4, §11.3). The legacy
-- generator derived the counter with `SELECT COUNT(*) ... + 1`, which is a
-- check-then-act race: concurrent create_crash calls can read the same count
-- and mint colliding identifiers against the UNIQUE constraint on
-- crashes.ccfp_identifier. A PostgreSQL sequence makes numbering atomic and
-- monotonic so concurrent transactions each get a distinct integer (the feature
-- agent calls nextval('ccfp_identifier_seq')). No external/distributed counter.
--
-- Initialize the sequence PAST the current crash count so it never re-issues a
-- value embedded in an already-seeded identifier. setval(..., is_called => true)
-- means the next nextval() returns the given value + 1; GREATEST(..., 1) guards
-- the empty-table case. Idempotent: CREATE SEQUENCE IF NOT EXISTS, and the
-- setval only ever advances the sequence forward (never below current).
-- =============================================================================

CREATE SEQUENCE IF NOT EXISTS ccfp_identifier_seq;

SELECT setval(
    'ccfp_identifier_seq',
    GREATEST(
        (SELECT COUNT(*) FROM crashes),
        (SELECT last_value FROM ccfp_identifier_seq),
        1
    ),
    true
);
