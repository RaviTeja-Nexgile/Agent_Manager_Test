-- =============================================================================
-- Seed 0018 - Authorization model rewrite (07)
-- ALL user data is fictitious and for development/testing/demo only.
-- =============================================================================
-- The January 2026 BRD rewrote who gets what. Four changes land together
-- because they describe one model:
--
--   BRD-04  New role "CCFP Super User (FMCSA Program Office Resource)", holding
--           Create/Read/Update/Delete on dashboards, visualizations, reports and
--           tables jointly with the CCFP Project Team. Defined ONLY by its
--           access-table row — it appears in neither Appendix A nor Appendix B,
--           which is worth raising back to FMCSA.
--
--   BRD-05  NTSB named as a consumer of shared data for the first time.
--
--   BRD-06  FMCSA HQ and FMCSA Enforcement promoted from footnote examples to
--           first-class members of the FMCSA Federal tier.
--
--   BRD-07  Outward sharing moved from the CCFP Project Team to the CCFP
--           Database Administrator, who until now held ZERO report:* and ZERO
--           analytics:* permissions. report:publish sat only on SYSTEM_ADMIN, so
--           no business role could publish to the public at all.
--
-- Note on the Data Scientist: the new BRD stops naming CCFP Data Scientist among
-- Federal Users. The role is NOT removed here — it still exists and still holds
-- its analytical permissions; it simply is no longer called out in the BRD's
-- audience list. Removing a working role on the strength of an omission would be
-- over-reading the document.
--
-- analysis_env:* permissions are deliberately NOT created here. They belong to
-- the Analysis Environment, which is a separate work item; inventing
-- them now would collide with it.
-- =============================================================================

-- ---------------------------------------------------------------------------
-- BRD-04 / BRD-06: new roles
-- ---------------------------------------------------------------------------
INSERT INTO roles (code, name, description) VALUES
 ('CCFP_SUPER_USER','CCFP Super User','FMCSA Program Office resource; creates and shares dashboards, visualizations, reports and tables alongside the CCFP Project Team (BRD Jan-2026 Visualize access table).'),
 ('FMCSA_HQ','FMCSA HQ','FMCSA Headquarters consumer of CCFP outputs; first-class member of the FMCSA Federal audience tier.'),
 ('FMCSA_ENFORCEMENT','FMCSA Enforcement','FMCSA enforcement consumer of CCFP outputs; first-class member of the FMCSA Federal audience tier.')
ON CONFLICT (code) DO NOTHING;

-- ---------------------------------------------------------------------------
-- BRD-05: National Transportation Safety Board organization
-- ---------------------------------------------------------------------------
-- 'NTSB' was added to organization_type in migration 0025; a separate file means
-- a separate transaction, which is what PostgreSQL requires before the new enum
-- value can be used.
INSERT INTO organizations (name, org_type, state_code, description) VALUES
 ('National Transportation Safety Board','NTSB',NULL,'Other Federal consumer of CCFP shared data (BRD Jan-2026 Appendix D / Manage-Share access table).')
ON CONFLICT DO NOTHING;

-- ---------------------------------------------------------------------------
-- BRD-04: Super User grants
-- ---------------------------------------------------------------------------
-- "Create and share dashboards, visualizations, reports, and tables with FMCSA
-- users, other Federal users, participating State users, and public users as
-- determined by CCFP Project Team" — CRUD.
INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id
FROM (VALUES
 ('CCFP_SUPER_USER', ARRAY['report:create','report:read','report:share','report:download','report:publish','analytics:query','analytics:dashboard','aggregated:read','notification:read']),
 -- BRD-06: HQ and Enforcement are consumers, mirroring FEDERAL_USER's reach.
 ('FMCSA_HQ',        ARRAY['report:read','report:download','public:read','notification:read']),
 ('FMCSA_ENFORCEMENT', ARRAY['report:read','report:download','public:read','notification:read'])
) AS m(role_code, perms)
JOIN roles r ON r.code = m.role_code
JOIN permissions p ON p.code = ANY(m.perms)
ON CONFLICT DO NOTHING;

-- ---------------------------------------------------------------------------
-- BRD-07: the CCFP Database Administrator owns the outward-sharing pipeline
-- ---------------------------------------------------------------------------
-- Previously the DBA held study:read, crash:read, source_data:*, pcr:*,
-- data_mgmt:* and notification:read — nothing at all in reports or analytics.
INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id
FROM (VALUES
 ('CCFP_DB_ADMIN', ARRAY['report:read','report:share','report:publish','report:download','analytics:query'])
) AS m(role_code, perms)
JOIN roles r ON r.code = m.role_code
JOIN permissions p ON p.code = ANY(m.perms)
ON CONFLICT DO NOTHING;

