-- =============================================================================
-- Seed 0007 - Additional study phases (development / demo)
-- =============================================================================
-- Adds future CCFP study phases (documentation §3.4 future scope) plus a
-- completed pilot, so the /studies page shows a fuller program lifecycle.
-- 100% synthetic. Idempotent: ON CONFLICT (code) DO NOTHING.
-- =============================================================================

INSERT INTO studies (code, name, phase_number, vehicle_type, crash_severity, description, start_date, end_date, pilot_start_date, status) VALUES
 ('PILOT-2025','Heavy-Duty Truck Pilot Feasibility',0,'Heavy-Duty Truck (Class 7/8, GVWR >= 26,001 lbs)','Fatal','Completed pilot that validated CCFP data-collection workflows ahead of Phase 1.','2025-01-01','2025-06-30','2025-01-15','CLOSED'),
 ('PHASE3-BUS','Motorcoach & Transit Bus Study',3,'Bus (motorcoach, transit, and school bus)','Fatal','Future CCFP phase studying fatal crashes involving buses.',NULL,NULL,NULL,'PLANNING'),
 ('PHASE4-HDT-SI','Heavy-Duty Truck Serious-Injury Study',4,'Heavy-Duty Truck (Class 7/8, GVWR >= 26,001 lbs)','Serious Injury','Serious-injury heavy-duty truck crashes with advanced investigation data.',NULL,NULL,NULL,'PLANNING'),
 ('PHASE5-HAZMAT','Hazardous Materials Carrier Study',5,'CMV transporting hazardous materials','Fatal and Serious Injury','Future phase focused on causal factors in hazmat-carrier crashes.',NULL,NULL,NULL,'PLANNING')
ON CONFLICT (code) DO NOTHING;
