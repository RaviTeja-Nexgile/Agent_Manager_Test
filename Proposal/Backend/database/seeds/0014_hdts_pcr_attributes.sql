-- =============================================================================
-- Seed 0014 - HDTS PCR data-form attribute catalog extension (GAP-PCR-02)
-- =============================================================================
-- The catalog held 109 element-level codes derived from the old KS Sample Study
-- Inclusion worksheet. The new HDTS Police Crash Report data form requires two
-- groups of additions:
--
--   (a) GENUINELY NEW  -- absent from the old worksheet entirely.
--   (b) NEVER MODELLED -- present in the old worksheet under different
--       (descriptive) names, but never carried by the application. These are
--       pre-existing shortfalls against the ORIGINAL specification, not changes
--       introduced by the new documents, which if anything raises their
--       priority.
--
-- Both groups are equally absent from data_attributes and equally require
-- seeding, so they are seeded together and distinguished only by the comment
-- markers (a)/(b) below.
--
-- Code scheme: continues the existing MMUCC-aligned per-section numbering
-- (C27+, F04+, LV12+, P26+, R11+, V25+) rather than minting more ad-hoc `*X*`
-- codes. Verified free against the live catalog before writing:
--   C max 26 · F max 03 · LV max 11 · NM max 06 · P max 25 · R max 10 · V max 24
--
-- Sensitivity is set deliberately, not defaulted:
--   PUBLIC    the Public Narrative -- the form says it is written for and
--             available to the public, so it must be separable from the
--             internal Crash Description (CX1, which stays SENSITIVE).
--   PII       names, addresses, phone numbers, age, height, licence dates,
--             officer/owner identities.
--   SENSITIVE injury, citation, and ejection detail.
--
-- Repeat metadata (repeats_on / max_selections / applies_to) is populated here
-- too, because an attribute is unusable without knowing whether it is captured
-- per crash, per vehicle, per person, or per trailer (GAP-PCR-03 built the
-- columns; GAP-PCR-04 refines the caps).
--
-- Idempotent: ON CONFLICT (code) DO NOTHING on inserts, targeted UPDATEs after.
-- =============================================================================

-- ---------------------------------------------------------------------------
-- 1. New attributes
-- ---------------------------------------------------------------------------
INSERT INTO data_attributes
    (code, name, category, pcr_section, data_type, sensitivity, repeats_on, applies_to, max_selections, description)
