-- =============================================================================
-- Seed 0004 - Synthetic demo crash records (development / testing / demo)
-- =============================================================================
-- ALL data below is fictitious. Names, addresses, phone numbers, DOT numbers,
-- VINs, license plates, and carriers are invented for demonstration only and
-- do not correspond to any real person, carrier, vehicle, or crash.
-- Fixed UUIDs are used so related rows can reference each other deterministically.
-- =============================================================================

-- ---------------------------------------------------------------------------
-- CRASH 1 - Kansas, in-scope, fully populated, COMPLETE
-- ---------------------------------------------------------------------------
INSERT INTO crashes (id, ccfp_identifier, study_id, local_report_number, crash_date, crash_time,
                     city, county, state_code, street_highway, latitude, longitude,
                     num_vehicles, num_persons, num_fatalities, lifecycle_phase, created_by)
SELECT 'c1a51001-0000-0000-0000-000000000001',
       'CCFP-2026-KS-000101',
       (SELECT id FROM studies WHERE code='PHASE1-HDT'),
       'KS-2026-004821','2026-03-12','06:45',
       'Salina','Saline','KS','I-70 near Mile Marker 252', 38.840300, -97.611400,
       2, 3, 1, 'ANALYSIS',
       (SELECT id FROM users WHERE email='nora.kowalczyk@ccfp.gov');

INSERT INTO crash_scope_classifications (crash_id, is_qualifying, scope, is_supplemental, classification_reason, classified_by)
VALUES ('c1a51001-0000-0000-0000-000000000001', true, 'IN_SCOPE', false,
        'Fatal crash involving a Class 8 truck in a participating State (KS).',
        (SELECT id FROM users WHERE email='elliot.fontaine@ccfp.gov'));

INSERT INTO initial_incident_forms (crash_id, status, event_summary, dot_number_validated, dot_validation_source, submitted_by, submitted_at, routed_at, created_by)
VALUES ('c1a51001-0000-0000-0000-000000000001','ROUTED',
        'Class 8 tractor-trailer rear-ended a passenger sedan slowed in a construction zone; one fatality in the sedan.',
        true,'SafeSpect',
        (SELECT id FROM users WHERE email='nora.kowalczyk@ccfp.gov'),
        '2026-03-12 09:10+00','2026-03-12 09:12+00',
        (SELECT id FROM users WHERE email='nora.kowalczyk@ccfp.gov'));

INSERT INTO incident_vehicles (crash_id, vehicle_number, is_cmv, us_dot_number, make, num_occupants, num_injured_occupants, carrier_name, carrier_phone)
VALUES
 ('c1a51001-0000-0000-0000-000000000001',1,true,'3192847','Freightliner',1,1,'Prairie Line Freight LLC','316-555-0170'),
 ('c1a51001-0000-0000-0000-000000000001',2,false,NULL,'Toyota',2,2,NULL,NULL);

INSERT INTO incident_persons (crash_id, person_type, related_vehicle_number, full_name, is_minor, primary_language, address, phone_primary, phone_type, injury)
VALUES
 ('c1a51001-0000-0000-0000-000000000001','DRIVER',1,'Wendell Pruitt',false,'English','4120 Cottonwood Rd, Wichita, KS 67220','316-555-0171','CELL','NO_INJURY'),
 ('c1a51001-0000-0000-0000-000000000001','DRIVER',2,'Carla Devereaux',false,'English','88 Maple Glen Ct, Salina, KS 67401','785-555-0172','CELL','FATAL'),
 ('c1a51001-0000-0000-0000-000000000001','OCCUPANT',2,'Jamie Devereaux',true,'English','88 Maple Glen Ct, Salina, KS 67401','785-555-0173','HOME','INJURY'),
 ('c1a51001-0000-0000-0000-000000000001','WITNESS',NULL,'Harold Brinkmann',false,'English','205 Front St, Salina, KS 67401','785-555-0174','CELL',NULL);

INSERT INTO post_crash_inspections (crash_id, source_system, inspection_number, inspection_date, inspector_name, violations_count, defects_count, details)
VALUES ('c1a51001-0000-0000-0000-000000000001','SafeSpect','INS-KS-77310','2026-03-12','N. Kowalczyk',2,1,
        '{"brake_violations":1,"hours_of_service_violations":1,"defect":"left front brake out of adjustment"}');

