-- =============================================================================
-- Seed 0001 - Reference data
-- US states/territories, PCR sections, BRD contributing-factor groups.
-- All values are public reference data (no PII).
-- =============================================================================

INSERT INTO ref_us_states (code, name, is_territory) VALUES
 ('AL','Alabama',false),('AK','Alaska',false),('AZ','Arizona',false),
 ('AR','Arkansas',false),('CA','California',false),('CO','Colorado',false),
 ('CT','Connecticut',false),('DE','Delaware',false),('FL','Florida',false),
 ('GA','Georgia',false),('HI','Hawaii',false),('ID','Idaho',false),
 ('IL','Illinois',false),('IN','Indiana',false),('IA','Iowa',false),
 ('KS','Kansas',false),('KY','Kentucky',false),('LA','Louisiana',false),
 ('ME','Maine',false),('MD','Maryland',false),('MA','Massachusetts',false),
 ('MI','Michigan',false),('MN','Minnesota',false),('MS','Mississippi',false),
 ('MO','Missouri',false),('MT','Montana',false),('NE','Nebraska',false),
 ('NV','Nevada',false),('NH','New Hampshire',false),('NJ','New Jersey',false),
 ('NM','New Mexico',false),('NY','New York',false),('NC','North Carolina',false),
 ('ND','North Dakota',false),('OH','Ohio',false),('OK','Oklahoma',false),
 ('OR','Oregon',false),('PA','Pennsylvania',false),('RI','Rhode Island',false),
 ('SC','South Carolina',false),('SD','South Dakota',false),('TN','Tennessee',false),
 ('TX','Texas',false),('UT','Utah',false),('VT','Vermont',false),
 ('VA','Virginia',false),('WA','Washington',false),('WV','West Virginia',false),
 ('WI','Wisconsin',false),('WY','Wyoming',false),('DC','District of Columbia',false),
 ('PR','Puerto Rico',true),('GU','Guam',true),('VI','U.S. Virgin Islands',true)
ON CONFLICT (code) DO NOTHING;

-- MMUCC-aligned PCR sections (documentation §8.5 / §19.3).
INSERT INTO ref_pcr_sections (code, name, sort_order) VALUES
 ('CRASH','Crash',1),
 ('DYNAMIC','Dynamic Data Elements',2),
 ('FATAL','Fatal Section',3),
 ('LARGE_VEH_HAZMAT','Large Vehicles & Hazardous Materials',4),
 ('NON_MOTORIST','Non-Motorist Section',5),
 ('PERSON','Person',6),
 ('ROADWAY','Roadway',7),
 ('VEHICLE','Vehicle',8)
ON CONFLICT (code) DO NOTHING;

-- BRD-specified contributing-factor groups for the analyst top-three prompt
-- (documentation §5, Phase 6).
INSERT INTO ref_contributing_factor_groups (code, name, applies_to, sort_order) VALUES
 ('CC_ROADWAY','Contributing circumstances - roadways','ROADWAY',1),
 ('CC_VEHICLE','Contributing circumstances - vehicles','VEHICLE',2),
 ('CC_NON_MOTORIST','Contributing circumstances - non-motorists','NON_MOTORIST',3),
 ('DRIVER_ACTIONS','Driver actions at the time of crash','DRIVER',4),
 ('DRIVER_CONDITIONS','Driver conditions at the time of crash','DRIVER',5),
 ('DISTRACTED_BY','Driver and non-motorists distracted by','DRIVER',6),
 ('NON_MOTORIST_ACTIONS','Non-motorist actions at the time of crash','NON_MOTORIST',7)
ON CONFLICT (code) DO NOTHING;
