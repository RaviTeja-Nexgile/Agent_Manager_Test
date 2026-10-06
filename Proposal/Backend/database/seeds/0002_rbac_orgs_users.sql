-- =============================================================================
-- Seed 0002 - Roles, permissions, organizations, synthetic users, assignments
-- ALL user data is fictitious and for development/testing/demo only.
-- Emails use a fictitious @ccfp.gov domain (not deliverable addresses).
-- =============================================================================

-- ---------------------------------------------------------------------------
-- Roles (documentation §4)
-- ---------------------------------------------------------------------------
INSERT INTO roles (code, name, description) VALUES
 ('MCSAP_INSPECTOR','MCSAP CMV Inspector','Responding inspector responsible for the Initial Incident Form and inspection inputs.'),
 ('STATE_CMV_ANALYST','State CMV Data Analyst','Coordinates State data collection, QC, coding, and analysis; selects primary contributing factors.'),
 ('CCFP_PROJECT_TEAM','CCFP Project Team','FMCSA/Volpe team for program operations, analysis, QC, and reporting.'),
 ('CCFP_PROJECT_ADMIN','CCFP Project Team Administrator','Administers users, roles, study parameters, attributes, and completeness rules.'),
 ('CCFP_DB_ADMIN','CCFP Database Administrator','Manages data mappings and analytical datasets; views raw and aggregated data.'),
 ('CCFP_DATA_SCIENTIST','CCFP Data Scientist','Federal analytical role for crash causal-factor research.'),
 ('BTS_CIPSEA_AGENT','BTS CIPSEA Agent','Conducts confidential interviews; access governed by CIPSEA.'),
 ('FMCSA_CIPSEA_AGENT','FMCSA CIPSEA Agent','FMCSA role authorized to view protected BTS data where permitted.'),
 ('FEDERAL_USER','Federal User','FMCSA/NHTSA/BTS and approved federal users; role-approved reports and tables.'),
 ('STATE_USER','State User','State enforcement/reconstruction/investigator participant; non-PII reports.'),
 ('PUBLIC_USER','Public User','Consumes summarized, de-identified published data only.'),
 ('SYSTEM_ADMIN','System Administrator','Technical operations: system configuration, environments, audit, support.')
ON CONFLICT (code) DO NOTHING;

-- ---------------------------------------------------------------------------
-- Permission catalog
-- ---------------------------------------------------------------------------
INSERT INTO permissions (code, name, category, description) VALUES
 ('study:read','View studies','studies',NULL),
 ('study:create','Create studies','studies',NULL),
 ('study:update','Update studies','studies',NULL),
 ('study:configure','Configure study parameters/attributes','studies',NULL),
 ('crash:read','View crash records','crashes',NULL),
 ('crash:create','Create crash records','crashes',NULL),
 ('crash:update','Update crash records','crashes',NULL),
 ('crash:delete','Delete crash records','crashes',NULL),
 ('crash:unlock','Unlock completed crash records','crashes',NULL),
 ('initial_incident:read','View Initial Incident Form','initial_incident',NULL),
 ('initial_incident:write','Create/update Initial Incident Form','initial_incident',NULL),
 ('initial_incident:submit','Submit and route Initial Incident Form','initial_incident',NULL),
 ('initial_incident:delete','Delete Initial Incident Form','initial_incident',NULL),
 ('source_data:read','View source data','source_data',NULL),
 ('source_data:ingest','Ingest/link source data','source_data',NULL),
 ('eld:upload','Upload ELD/eRODS files','source_data',NULL),
 ('recon:upload','Upload reconstruction reports','source_data',NULL),
 ('recon:code','Code reconstruction narrative findings','source_data',NULL),
 ('pcr:read','View PCR data','source_data',NULL),
 ('pcr:map','Map State PCR attributes','source_data',NULL),
 ('data_mgmt:read_raw','View raw source data','data_management',NULL),
 ('data_mgmt:read_aggregated','View aggregated crash data','data_management',NULL),
 ('data_mgmt:edit','Edit data attributes during QC','data_management',NULL),
 ('data_mgmt:qc','Run/review quality control','data_management',NULL),
 ('data_mgmt:complete','Manage complete/incomplete status','data_management',NULL),
 ('contributing_factor:select','Select top-three contributing factors','data_management',NULL),
 ('analytics:query','Run ad-hoc analytical queries','analytics',NULL),
 ('analytics:dashboard','Create/view dashboards & visualizations','analytics',NULL),
 ('report:read','View reports','reports',NULL),
 ('report:create','Create reports/tables','reports',NULL),
 ('report:share','Share reports','reports',NULL),
 ('report:download','Download reports','reports',NULL),
 ('report:publish','Publish de-identified public outputs','reports',NULL),
 ('bts:read','View CIPSEA-protected BTS data','bts',NULL),
 ('public:read','View public de-identified outputs','public',NULL),
 ('admin:users','Manage users','admin',NULL),
 ('admin:roles','Manage roles & permissions','admin',NULL),
 ('admin:attributes','Manage data attributes & requirements','admin',NULL),
 ('admin:completeness','Manage completeness rules','admin',NULL),
 ('admin:system','Manage system configuration','admin',NULL),
 ('audit:read','View audit logs','audit',NULL),
 ('notification:read','View notifications','notifications',NULL)
