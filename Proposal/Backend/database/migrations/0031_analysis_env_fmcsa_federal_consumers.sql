-- =============================================================================
-- CCFP IT Solution - Migration 0031: FMCSA HQ, FMCSA Enforcement and the CCFP
-- Super User reach the Analysis Environment (GAP-BRD-02 / -04 / -06 follow-up)
-- =============================================================================
-- Seed 0020 created the three roles the January 2026 BRD introduces and gave
-- them report-level grants, but no `analysis_env:*` permission. The result is
-- that three roles the new BRD created specifically to consume the Analysis
-- Environment cannot reach it at all — FMCSA_HQ and FMCSA_ENFORCEMENT hold four
-- permissions each (notification:read, public:read, report:read,
-- report:download), which is strictly less than STATE_USER, who already holds
-- analysis_env:read.
--
-- This is the same class of omission migration 0027 fixed for MCSAP_INSPECTOR:
-- the tier model was right and the grant was simply never made. All three roles
-- are already members of FMCSA_FEDERAL_ROLES in app/core/security.py, so the
-- audience resolution admits them as soon as they hold the permission — this
-- migration widens *who may read*, not *what is readable*.
--
-- The BRD's "Data Analysis and Sharing" chapter enumerates the environment's
-- users (p. 14):
--
--     FMCSA Federal Users
--       o CCFP Project Team
--       o CCFP Database Administrator
--       o FMCSA HQ                       <-- missed by seed 0020
--       o FMCSA Enforcement              <-- missed by seed 0020
--
-- and its Visualize access table (p. 15) gives "FMCSA Users and Other Federal
-- Users (PII)" Read on "dashboards, visualizations, reports, and tables".
--
-- Grants, kept minimal and matched to the BRD's own access column:
--
--   FMCSA_HQ / FMCSA_ENFORCEMENT  analysis_env:read
--       Consumers. The BRD's access column for them is Read. No dataset, share
--       or statistics grant: creating derived views is reserved to the CCFP
--       Project Team, sharing to the CCFP Database Administrator (p. 14), and
--       statistical analysis to the CCFP Project Team (p. 15).
--
--   CCFP_SUPER_USER               analysis_env:read, analysis_env:dataset
--       The BRD (p. 15) grants the Super User "Create and share dashboards,
--       visualizations, reports, and tables ... Create, Read, Update, Delete"
--       alongside the CCFP Project Team. The dashboards and tables in question
--       are backed by analysis datasets, so CRUD on them requires the dataset
--       grant the Project Team already holds. The *sharing* half of that
--       sentence is already satisfied by report:share, which seed 0020 granted;
--       analysis_env:share is deliberately NOT added, because p. 14 assigns
--       sharing of Aggregated Data and Analysis Environment data to the CCFP
--       Database Administrator alone and that separation is load-bearing.
-- =============================================================================

INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id
FROM (VALUES
 ('FMCSA_HQ',          ARRAY['analysis_env:read']),
 ('FMCSA_ENFORCEMENT', ARRAY['analysis_env:read']),
 ('CCFP_SUPER_USER',   ARRAY['analysis_env:read','analysis_env:dataset'])
) AS m(role_code, perms)
JOIN roles r ON r.code = m.role_code
JOIN permissions p ON p.code = ANY(m.perms)
ON CONFLICT DO NOTHING;