INSERT INTO post_crash_investigations (crash_id, case_number, inspection_number, officer_name, officer_id, post_crash_date, status, sections, created_by)
VALUES ('c1a51001-0000-0000-0000-000000000001','PCI-KS-2026-0098','INS-KS-77310','Sgt. R. Alvarado','KHP-4471','2026-03-19','SUBMITTED',
        '{"motor_carrier":{"name":"Prairie Line Freight LLC","us_dot":"3192847","nsc":null},"power_unit":{"year":2021,"make":"Freightliner","model":"Cascadia","vin":"1FUJGLDR0MLAA0001","gvwr_lbs":52000},"driver_hos":{"on_duty_hours":11.5,"driving_hours":10.0,"eld_present":true},"brakes":{"abs":"present","air_leaks":false,"adjustment":"left front out of adjustment"}}',
        (SELECT id FROM users WHERE email='elliot.fontaine@ccfp.gov'));

INSERT INTO police_crash_reports (crash_id, state_code, source_repository, pcr_number, report_date, mapping_status, mapped_by)
VALUES ('c1a51001-0000-0000-0000-000000000001','KS','Kansas Crash Repository (KARS)','KS-PCR-2026-558210','2026-03-15','MAPPED',
        (SELECT id FROM users WHERE email='victor.delacruz@ccfp.gov'));

-- Documents (reconstruction PDF + ELD CSV) for cross-reference
INSERT INTO documents (id, crash_id, doc_type, file_name, mime_type, storage_uri, size_bytes, sensitivity, malware_scan, uploaded_by)
VALUES
 ('d0c00001-0000-0000-0000-000000000001','c1a51001-0000-0000-0000-000000000001','PDF','recon_KS_000101.pdf','application/pdf','s3://ccfp-objects/ks/000101/recon_KS_000101.pdf',2483712,'SENSITIVE','CLEAN',(SELECT id FROM users WHERE email='elliot.fontaine@ccfp.gov')),
 ('d0c00001-0000-0000-0000-000000000002','c1a51001-0000-0000-0000-000000000001','ELD_CSV','eld_3192847_20260312.csv','text/csv','s3://ccfp-objects/ks/000101/eld_3192847_20260312.csv',58210,'INTERNAL','CLEAN',(SELECT id FROM users WHERE email='nora.kowalczyk@ccfp.gov')),
 ('d0c00001-0000-0000-0000-000000000003','c1a51001-0000-0000-0000-000000000001','IMAGE','scene_photo_01.jpg','image/jpeg','s3://ccfp-objects/ks/000101/scene_photo_01.jpg',1820345,'INTERNAL','CLEAN',(SELECT id FROM users WHERE email='nora.kowalczyk@ccfp.gov'));

INSERT INTO reconstruction_reports (crash_id, title, received_date, document_id, coding_status, coded_by, coded_findings)
VALUES ('c1a51001-0000-0000-0000-000000000001','Reconstruction - I-70 MM252 rear-end','2026-06-01','d0c00001-0000-0000-0000-000000000001','CODED',
        (SELECT id FROM users WHERE email='elliot.fontaine@ccfp.gov'),
        '{"primary_finding":"following too closely","speed_estimate_mph":62,"avoidance_maneuver":"none"}');

INSERT INTO eld_files (id, crash_id, file_name, document_id, ccfp_code_in_file, provider, model, version, upload_status, event_count, uploaded_by, parsed_at)
VALUES ('e1d00001-0000-0000-0000-000000000001','c1a51001-0000-0000-0000-000000000001','eld_3192847_20260312.csv','d0c00001-0000-0000-0000-000000000002','CCFP-2026-KS-000101','KeepTruckin Clone','LogBookPro','4.2','PARSED',5,
        (SELECT id FROM users WHERE email='nora.kowalczyk@ccfp.gov'),'2026-03-12 09:30+00');

