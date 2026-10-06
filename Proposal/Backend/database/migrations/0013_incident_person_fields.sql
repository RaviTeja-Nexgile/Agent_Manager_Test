-- =============================================================================
-- CCFP IT Solution - Migration 0013: incident-person IIF fields (INIT-1/2/3)
-- =============================================================================
-- §19.1 (l.828-830), §8.2: the Initial Incident Form requires structured person
-- details that the single free-text full_name / shared phone_type cannot hold:
--   * INIT-1 — names as last / first / middle parts.
--   * INIT-2 — two phone numbers, EACH tagged with a home/cell/work type.
--   * INIT-3 — a non-motorist occupant-vs-pedestrian discriminator.
-- All columns are nullable and additive; the existing full_name and phone_type
-- columns are KEPT (full_name stays the derived convenience value that PII
-- masking already redacts; phone_type can be backfilled into phone_primary_type).
--
-- Idempotent / additive: ADD COLUMN IF NOT EXISTS.
-- =============================================================================

-- INIT-1: structured name parts.
ALTER TABLE incident_persons ADD COLUMN IF NOT EXISTS name_last   TEXT;
ALTER TABLE incident_persons ADD COLUMN IF NOT EXISTS name_first  TEXT;
ALTER TABLE incident_persons ADD COLUMN IF NOT EXISTS name_middle TEXT;

-- INIT-2: per-number phone types (HOME | CELL | WORK; vocabulary in app.enums.PhoneType).
ALTER TABLE incident_persons ADD COLUMN IF NOT EXISTS phone_primary_type   TEXT;
ALTER TABLE incident_persons ADD COLUMN IF NOT EXISTS phone_secondary_type TEXT;

-- INIT-3: non-motorist kind (OCCUPANT | PEDESTRIAN; vocabulary in app.enums.NonMotoristKind).
ALTER TABLE incident_persons ADD COLUMN IF NOT EXISTS non_motorist_kind TEXT;

COMMENT ON COLUMN incident_persons.name_last IS 'IIF structured name part (INIT-1, §19.1).';
COMMENT ON COLUMN incident_persons.phone_primary_type IS
    'Type of phone_primary: HOME | CELL | WORK (INIT-2). Vocabulary: app.enums.PhoneType.';
COMMENT ON COLUMN incident_persons.non_motorist_kind IS
    'Non-motorist discriminator: OCCUPANT | PEDESTRIAN (INIT-3). Only meaningful '
    'when person_type = NON_MOTORIST. Vocabulary: app.enums.NonMotoristKind.';
