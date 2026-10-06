-- =============================================================================
-- Seed 0003 - Studies, parameters, PCR attribute catalog, requirements,
--             State PCR coverage, QC rules, completeness rules.
-- Reference/configuration data derived from the documentation (synthetic).
-- =============================================================================

-- ---------------------------------------------------------------------------
-- Studies (Phase 1 active; a future planning phase for configurability demo)
-- ---------------------------------------------------------------------------
INSERT INTO studies (code, name, phase_number, vehicle_type, crash_severity, description, start_date, end_date, pilot_start_date, status) VALUES
 ('PHASE1-HDT','Heavy-Duty Truck Study',1,'Heavy-Duty Truck (Class 7/8, GVWR >= 26,001 lbs)','Fatal','Phase 1 CCFP study of fatal crashes involving Class 7/8 trucks.','2025-07-01',NULL,'2026-01-01','ACTIVE'),
 ('PHASE2-MDT','Medium-Duty Truck Study',2,'Medium-Duty Truck (Class 3-6, GVWR 10,001-26,000 lbs)','Fatal and Serious Injury','Future phase placeholder demonstrating multi-phase configurability.',NULL,NULL,NULL,'PLANNING')
ON CONFLICT (code) DO NOTHING;

-- Study parameters (scope rules) for Phase 1.
INSERT INTO study_parameters (study_id, param_key, param_value, description)
SELECT s.id, p.k, p.v::jsonb, p.d
FROM studies s JOIN (VALUES
 ('min_gvwr_lbs','26001','Minimum GVWR for a qualifying heavy-duty truck'),
 ('vehicle_classes','["7","8"]','Qualifying vehicle classes'),
 ('qualifying_rule','{"min_fatalities":1,"requires_heavy_duty_truck":true}','At least one fatality and one Class 7/8 truck'),
 ('iif_submission_window_hours','{"min":24,"max":48}','Initial Incident Form submission window after a crash'),
 ('recon_expected_days','{"min":90,"max":120}','Expected reconstruction report turnaround'),
 ('top_contributing_factors','3','Number of primary contributing factors selected by analyst')
) AS p(k,v,d) ON s.code='PHASE1-HDT'
ON CONFLICT (study_id, param_key) DO NOTHING;

-- Participating / non-participating states for Phase 1.
INSERT INTO study_states (study_id, state_code, is_participating, agreement_status, onboarded_at)
SELECT s.id, ss.state_code, ss.participating, ss.status, ss.onboarded
FROM studies s JOIN (VALUES
 ('KS',true,'SIGNED',DATE '2025-07-15'),
 ('TX',true,'SIGNED',DATE '2025-08-01'),
 ('CA',true,'SIGNED',DATE '2025-08-20'),
 ('MO',false,'PENDING',NULL),
 ('OK',false,'PENDING',NULL)
) AS ss(state_code, participating, status, onboarded) ON s.code='PHASE1-HDT'
ON CONFLICT (study_id, state_code) DO NOTHING;