INSERT INTO eld_events (eld_file_id, event_sequence, event_timestamp, duty, event_type, location, latitude, longitude, miles_driven, engine_hours, ignition_status)
VALUES
 ('e1d00001-0000-0000-0000-000000000001',1,'2026-03-11 20:00+00','OFF_DUTY','status_change','Wichita, KS',37.6872,-97.3301,0,1420.5,'OFF'),
 ('e1d00001-0000-0000-0000-000000000001',2,'2026-03-12 04:30+00','ON_DUTY_NOT_DRIVING','pre_trip','Wichita, KS',37.6872,-97.3301,0,1420.5,'ON'),
 ('e1d00001-0000-0000-0000-000000000001',3,'2026-03-12 05:00+00','DRIVING','status_change','Wichita, KS',37.6872,-97.3301,0,1421.0,'ON'),
 ('e1d00001-0000-0000-0000-000000000001',4,'2026-03-12 06:44+00','DRIVING','position',  'I-70 MM252, Saline, KS',38.8403,-97.6114,92.4,1422.7,'ON'),
 ('e1d00001-0000-0000-0000-000000000001',5,'2026-03-12 06:46+00','ON_DUTY_NOT_DRIVING','crash_indicator','I-70 MM252, Saline, KS',38.8403,-97.6114,92.4,1422.8,'ON');

INSERT INTO source_records (crash_id, source_system, source_type, external_id, raw_zone_uri, provenance_note)
VALUES
 ('c1a51001-0000-0000-0000-000000000001','SafeSpect','INSPECTION','INS-KS-77310','s3://ccfp-raw/safespect/INS-KS-77310.json','Automated SafeSpect ingestion'),
 ('c1a51001-0000-0000-0000-000000000001','MCMIS','PCR','KS-PCR-2026-558210','s3://ccfp-raw/mcmis/KS-PCR-2026-558210.xml','MCMIS crash extract'),
 ('c1a51001-0000-0000-0000-000000000001','eRODS','ELD','CCFP-2026-KS-000101','s3://ccfp-raw/erods/eld_3192847_20260312.csv','Manual ELD upload');

-- Canonical aggregated attribute values (a representative subset)
INSERT INTO crash_attribute_values (crash_id, attribute_id, value_text, source_system, confidence, is_edited)
SELECT 'c1a51001-0000-0000-0000-000000000001', da.id, v.val, v.src, v.conf, v.edited
FROM (VALUES
 ('C01','CCFP-2026-KS-000101','CCFP',100.0,false),
 ('C03','2026-03-12T06:45:00','MCMIS',98.0,false),
 ('C04','Saline','MCMIS',100.0,false),
 ('C19','Fatal','MCMIS',100.0,false),
 ('C24','1','MCMIS',100.0,false),
 ('LV07','Prairie Line Freight LLC (USDOT 3192847)','SafeSpect',95.0,false),
 ('V05','Freightliner','MCMIS',97.0,false),
 ('V06','2021','PCI',90.0,true),
 ('P04','Driver','MCMIS',100.0,false)
) AS v(code, val, src, conf, edited)
JOIN data_attributes da ON da.code = v.code;

INSERT INTO data_quality_results (crash_id, rule_id, status, message)
SELECT 'c1a51001-0000-0000-0000-000000000001', dr.id, st.status::qc_result_status, st.msg
FROM (VALUES
 ('DQ_MISSING_IIF','PASS','Initial Incident Form present and routed.'),
 ('DQ_DOT_SAFESPECT','PASS','USDOT 3192847 validated via SafeSpect.'),
 ('DQ_FATALITY_COUNT','PASS','1 fatality recorded.'),
 ('DQ_CDLIS_CHECK','PASS','Driver license validated via CDLIS.'),
 ('DQ_TOP_FACTORS','PASS','Three contributing factors selected.')
) AS st(code, status, msg)
JOIN data_quality_rules dr ON dr.code = st.code;

INSERT INTO crash_completeness_status (crash_id, status, is_current, is_locked, missing_summary, changed_by)
VALUES ('c1a51001-0000-0000-0000-000000000001','COMPLETE',true,true,'{"missing":[]}',
        (SELECT id FROM users WHERE email='elliot.fontaine@ccfp.gov'));

INSERT INTO contributing_factor_selections (crash_id, factor_group_id, factor_value, rank, selected_by)
SELECT 'c1a51001-0000-0000-0000-000000000001', g.id, v.val, v.rank,
       (SELECT id FROM users WHERE email='elliot.fontaine@ccfp.gov')