ON CONFLICT (code) DO NOTHING;

-- ---------------------------------------------------------------------------
-- Role -> permission mapping
-- ---------------------------------------------------------------------------
-- SYSTEM_ADMIN: everything.
INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id FROM roles r CROSS JOIN permissions p
WHERE r.code = 'SYSTEM_ADMIN'
ON CONFLICT DO NOTHING;

-- Map each remaining role to an explicit list of permission codes.
INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id
FROM (VALUES
 ('MCSAP_INSPECTOR', ARRAY['crash:read','crash:create','initial_incident:read','initial_incident:write','initial_incident:submit','initial_incident:delete','source_data:read','source_data:ingest','eld:upload','notification:read']),
 ('STATE_CMV_ANALYST', ARRAY['crash:read','crash:create','crash:update','initial_incident:read','initial_incident:write','initial_incident:submit','source_data:read','source_data:ingest','eld:upload','recon:upload','recon:code','pcr:read','pcr:map','data_mgmt:read_raw','data_mgmt:read_aggregated','data_mgmt:edit','data_mgmt:qc','data_mgmt:complete','contributing_factor:select','report:read','notification:read']),
 ('CCFP_PROJECT_TEAM', ARRAY['study:read','crash:read','crash:update','source_data:read','pcr:read','data_mgmt:read_raw','data_mgmt:read_aggregated','data_mgmt:edit','data_mgmt:qc','data_mgmt:complete','analytics:query','analytics:dashboard','report:read','report:create','report:share','report:download','notification:read']),
 ('CCFP_PROJECT_ADMIN', ARRAY['study:read','study:create','study:update','study:configure','crash:read','admin:users','admin:roles','admin:attributes','admin:completeness','report:read','notification:read']),
 ('CCFP_DB_ADMIN', ARRAY['study:read','crash:read','source_data:read','source_data:ingest','pcr:read','pcr:map','data_mgmt:read_raw','data_mgmt:read_aggregated','data_mgmt:edit','notification:read']),
 ('CCFP_DATA_SCIENTIST', ARRAY['study:read','crash:read','data_mgmt:read_aggregated','analytics:query','analytics:dashboard','report:read','report:create','report:download','notification:read']),
 ('BTS_CIPSEA_AGENT', ARRAY['crash:read','bts:read','notification:read']),
 ('FMCSA_CIPSEA_AGENT', ARRAY['crash:read','bts:read','data_mgmt:read_aggregated','report:read','notification:read']),
 ('FEDERAL_USER', ARRAY['report:read','report:download','public:read','notification:read']),
 ('STATE_USER', ARRAY['crash:read','report:read','report:download','public:read','notification:read']),
 ('PUBLIC_USER', ARRAY['public:read'])
) AS m(role_code, perms)
JOIN roles r ON r.code = m.role_code
JOIN permissions p ON p.code = ANY(m.perms)
ON CONFLICT DO NOTHING;

-- ---------------------------------------------------------------------------
-- Organizations (synthetic / public agency names)
-- ---------------------------------------------------------------------------
INSERT INTO organizations (name, org_type, state_code, description) VALUES
 ('FMCSA Headquarters','FMCSA',NULL,'Federal Motor Carrier Safety Administration HQ'),
 ('FMCSA CCFP Project Team','FMCSA',NULL,'CCFP program operations team'),
 ('Volpe National Transportation Systems Center','VOLPE',NULL,'U.S. DOT support center'),
 ('Bureau of Transportation Statistics','BTS',NULL,'CIPSEA confidential interview program'),
 ('Kansas Highway Patrol','STATE_AGENCY','KS','State CMV enforcement (demo)'),
 ('Kansas Department of Transportation','STATE_AGENCY','KS','State crash data repository (demo)'),
 ('Texas Department of Public Safety','STATE_AGENCY','TX','State CMV enforcement (demo)'),
 ('California Highway Patrol','STATE_AGENCY','CA','State CMV enforcement (demo)'),
 ('National Highway Traffic Safety Administration','NHTSA',NULL,'Federal safety partner'),
 ('Federal Highway Administration','FHWA',NULL,'HPMS/MIRE roadway data'),
 ('National Oceanic and Atmospheric Administration','NOAA',NULL,'HRRR weather data'),
 ('American Association of Motor Vehicle Administrators','AAMVA',NULL,'CDLIS')
ON CONFLICT DO NOTHING;

