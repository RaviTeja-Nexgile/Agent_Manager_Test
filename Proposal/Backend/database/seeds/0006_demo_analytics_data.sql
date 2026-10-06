-- =============================================================================
-- Seed 0005 - Additional synthetic data for Analytics, Reports & Public outputs
-- =============================================================================
-- Purpose: the base demo set (seed 0004) contains only 4 crashes / 2 reports /
-- 1 published output, which leaves the Analytics, Reports and Public-outputs
-- pages looking sparse. This seed adds more fictitious crashes (spread across
-- States, lifecycle phases and fatality counts), data-quality results (spread
-- across QC rules so "QC failures by rule" is meaningful), additional reports,
-- and several published, de-identified PUBLIC outputs.
--
-- ALL data below is fictitious. Names, places, DOT numbers and report numbers
-- are invented for demonstration only and do not correspond to any real person,
-- carrier, vehicle, or crash. Applied exactly once (tracked by filename).
-- =============================================================================

-- ---------------------------------------------------------------------------
-- Additional crash records (16) — Phase 1 Heavy-Duty Truck Study
-- ---------------------------------------------------------------------------
INSERT INTO crashes (id, ccfp_identifier, study_id, local_report_number, crash_date, crash_time,
                     city, county, state_code, street_highway, latitude, longitude,
                     num_vehicles, num_persons, num_fatalities, lifecycle_phase, created_by)
SELECT v.id::uuid, v.ccfp,
       (SELECT id FROM studies WHERE code='PHASE1-HDT'),
       v.lrn, v.cdate::date, v.ctime::time, v.city, v.county, v.state, v.road,
       v.lat::numeric, v.lon::numeric, v.nv, v.np, v.nf, v.phase::crash_lifecycle_phase,
       (SELECT id FROM users WHERE email=v.creator)