FROM (VALUES
 ('DRIVER_ACTIONS','Following too closely',1),
 ('DRIVER_CONDITIONS','Fatigued / hours-of-service exceedance',2),
 ('CC_VEHICLE','Brake out of adjustment (left front)',3)
) AS v(grp, val, rank)
JOIN ref_contributing_factor_groups g ON g.code = v.grp;

-- ---------------------------------------------------------------------------
-- CRASH 2 - Texas, in-scope, in DATA_COLLECTION
-- ---------------------------------------------------------------------------
INSERT INTO crashes (id, ccfp_identifier, study_id, local_report_number, crash_date, crash_time,
                     city, county, state_code, street_highway, latitude, longitude,
                     num_vehicles, num_persons, num_fatalities, lifecycle_phase, created_by)
SELECT 'c2b72002-0000-0000-0000-000000000002','CCFP-2026-TX-000102',
       (SELECT id FROM studies WHERE code='PHASE1-HDT'),
       'TX-2026-119034','2026-04-28','17:20','Waco','McLennan','TX','US-77 at Loop 340', 31.549300, -97.146700,
       3, 4, 1, 'DATA_COLLECTION',
       (SELECT id FROM users WHERE email='rosa.menendez@ccfp.gov');

INSERT INTO crash_scope_classifications (crash_id, is_qualifying, scope, is_supplemental, classification_reason, classified_by)
VALUES ('c2b72002-0000-0000-0000-000000000002', true, 'IN_SCOPE', false,
        'Fatal crash involving a Class 7 truck in a participating State (TX).',
        (SELECT id FROM users WHERE email='grant.holloway@ccfp.gov'));

INSERT INTO initial_incident_forms (crash_id, status, event_summary, dot_number_validated, dot_validation_source, submitted_by, submitted_at, routed_at, created_by)
VALUES ('c2b72002-0000-0000-0000-000000000002','ROUTED',
        'Multi-vehicle crash at a signalized intersection; box truck struck two vehicles, one fatality.',
        true,'SafeSpect',
        (SELECT id FROM users WHERE email='rosa.menendez@ccfp.gov'),
        '2026-04-28 21:05+00','2026-04-28 21:06+00',
        (SELECT id FROM users WHERE email='rosa.menendez@ccfp.gov'));

INSERT INTO incident_vehicles (crash_id, vehicle_number, is_cmv, us_dot_number, make, num_occupants, num_injured_occupants, carrier_name, carrier_phone)
VALUES
 ('c2b72002-0000-0000-0000-000000000002',1,true,'2785561','International',1,0,'Lone Star Hauling Co','254-555-0180'),
 ('c2b72002-0000-0000-0000-000000000002',2,false,NULL,'Honda',2,1,NULL,NULL),
 ('c2b72002-0000-0000-0000-000000000002',3,false,NULL,'Ford',1,1,NULL,NULL);

INSERT INTO incident_persons (crash_id, person_type, related_vehicle_number, full_name, is_minor, primary_language, address, phone_primary, phone_type, injury)
VALUES
 ('c2b72002-0000-0000-0000-000000000002','DRIVER',1,'Darnell Whitaker',false,'English','910 Industrial Pkwy, Temple, TX 76501','254-555-0181','CELL','NO_INJURY'),
 ('c2b72002-0000-0000-0000-000000000002','DRIVER',2,'Sofia Marchetti',false,'Spanish','3312 Austin Ave, Waco, TX 76710','254-555-0182','CELL','FATAL'),
 ('c2b72002-0000-0000-0000-000000000002','DRIVER',3,'Gregory Paulsen',false,'English','77 Bosque Blvd, Waco, TX 76707','254-555-0183','CELL','INJURY');

INSERT INTO post_crash_inspections (crash_id, source_system, inspection_number, inspection_date, inspector_name, violations_count, defects_count, details)
VALUES ('c2b72002-0000-0000-0000-000000000002','SafeSpect','INS-TX-44219','2026-04-28','R. Menendez',0,0,'{"result":"no violations found"}');

