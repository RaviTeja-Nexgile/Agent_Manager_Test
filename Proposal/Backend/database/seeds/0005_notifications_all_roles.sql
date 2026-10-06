-- =============================================================================
-- Seed 0005 — Notifications for ALL roles (documentation §8.11)
-- -----------------------------------------------------------------------------
-- Adds realistic, crash-linked, role-appropriate IN_APP / EMAIL notifications
-- for every seeded user so the /notifications page is populated regardless of
-- which demo account is logged in. Notification types follow §8.11 (NEW_IIF,
-- IN_SCOPE_ROUTING, OUT_OF_SCOPE_ROUTING, MISSING_DATA, MISSING_IIF, QC_FAILURE,
-- COMPLETENESS_CHANGE, REPORT_PUBLISHED, REPORT_SHARED) plus operational
-- SYSTEM_ALERT / INTEGRATION_STATUS / DATA_MAPPING / DATASET_READY events.
--
-- References the four demo crashes from 0004_demo_crashes.sql:
--   KS-000101 c1a51001-… (in-scope, complete)   TX-000102 c2b72002-…
--   CA-000103 c3c93003-…                         MO-000104 c4d04004-… (out-of-scope)
--
-- 100% synthetic / development data. Deterministic & re-runnable: it clears the
-- notifications table first, so applying it always yields the same full set.
-- =============================================================================

DELETE FROM notifications;

INSERT INTO notifications (recipient_user_id, notification_type, crash_id, title, message, channel, status, read_at)
VALUES
-- --- MCSAP CMV Inspectors (filed the Initial Incident Forms) ----------------
 ((SELECT id FROM users WHERE email='nora.kowalczyk@ccfp.gov'),'NEW_IIF','c1a51001-0000-0000-0000-000000000001','Initial Incident Form received','Your IIF for CCFP-2026-KS-000101 was accepted and the CCFP record was created.','IN_APP','READ','2026-03-12 09:45+00'),
 ((SELECT id FROM users WHERE email='nora.kowalczyk@ccfp.gov'),'MISSING_DATA','c1a51001-0000-0000-0000-000000000001','Missing required field','Carrier phone number is missing on CCFP-2026-KS-000101. Please complete the IIF.','IN_APP','SENT',NULL),
 ((SELECT id FROM users WHERE email='nora.kowalczyk@ccfp.gov'),'ELD_UPLOAD_REQUEST','c1a51001-0000-0000-0000-000000000001','ELD file requested','Upload the ELD/eRODS CSV for the power unit in CCFP-2026-KS-000101.','EMAIL','DELIVERED',NULL),
 ((SELECT id FROM users WHERE email='rosa.menendez@ccfp.gov'),'NEW_IIF','c2b72002-0000-0000-0000-000000000002','Initial Incident Form received','Your IIF for CCFP-2026-TX-000102 was accepted and the CCFP record was created.','IN_APP','READ','2026-04-03 14:10+00'),
 ((SELECT id FROM users WHERE email='rosa.menendez@ccfp.gov'),'MISSING_DATA','c2b72002-0000-0000-0000-000000000002','Missing required field','Number of injured occupants is blank for vehicle 1 on CCFP-2026-TX-000102.','IN_APP','SENT',NULL),