FROM (VALUES
 ('c5d00005-0000-0000-0000-000000000105','CCFP-2026-KS-000105','KS-2026-005120','2026-03-22','07:15','Topeka','Shawnee','KS','I-70 near Wanamaker Rd',39.0558,-95.7956,2,3,1,'DATA_MAPPING','nora.kowalczyk@khp.example.gov'),
 ('c5d00005-0000-0000-0000-000000000106','CCFP-2026-KS-000106','KS-2026-005219','2026-04-03','15:40','Wichita','Sedgwick','KS','US-54 at Rock Rd',37.6889,-97.2419,3,4,2,'QUALITY_CONTROL','nora.kowalczyk@khp.example.gov'),
 ('c5d00005-0000-0000-0000-000000000107','CCFP-2026-KS-000107','KS-2026-005377','2026-04-19','09:05','Lawrence','Douglas','KS','K-10 near Eudora',38.9461,-95.1042,2,2,1,'ANALYSIS','nora.kowalczyk@khp.example.gov'),
 ('c5d00005-0000-0000-0000-000000000108','CCFP-2026-KS-000108','KS-2026-005461','2026-01-28','18:50','Hays','Ellis','KS','I-70 near Mile Marker 159',38.8792,-99.3268,2,2,1,'PUBLICATION','nora.kowalczyk@khp.example.gov'),
 ('c5d00005-0000-0000-0000-000000000109','CCFP-2026-KS-000109','KS-2026-005588','2026-05-11','12:25','Emporia','Lyon','KS','I-35 near Industrial Rd',38.4039,-96.1817,2,3,1,'DATA_COLLECTION','nora.kowalczyk@khp.example.gov'),
 ('c5d00005-0000-0000-0000-000000000110','CCFP-2026-TX-000110','TX-2026-120145','2026-03-30','08:30','Dallas','Dallas','TX','I-35E near Illinois Ave',32.7322,-96.8245,4,5,2,'ANALYSIS','rosa.menendez@dps.tx.example.gov'),
 ('c5d00005-0000-0000-0000-000000000111','CCFP-2026-TX-000111','TX-2026-120318','2026-04-14','16:10','Houston','Harris','TX','I-610 at US-290',29.8019,-95.4630,3,3,1,'QUALITY_CONTROL','rosa.menendez@dps.tx.example.gov'),
 ('c5d00005-0000-0000-0000-000000000112','CCFP-2026-TX-000112','TX-2026-120474','2026-05-06','11:00','Austin','Travis','TX','I-35 near Riverside Dr',30.2426,-97.7281,2,2,1,'DATA_MAPPING','rosa.menendez@dps.tx.example.gov'),
 ('c5d00005-0000-0000-0000-000000000113','CCFP-2026-TX-000113','TX-2026-120612','2026-05-25','20:45','El Paso','El Paso','TX','I-10 near Airway Blvd',31.8009,-106.3784,2,4,1,'NOTIFICATION','rosa.menendez@dps.tx.example.gov'),
 ('c5d00005-0000-0000-0000-000000000114','CCFP-2026-CA-000114','CA-2026-553118','2026-03-17','06:20','Fresno','Fresno','CA','SR-99 near Ashlan Ave',36.7783,-119.7935,2,3,1,'ANALYSIS','linh.tran@chp.ca.example.gov'),
 ('c5d00005-0000-0000-0000-000000000115','CCFP-2026-CA-000115','CA-2026-553290','2026-04-26','14:35','Sacramento','Sacramento','CA','I-5 near Sutterville Rd',38.5176,-121.5020,3,5,2,'DATA_COLLECTION','linh.tran@chp.ca.example.gov'),
 ('c5d00005-0000-0000-0000-000000000116','CCFP-2026-CA-000116','CA-2026-553451','2026-05-18','10:50','Stockton','San Joaquin','CA','I-5 near Hammer Ln',38.0297,-121.3469,2,2,1,'QUALITY_CONTROL','linh.tran@chp.ca.example.gov'),
 ('c5d00005-0000-0000-0000-000000000117','CCFP-2026-MO-000117','MO-2026-301204','2026-02-21','13:30','Kansas City','Jackson','MO','I-435 near Front St',39.1283,-94.5102,2,3,1,'DATA_COLLECTION','dana.whitfield@ccfp.example.gov'),
 ('c5d00005-0000-0000-0000-000000000118','CCFP-2026-MO-000118','MO-2026-301355','2026-03-08','09:45','Springfield','Greene','MO','I-44 near Glenstone Ave',37.2153,-93.2784,2,2,0,'DATA_MAPPING','dana.whitfield@ccfp.example.gov'),
 ('c5d00005-0000-0000-0000-000000000119','CCFP-2026-OK-000119','OK-2026-410117','2026-04-11','19:20','Tulsa','Tulsa','OK','I-44 near Yale Ave',36.1156,-95.9211,2,3,1,'NOTIFICATION','marcus.ellingsworth@ccfp.example.gov'),
 ('c5d00005-0000-0000-0000-000000000120','CCFP-2026-OK-000120','OK-2026-410288','2026-05-02','15:15','Oklahoma City','Oklahoma','OK','I-40 near Meridian Ave',35.4676,-97.5836,3,4,2,'ANALYSIS','marcus.ellingsworth@ccfp.example.gov')
) AS v(id, ccfp, lrn, cdate, ctime, city, county, state, road, lat, lon, nv, np, nf, phase, creator);

-- ---------------------------------------------------------------------------
-- Scope classifications (participating States IN_SCOPE; MO/OK OUT_OF_SCOPE)
-- ---------------------------------------------------------------------------
INSERT INTO crash_scope_classifications (crash_id, is_qualifying, scope, is_supplemental, classification_reason, classified_by)
SELECT v.id::uuid, true, v.scope::crash_scope, v.suppl, v.reason,
       (SELECT id FROM users WHERE email=v.classifier)