-- ---------------------------------------------------------------------------
-- PCR / CCFP data attribute catalog (documentation §19.4)
-- ---------------------------------------------------------------------------
INSERT INTO data_attributes (code, name, category, pcr_section, data_type, sensitivity) VALUES
 -- Crash
 ('C01','Crash identifier','Crash','CRASH','CODE','INTERNAL'),
 ('C02','Crash classification','Crash','CRASH','CODE','INTERNAL'),
 ('C03','Crash date and time','Crash','CRASH','DATETIME','INTERNAL'),
 ('C04','Crash county','Crash','CRASH','TEXT','INTERNAL'),
 ('C05','Crash city/place','Crash','CRASH','TEXT','INTERNAL'),
 ('C06','Crash location','Crash','CRASH','TEXT','INTERNAL'),
 ('C07','First harmful event','Crash','CRASH','CODE','INTERNAL'),
 ('C08','Location of first harmful event relative to trafficway','Crash','CRASH','CODE','INTERNAL'),
 ('C09','Manner of crash/collision','Crash','CRASH','CODE','INTERNAL'),
 ('C10','Source of information','Crash','CRASH','TEXT','INTERNAL'),
 ('C11','Weather conditions','Crash','CRASH','CODE','INTERNAL'),
 ('C12','Light condition','Crash','CRASH','CODE','INTERNAL'),
 ('C13','Roadway surface condition','Crash','CRASH','CODE','INTERNAL'),
 ('C14','Contributing circumstances','Crash','CRASH','CODE','INTERNAL'),
 ('C15','Relation to junction','Crash','CRASH','CODE','INTERNAL'),
 ('C16','Type of intersection','Crash','CRASH','CODE','INTERNAL'),
 ('C19','Crash severity','Crash','CRASH','CODE','INTERNAL'),
 ('C20','Number of motor vehicles involved','Crash','CRASH','NUMBER','INTERNAL'),
 ('C21','Number of motorists','Crash','CRASH','NUMBER','INTERNAL'),
 ('C23','Number of non-fatally injured persons','Crash','CRASH','NUMBER','INTERNAL'),
 ('C24','Number of fatalities','Crash','CRASH','NUMBER','INTERNAL'),
 ('C25','Alcohol involvement','Crash','CRASH','CODE','SENSITIVE'),
 ('C26','Drug involvement','Crash','CRASH','CODE','SENSITIVE'),
 ('CX1','Crash description','Crash','CRASH','TEXT','SENSITIVE'),
 ('CX2','Property damage not vehicle','Crash','CRASH','TEXT','INTERNAL'),
 -- Dynamic data elements
 ('DV01','Motor vehicle automated driving systems','Dynamic','DYNAMIC','CODE','INTERNAL'),
 -- Fatal section
 ('F01','Attempted avoidance maneuver','Fatal','FATAL','CODE','INTERNAL'),
 ('F02','Alcohol test type and results','Fatal','FATAL','CODE','SENSITIVE'),
 ('F03','Drug test type and results','Fatal','FATAL','CODE','SENSITIVE'),
 ('FX1','Person (fatal)','Fatal','FATAL','TEXT','PII'),
 -- Large vehicles & hazardous materials
 ('LV01','CMV license status and CDL endorsement compliance','Large Vehicles & HazMat','LARGE_VEH_HAZMAT','CODE','INTERNAL'),
 ('LV02','Trailer license plate number','Large Vehicles & HazMat','LARGE_VEH_HAZMAT','TEXT','INTERNAL'),
 ('LV03','Trailer VINs','Large Vehicles & HazMat','LARGE_VEH_HAZMAT','TEXT','INTERNAL'),
 ('LV05','Trailer models','Large Vehicles & HazMat','LARGE_VEH_HAZMAT','TEXT','INTERNAL'),
 ('LV06','Trailer model years','Large Vehicles & HazMat','LARGE_VEH_HAZMAT','NUMBER','INTERNAL'),
 ('LV07','Motor carrier identification','Large Vehicles & HazMat','LARGE_VEH_HAZMAT','TEXT','INTERNAL'),
 ('LV08','Vehicle configuration','Large Vehicles & HazMat','LARGE_VEH_HAZMAT','CODE','INTERNAL'),
 ('LV09','Cargo body type','Large Vehicles & HazMat','LARGE_VEH_HAZMAT','CODE','INTERNAL'),
 ('LV10','Hazardous materials cargo','Large Vehicles & HazMat','LARGE_VEH_HAZMAT','CODE','INTERNAL'),
 ('LV11','Total number of axles','Large Vehicles & HazMat','LARGE_VEH_HAZMAT','NUMBER','INTERNAL'),
 ('LVX1','Cargo','Large Vehicles & HazMat','LARGE_VEH_HAZMAT','TEXT','INTERNAL'),
 ('LVX2','Trailer sizing','Large Vehicles & HazMat','LARGE_VEH_HAZMAT','TEXT','INTERNAL'),
 ('LVX3','Trailer type','Large Vehicles & HazMat','LARGE_VEH_HAZMAT','CODE','INTERNAL'),
 -- Non-motorist
 ('NM01','Unit number of motor vehicle striking non-motorist','Non-Motorist','NON_MOTORIST','NUMBER','INTERNAL'),
 ('NM02','Non-motorist crash data','Non-Motorist','NON_MOTORIST','CODE','INTERNAL'),
 ('NM03','Non-motorist contributing circumstances/actions','Non-Motorist','NON_MOTORIST','CODE','INTERNAL'),
 ('NM04','Non-motorist location','Non-Motorist','NON_MOTORIST','CODE','INTERNAL'),
 ('NM05','Non-motorist safety equipment','Non-Motorist','NON_MOTORIST','CODE','INTERNAL'),
 ('NM06','Initial contact point','Non-Motorist','NON_MOTORIST','CODE','INTERNAL'),
 ('NMX1','Non-motorist unit type','Non-Motorist','NON_MOTORIST','CODE','INTERNAL'),
 ('NMX2','Non-motorist direction','Non-Motorist','NON_MOTORIST','CODE','INTERNAL'),
 -- Person
 ('P01','Name','Person','PERSON','TEXT','PII'),
 ('P02','Date of birth','Person','PERSON','DATE','PII'),
 ('P03','Sex','Person','PERSON','CODE','PII'),
 ('P04','Person type','Person','PERSON','CODE','INTERNAL'),
 ('P05','Injury status','Person','PERSON','CODE','SENSITIVE'),
 ('P06','Occupant''s motor vehicle','Person','PERSON','NUMBER','INTERNAL'),
 ('P07','Seating position','Person','PERSON','CODE','INTERNAL'),
 ('P08','Restraint systems/motorcycle helmet','Person','PERSON','CODE','INTERNAL'),
 ('P09','Air bag deployed','Person','PERSON','CODE','INTERNAL'),
 ('P10','Ejection','Person','PERSON','CODE','INTERNAL'),
 ('P11','Driver license jurisdiction','Person','PERSON','CODE','PII'),
 ('P12','Driver license number','Person','PERSON','TEXT','PII'),
 ('P14','Driver actions at time of crash','Person','PERSON','CODE','INTERNAL'),
 ('P15','Violation codes','Person','PERSON','CODE','SENSITIVE'),
 ('P16','Driver license restrictions','Person','PERSON','CODE','PII'),
 ('P17','Driver license status','Person','PERSON','CODE','PII'),
 ('P18','Distracted by','Person','PERSON','CODE','INTERNAL'),
 ('P19','Condition at time of crash','Person','PERSON','CODE','SENSITIVE'),
 ('P20','Law enforcement suspects alcohol use','Person','PERSON','CODE','SENSITIVE'),
 ('P21','Alcohol test','Person','PERSON','CODE','SENSITIVE'),
 ('P22','Law enforcement suspects drug use','Person','PERSON','CODE','SENSITIVE'),
 ('P23','Drug test','Person','PERSON','CODE','SENSITIVE'),
 ('P24','Transported to first medical facility by','Person','PERSON','CODE','SENSITIVE'),
 ('P25','Injury area','Person','PERSON','CODE','SENSITIVE'),
 ('PX1','Enforcement indicator','Person','PERSON','CODE','SENSITIVE'),
 ('PX2','Person address','Person','PERSON','TEXT','PII'),
 ('PX3','Person demographics','Person','PERSON','TEXT','PII'),
 -- Roadway
 ('R05','Roadway functional class','Roadway','ROADWAY','CODE','INTERNAL'),
 ('R07','Lane and shoulder widths','Roadway','ROADWAY','TEXT','INTERNAL'),
 ('R08','Median width','Roadway','ROADWAY','NUMBER','INTERNAL'),
 ('R09','Access control','Roadway','ROADWAY','CODE','INTERNAL'),
 ('R10','Railway crossing ID','Roadway','ROADWAY','TEXT','INTERNAL'),
 ('RX1','Roadway surface type','Roadway','ROADWAY','CODE','INTERNAL'),
 -- Vehicle
 ('V01','VIN','Vehicle','VEHICLE','TEXT','INTERNAL'),
 ('V02','Motor vehicle unit type and number','Vehicle','VEHICLE','CODE','INTERNAL'),
 ('V03','Registration State and year','Vehicle','VEHICLE','TEXT','INTERNAL'),
 ('V04','License plate number','Vehicle','VEHICLE','TEXT','INTERNAL'),
 ('V05','Make','Vehicle','VEHICLE','TEXT','INTERNAL'),
 ('V06','Model year','Vehicle','VEHICLE','NUMBER','INTERNAL'),
 ('V07','Model','Vehicle','VEHICLE','TEXT','INTERNAL'),
 ('V08','Body type','Vehicle','VEHICLE','CODE','INTERNAL'),
 ('V09','Total occupants','Vehicle','VEHICLE','NUMBER','INTERNAL'),
 ('V10','Special function','Vehicle','VEHICLE','CODE','INTERNAL'),
 ('V11','Emergency motor vehicle use','Vehicle','VEHICLE','CODE','INTERNAL'),
 ('V12','Posted/statutory speed limit','Vehicle','VEHICLE','NUMBER','INTERNAL'),
 ('V13','Direction of travel before crash','Vehicle','VEHICLE','CODE','INTERNAL'),
 ('V14','Trafficway description','Vehicle','VEHICLE','CODE','INTERNAL'),
 ('V15','Total lanes','Vehicle','VEHICLE','NUMBER','INTERNAL'),
 ('V16','Roadway alignment and grade','Vehicle','VEHICLE','CODE','INTERNAL'),
 ('V17','Traffic control device type','Vehicle','VEHICLE','CODE','INTERNAL'),
 ('V18','Maneuver/action','Vehicle','VEHICLE','CODE','INTERNAL'),
 ('V19','Vehicle damage','Vehicle','VEHICLE','CODE','INTERNAL'),
 ('V20','Sequence of events','Vehicle','VEHICLE','CODE','INTERNAL'),
 ('V21','Most harmful event','Vehicle','VEHICLE','CODE','INTERNAL'),
 ('V22','Hit and run','Vehicle','VEHICLE','CODE','INTERNAL'),
 ('V23','Towed due to disabling damage','Vehicle','VEHICLE','CODE','INTERNAL'),
 ('V24','Contributing circumstances for motor vehicle','Vehicle','VEHICLE','CODE','INTERNAL'),
 ('VX1','Vehicle owner','Vehicle','VEHICLE','TEXT','PII')