-- --- State CMV Data Analysts (per-State routing, QC, completeness) -----------
 ((SELECT id FROM users WHERE email='elliot.fontaine@ccfp.gov'),'NEW_IIF','c1a51001-0000-0000-0000-000000000001','New crash routed to you','In-scope crash CCFP-2026-KS-000101 is ready for data collection and QC.','IN_APP','READ','2026-03-12 10:00+00'),
 ((SELECT id FROM users WHERE email='elliot.fontaine@ccfp.gov'),'QC_FAILURE','c1a51001-0000-0000-0000-000000000001','QC rule failed','PCR roadway section is below required completion for CCFP-2026-KS-000101.','IN_APP','SENT',NULL),
 ((SELECT id FROM users WHERE email='elliot.fontaine@ccfp.gov'),'COMPLETENESS_CHANGE','c1a51001-0000-0000-0000-000000000001','Record marked complete','CCFP-2026-KS-000101 met all completeness rules and is now locked.','IN_APP','SENT',NULL),
 ((SELECT id FROM users WHERE email='grant.holloway@ccfp.gov'),'NEW_IIF','c2b72002-0000-0000-0000-000000000002','New crash routed to you','A new IIF was submitted for CCFP-2026-TX-000102.','IN_APP','SENT',NULL),
 ((SELECT id FROM users WHERE email='grant.holloway@ccfp.gov'),'QC_FAILURE','c2b72002-0000-0000-0000-000000000002','Contributing factors pending','Top three primary contributing factors are not yet selected for CCFP-2026-TX-000102.','IN_APP','PENDING',NULL),
 ((SELECT id FROM users WHERE email='linh.tran@ccfp.gov'),'NEW_IIF','c3c93003-0000-0000-0000-000000000003','New crash routed to you','A new IIF was submitted for CCFP-2026-CA-000103.','IN_APP','SENT',NULL),
 ((SELECT id FROM users WHERE email='linh.tran@ccfp.gov'),'QC_FAILURE','c3c93003-0000-0000-0000-000000000003','USDOT validation pending','USDOT number is awaiting SafeSpect validation for CCFP-2026-CA-000103.','IN_APP','SENT',NULL),

-- --- BTS CIPSEA Agent (confidential interview routing for in-scope crashes) --
 ((SELECT id FROM users WHERE email='helena.brandt@ccfp.gov'),'IN_SCOPE_ROUTING','c1a51001-0000-0000-0000-000000000001','In-scope crash for CIPSEA interview','In-scope crash CCFP-2026-KS-000101 routed to the BTS CIPSEA interview workflow.','EMAIL','DELIVERED',NULL),
 ((SELECT id FROM users WHERE email='helena.brandt@ccfp.gov'),'IN_SCOPE_ROUTING','c3c93003-0000-0000-0000-000000000003','In-scope crash for CIPSEA interview','In-scope crash CCFP-2026-CA-000103 routed to the BTS CIPSEA interview workflow.','EMAIL','SENT',NULL),

-- --- FMCSA CIPSEA Agent (access to protected BTS data where permitted) ------
 ((SELECT id FROM users WHERE email='marcus.ellingsworth@ccfp.gov'),'IN_SCOPE_ROUTING','c1a51001-0000-0000-0000-000000000001','CIPSEA data available','BTS interview summary is available for CCFP-2026-KS-000101 under CIPSEA controls.','IN_APP','SENT',NULL),
 ((SELECT id FROM users WHERE email='marcus.ellingsworth@ccfp.gov'),'IN_SCOPE_ROUTING','c3c93003-0000-0000-0000-000000000003','CIPSEA data available','BTS interview summary is available for CCFP-2026-CA-000103 under CIPSEA controls.','IN_APP','PENDING',NULL),

-- --- CCFP Project Team (program-wide lifecycle oversight) -------------------
 ((SELECT id FROM users WHERE email='dana.whitfield@ccfp.gov'),'NEW_IIF','c2b72002-0000-0000-0000-000000000002','New crash identified','A new in-scope crash CCFP-2026-TX-000102 has entered the program.','IN_APP','READ','2026-04-03 14:30+00'),
 ((SELECT id FROM users WHERE email='dana.whitfield@ccfp.gov'),'OUT_OF_SCOPE_ROUTING','c4d04004-0000-0000-0000-000000000004','Out-of-scope supplemental record','Supplemental out-of-scope crash CCFP-2026-MO-000104 added for analysis.','IN_APP','SENT',NULL),
 ((SELECT id FROM users WHERE email='dana.whitfield@ccfp.gov'),'COMPLETENESS_CHANGE','c1a51001-0000-0000-0000-000000000001','Record completed','CCFP-2026-KS-000101 is now complete and locked.','IN_APP','SENT',NULL),
 ((SELECT id FROM users WHERE email='dana.whitfield@ccfp.gov'),'REPORT_PUBLISHED',NULL,'Public summary published','The Phase 1 Fatal HDT Crashes public summary has been published.','IN_APP','SENT',NULL),