INSERT INTO police_crash_reports (crash_id, state_code, source_repository, pcr_number, report_date, mapping_status)
VALUES ('c2b72002-0000-0000-0000-000000000002','TX','Texas CRIS','TX-CRIS-2026-771203','2026-05-02','PENDING');

INSERT INTO source_records (crash_id, source_system, source_type, external_id, raw_zone_uri, provenance_note)
VALUES ('c2b72002-0000-0000-0000-000000000002','SafeSpect','INSPECTION','INS-TX-44219','s3://ccfp-raw/safespect/INS-TX-44219.json','Automated SafeSpect ingestion');

INSERT INTO crash_completeness_status (crash_id, status, is_current, is_locked, missing_summary, changed_by)
VALUES ('c2b72002-0000-0000-0000-000000000002','INCOMPLETE',true,false,
        '{"missing":["police_crash_report_mapping","post_crash_investigation","contributing_factors"]}',
        (SELECT id FROM users WHERE email='grant.holloway@ccfp.gov'));

INSERT INTO data_quality_results (crash_id, rule_id, status, message)
SELECT 'c2b72002-0000-0000-0000-000000000002', dr.id, st.status::qc_result_status, st.msg
FROM (VALUES
 ('DQ_MISSING_IIF','PASS','Initial Incident Form present.'),
 ('DQ_DOT_SAFESPECT','PASS','USDOT 2785561 validated via SafeSpect.'),
 ('DQ_TOP_FACTORS','FAIL','Top three contributing factors not yet selected.')
) AS st(code, status, msg)
JOIN data_quality_rules dr ON dr.code = st.code;

-- ---------------------------------------------------------------------------
-- CRASH 3 - California, in-scope, INITIAL_INCIDENT only (just created)
-- ---------------------------------------------------------------------------
INSERT INTO crashes (id, ccfp_identifier, study_id, local_report_number, crash_date, crash_time,
                     city, county, state_code, street_highway, latitude, longitude,
                     num_vehicles, num_persons, num_fatalities, lifecycle_phase, created_by)
SELECT 'c3c93003-0000-0000-0000-000000000003','CCFP-2026-CA-000103',
       (SELECT id FROM studies WHERE code='PHASE1-HDT'),
       'CA-2026-552201','2026-05-30','22:10','Bakersfield','Kern','CA','SR-99 NB near Olive Dr', 35.413700, -119.018700,
       2, 2, 1, 'NOTIFICATION',
       (SELECT id FROM users WHERE email='linh.tran@ccfp.gov');

INSERT INTO crash_scope_classifications (crash_id, is_qualifying, scope, is_supplemental, classification_reason, classified_by)
VALUES ('c3c93003-0000-0000-0000-000000000003', true, 'IN_SCOPE', false,
        'Fatal crash involving a Class 8 truck in a participating State (CA).',
        (SELECT id FROM users WHERE email='linh.tran@ccfp.gov'));

INSERT INTO initial_incident_forms (crash_id, status, event_summary, dot_number_validated, dot_validation_source, submitted_by, submitted_at, created_by)
VALUES ('c3c93003-0000-0000-0000-000000000003','SUBMITTED',
        'Tractor-trailer single-vehicle rollover on highway ramp; driver fatality. Pending DOT validation.',
        false,'SafeSpect',
        (SELECT id FROM users WHERE email='linh.tran@ccfp.gov'),
        '2026-05-31 01:40+00',
        (SELECT id FROM users WHERE email='linh.tran@ccfp.gov'));

INSERT INTO incident_vehicles (crash_id, vehicle_number, is_cmv, us_dot_number, make, num_occupants, num_injured_occupants, carrier_name, carrier_phone)
VALUES ('c3c93003-0000-0000-0000-000000000003',1,true,'4410092','Peterbilt',1,1,'Golden Valley Transport Inc','661-555-0190');

INSERT INTO incident_persons (crash_id, person_type, related_vehicle_number, full_name, is_minor, primary_language, address, phone_primary, phone_type, injury)
VALUES ('c3c93003-0000-0000-0000-000000000003','DRIVER',1,'Eduardo Salcedo',false,'Spanish','1450 Rosedale Hwy, Bakersfield, CA 93308','661-555-0191','CELL','FATAL');

