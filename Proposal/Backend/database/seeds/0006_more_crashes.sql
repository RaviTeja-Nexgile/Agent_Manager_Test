-- =============================================================================
-- Seed 0006 - Additional synthetic demo crash records (development / demo)
-- =============================================================================
-- Adds 10 more fictitious crash records so the /crashes list is well populated.
-- ALL data is invented; references the PHASE1-HDT study and the @ccfp.gov demo
-- users. Idempotent: ON CONFLICT (ccfp_identifier / crash_id) DO NOTHING.
-- =============================================================================

-- ---------------------------------------------------------------------------
-- Crashes
-- ---------------------------------------------------------------------------
INSERT INTO crashes (id, ccfp_identifier, study_id, local_report_number, crash_date, crash_time,
                     city, county, state_code, street_highway, latitude, longitude,
                     num_vehicles, num_persons, num_fatalities, lifecycle_phase, created_by)
SELECT v.id::uuid,
       v.ccfp,
       (SELECT id FROM studies WHERE code = 'PHASE1-HDT'),
       v.local, v.cdate::date, v.ctime::time,
       v.city, v.county, v.state, v.road, v.lat::numeric, v.lon::numeric,
       v.nveh, v.npers, v.nfat, v.phase::crash_lifecycle_phase,
       (SELECT id FROM users WHERE email = v.creator)
FROM (VALUES
 ('c5a00001-0000-0000-0000-000000000105','CCFP-2026-KS-000105','KS-2026-006120','2026-05-14','15:30','Topeka','Shawnee','KS','I-470 near Burlingame Rd',39.0123,-95.7600,2,3,1,'DATA_COLLECTION','nora.kowalczyk@ccfp.gov'),
 ('c5a00001-0000-0000-0000-000000000106','CCFP-2026-TX-000106','TX-2026-220145','2026-05-20','08:05','Austin','Travis','TX','US-183 at Mopac',30.3870,-97.7430,3,4,2,'QUALITY_CONTROL','rosa.menendez@ccfp.gov'),
 ('c5a00001-0000-0000-0000-000000000107','CCFP-2026-CA-000107','CA-2026-553300','2026-04-11','19:45','Fresno','Fresno','CA','SR-99 at Shaw Ave',36.8080,-119.8500,2,2,1,'DATA_MAPPING','linh.tran@ccfp.gov'),
 ('c5a00001-0000-0000-0000-000000000108','CCFP-2026-KS-000108','KS-2026-006233','2026-03-30','11:20','Wichita','Sedgwick','KS','I-135 at 21st St',37.7210,-97.3360,2,5,1,'ANALYSIS','elliot.fontaine@ccfp.gov'),
 ('c5a00001-0000-0000-0000-000000000109','CCFP-2026-TX-000109','TX-2026-220460','2026-06-01','06:50','Dallas','Dallas','TX','I-635 LBJ Freeway',32.9260,-96.7700,4,6,1,'INITIAL_INCIDENT','grant.holloway@ccfp.gov'),
 ('c5a00001-0000-0000-0000-000000000110','CCFP-2026-CA-000110','CA-2026-553612','2026-02-22','22:10','Sacramento','Sacramento','CA','I-5 at Pocket Rd',38.4900,-121.5160,2,3,1,'PUBLICATION','linh.tran@ccfp.gov'),
 ('c5a00001-0000-0000-0000-000000000111','CCFP-2026-MO-000111','MO-2026-300455','2026-01-18','13:40','Kansas City','Jackson','MO','I-435 at Front St',39.1230,-94.5300,2,2,0,'DATA_COLLECTION','dana.whitfield@ccfp.gov'),
 ('c5a00001-0000-0000-0000-000000000112','CCFP-2026-OK-000112','OK-2026-410233','2026-05-05','17:15','Tulsa','Tulsa','OK','I-44 at Yale Ave',36.1250,-95.9210,3,4,1,'NOTIFICATION','dana.whitfield@ccfp.gov'),
 ('c5a00001-0000-0000-0000-000000000113','CCFP-2026-NE-000113','NE-2026-280144','2026-04-27','09:35','Omaha','Douglas','NE','I-80 at 72nd St',41.2330,-96.0470,2,3,1,'DATA_COLLECTION','dana.whitfield@ccfp.gov'),
 ('c5a00001-0000-0000-0000-000000000114','CCFP-2026-TX-000114','TX-2026-220701','2026-06-03','07:25','Houston','Harris','TX','I-610 at US-290',29.8000,-95.4500,5,7,2,'INITIAL_INCIDENT','rosa.menendez@ccfp.gov')
) AS v(id, ccfp, local, cdate, ctime, city, county, state, road, lat, lon, nveh, npers, nfat, phase, creator)
ON CONFLICT (ccfp_identifier) DO NOTHING;

-- ---------------------------------------------------------------------------
-- Scope classifications
-- ---------------------------------------------------------------------------
INSERT INTO crash_scope_classifications (crash_id, is_qualifying, scope, is_supplemental, classification_reason, classified_by)
SELECT c.id, v.qual, v.scope::crash_scope, v.suppl, v.reason,
       (SELECT id FROM users WHERE email = 'dana.whitfield@ccfp.gov')
FROM (VALUES
 ('CCFP-2026-KS-000105', true,  'IN_SCOPE',     false, 'Fatal Class 8 truck crash in a participating State (KS).'),
 ('CCFP-2026-TX-000106', true,  'IN_SCOPE',     false, 'Multi-fatality crash involving a Class 7 truck in a participating State (TX).'),
 ('CCFP-2026-CA-000107', true,  'IN_SCOPE',     false, 'Fatal heavy-duty truck crash in a participating State (CA).'),
 ('CCFP-2026-KS-000108', true,  'IN_SCOPE',     false, 'Fatal Class 8 truck crash in a participating State (KS).'),
 ('CCFP-2026-TX-000109', false, 'UNDETERMINED', false, 'Newly filed incident; qualification under review.'),
 ('CCFP-2026-CA-000110', true,  'IN_SCOPE',     false, 'Fatal heavy-duty truck crash in a participating State (CA); study published.'),
 ('CCFP-2026-MO-000111', true,  'OUT_OF_SCOPE', true,  'Heavy-duty truck serious-injury crash in a non-participating State (MO); supplemental.'),
 ('CCFP-2026-OK-000112', true,  'OUT_OF_SCOPE', true,  'Qualifying crash in a non-participating State (OK); supplemental.'),
 ('CCFP-2026-NE-000113', true,  'OUT_OF_SCOPE', true,  'Qualifying crash in a non-participating State (NE); supplemental.'),
 ('CCFP-2026-TX-000114', true,  'IN_SCOPE',     false, 'Multi-fatality Class 8 truck crash in a participating State (TX).')
) AS v(ccfp, qual, scope, suppl, reason)
JOIN crashes c ON c.ccfp_identifier = v.ccfp
ON CONFLICT (crash_id) DO NOTHING;