-- --- CCFP Project Admin (users, roles, study config, rules) -----------------
 ((SELECT id FROM users WHERE email='avery.thornton@ccfp.gov'),'MISSING_IIF',NULL,'Crash missing Initial Incident Form','A qualifying crash was detected with no IIF within 48 hours. Review required.','IN_APP','SENT',NULL),
 ((SELECT id FROM users WHERE email='avery.thornton@ccfp.gov'),'ADMIN_ACTION',NULL,'New user access request','A State user from KDOT has requested access and is awaiting role assignment.','IN_APP','PENDING',NULL),
 ((SELECT id FROM users WHERE email='avery.thornton@ccfp.gov'),'STUDY_CONFIG',NULL,'Completeness rule updated','Completeness rules for the Phase 1 Heavy-Duty Truck Study were modified.','IN_APP','READ','2026-05-20 16:00+00'),

-- --- CCFP Database Administrator (mapping, source ingestion) -----------------
 ((SELECT id FROM users WHERE email='victor.delacruz@ccfp.gov'),'DATA_MAPPING','c2b72002-0000-0000-0000-000000000002','PCR mapping required','Texas PCR fields for CCFP-2026-TX-000102 need mapping to CCFP attributes.','IN_APP','SENT',NULL),
 ((SELECT id FROM users WHERE email='victor.delacruz@ccfp.gov'),'INTEGRATION_STATUS',NULL,'MCMIS ingestion complete','Nightly MCMIS crash/inspection extract was ingested into the Raw zone.','IN_APP','DELIVERED',NULL),
 ((SELECT id FROM users WHERE email='victor.delacruz@ccfp.gov'),'DATA_MAPPING','c3c93003-0000-0000-0000-000000000003','Unmapped source attribute','3 California PCR attributes for CCFP-2026-CA-000103 are unmapped.','IN_APP','PENDING',NULL),

-- --- CCFP Data Scientist (analytical datasets, shared reports) ---------------
 ((SELECT id FROM users WHERE email='priya.ramanathan@ccfp.gov'),'DATASET_READY',NULL,'Analytical dataset refreshed','The curated Phase 1 crash dataset has been refreshed in the Analytical zone.','IN_APP','SENT',NULL),
 ((SELECT id FROM users WHERE email='priya.ramanathan@ccfp.gov'),'REPORT_SHARED',NULL,'Dashboard shared with you','The CCFP Operations Dashboard was shared with you for causal-factor analysis.','IN_APP','READ','2026-05-28 11:15+00'),

-- --- Federal User (role-approved reports) -----------------------------------
 ((SELECT id FROM users WHERE email='omar.haddad@ccfp.gov'),'REPORT_PUBLISHED',NULL,'New report available','The Phase 1 Fatal HDT Crashes summary is available to federal users.','IN_APP','SENT',NULL),
 ((SELECT id FROM users WHERE email='omar.haddad@ccfp.gov'),'REPORT_SHARED',NULL,'Report shared with you','A CCFP analyst shared the State coverage report with you.','EMAIL','DELIVERED',NULL),

-- --- State User (non-PII State reports) -------------------------------------
 ((SELECT id FROM users WHERE email='tomasz.bialek@ccfp.gov'),'REPORT_SHARED',NULL,'Kansas crash report shared','A non-PII Kansas crash summary report was shared with you.','IN_APP','SENT',NULL),
 ((SELECT id FROM users WHERE email='tomasz.bialek@ccfp.gov'),'NEW_IIF','c1a51001-0000-0000-0000-000000000001','New Kansas crash recorded','A new qualifying crash CCFP-2026-KS-000101 was recorded in your State.','IN_APP','READ','2026-03-13 08:00+00'),

-- --- Public User (published, de-identified outputs only) --------------------
 ((SELECT id FROM users WHERE email='public.demo@ccfp.gov'),'REPORT_PUBLISHED',NULL,'New public study summary','A summarized, de-identified Heavy-Duty Truck Study output is now public.','IN_APP','SENT',NULL),