VALUES
 -- ===== Crash Data Elements ================================================
 ('C27','Case/report number','Crash','CRASH','TEXT','INTERNAL',NULL,NULL,NULL,
  '(a) New. Third identifier alongside State Specific Identifier and Local Case Number.'),
 ('C28','Time of roadway clearance','Crash','CRASH','TEXT','INTERNAL',NULL,NULL,NULL,
  '(a) New. HHMM; midnight is recorded as "0000".'),
 ('C29','Route number','Crash','CRASH','TEXT','INTERNAL',NULL,NULL,NULL,'(a) New.'),
 ('C30','Milepost','Crash','CRASH','TEXT','INTERNAL',NULL,NULL,NULL,'(a) New.'),
 ('C31','Public narrative','Crash','CRASH','TEXT','PUBLIC',NULL,NULL,NULL,
  '(a) New. Written for and available to the public. Deliberately DISTINCT from CX1 Crash description (SENSITIVE) so it can be released without redaction.'),
 ('C32','Direction in which crash initiated','Crash','CRASH','CODE','INTERNAL',NULL,NULL,NULL,
  '(a) New. E / N / S / W.'),
 ('C33','Post-crash inspection: inspecting agency name','Crash','CRASH','TEXT','INTERNAL',NULL,NULL,NULL,
  '(a) New. PCR-reported; cross-checked against the SafeSpect-sourced post_crash_inspections row (GAP-PCR-07).'),
 ('C34','Post-crash inspection: report number','Crash','CRASH','TEXT','INTERNAL',NULL,NULL,NULL,'(a) New.'),
 ('C35','Post-crash inspection: inspecting officer name','Crash','CRASH','TEXT','PII',NULL,NULL,NULL,'(a) New.'),
 ('C36','Post-crash inspection type','Crash','CRASH','CODE','INTERNAL',NULL,NULL,NULL,
  '(a) New. Driver or Vehicle.'),
 ('C37','Driver out of service (OOS)','Crash','CRASH','BOOLEAN','INTERNAL',NULL,NULL,NULL,
  '(a) New. "Out of service" appears nowhere in the old worksheet.'),
 ('C38','FMCSA reportable crash','Crash','CRASH','BOOLEAN','INTERNAL',NULL,NULL,NULL,'(a) New. Reportable Crash Indicators.'),
 ('C39','State reportable crash','Crash','CRASH','BOOLEAN','INTERNAL',NULL,NULL,NULL,'(a) New. Reportable Crash Indicators.'),
 ('C40','Officer badge number','Crash','CRASH','TEXT','PII',NULL,NULL,NULL,
  '(b) In the old worksheet; never modelled by the application.'),
 ('C41','Crash diagram','Crash','CRASH','JSON','INTERNAL',NULL,NULL,NULL,
  '(b) In the old worksheet; never modelled. The new form adds an explicit diagram file upload -- the FILE itself is handled by GAP-PCR-06 (documents.pcr_id + CRASH_DIAGRAM); this attribute carries the reference/metadata.'),

 -- ===== Fatal Data Elements ================================================
 ('F04','Federally reportable crash','Fatal','FATAL','BOOLEAN','INTERNAL',NULL,NULL,NULL,'(a) New.'),
 ('F05','Person height','Fatal','FATAL','TEXT','PII','PERSON','ALL_PERSONS',NULL,
  '(a) New. Feet/inches. The old worksheet''s only "height" is Over-height under Special Sizing -- a vehicle dimension, not a person''s.'),

 -- ===== Large Vehicle and Hazardous Material (HM) Data Elements ============
 ('LV12','Trailer owner name','Large Vehicles & HazMat','LARGE_VEH_HAZMAT','TEXT','PII','TRAILER',NULL,NULL,
  '(a) New. Captured per trailer position.'),
 ('LV13','Trailer owner street address','Large Vehicles & HazMat','LARGE_VEH_HAZMAT','TEXT','PII','TRAILER',NULL,NULL,'(a) New. Per trailer position.'),
 ('LV14','Trailer owner city','Large Vehicles & HazMat','LARGE_VEH_HAZMAT','TEXT','PII','TRAILER',NULL,NULL,'(a) New. Per trailer position.'),
 ('LV15','Trailer owner ZIP','Large Vehicles & HazMat','LARGE_VEH_HAZMAT','TEXT','PII','TRAILER',NULL,NULL,'(a) New. Per trailer position.'),
 ('LV16','Cargo load indicator','Large Vehicles & HazMat','LARGE_VEH_HAZMAT','CODE','INTERNAL','VEHICLE',NULL,NULL,
  '(a) New. Loaded / Partially Loaded / Unloaded.'),
 ('LV17','Total hazmat types transported','Large Vehicles & HazMat','LARGE_VEH_HAZMAT','NUMBER','INTERNAL','VEHICLE',NULL,NULL,'(a) New.'),
 ('LV18','Motor carrier email address','Large Vehicles & HazMat','LARGE_VEH_HAZMAT','TEXT','PII',NULL,NULL,NULL,
  '(a) New. The old worksheet''s only "email" is the CCFP@dot.gov instruction line.'),
 ('LV19','Hazardous materials placard displayed','Large Vehicles & HazMat','LARGE_VEH_HAZMAT','BOOLEAN','INTERNAL','VEHICLE',NULL,NULL,
  '(b) In the old worksheet at vehicle level; never modelled.'),
 ('LV20','Number of trailing units','Large Vehicles & HazMat','LARGE_VEH_HAZMAT','NUMBER','INTERNAL','VEHICLE',NULL,NULL,
  '(b) In the old worksheet as "Number of Trailing Units"; never modelled.'),

 -- ===== Person Data Elements ===============================================
 ('P26','Name suffix','Person','PERSON','TEXT','PII','PERSON','ALL_PERSONS',NULL,'(a) New.'),
 ('P27','Person phone number','Person','PERSON','TEXT','PII','PERSON','ALL_PERSONS',NULL,
  '(a) New. The old worksheet''s phone attributes are all Motor Carrier Phone or mobile-phone distraction values.'),
 ('P28','Driver presence','Person','PERSON','CODE','INTERNAL','PERSON','ALL_OCCUPANTS',NULL,'(a) New. No / Yes.'),
 ('P29','Seat belt use indicator','Person','PERSON','CODE','INTERNAL','PERSON','ALL_OCCUPANTS',NULL,'(a) New.'),
 ('P30','Driver license issued date','Person','PERSON','DATE','PII','PERSON','ALL_DRIVERS',NULL,'(a) New.'),
 ('P31','Driver license expiration date','Person','PERSON','DATE','PII','PERSON','ALL_DRIVERS',NULL,'(a) New.'),
 ('P32','Withdrawal action pending','Person','PERSON','BOOLEAN','PII','PERSON','ALL_DRIVERS',NULL,'(a) New.'),
 ('P33','Distracted by source','Person','PERSON','CODE','INTERNAL','PERSON','DRIVERS_AND_NON_MOTORISTS',4,
  '(a) New as a SEPARATE axis. Old P18 had a single combined "Distracted By"; the new form splits action from source. Check up to 4.'),
 ('P34','Injury severity','Person','PERSON','CODE','SENSITIVE','PERSON','ALL_INJURED',NULL,
  '(a) New as a separate axis alongside Injury Area (P25). Fatal / Serious / Moderate / Minor / No Injury / Unknown.'),
 ('P35','Person age','Person','PERSON','NUMBER','PII','PERSON','ALL_PERSONS',NULL,
  '(b) In the old worksheet as AAA.Age; never modelled.'),
 ('P36','Ejection path','Person','PERSON','CODE','SENSITIVE','PERSON','ALL_OCCUPANTS',NULL,
  '(b) In the old worksheet; never modelled. Distinct from P10 Ejection.'),
 ('P37','Citation issued indicator','Person','PERSON','BOOLEAN','SENSITIVE','PERSON','ALL_PERSONS',NULL,
  '(b) In the old worksheet as PX.Enforcement Indicator; never modelled as its own attribute.'),
 ('P38','Citation number','Person','PERSON','TEXT','SENSITIVE','PERSON','ALL_PERSONS',NULL,'(b) In the old worksheet; never modelled.'),
 ('P39','Person city','Person','PERSON','TEXT','PII','PERSON','ALL_PERSONS',NULL,
  '(b) Component of the old PX2 Person address block, which the new form splits into City/State/ZIP/Country.'),
 ('P40','Person state','Person','PERSON','TEXT','PII','PERSON','ALL_PERSONS',NULL,'(b) Component of the old PX2 Person address block.'),
 ('P41','Person ZIP','Person','PERSON','TEXT','PII','PERSON','ALL_PERSONS',NULL,'(b) Component of the old PX2 Person address block.'),
 ('P42','Person country','Person','PERSON','TEXT','PII','PERSON','ALL_PERSONS',NULL,'(b) Component of the old PX2 Person address block.'),
 ('P43','Sequential identifying number','Person','PERSON','NUMBER','INTERNAL','PERSON','ALL_PERSONS',NULL,
  '(b) In the old worksheet; never modelled. The new form keys the whole repeating Person section on it.'),

 -- ===== Vehicle Data Elements ==============================================
 ('V25','Truck indicator','Vehicle','VEHICLE','BOOLEAN','INTERNAL','VEHICLE',NULL,NULL,
  '(a) New. The old worksheet has a Bus Indicator only.'),
 ('V26','Fire indicator','Vehicle','VEHICLE','BOOLEAN','INTERNAL','VEHICLE',NULL,NULL,'(a) New. Within Vehicle Damage.'),
 ('V27','Vehicle color','Vehicle','VEHICLE','TEXT','INTERNAL','VEHICLE',NULL,NULL,'(b) In the old worksheet; never modelled.'),
 ('V28','Motor vehicle type','Vehicle','VEHICLE','CODE','INTERNAL','VEHICLE',NULL,NULL,
  '(b) In the old worksheet; never modelled. Transport / Parked / Working.'),
 ('V29','Vehicle size and GVWR','Vehicle','VEHICLE','NUMBER','INTERNAL','VEHICLE',NULL,NULL,
  '(b) In the old worksheet; never modelled. REQUIRED for Phase 1 scope: qualification is Class 7/8 with GVWR >= 26,001 lbs, which previously had NO attribute backing it.'),
 ('V30','Commercial motor vehicle indicator','Vehicle','VEHICLE','BOOLEAN','INTERNAL','VEHICLE',NULL,NULL,
  '(b) In the old worksheet as "Is CMV?"; never modelled.'),
 ('V31','Override/underride','Vehicle','VEHICLE','CODE','INTERNAL','VEHICLE',NULL,NULL,'(b) In the old worksheet; never modelled.'),
 ('V32','Most damaged area','Vehicle','VEHICLE','CODE','INTERNAL','VEHICLE',NULL,NULL,'(b) In the old worksheet; never modelled.'),
 ('V33','Vision obscured by','Vehicle','VEHICLE','CODE','INTERNAL','VEHICLE',NULL,NULL,
  '(b) In the old worksheet as "Visual Obstruction"; never modelled.'),
 ('V34','Trip origin','Vehicle','VEHICLE','TEXT','INTERNAL','VEHICLE',NULL,NULL,'(b) In the old worksheet as Origin/Destination; never modelled.'),
 ('V35','Trip destination','Vehicle','VEHICLE','TEXT','INTERNAL','VEHICLE',NULL,NULL,'(b) In the old worksheet as Origin/Destination; never modelled.'),
 ('V36','Air bag in vehicle','Vehicle','VEHICLE','BOOLEAN','INTERNAL','VEHICLE',NULL,NULL,
  '(b) In the old worksheet; never modelled. Distinct from P09 Air bag deployed.'),

 -- ===== Roadway Data Elements ==============================================
 ('R11','Roadway lighting','Roadway','ROADWAY','CODE','INTERNAL',NULL,NULL,NULL,
  '(a) New. Continuous one/both sides · No Lighting · Spot one/both sides. Distinct from C12 Light condition.'),
 ('R12','Mainline number of lanes at intersection','Roadway','ROADWAY','NUMBER','INTERNAL',NULL,NULL,NULL,'(a) New.'),
 ('R13','Cross-street number of lanes at intersection','Roadway','ROADWAY','NUMBER','INTERNAL',NULL,NULL,NULL,'(a) New.'),
 ('R14','Railway crossing warning device type','Roadway','ROADWAY','CODE','INTERNAL',NULL,NULL,NULL,
  '(a) New. Gate · Crossbucks · Stop Signs · Flashing Lights · WigWags/Bells · Four Quad (Full Barrier) Gates · Non-Train Activated Special Protection.'),
 ('R15','Number of stop signs','Roadway','ROADWAY','NUMBER','INTERNAL',NULL,NULL,NULL,'(a) New. Part of the railway-crossing warning device block.'),
 ('R16','Number of yield signs','Roadway','ROADWAY','NUMBER','INTERNAL',NULL,NULL,NULL,'(a) New. Part of the railway-crossing warning device block.'),
 ('R17','Auxiliary lanes','Roadway','ROADWAY','CODE','INTERNAL',NULL,NULL,NULL,'(b) In the old worksheet; never modelled.'),
 ('R18','Pavement markings','Roadway','ROADWAY','CODE','INTERNAL',NULL,NULL,NULL,'(b) In the old worksheet; never modelled.'),
 ('R19','Inoperative or missing traffic control devices','Roadway','ROADWAY','CODE','INTERNAL',NULL,NULL,NULL,'(b) In the old worksheet; never modelled.'),
 ('R20','Barrier type','Roadway','ROADWAY','CODE','INTERNAL',NULL,NULL,NULL,'(b) In the old worksheet under V14; never modelled as its own attribute.'),
 ('R21','Bicycle facility','Roadway','ROADWAY','CODE','INTERNAL',NULL,NULL,NULL,'(b) In the old worksheet; never modelled.')