ON CONFLICT (code) DO NOTHING;

-- ---------------------------------------------------------------------------
-- Attribute requirements for the Phase 1 study (core fields required).
-- ---------------------------------------------------------------------------
INSERT INTO attribute_requirements (study_id, attribute_id, is_required, is_optional, is_read_only, is_editable)
SELECT s.id, da.id,
       (da.code = ANY(ARRAY['C01','C03','C04','C06','C19','C24','LV07','LV10',
                            'V01','V02','V05','V06','V07','P01','P04','P05'])) AS is_req,
       NOT (da.code = ANY(ARRAY['C01','C03','C04','C06','C19','C24','LV07','LV10',
                            'V01','V02','V05','V06','V07','P01','P04','P05'])) AS is_opt,
       FALSE, TRUE
FROM studies s CROSS JOIN data_attributes da
WHERE s.code = 'PHASE1-HDT'
ON CONFLICT (study_id, attribute_id) DO NOTHING;

-- ---------------------------------------------------------------------------
-- Kansas State PCR coverage summary (documentation §19.3)
-- ---------------------------------------------------------------------------
INSERT INTO state_pcr_coverage (study_id, state_code, pcr_section_code, required_collected, total_required, optional_collected, total_optional)
SELECT s.id, 'KS', c.section, c.req_coll, c.req_total, c.opt_coll, c.opt_total
FROM studies s JOIN (VALUES
 ('CRASH',129,202,0,6),
 ('DYNAMIC',0,21,0,0),
 ('FATAL',2,46,0,8),
 ('LARGE_VEH_HAZMAT',92,168,0,1),
 ('NON_MOTORIST',34,69,0,1),
 ('PERSON',155,294,0,17),
 ('ROADWAY',11,16,0,0),
 ('VEHICLE',213,378,0,17)
) AS c(section, req_coll, req_total, opt_coll, opt_total) ON s.code='PHASE1-HDT'
ON CONFLICT (study_id, state_code, pcr_section_code) DO NOTHING;