FROM (VALUES
 ('c5d00005-0000-0000-0000-000000000105','IN_SCOPE',false,'Fatal Class 8 truck crash in a participating State (KS).','elliot.fontaine@khp.example.gov'),
 ('c5d00005-0000-0000-0000-000000000106','IN_SCOPE',false,'Fatal Class 8 truck crash in a participating State (KS).','elliot.fontaine@khp.example.gov'),
 ('c5d00005-0000-0000-0000-000000000107','IN_SCOPE',false,'Fatal Class 7 truck crash in a participating State (KS).','elliot.fontaine@khp.example.gov'),
 ('c5d00005-0000-0000-0000-000000000108','IN_SCOPE',false,'Fatal Class 8 truck crash in a participating State (KS).','elliot.fontaine@khp.example.gov'),
 ('c5d00005-0000-0000-0000-000000000109','IN_SCOPE',false,'Fatal Class 8 truck crash in a participating State (KS).','elliot.fontaine@khp.example.gov'),
 ('c5d00005-0000-0000-0000-000000000110','IN_SCOPE',false,'Fatal Class 8 truck crash in a participating State (TX).','grant.holloway@dps.tx.example.gov'),
 ('c5d00005-0000-0000-0000-000000000111','IN_SCOPE',false,'Fatal Class 7 truck crash in a participating State (TX).','grant.holloway@dps.tx.example.gov'),
 ('c5d00005-0000-0000-0000-000000000112','IN_SCOPE',false,'Fatal Class 8 truck crash in a participating State (TX).','grant.holloway@dps.tx.example.gov'),
 ('c5d00005-0000-0000-0000-000000000113','IN_SCOPE',false,'Fatal Class 8 truck crash in a participating State (TX).','grant.holloway@dps.tx.example.gov'),
 ('c5d00005-0000-0000-0000-000000000114','IN_SCOPE',false,'Fatal Class 8 truck crash in a participating State (CA).','linh.tran@chp.ca.example.gov'),
 ('c5d00005-0000-0000-0000-000000000115','IN_SCOPE',false,'Fatal Class 8 truck crash in a participating State (CA).','linh.tran@chp.ca.example.gov'),
 ('c5d00005-0000-0000-0000-000000000116','IN_SCOPE',false,'Fatal Class 7 truck crash in a participating State (CA).','linh.tran@chp.ca.example.gov'),
 ('c5d00005-0000-0000-0000-000000000117','OUT_OF_SCOPE',true,'Qualifying HDT crash in a non-participating State (MO); retained as supplemental.','dana.whitfield@ccfp.example.gov'),
 ('c5d00005-0000-0000-0000-000000000118','OUT_OF_SCOPE',true,'Qualifying HDT serious-injury crash in a non-participating State (MO); supplemental.','dana.whitfield@ccfp.example.gov'),
 ('c5d00005-0000-0000-0000-000000000119','OUT_OF_SCOPE',true,'Qualifying HDT crash in a non-participating State (OK); retained as supplemental.','marcus.ellingsworth@ccfp.example.gov'),
 ('c5d00005-0000-0000-0000-000000000120','OUT_OF_SCOPE',true,'Qualifying HDT crash in a non-participating State (OK); retained as supplemental.','marcus.ellingsworth@ccfp.example.gov')
) AS v(id, scope, suppl, reason, classifier);