ON CONFLICT (code) DO NOTHING;


-- ---------------------------------------------------------------------------
-- 2. Repeat metadata for the PRE-EXISTING catalog.
--
-- The new form makes multiplicity structural: the whole Vehicle section repeats
-- per Vehicle Sequential Number, the whole Person section per Sequential
-- Identifying Number, and trailer elements per trailer position. The existing
-- codes were seeded flat, so without this every pre-existing per-vehicle and
-- per-person attribute would still be limited to one value per crash by
-- uq_cav_current (GAP-PCR-03).
--
-- Set by SECTION, not by hand-listing codes, so the rule stays true as the
-- catalog grows.
-- ---------------------------------------------------------------------------

-- Whole Vehicle section repeats per vehicle.
UPDATE data_attributes SET repeats_on = 'VEHICLE'
 WHERE pcr_section = 'VEHICLE' AND repeats_on IS NULL AND is_active;

-- Whole Person section repeats per person.
UPDATE data_attributes SET repeats_on = 'PERSON'
 WHERE pcr_section = 'PERSON' AND repeats_on IS NULL AND is_active;

-- Non-motorist elements repeat per non-motorist unit.
UPDATE data_attributes SET repeats_on = 'NON_MOTORIST'
 WHERE pcr_section = 'NON_MOTORIST' AND repeats_on IS NULL AND is_active;