INSERT INTO crash_completeness_status (crash_id, status, is_current, is_locked, missing_summary, changed_by)
VALUES ('c3c93003-0000-0000-0000-000000000003','INCOMPLETE',true,false,
        '{"missing":["dot_validation","post_crash_inspection","police_crash_report","investigation"]}',
        (SELECT id FROM users WHERE email='linh.tran@ccfp.gov'));

INSERT INTO data_quality_results (crash_id, rule_id, status, message)
SELECT 'c3c93003-0000-0000-0000-000000000003', dr.id, st.status::qc_result_status, st.msg
FROM (VALUES
 ('DQ_MISSING_IIF','PASS','Initial Incident Form submitted.'),
 ('DQ_DOT_SAFESPECT','FAIL','USDOT 4410092 pending SafeSpect validation.')
) AS st(code, status, msg)
JOIN data_quality_rules dr ON dr.code = st.code;

-- ---------------------------------------------------------------------------
-- CRASH 4 - Missouri (non-participating), OUT_OF_SCOPE supplemental
-- ---------------------------------------------------------------------------
INSERT INTO crashes (id, ccfp_identifier, study_id, local_report_number, crash_date, crash_time,
                     city, county, state_code, street_highway, latitude, longitude,
                     num_vehicles, num_persons, num_fatalities, lifecycle_phase, created_by)
SELECT 'c4d04004-0000-0000-0000-000000000004','CCFP-2026-MO-000104',
       (SELECT id FROM studies WHERE code='PHASE1-HDT'),
       'MO-2026-300118','2026-02-09','13:05','Columbia','Boone','MO','I-70 EB MM126', 38.951100, -92.328500,
       2, 3, 0, 'DATA_COLLECTION',
       (SELECT id FROM users WHERE email='dana.whitfield@ccfp.gov');

INSERT INTO crash_scope_classifications (crash_id, is_qualifying, scope, is_supplemental, classification_reason, classified_by)
VALUES ('c4d04004-0000-0000-0000-000000000004', true, 'OUT_OF_SCOPE', true,
        'Qualifying heavy-duty truck serious-injury crash in a non-participating State (MO); retained as supplemental.',
        (SELECT id FROM users WHERE email='dana.whitfield@ccfp.gov'));

INSERT INTO incident_vehicles (crash_id, vehicle_number, is_cmv, us_dot_number, make, num_occupants, num_injured_occupants, carrier_name, carrier_phone)
VALUES
 ('c4d04004-0000-0000-0000-000000000004',1,true,'1559872','Kenworth',1,1,'Heartland Carriers LLC','573-555-0195'),
 ('c4d04004-0000-0000-0000-000000000004',2,false,NULL,'Chevrolet',2,2,NULL,NULL);

INSERT INTO incident_persons (crash_id, person_type, related_vehicle_number, full_name, is_minor, primary_language, address, phone_primary, phone_type, injury)
VALUES
 ('c4d04004-0000-0000-0000-000000000004','DRIVER',1,'Travis Lundqvist',false,'English','62 Depot St, Columbia, MO 65201','573-555-0196','CELL','INJURY'),
 ('c4d04004-0000-0000-0000-000000000004','DRIVER',2,'Renata Oyelaran',false,'English','1209 Broadway, Columbia, MO 65203','573-555-0197','CELL','INJURY');

INSERT INTO crash_completeness_status (crash_id, status, is_current, is_locked, missing_summary, changed_by)
VALUES ('c4d04004-0000-0000-0000-000000000004','INCOMPLETE',true,false,
        '{"note":"supplemental out-of-scope record; completeness rules not enforced"}',
        (SELECT id FROM users WHERE email='dana.whitfield@ccfp.gov'));