-- ---------------------------------------------------------------------------
-- Data-quality results — spread PASS / FAIL / WARNING across all QC rules so
-- the "QC failures by rule" analytics chart is populated and varied.
-- ---------------------------------------------------------------------------
INSERT INTO data_quality_results (crash_id, rule_id, status, message)
SELECT v.id::uuid, dr.id, v.status::qc_result_status, v.msg
FROM (VALUES
 ('c5d00005-0000-0000-0000-000000000105','DQ_MISSING_IIF','PASS','Initial Incident Form present and routed.'),
 ('c5d00005-0000-0000-0000-000000000105','DQ_ELD_LINKED','FAIL','No ELD file linked to the crash record.'),
 ('c5d00005-0000-0000-0000-000000000106','DQ_MISSING_IIF','PASS','Initial Incident Form present.'),
 ('c5d00005-0000-0000-0000-000000000106','DQ_FATALITY_COUNT','PASS','2 fatalities recorded and reconciled.'),
 ('c5d00005-0000-0000-0000-000000000107','DQ_CDLIS_CHECK','FAIL','Driver license could not be validated via CDLIS.'),
 ('c5d00005-0000-0000-0000-000000000108','DQ_TOP_FACTORS','PASS','Three contributing factors selected.'),
 ('c5d00005-0000-0000-0000-000000000109','DQ_MISSING_REQUIRED_ATTR','FAIL','Required attribute "carrier USDOT" is missing.'),
 ('c5d00005-0000-0000-0000-000000000110','DQ_FATALITY_COUNT','WARNING','Fatality count differs between PCR and IIF; review needed.'),
 ('c5d00005-0000-0000-0000-000000000110','DQ_TOP_FACTORS','PASS','Three contributing factors selected.'),
 ('c5d00005-0000-0000-0000-000000000111','DQ_DOT_FORMAT','FAIL','USDOT number fails format validation.'),
 ('c5d00005-0000-0000-0000-000000000112','DQ_TOP_FACTORS','FAIL','Top three contributing factors not yet selected.'),
 ('c5d00005-0000-0000-0000-000000000113','DQ_MISSING_IIF','FAIL','Initial Incident Form not yet submitted.'),
 ('c5d00005-0000-0000-0000-000000000114','DQ_DOT_SAFESPECT','FAIL','USDOT pending SafeSpect validation.'),
 ('c5d00005-0000-0000-0000-000000000114','DQ_FATALITY_COUNT','PASS','1 fatality recorded.'),
 ('c5d00005-0000-0000-0000-000000000115','DQ_ELD_LINKED','FAIL','No ELD file linked to the crash record.'),
 ('c5d00005-0000-0000-0000-000000000116','DQ_CDLIS_CHECK','PASS','Driver license validated via CDLIS.'),
 ('c5d00005-0000-0000-0000-000000000117','DQ_CDLIS_CHECK','FAIL','Driver license could not be validated via CDLIS.'),
 ('c5d00005-0000-0000-0000-000000000118','DQ_MISSING_REQUIRED_ATTR','WARNING','Optional attribute "trailer configuration" is missing.'),
 ('c5d00005-0000-0000-0000-000000000119','DQ_DOT_FORMAT','FAIL','USDOT number fails format validation.'),
 ('c5d00005-0000-0000-0000-000000000120','DQ_TOP_FACTORS','FAIL','Top three contributing factors not yet selected.')
) AS v(id, rule_code, status, msg)
JOIN data_quality_rules dr ON dr.code = v.rule_code;

-- ---------------------------------------------------------------------------
-- Completeness status (one current row per new crash)
-- ---------------------------------------------------------------------------
INSERT INTO crash_completeness_status (crash_id, status, is_current, is_locked, missing_summary, changed_by)
SELECT v.id::uuid, v.status::completeness_status, v.cur, v.locked, v.missing::jsonb,
       (SELECT id FROM users WHERE email=v.changer)
FROM (VALUES
 ('c5d00005-0000-0000-0000-000000000105','INCOMPLETE',true,false,'{"missing":["eld_file"]}','elliot.fontaine@khp.example.gov'),
 ('c5d00005-0000-0000-0000-000000000106','COMPLETE',true,true,'{"missing":[]}','elliot.fontaine@khp.example.gov'),
 ('c5d00005-0000-0000-0000-000000000107','INCOMPLETE',true,false,'{"missing":["cdlis_validation"]}','elliot.fontaine@khp.example.gov'),
 ('c5d00005-0000-0000-0000-000000000108','COMPLETE',true,true,'{"missing":[]}','elliot.fontaine@khp.example.gov'),
 ('c5d00005-0000-0000-0000-000000000109','INCOMPLETE',true,false,'{"missing":["carrier_usdot"]}','elliot.fontaine@khp.example.gov'),
 ('c5d00005-0000-0000-0000-000000000110','COMPLETE',true,false,'{"missing":[]}','grant.holloway@dps.tx.example.gov'),
 ('c5d00005-0000-0000-0000-000000000111','INCOMPLETE',true,false,'{"missing":["dot_format"]}','grant.holloway@dps.tx.example.gov'),
 ('c5d00005-0000-0000-0000-000000000112','INCOMPLETE',true,false,'{"missing":["contributing_factors"]}','grant.holloway@dps.tx.example.gov'),
 ('c5d00005-0000-0000-0000-000000000113','INCOMPLETE',true,false,'{"missing":["initial_incident_form"]}','grant.holloway@dps.tx.example.gov'),
 ('c5d00005-0000-0000-0000-000000000114','INCOMPLETE',true,false,'{"missing":["dot_validation"]}','linh.tran@chp.ca.example.gov'),
 ('c5d00005-0000-0000-0000-000000000115','INCOMPLETE',true,false,'{"missing":["eld_file"]}','linh.tran@chp.ca.example.gov'),
 ('c5d00005-0000-0000-0000-000000000116','COMPLETE',true,false,'{"missing":[]}','linh.tran@chp.ca.example.gov'),
 ('c5d00005-0000-0000-0000-000000000117','INCOMPLETE',true,false,'{"missing":["cdlis_validation"]}','dana.whitfield@ccfp.example.gov'),
 ('c5d00005-0000-0000-0000-000000000118','INCOMPLETE',true,false,'{"note":"supplemental out-of-scope record"}','dana.whitfield@ccfp.example.gov'),
 ('c5d00005-0000-0000-0000-000000000119','INCOMPLETE',true,false,'{"note":"supplemental out-of-scope record"}','marcus.ellingsworth@ccfp.example.gov'),
 ('c5d00005-0000-0000-0000-000000000120','INCOMPLETE',true,false,'{"note":"supplemental out-of-scope record"}','marcus.ellingsworth@ccfp.example.gov')
) AS v(id, status, cur, locked, missing, changer);