-- Fatal-section person detail repeats per person.
UPDATE data_attributes SET repeats_on = 'PERSON'
 WHERE code IN ('FX1') AND repeats_on IS NULL;

-- Trailer-specific Large Vehicle elements repeat per trailer POSITION; the
-- remaining Large Vehicle elements describe the power unit and repeat per
-- vehicle. Listed explicitly because the section mixes the two.
UPDATE data_attributes SET repeats_on = 'TRAILER'
 WHERE code IN ('LV02','LV03','LV05','LV06','LVX2','LVX3');
UPDATE data_attributes SET repeats_on = 'VEHICLE'
 WHERE code IN ('LV01','LV08','LV09','LV10','LV11','LVX1') AND repeats_on IS NULL;


-- ---------------------------------------------------------------------------
-- 3. Retire and alias the coarse pseudo-code the new form decomposes.
--
-- PX2 "Person address" is replaced by four discrete fields. It is deactivated
-- rather than deleted so historical values stay resolvable, and points forward
-- at P39 as the primary replacement (the split is spelled out in description).
-- ---------------------------------------------------------------------------
UPDATE data_attributes
   SET is_active = FALSE,
       superseded_by_code = 'P39',
       description = 'Retired by GAP-PCR-02: the HDTS PCR data form splits the person address block into P39 city, P40 state, P41 ZIP, P42 country. Retained so historical values remain resolvable.'
 WHERE code = 'PX2';

