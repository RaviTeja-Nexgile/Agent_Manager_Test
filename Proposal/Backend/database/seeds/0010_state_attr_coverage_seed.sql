-- =============================================================================
-- Seed 0010 - Kansas per-attribute PCR coverage (PCR-3)
-- ALL data is synthetic / dev-test-demo only.
-- =============================================================================
-- Marks a realistic subset of the Phase 1 (PHASE1-HDT) required attributes as
-- collected for Kansas so the per-attribute coverage view shows all three colour
-- statuses:
--   * REQUIRED_COLLECTED (green)     <- required attribute with is_collected = TRUE.
--   * REQUIRED_NOT_COLLECTED (red)   <- required attribute with is_collected = FALSE.
--   * OPTIONAL_NOT_COLLECTED (amber) <- optional attributes (no coverage row /
--                                       is_collected = FALSE).
-- The Phase 1 required set (seed 0003) is:
--   C01,C03,C04,C06,C19,C24,LV07,LV10,V01,V02,V05,V06,V07,P01,P04,P05.
-- Subquery-resolved ids; idempotent via ON CONFLICT on the natural key.
-- =============================================================================

INSERT INTO state_attribute_coverage (study_id, state_code, attribute_id, is_collected)
SELECT s.id, 'KS', da.id, v.collected
FROM studies s
JOIN (VALUES
 -- Collected (green): core crash/vehicle identifiers an analyst maps first.
 ('C01', TRUE),
 ('C03', TRUE),
 ('C04', TRUE),
 ('C06', TRUE),
 ('C19', TRUE),
 ('C24', TRUE),
 ('V01', TRUE),
 ('V02', TRUE),
 ('V05', TRUE),
 -- Not yet collected (red): still-pending required attributes.
 ('V06', FALSE),
 ('V07', FALSE),
 ('LV07', FALSE),
 ('LV10', FALSE),
 ('P01', FALSE),
 ('P04', FALSE),
 ('P05', FALSE)
) AS v(code, collected) ON TRUE
JOIN data_attributes da ON da.code = v.code
WHERE s.code = 'PHASE1-HDT'
ON CONFLICT (study_id, state_code, attribute_id) DO NOTHING;