-- --- System Administrator (operational / security events) -------------------
 ((SELECT id FROM users WHERE email='sysadmin@ccfp.gov'),'SYSTEM_ALERT',NULL,'Malware scan flagged an upload','An uploaded document failed the malware scan and was quarantined. Review required.','IN_APP','SENT',NULL),
 ((SELECT id FROM users WHERE email='sysadmin@ccfp.gov'),'INTEGRATION_STATUS',NULL,'SafeSpect integration degraded','SafeSpect USDOT validation latency is elevated; monitoring the adapter.','IN_APP','PENDING',NULL),
 ((SELECT id FROM users WHERE email='sysadmin@ccfp.gov'),'SYSTEM_ALERT',NULL,'Audit log export ready','The monthly immutable audit-log export completed successfully.','IN_APP','READ','2026-06-01 02:00+00'),
 ((SELECT id FROM users WHERE email='sysadmin@ccfp.gov'),'INTEGRATION_STATUS',NULL,'Scheduled maintenance window','A maintenance window is scheduled; background workers will pause briefly.','EMAIL','DELIVERED',NULL);

-- ===========================================================================
-- Additional notifications (broader coverage, linked to the 0006 demo crashes)
-- ===========================================================================
INSERT INTO notifications (recipient_user_id, notification_type, crash_id, title, message, channel, status, read_at)
VALUES
-- --- System Administrator (more operational / security events) --------------
 ((SELECT id FROM users WHERE email='sysadmin@ccfp.gov'),'SYSTEM_ALERT',NULL,'Nightly database backup completed','The encrypted backup of the CCFP transactional database finished without errors.','IN_APP','READ','2026-06-02 02:10+00'),
 ((SELECT id FROM users WHERE email='sysadmin@ccfp.gov'),'SYSTEM_ALERT',NULL,'New user account provisioned','A new MCSAP inspector account was created and is pending role assignment.','IN_APP','SENT',NULL),
 ((SELECT id FROM users WHERE email='sysadmin@ccfp.gov'),'INTEGRATION_STATUS',NULL,'CDLIS connectivity restored','The CDLIS driver-verification adapter is responding normally again.','IN_APP','READ','2026-06-01 18:30+00'),
 ((SELECT id FROM users WHERE email='sysadmin@ccfp.gov'),'DATASET_READY',NULL,'Analytical dataset rebuilt','The curated analytics dataset was refreshed and is ready for reporting.','IN_APP','SENT',NULL),
 ((SELECT id FROM users WHERE email='sysadmin@ccfp.gov'),'SYSTEM_ALERT',NULL,'API certificate renewal due','The TLS certificate for the API gateway expires in 30 days.','EMAIL','DELIVERED',NULL),

-- --- CCFP Project Team -------------------------------------------------------
 ((SELECT id FROM users WHERE email='dana.whitfield@ccfp.gov'),'REPORT_SHARED',NULL,'Report shared with you','The Phase 1 Quarterly QC Summary was shared with the project team.','IN_APP','SENT',NULL),
 ((SELECT id FROM users WHERE email='dana.whitfield@ccfp.gov'),'COMPLETENESS_CHANGE',(SELECT id FROM crashes WHERE ccfp_identifier='CCFP-2026-KS-000108'),'Record marked complete','CCFP-2026-KS-000108 met all completeness rules and is now locked.','IN_APP','READ','2026-05-29 16:00+00'),
 ((SELECT id FROM users WHERE email='dana.whitfield@ccfp.gov'),'QC_FAILURE',(SELECT id FROM crashes WHERE ccfp_identifier='CCFP-2026-TX-000106'),'QC failures detected','Two quality-control rules failed on CCFP-2026-TX-000106 during review.','IN_APP','SENT',NULL),

-- --- CCFP Data Scientist -----------------------------------------------------
 ((SELECT id FROM users WHERE email='priya.ramanathan@ccfp.gov'),'DATASET_READY',NULL,'Causal-factor dataset refreshed','New contributing-factor extracts are available for modeling.','IN_APP','SENT',NULL),
 ((SELECT id FROM users WHERE email='priya.ramanathan@ccfp.gov'),'REPORT_PUBLISHED',NULL,'Dashboard updated','The program operations dashboard was refreshed with the latest data.','IN_APP','READ','2026-06-01 09:15+00'),