-- ---------------------------------------------------------------------------
-- Data quality rules (documentation §8.8 / §5 Phase 5)
-- ---------------------------------------------------------------------------
INSERT INTO data_quality_rules (code, name, rule_type, severity, definition) VALUES
 ('DQ_MISSING_IIF','Crash is missing an Initial Incident Form','MISSING','CRITICAL','{"check":"initial_incident_form_exists"}'),
 ('DQ_DOT_FORMAT','U.S. DOT number format invalid','FORMAT','ERROR','{"pattern":"^[0-9]{1,8}$"}'),
 ('DQ_DOT_SAFESPECT','U.S. DOT number not validated against SafeSpect','COMPLIANCE','ERROR','{"source":"SafeSpect"}'),
 ('DQ_MISSING_REQUIRED_ATTR','Required CCFP attribute is missing','MISSING','ERROR','{"scope":"required_attributes"}'),
 ('DQ_FATALITY_COUNT','Fatality count must be at least 1 for a qualifying crash','CROSS_FIELD','ERROR','{"min_fatalities":1}'),
 ('DQ_CDLIS_CHECK','Driver license not validated against CDLIS','COMPLIANCE','WARNING','{"source":"CDLIS"}'),
 ('DQ_ELD_LINKED','ELD file not linked to crash via CCFP code','CROSS_FIELD','WARNING','{"check":"eld_ccfp_code"}'),
 ('DQ_TOP_FACTORS','Top three contributing factors not selected','MISSING','WARNING','{"required_count":3}')
ON CONFLICT (code) DO NOTHING;

-- ---------------------------------------------------------------------------
-- Completeness rules for Phase 1
-- ---------------------------------------------------------------------------
INSERT INTO completeness_rules (study_id, name, description, definition)
SELECT s.id, r.name, r.descr, r.def::jsonb
FROM studies s JOIN (VALUES
 ('Initial Incident Form submitted','Crash must have a submitted Initial Incident Form','{"requires":["initial_incident_submitted"]}'),
 ('Core PCR attributes collected','All required PCR attributes must have current values','{"requires":["required_attributes_present"]}'),
 ('Post-crash inspection linked','At least one post-crash inspection record linked','{"requires":["post_crash_inspection_exists"]}'),
 ('Contributing factors selected','Analyst selected three primary contributing factors','{"requires":["three_contributing_factors"]}'),
 ('No critical QC failures','No open CRITICAL or ERROR quality-control failures','{"requires":["no_critical_qc_failures"]}')
) AS r(name, descr, def) ON s.code='PHASE1-HDT'
ON CONFLICT DO NOTHING;
