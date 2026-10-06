-- =============================================================================
-- Seed 0014 - Appendix D external data sources + aggregated:* permissions
-- (BRD January 2026)
-- =============================================================================
-- Two things, both required before CCFP Aggregated Data can be created:
--
--   1. The Appendix D vocabulary, verbatim from the January 2026 BRD
--      ("External Data Sources for CCFP IT Solution"): 11 FMCSA-owned sources
--      and 6 owned by other entities. Held as reference DATA so that the BRD's
--      own forward-compatibility note -- "some information may shift to Motus or
--      other systems as FMCSA works to modernize its legacy IT systems" -- is an
--      INSERT, not a migration.
--
--   2. The two new permission codes the BRD's access table implies. The
--      Jan-2026 BRD assigns "Create CCFP Aggregated Data by linking raw CCFP
--      crash data and data from external systems" to the CCFP Database
--      Administrator with Create/Update/Read; that role previously held no
--      create-grade permission over aggregated data at all.
--
-- `relevant_data` is the BRD's own "Relevant Data for CCFP" column, kept so the
-- catalog is traceable to the published specification without a second lookup.
-- =============================================================================

-- ---------------------------------------------------------------------------
-- FMCSA-owned data sources (BRD Appendix D, table 1 - 11 rows)
-- ---------------------------------------------------------------------------
INSERT INTO ref_external_systems (code, name, owner, is_fmcsa_owned, relevant_data, sort_order) VALUES
 ('ACE','Activity Center for Enforcement (ACE)','FMCSA',TRUE,
  'Investigation reports; carrier files',10),
 ('DATAQS','DataQs','FMCSA',TRUE,
  'Requests for data reviews, results of those reviews, including Crash Preventability determinations',20),
 ('DIR','Driver Information Resource (DIR)','FMCSA',TRUE,
  'Driver inspection history, crash history, DACH information',30),
 ('DACH','Drug and Alcohol Clearinghouse (DACH)','FMCSA',TRUE,
  'CDL driver drug and alcohol violations; current carrier queries',40),
 ('DSMS','Driver Safety Measurement System (DSMS)','FMCSA',TRUE,
  'Internal enforcement tool; driver inspection results, investigation results, and crash history; DSMS percentiles that reflect a driver''s safety performance relative to other drivers',50),
 ('ELD_ERODS','Electronic Logging Device (ELD)/Electronic Record of Duty Status (eRODS)','FMCSA',TRUE,
  'Record of driving time, hours of service, engine hours, ignition status, location and miles driven',60),
 ('MCMIS','Motor Carrier Management Information System (MCMIS)','FMCSA',TRUE,
  'Motor carrier registration data, inspection and crash history, compliance review and other post-crash enforcement data (note: some information may shift to Motus or other systems as FMCSA works to modernize its legacy IT systems)',70),
 ('NRCME','National Registry of Certified Medical Examiners','FMCSA',TRUE,
  'Driver medical certificate information',80),
 ('SAFESPECT_INSPECTIONS','SafeSpect Inspections','FMCSA',TRUE,
  'Inspection data related to vehicles, drivers, carriers, cargo, and enforcement actions and outcomes. Uploaded to FMCSA SafeSpect system.',90),
 ('SMS','Safety Measurement System (SMS)','FMCSA',TRUE,
  'Carrier exposure data (VMT per average PU), inspection results, investigation results, and crash history; SMS percentiles that reflect a carrier''s safety performance relative to other carriers',100),
 ('TPR','Training Provider Registry (TPR)','FMCSA',TRUE,
  'Driver training records for FMCSA-mandated entry-level driver training',110)
ON CONFLICT (code) DO NOTHING;

-- ---------------------------------------------------------------------------
-- Data sources owned by other entities (BRD Appendix D, table 2 - 6 rows)
-- ---------------------------------------------------------------------------
INSERT INTO ref_external_systems (code, name, owner, is_fmcsa_owned, relevant_data, sort_order) VALUES
 ('BTS_SECURE_DB','CCFP BTS Secure Database','BTS',FALSE,
  'Aggregated, anonymized data from confidential interviews of drivers, carriers, and witnesses involved in a qualifying crash.',200),
 ('CDLIS','Commercial Driver''s License Information System (CDLIS)','AAMVA (or soon to be FMCSA)',FALSE,
  'CDL records, driver status and history',210),
 ('HPMS_MIRE','Highway Performance Monitoring System (HPMS)/Model Inventory of Roadway Elements (MIRE)','FHWA',FALSE,
  'Official federal government source of data on the extent, conditions, performance, use, and operating characteristics of all public roads/highways',220),
 ('GOOGLE_MAPS','Google Maps/Earth','Google',FALSE,
  'Location information; aerial views',230),
 ('NHTSA_RECALLS','NHTSA Recalls Database','NHTSA',FALSE,
  'Recall data for vehicle parts and accessories from the original equipment manufacturer',240),
 ('NOAA_HRRR','High-Resolution Rapid Refresh (HRRR) Database','NOAA',FALSE,
  'Real-time weather data including solar radiation (Watts/m2), relative humidity (%), wind speed (miles per hour), air temperature (degrees Fahrenheit), precipitation (amount of rainfall in inches), and visibility (miles).',250)
ON CONFLICT (code) DO NOTHING;

-- ---------------------------------------------------------------------------
-- New permission codes
-- ---------------------------------------------------------------------------
-- aggregated:read  - read the assembled CCFP Aggregated Data document.
-- aggregated:link  - create/remove the external-system linkage that PRODUCES it
--                    (the BRD's Create/Update/Read for the CCFP DBA).
INSERT INTO permissions (code, name, category, description) VALUES
 ('aggregated:read','View CCFP Aggregated Data','data_management',
  'Read the assembled aggregated document for a crash: canonical attributes with provenance, CCFP source records, and external-system links.'),
 ('aggregated:link','Link CCFP Aggregated Data to external systems','data_management',
  'Create and remove links between a CCFP crash record and records in Appendix D external systems (CCFP Database Administrator).')
ON CONFLICT (code) DO NOTHING;

-- ---------------------------------------------------------------------------
-- Role -> permission grants
-- ---------------------------------------------------------------------------
-- SYSTEM_ADMIN holds every permission. Seed 0002's blanket CROSS JOIN already
-- ran, so it cannot pick up codes introduced later -- re-run it, restricted to
-- the two new codes.
INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id
FROM roles r
CROSS JOIN permissions p
WHERE r.code = 'SYSTEM_ADMIN'
  AND p.code IN ('aggregated:read','aggregated:link')
ON CONFLICT DO NOTHING;

-- CCFP_DB_ADMIN owns the linkage per the Jan-2026 BRD access table.
-- aggregated:read additionally goes to the roles that already hold
-- data_mgmt:read_aggregated, so the new document endpoint stays reachable for
-- exactly the cohort that could already read aggregated data -- no widening.
INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id
FROM (VALUES
 ('CCFP_DB_ADMIN',      ARRAY['aggregated:read','aggregated:link']),
 ('STATE_CMV_ANALYST',  ARRAY['aggregated:read']),
 ('CCFP_PROJECT_TEAM',  ARRAY['aggregated:read']),
 ('CCFP_DATA_SCIENTIST',ARRAY['aggregated:read']),
 ('FMCSA_CIPSEA_AGENT', ARRAY['aggregated:read'])
) AS m(role_code, perms)
JOIN roles r ON r.code = m.role_code
JOIN permissions p ON p.code = ANY(m.perms)
ON CONFLICT DO NOTHING;
