-- =============================================================================
-- Seed 0017 - Backfill the State binding on pre-existing STATE reports
--
-- =============================================================================
-- Migration 0024 adds reports.state_code and treats NULL as "not State-bound",
-- so reports created before the column existed keep their previous audience
-- rather than vanishing for the State users who could already see them.
--
-- That back-compat rule leaves a real hole in the seeded data: the demo report
-- "Kansas Crash Working Table" is STATE-visibility but unbound, so a Texas
-- analyst can read a report that is Kansas by name and by content. Binding it
-- is the whole point of State-scoping reports, so bind it.
--
-- Scoped deliberately narrowly - matched by exact name, not by guessing a State
-- out of report titles. Any real deployment needs a considered backfill of its
-- own; an unbound STATE report stays readable by every participating State
-- until someone decides which State owns it.
--
-- Idempotent: the WHERE clause no-ops once the binding is set.
-- =============================================================================

UPDATE reports
   SET state_code = 'KS'
 WHERE name = 'Kansas Crash Working Table'
   AND visibility = 'STATE'
   AND state_code IS NULL;
