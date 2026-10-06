-- =============================================================================
-- Seed 0011 - Contributing-factor value catalog (DATA-7)
-- ALL data is synthetic / dev-test-demo only.
-- =============================================================================
-- Populates a per-group catalog of allowed contributing-factor values for the
-- seven seeded groups so the analyst's "top three" Factor field is a structured
-- dropdown instead of free text (§5 Phase 6).
--
-- CRITICAL: the exact values used by the existing lifecycle test
-- (test_full_crash_lifecycle) MUST be present under their groups so that test
-- stays green after value validation is enforced:
--   DRIVER_ACTIONS    -> 'Following too closely'
--   DRIVER_CONDITIONS -> 'Fatigue'
--   CC_VEHICLE        -> 'Brakes'
--
-- Subquery-resolved group ids; idempotent via ON CONFLICT (factor_group_id, label).
-- =============================================================================

INSERT INTO ref_contributing_factor_values (factor_group_id, code, label, sort_order)
SELECT g.id, v.code, v.label, v.sort_order
FROM ref_contributing_factor_groups g
JOIN (VALUES
 -- CC_ROADWAY
 ('CC_ROADWAY','CCR_SURFACE','Slick/wet road surface',1),
 ('CC_ROADWAY','CCR_OBSTRUCTION','Obstruction in roadway',2),
 ('CC_ROADWAY','CCR_SIGNAGE','Inadequate/obscured signage',3),
 ('CC_ROADWAY','CCR_WORKZONE','Work zone',4),
 -- CC_VEHICLE
 ('CC_VEHICLE','CCV_BRAKES','Brakes',1),
 ('CC_VEHICLE','CCV_BRAKE_ADJ','Brake out of adjustment',2),
 ('CC_VEHICLE','CCV_TIRE','Tire failure',3),
 ('CC_VEHICLE','CCV_LIGHTING','Defective lighting',4),
 ('CC_VEHICLE','CCV_STEERING','Steering defect',5),
 -- CC_NON_MOTORIST
 ('CC_NON_MOTORIST','CCN_DARK_CLOTHING','Dark/low-visibility clothing',1),
 ('CC_NON_MOTORIST','CCN_NOT_CROSSWALK','Not in crosswalk',2),
 ('CC_NON_MOTORIST','CCN_IMPAIRMENT','Impairment',3),
 -- DRIVER_ACTIONS
 ('DRIVER_ACTIONS','DA_FOLLOW_CLOSE','Following too closely',1),
 ('DRIVER_ACTIONS','DA_FAIL_YIELD','Failure to yield',2),
 ('DRIVER_ACTIONS','DA_SPEEDING','Exceeding speed limit',3),
 ('DRIVER_ACTIONS','DA_IMPROPER_LANE','Improper lane change',4),
 ('DRIVER_ACTIONS','DA_RAN_SIGNAL','Disregarded traffic signal',5),
 -- DRIVER_CONDITIONS
 ('DRIVER_CONDITIONS','DC_FATIGUE','Fatigue',1),
 ('DRIVER_CONDITIONS','DC_ILLNESS','Illness',2),
 ('DRIVER_CONDITIONS','DC_ALCOHOL','Under the influence of alcohol',3),
 ('DRIVER_CONDITIONS','DC_DRUGS','Under the influence of drugs',4),
 -- DISTRACTED_BY
 ('DISTRACTED_BY','DB_PHONE','Mobile phone',1),
 ('DISTRACTED_BY','DB_INVEHICLE','In-vehicle device',2),
 ('DISTRACTED_BY','DB_PASSENGER','Passenger',3),
 ('DISTRACTED_BY','DB_EXTERNAL','External distraction',4),
 -- NON_MOTORIST_ACTIONS
 ('NON_MOTORIST_ACTIONS','NMA_CROSS_NO_SIGNAL','Crossing against signal',1),
 ('NON_MOTORIST_ACTIONS','NMA_IN_ROADWAY','Walking/standing in roadway',2),
 ('NON_MOTORIST_ACTIONS','NMA_DARTING','Darting into traffic',3)
) AS v(group_code, code, label, sort_order) ON v.group_code = g.code
ON CONFLICT (factor_group_id, label) DO NOTHING;