-- ---------------------------------------------------------------------------
-- Synthetic users (fictitious names + reserved-domain emails)
-- ---------------------------------------------------------------------------
INSERT INTO users (email, full_name, idp_subject, organization_id, title, phone, piv_cac_required)
SELECT u.email, u.full_name, u.idp_subject, o.id, u.title, u.phone, u.piv
FROM (VALUES
 ('sysadmin@ccfp.gov','Morgan Castellano','idp|sysadmin','FMCSA CCFP Project Team','System Administrator','202-555-0101',true),
 ('avery.thornton@ccfp.gov','Avery Thornton','idp|avery','FMCSA CCFP Project Team','CCFP Project Team Administrator','202-555-0102',true),
 ('dana.whitfield@ccfp.gov','Dana Whitfield','idp|dana','FMCSA CCFP Project Team','CCFP Project Team Lead','202-555-0103',true),
 ('priya.ramanathan@ccfp.gov','Priya Ramanathan','idp|priya','FMCSA CCFP Project Team','CCFP Data Scientist','202-555-0104',true),
 ('victor.delacruz@ccfp.gov','Victor De La Cruz','idp|victor','FMCSA CCFP Project Team','CCFP Database Administrator','202-555-0105',true),
 ('helena.brandt@ccfp.gov','Helena Brandt','idp|helena','Bureau of Transportation Statistics','BTS CIPSEA Agent','202-555-0106',true),
 ('marcus.ellingsworth@ccfp.gov','Marcus Ellingsworth','idp|marcus','FMCSA CCFP Project Team','FMCSA CIPSEA Agent','202-555-0107',true),
 ('nora.kowalczyk@ccfp.gov','Nora Kowalczyk','idp|nora','Kansas Highway Patrol','MCSAP CMV Inspector','785-555-0108',false),
 ('elliot.fontaine@ccfp.gov','Elliot Fontaine','idp|elliot','Kansas Highway Patrol','State CMV Data Analyst','785-555-0109',false),
 ('tomasz.bialek@ccfp.gov','Tomasz Bialek','idp|tomasz','Kansas Department of Transportation','State User','785-555-0110',false),
 ('rosa.menendez@ccfp.gov','Rosa Menendez','idp|rosa','Texas Department of Public Safety','MCSAP CMV Inspector','512-555-0111',false),
 ('grant.holloway@ccfp.gov','Grant Holloway','idp|grant','Texas Department of Public Safety','State CMV Data Analyst','512-555-0112',false),
 ('linh.tran@ccfp.gov','Linh Tran','idp|linh','California Highway Patrol','State CMV Data Analyst','916-555-0113',false),
 ('omar.haddad@ccfp.gov','Omar Haddad','idp|omar','National Highway Traffic Safety Administration','Federal User','202-555-0114',true),
 ('public.demo@ccfp.gov','Public Demo Account','idp|public','NULL_ORG','Public User',NULL,false)
) AS u(email, full_name, idp_subject, org_name, title, phone, piv)
LEFT JOIN organizations o ON o.name = u.org_name
ON CONFLICT (email) DO NOTHING;

-- ---------------------------------------------------------------------------
-- Role assignments (scoped by role / state / org where relevant)
-- ---------------------------------------------------------------------------
INSERT INTO user_role_assignments (user_id, role_id, scope_type, state_code, organization_id)
SELECT us.id, r.id, a.scope::assignment_scope, a.state_code,
       CASE WHEN a.scope='ORGANIZATION' THEN us.organization_id ELSE NULL END
FROM (VALUES
 ('sysadmin@ccfp.gov','SYSTEM_ADMIN','GLOBAL',NULL),
 ('avery.thornton@ccfp.gov','CCFP_PROJECT_ADMIN','GLOBAL',NULL),
 ('dana.whitfield@ccfp.gov','CCFP_PROJECT_TEAM','GLOBAL',NULL),
 ('priya.ramanathan@ccfp.gov','CCFP_DATA_SCIENTIST','GLOBAL',NULL),
 ('victor.delacruz@ccfp.gov','CCFP_DB_ADMIN','GLOBAL',NULL),
 ('helena.brandt@ccfp.gov','BTS_CIPSEA_AGENT','GLOBAL',NULL),
 ('marcus.ellingsworth@ccfp.gov','FMCSA_CIPSEA_AGENT','GLOBAL',NULL),
 ('nora.kowalczyk@ccfp.gov','MCSAP_INSPECTOR','STATE','KS'),
 ('elliot.fontaine@ccfp.gov','STATE_CMV_ANALYST','STATE','KS'),
 ('tomasz.bialek@ccfp.gov','STATE_USER','STATE','KS'),
 ('rosa.menendez@ccfp.gov','MCSAP_INSPECTOR','STATE','TX'),
 ('grant.holloway@ccfp.gov','STATE_CMV_ANALYST','STATE','TX'),
 ('linh.tran@ccfp.gov','STATE_CMV_ANALYST','STATE','CA'),
 ('omar.haddad@ccfp.gov','FEDERAL_USER','GLOBAL',NULL),
 ('public.demo@ccfp.gov','PUBLIC_USER','GLOBAL',NULL)
) AS a(email, role_code, scope, state_code)
JOIN users us ON us.email = a.email
JOIN roles r ON r.code = a.role_code
ON CONFLICT DO NOTHING;