-- ---------------------------------------------------------------------------
-- Additional reports — internal dashboards/tables plus several published,
-- de-identified PUBLIC outputs (so the Public-outputs page is populated).
-- ---------------------------------------------------------------------------
INSERT INTO reports (name, report_type, study_id, description, definition, visibility, is_published, is_deidentified, owner_id, published_at)
SELECT r.name, r.rtype::report_type,
       (SELECT id FROM studies WHERE code='PHASE1-HDT'),
       r.descr, r.def::jsonb, r.vis::report_visibility, r.pub, r.deid,
       (SELECT id FROM users WHERE email=r.owner),
       r.pubat::timestamptz
FROM (VALUES
 -- Published, de-identified PUBLIC outputs (appear on the Public-outputs page)
 ('Heavy-Duty Truck Fatal Crashes — 2026 Q1 Public Brief','REPORT','Aggregated, de-identified summary of fatal heavy-duty truck crashes across participating States for the first quarter of 2026.','{"metrics":["crash_count","fatality_count","by_state"],"period":"2026-Q1"}','PUBLIC',true,true,'priya.ramanathan@ccfp.example.gov','2026-04-15 12:00+00'),
 ('Contributing Factors Frequency — Public Dataset','TABLE','De-identified frequency table of the leading contributing factors selected across in-scope crashes.','{"columns":["factor_group","factor","count","pct"]}','PUBLIC',true,true,'priya.ramanathan@ccfp.example.gov','2026-05-01 12:00+00'),
 ('State Participation & Crash Coverage — Public Summary','REPORT','Public-facing summary of participating States and crash-record coverage for the Heavy-Duty Truck Study.','{"metrics":["participating_states","records_collected","coverage_pct"]}','PUBLIC',true,true,'priya.ramanathan@ccfp.example.gov','2026-05-20 12:00+00'),
 ('HDT Fatality Trends — Public Visualization','VISUALIZATION','De-identified monthly trend of heavy-duty truck fatalities released as open data.','{"chart":"line","series":["fatalities_by_month"]}','PUBLIC',true,true,'priya.ramanathan@ccfp.example.gov','2026-05-28 12:00+00'),
 -- Internal / role-restricted reports (NOT public)
 ('CCFP Causal Factor Dashboard','DASHBOARD','Internal dashboard of contributing-factor distribution and QC status across the data lake.','{"widgets":["factor_distribution","qc_failures","fatalities_by_state"]}','ORGANIZATION',false,false,'priya.ramanathan@ccfp.example.gov',NULL),
 ('QC Exceptions Dashboard','DASHBOARD','Internal dashboard tracking open data-quality exceptions by rule and State.','{"widgets":["qc_failures_by_rule","exceptions_by_state"]}','ORGANIZATION',false,false,'priya.ramanathan@ccfp.example.gov',NULL),
 ('Federal Oversight Report — HDT Phase 1','REPORT','Federal-user oversight report on crash-record completeness and lifecycle progression.','{"metrics":["completeness_rate","phase_distribution"]}','FEDERAL',false,false,'omar.haddad@nhtsa.example.gov',NULL),
 ('Kansas Crash Working Table','TABLE','State analyst working table of Kansas crash records and mapping status.','{"columns":["ccfp_id","city","phase","completeness"]}','STATE',false,false,'elliot.fontaine@khp.example.gov',NULL)
) AS r(name, rtype, descr, def, vis, pub, deid, owner, pubat);
