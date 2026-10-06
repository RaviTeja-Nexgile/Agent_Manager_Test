-- =============================================================================
-- Seed 0008 - Access groups + role memberships (AUTH-3)
-- ALL data is synthetic / dev-test-demo only.
-- =============================================================================
-- Seeds the four first-class access groups and maps every seeded role to the
-- group(s) that EXACTLY preserve today's effective sensitivity reach. Memberships
-- are derived by checking which permission codes each role actually holds (NOT by
-- role name), so no role gains or loses PII/CIPSEA visibility as a side effect of
-- this structural change.
--   * PII   (data_sensitivity_max = 'PII')      <- roles holding any of the five
--            PII permission codes mirrored from core/security._PII_PERMISSIONS:
--            initial_incident:read/write, data_mgmt:edit, data_mgmt:read_raw,
--            crash:update.
--   * CIPSEA(data_sensitivity_max = 'CIPSEA')   <- roles holding bts:read.
--   * PUBLIC(data_sensitivity_max = 'PUBLIC')   <- PUBLIC_USER (public:read only).
--   * NOPII (data_sensitivity_max = 'INTERNAL') <- every other role.
-- =============================================================================

-- ---------------------------------------------------------------------------
-- The four access groups.
-- ---------------------------------------------------------------------------
INSERT INTO access_groups (code, name, data_sensitivity_max, description) VALUES
 ('PII','Federal Users (PII)','PII','May view PII / SENSITIVE operational data (§4 l.142).'),
 ('NOPII','State Users (No PII)','INTERNAL','May view INTERNAL/PUBLIC data; PII withheld (§4 l.142).'),
 ('CIPSEA','CIPSEA Agents','CIPSEA','May view CIPSEA-protected BTS interview data.'),
 ('PUBLIC','Public Users','PUBLIC','May view only de-identified published outputs (§4 l.142).')
ON CONFLICT (code) DO NOTHING;

-- ---------------------------------------------------------------------------
-- PII group: roles holding ANY of the five PII permission codes today
-- (matches core/security._PII_PERMISSIONS). Derived by permission code, not name.
-- ---------------------------------------------------------------------------
INSERT INTO role_access_groups (role_id, group_id)
SELECT DISTINCT r.id, g.id
FROM roles r
JOIN role_permissions rp ON rp.role_id = r.id
JOIN permissions p ON p.id = rp.permission_id
JOIN access_groups g ON g.code = 'PII'
WHERE p.code IN (
    'initial_incident:read','initial_incident:write',
    'data_mgmt:edit','data_mgmt:read_raw','crash:update'
)
ON CONFLICT DO NOTHING;

-- ---------------------------------------------------------------------------
-- CIPSEA group: roles holding bts:read (BTS_CIPSEA_AGENT, FMCSA_CIPSEA_AGENT).
-- ---------------------------------------------------------------------------
INSERT INTO role_access_groups (role_id, group_id)
SELECT DISTINCT r.id, g.id
FROM roles r
JOIN role_permissions rp ON rp.role_id = r.id
JOIN permissions p ON p.id = rp.permission_id
JOIN access_groups g ON g.code = 'CIPSEA'
WHERE p.code = 'bts:read'
ON CONFLICT DO NOTHING;

-- ---------------------------------------------------------------------------
-- PUBLIC group: PUBLIC_USER (the only role limited to public:read).
-- ---------------------------------------------------------------------------
INSERT INTO role_access_groups (role_id, group_id)
SELECT r.id, g.id
FROM roles r
JOIN access_groups g ON g.code = 'PUBLIC'
WHERE r.code = 'PUBLIC_USER'
ON CONFLICT DO NOTHING;

-- ---------------------------------------------------------------------------
-- NOPII group: every role NOT already in the PII group and NOT PUBLIC_USER.
-- (CIPSEA agents are NOPII for operational data AND additionally CIPSEA above —
-- they hold no PII code, so NOPII is their operational ceiling, matching today.)
-- ---------------------------------------------------------------------------
INSERT INTO role_access_groups (role_id, group_id)
SELECT r.id, g.id
FROM roles r
JOIN access_groups g ON g.code = 'NOPII'
WHERE r.code <> 'PUBLIC_USER'
  AND r.id NOT IN (
      SELECT rag.role_id
      FROM role_access_groups rag
      JOIN access_groups pg ON pg.id = rag.group_id AND pg.code = 'PII'
  )
ON CONFLICT DO NOTHING;