UPDATE attribute_requirements
   SET is_required = FALSE, is_optional = FALSE, updated_at = now()
 WHERE attribute_id IN (SELECT id FROM data_attributes WHERE code = 'PX2');


-- ---------------------------------------------------------------------------
-- 4. Phase 1 attribute requirements.
--
-- The seed marked only 16 attributes required. Most importantly V29 (Vehicle
-- Size and GVWR) is added: Phase 1 qualification is a Class 7/8 truck with
-- GVWR >= 26,001 lbs and the study had no attribute carrying it, so a
-- "complete" record could never actually evidence the scope rule.
--
-- Everything else added here is identity/reportability detail the new form
-- treats as core. Optional-but-collected attributes are left optional so the
-- required set stays a deliberate, administrator-manageable list rather than
-- "everything on the form".
-- ---------------------------------------------------------------------------
INSERT INTO attribute_requirements (study_id, attribute_id, is_required, is_optional, is_read_only, is_editable)
SELECT s.id, da.id, TRUE, FALSE, FALSE, TRUE
  FROM studies s
  JOIN data_attributes da ON da.code = ANY(ARRAY[
        'V29',   -- Vehicle size and GVWR -- backs the Class 7/8 scope rule
        'V30',   -- CMV indicator
        'C27',   -- Case/report number
        'C38',   -- FMCSA reportable
        'C39',   -- State reportable
        'P43',   -- Sequential identifying number (keys the Person repeat)
        'P34'    -- Injury severity
  ])
 WHERE s.code = 'PHASE1-HDT'
ON CONFLICT (study_id, attribute_id) DO UPDATE
   SET is_required = TRUE, is_optional = FALSE, updated_at = now();

-- Every other newly seeded attribute becomes an OPTIONAL requirement row for
-- Phase 1, so it appears in the study's attribute matrix and in coverage
-- denominators (GAP-PCR-05) instead of being invisible until an administrator
-- adds it by hand.
INSERT INTO attribute_requirements (study_id, attribute_id, is_required, is_optional, is_read_only, is_editable)
SELECT s.id, da.id, FALSE, TRUE, FALSE, TRUE
  FROM studies s
  JOIN data_attributes da ON da.is_active
 WHERE s.code = 'PHASE1-HDT'
ON CONFLICT (study_id, attribute_id) DO NOTHING;
