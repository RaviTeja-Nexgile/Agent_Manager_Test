-- =============================================================================
-- CCFP IT Solution - Migration 0027: MCSAP Inspector read access to the
-- Analysis Environment (GAP-BRD-02 follow-up)
-- =============================================================================
-- Migration 0022 granted analysis_env:read to STATE_CMV_ANALYST and STATE_USER
-- but not to MCSAP_INSPECTOR. That was a misreading of the BRD.
--
-- The January 2026 BRD's "Data Analysis and Sharing" chapter enumerates the
-- environment's users (p. 14), and MCSAP CMV Inspectors are named explicitly:
--
--     Participating State Users
--       o State CMV Data Analysts
--       o MCSAP CMV Inspectors            <-- missed by 0022
--       o State Enforcement
--       o State Crash Reconstructionists/Post-Crash Investigators
--
-- and the Visualize access table (p. 17) gives Participating State Users
-- "Read - No PII, Only View Own Data" for dashboards, visualizations, reports
-- and tables.
--
-- Read only. Inspectors get no manage/dataset/share grant: the BRD reserves
-- creating derived views for the CCFP Project Team and sharing for the CCFP
-- Database Administrator.
--
-- No new enforcement is needed for "no PII, only view own data" — an inspector
-- is a State-scoped principal, so the existing audience resolution already
-- restricts them to datasets carrying an ACTIVE PARTICIPATING_STATE share for
-- their State, and filters rows to that State. The database trigger guarantees
-- such a dataset is non-PII and State-partitioned. This migration therefore
-- widens *who* may read, not *what* is readable.
-- =============================================================================

INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id
FROM roles r
JOIN permissions p ON p.code = 'analysis_env:read'
WHERE r.code = 'MCSAP_INSPECTOR'
ON CONFLICT DO NOTHING;