-- --- CCFP Database Administrator ---------------------------------------------
 ((SELECT id FROM users WHERE email='victor.delacruz@ccfp.gov'),'DATA_MAPPING',(SELECT id FROM crashes WHERE ccfp_identifier='CCFP-2026-CA-000107'),'PCR mapping completed','State PCR attributes were mapped to the CCFP canonical model for CCFP-2026-CA-000107.','IN_APP','READ','2026-04-12 10:00+00'),
 ((SELECT id FROM users WHERE email='victor.delacruz@ccfp.gov'),'DATA_MAPPING',NULL,'Source ingestion finished','The MCMIS nightly extract was ingested into the Raw zone.','IN_APP','SENT',NULL),

-- --- State CMV Data Analysts (new crashes) -----------------------------------
 ((SELECT id FROM users WHERE email='elliot.fontaine@ccfp.gov'),'NEW_IIF',(SELECT id FROM crashes WHERE ccfp_identifier='CCFP-2026-KS-000105'),'New crash routed to you','In-scope crash CCFP-2026-KS-000105 is ready for data collection and QC.','IN_APP','SENT',NULL),
 ((SELECT id FROM users WHERE email='elliot.fontaine@ccfp.gov'),'CONTRIBUTING_FACTORS_PENDING',(SELECT id FROM crashes WHERE ccfp_identifier='CCFP-2026-KS-000108'),'Select contributing factors','Top three contributing factors are pending for CCFP-2026-KS-000108.','IN_APP','SENT',NULL),
 ((SELECT id FROM users WHERE email='grant.holloway@ccfp.gov'),'QC_FAILURE',(SELECT id FROM crashes WHERE ccfp_identifier='CCFP-2026-TX-000106'),'QC rule failed','The vehicle section is incomplete on CCFP-2026-TX-000106.','IN_APP','SENT',NULL),
 ((SELECT id FROM users WHERE email='grant.holloway@ccfp.gov'),'NEW_IIF',(SELECT id FROM crashes WHERE ccfp_identifier='CCFP-2026-TX-000109'),'New crash routed to you','A new IIF was submitted for CCFP-2026-TX-000109.','IN_APP','READ','2026-06-01 12:00+00'),
 ((SELECT id FROM users WHERE email='linh.tran@ccfp.gov'),'COMPLETENESS_CHANGE',(SELECT id FROM crashes WHERE ccfp_identifier='CCFP-2026-CA-000110'),'Record published','CCFP-2026-CA-000110 completed the publication workflow.','IN_APP','READ','2026-02-23 14:30+00'),

-- --- MCSAP CMV Inspectors ----------------------------------------------------
 ((SELECT id FROM users WHERE email='nora.kowalczyk@ccfp.gov'),'MISSING_DATA',(SELECT id FROM crashes WHERE ccfp_identifier='CCFP-2026-KS-000105'),'Missing required field','Carrier phone number is missing on CCFP-2026-KS-000105.','IN_APP','SENT',NULL),
 ((SELECT id FROM users WHERE email='rosa.menendez@ccfp.gov'),'NEW_IIF',(SELECT id FROM crashes WHERE ccfp_identifier='CCFP-2026-TX-000114'),'Initial Incident Form received','Your IIF for CCFP-2026-TX-000114 was accepted and the CCFP record was created.','IN_APP','READ','2026-06-03 08:00+00'),

-- --- BTS CIPSEA Agent --------------------------------------------------------
 ((SELECT id FROM users WHERE email='helena.brandt@ccfp.gov'),'IN_SCOPE_ROUTING',(SELECT id FROM crashes WHERE ccfp_identifier='CCFP-2026-KS-000105'),'In-scope crash for CIPSEA interview','In-scope crash CCFP-2026-KS-000105 routed to the BTS CIPSEA interview workflow.','EMAIL','DELIVERED',NULL),

-- --- Federal User ------------------------------------------------------------
 ((SELECT id FROM users WHERE email='omar.haddad@ccfp.gov'),'REPORT_PUBLISHED',NULL,'New published output','A de-identified Phase 1 Heavy-Duty Truck Study summary is now available.','IN_APP','SENT',NULL),

-- --- Public User -------------------------------------------------------------
 ((SELECT id FROM users WHERE email='public.demo@ccfp.gov'),'REPORT_PUBLISHED',NULL,'New public summary available','A new de-identified study summary was released to the public.','IN_APP','SENT',NULL);