-- ---------------------------------------------------------------------------
-- Notifications (lifecycle routing + QC) referencing the demo crashes
-- ---------------------------------------------------------------------------
INSERT INTO notifications (recipient_user_id, notification_type, crash_id, title, message, channel, status, read_at)
VALUES
 ((SELECT id FROM users WHERE email='elliot.fontaine@ccfp.gov'),'NEW_IIF','c1a51001-0000-0000-0000-000000000001','New Initial Incident Form','A new IIF was submitted for CCFP-2026-KS-000101.','IN_APP','READ','2026-03-12 10:00+00'),
 ((SELECT id FROM users WHERE email='helena.brandt@ccfp.gov'),'IN_SCOPE_ROUTING','c1a51001-0000-0000-0000-000000000001','In-scope crash for CIPSEA interview','In-scope crash CCFP-2026-KS-000101 routed to BTS CIPSEA workflow.','EMAIL','DELIVERED',NULL),
 ((SELECT id FROM users WHERE email='grant.holloway@ccfp.gov'),'NEW_IIF','c2b72002-0000-0000-0000-000000000002','New Initial Incident Form','A new IIF was submitted for CCFP-2026-TX-000102.','IN_APP','SENT',NULL),
 ((SELECT id FROM users WHERE email='grant.holloway@ccfp.gov'),'QC_FAILURE','c2b72002-0000-0000-0000-000000000002','QC failure: contributing factors','Top three contributing factors not yet selected for CCFP-2026-TX-000102.','IN_APP','PENDING',NULL),
 ((SELECT id FROM users WHERE email='linh.tran@ccfp.gov'),'QC_FAILURE','c3c93003-0000-0000-0000-000000000003','QC failure: DOT validation','USDOT pending SafeSpect validation for CCFP-2026-CA-000103.','IN_APP','SENT',NULL);

-- ---------------------------------------------------------------------------
-- Reports (one published de-identified public output + one internal dashboard)
-- ---------------------------------------------------------------------------
INSERT INTO reports (name, report_type, study_id, description, definition, visibility, is_published, is_deidentified, owner_id, published_at)
SELECT r.name, r.rtype::report_type,
       (SELECT id FROM studies WHERE code='PHASE1-HDT'),
       r.descr, r.def::jsonb, r.vis::report_visibility, r.pub, r.deid,
       (SELECT id FROM users WHERE email='priya.ramanathan@ccfp.gov'),
       r.pubat::timestamptz
FROM (VALUES
 ('Phase 1 Fatal HDT Crashes - Public Summary','REPORT','Summarized, de-identified public output for the Heavy-Duty Truck Study.','{"metrics":["crash_count","fatality_count","top_factors"]}','PUBLIC',true,true,'2026-06-01 12:00+00'),
 ('CCFP Operations Dashboard','DASHBOARD','Internal dashboard of crash lifecycle status and QC results.','{"widgets":["lifecycle_funnel","qc_failures","state_coverage"]}','ORGANIZATION',false,false,NULL)
) AS r(name, rtype, descr, def, vis, pub, deid, pubat);

-- ---------------------------------------------------------------------------
-- Audit log entries for the demo crashes
-- ---------------------------------------------------------------------------
INSERT INTO audit_logs (actor_user_id, action, entity_type, entity_id, crash_id, after_state, ip_address)
VALUES
 ((SELECT id FROM users WHERE email='nora.kowalczyk@ccfp.gov'),'CREATE','crash','c1a51001-0000-0000-0000-000000000001','c1a51001-0000-0000-0000-000000000001','{"ccfp_identifier":"CCFP-2026-KS-000101"}','198.51.100.21'),
 ((SELECT id FROM users WHERE email='nora.kowalczyk@ccfp.gov'),'SUBMIT','initial_incident_form',NULL,'c1a51001-0000-0000-0000-000000000001','{"status":"ROUTED"}','198.51.100.21'),
 ((SELECT id FROM users WHERE email='elliot.fontaine@ccfp.gov'),'UPDATE','crash_completeness_status',NULL,'c1a51001-0000-0000-0000-000000000001','{"status":"COMPLETE","is_locked":true}','203.0.113.40'),
 ((SELECT id FROM users WHERE email='rosa.menendez@ccfp.gov'),'CREATE','crash','c2b72002-0000-0000-0000-000000000002','c2b72002-0000-0000-0000-000000000002','{"ccfp_identifier":"CCFP-2026-TX-000102"}','192.0.2.55'),
 ((SELECT id FROM users WHERE email='linh.tran@ccfp.gov'),'CREATE','crash','c3c93003-0000-0000-0000-000000000003','c3c93003-0000-0000-0000-000000000003','{"ccfp_identifier":"CCFP-2026-CA-000103"}','192.0.2.77');