-- ---------------------------------------------------------------------------
-- SYSTEM_ADMIN keeps every permission (seed 0002's blanket CROSS JOIN cannot
-- pick up codes added later; there are none new here, but re-running it is the
-- cheap guard against drift).
-- ---------------------------------------------------------------------------
INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id FROM roles r CROSS JOIN permissions p
WHERE r.code = 'SYSTEM_ADMIN'
ON CONFLICT DO NOTHING;

-- ---------------------------------------------------------------------------
-- Synthetic users for the new roles (fictitious; @ccfp.gov is not deliverable)
-- ---------------------------------------------------------------------------
INSERT INTO users (email, full_name, idp_subject, organization_id, title, phone, piv_cac_required)
SELECT u.email, u.full_name, u.idp_subject, o.id, u.title, u.phone, u.piv
FROM (VALUES
 ('imogen.sandoval@ccfp.gov','Imogen Sandoval','idp|imogen','FMCSA Headquarters','CCFP Super User','202-555-0115',true),
 ('desmond.okafor@ccfp.gov','Desmond Okafor','idp|desmond','FMCSA Headquarters','FMCSA HQ Analyst','202-555-0116',true),
 ('bernadette.kruse@ccfp.gov','Bernadette Kruse','idp|bernadette','FMCSA Headquarters','FMCSA Enforcement Officer','202-555-0117',true),
 ('soren.vasquez@ccfp.gov','Soren Vasquez','idp|soren','National Transportation Safety Board','NTSB Investigator','202-555-0118',true)
) AS u(email, full_name, idp_subject, org_name, title, phone, piv)
LEFT JOIN organizations o ON o.name = u.org_name
ON CONFLICT (email) DO NOTHING;

INSERT INTO user_role_assignments (user_id, role_id, scope_type, state_code, organization_id)
SELECT us.id, r.id, a.scope::assignment_scope, a.state_code, NULL
FROM (VALUES
 ('imogen.sandoval@ccfp.gov','CCFP_SUPER_USER','GLOBAL',NULL),
 ('desmond.okafor@ccfp.gov','FMCSA_HQ','GLOBAL',NULL),
 ('bernadette.kruse@ccfp.gov','FMCSA_ENFORCEMENT','GLOBAL',NULL),
 -- NTSB consumes through the generic Federal User role; the tier separation is
 -- carried by ROLE_GROUPS / OTHER_FEDERAL_ROLE_CODES, not by a bespoke role.
 ('soren.vasquez@ccfp.gov','FEDERAL_USER','GLOBAL',NULL)
) AS a(email, role_code, scope, state_code)
JOIN users us ON us.email = a.email
JOIN roles r ON r.code = a.role_code
ON CONFLICT DO NOTHING;

-- ---------------------------------------------------------------------------
-- Access-group membership for the new roles (AUTH-3)
-- ---------------------------------------------------------------------------
-- None of the new roles hold any of the five PII permission codes, so all three
-- land in NOPII — the same operational ceiling as FEDERAL_USER today. Derived by
-- permission code, exactly as seed 0008 does, so this cannot drift from it.
INSERT INTO role_access_groups (role_id, group_id)
SELECT r.id, g.id
FROM roles r
JOIN access_groups g ON g.code = 'NOPII'
WHERE r.code IN ('CCFP_SUPER_USER','FMCSA_HQ','FMCSA_ENFORCEMENT')
  AND r.id NOT IN (
      SELECT rag.role_id FROM role_access_groups rag
      JOIN access_groups pg ON pg.id = rag.group_id AND pg.code = 'PII'
  )
ON CONFLICT DO NOTHING;

-- ---------------------------------------------------------------------------
-- Development password for the new accounts (synthetic; see seed 0005)
-- ---------------------------------------------------------------------------
-- Seed 0005 has already run, so it will not touch users created above. Same
-- bcrypt hash of the shared dev password "Second@123"; only NULL hashes are set.
UPDATE users
   SET password_hash = '$2b$12$iDP98tAu7ZbVeY0YZZjiouOeLsOLdTwL2vhXHsTLO8.UoIv7WCxVu'
 WHERE password_hash IS NULL;
