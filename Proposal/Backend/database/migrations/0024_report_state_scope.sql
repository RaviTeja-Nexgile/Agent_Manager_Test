-- =============================================================================
-- CCFP IT Solution - Migration 0024: State-bind reports
-- =============================================================================
-- The January 2026 BRD states the constraint explicitly for the first time:
--   * Visualize access table: "Participating State Users (No PII, ONLY VIEW OWN
--     DATA)"
--   * Manage/Share: "data shared would be State-specific", "data will be
--     State-specific, have no PII"
--   * Visualize system requirement: "Provide role-based access to data sets
--     (e.g., State-limited views)."
--
-- Crash-level scoping already honours this (scope_crash_query confines a
-- State-scoped principal to allowed_states). REPORTS DID NOT: `_visible_filter`
-- in app/features/reports.py granted every caller holding any State scope
-- visibility of EVERY report with visibility = 'STATE', because the reports
-- table carried nothing to compare a State against. A Kansas analyst could read
-- a Texas report through GET /reports, GET /reports/{id} and the CSV download.
--
-- This adds the missing discriminator. NULL means "not State-bound" and stays
-- visible to every State user, so reports created before this change keep their
-- current audience rather than silently disappearing; only a report that
-- declares a State becomes restricted to it.
--
-- Idempotent / additive: ADD COLUMN IF NOT EXISTS, no existing row is altered.
-- =============================================================================

ALTER TABLE reports
    ADD COLUMN IF NOT EXISTS state_code CHAR(2) REFERENCES ref_us_states(code);

-- Partial: only State-bound reports are ever filtered on this column.
CREATE INDEX IF NOT EXISTS idx_reports_state_code
    ON reports (state_code)
    WHERE state_code IS NOT NULL;

COMMENT ON COLUMN reports.state_code IS
    'State this report is bound to (BRD Jan-2026 "Only View Own '
    'Data"). NULL = not State-bound and visible to every State user, preserving '
    'the audience of reports created before the column existed. When set, only '
    'principals whose scope includes this State may read or download the report.';
