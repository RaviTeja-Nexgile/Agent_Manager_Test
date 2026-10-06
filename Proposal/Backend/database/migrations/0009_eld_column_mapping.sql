-- =============================================================================
-- CCFP IT Solution - Migration 0009: ELD column & duty-code mapping (RECO-5)
-- =============================================================================
-- §3.4 Future Scope / §8.7: the platform must be configurable for future
-- phases/providers without code changes, but the ELD CSV parser hardcodes a
-- single schema (duty-code dict + inline header alias lists in
-- app/workers/tasks.py). This moves the column-name and duty-status mapping into
-- PostgreSQL configuration (per-study and/or per-provider) so mappings can be
-- administered as data. NULL study_id/provider = global default.
--
-- The mapping is a plain PostgreSQL table read by the existing worker — no
-- external mapping/transform engine. Idempotent: IF NOT EXISTS.
-- =============================================================================

-- Header -> canonical-field mapping. A canonical field (e.g. event_sequence,
-- event_timestamp, duty, event_type, location, latitude, longitude,
-- miles_driven, engine_hours, ignition_status) may have multiple source headers
-- (aliases); `priority` lets a study+provider-specific row win over a default.
CREATE TABLE IF NOT EXISTS eld_field_mappings (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    study_id        UUID REFERENCES studies(id) ON DELETE CASCADE,   -- NULL = global default
    provider        TEXT,                                            -- NULL = any provider
    canonical_field TEXT NOT NULL,
    source_header   TEXT NOT NULL,
    priority        INT NOT NULL DEFAULT 0,
    is_active       BOOLEAN NOT NULL DEFAULT TRUE
);
CREATE INDEX IF NOT EXISTS idx_eld_field_mappings_lookup
    ON eld_field_mappings (study_id, provider, canonical_field);

-- Source duty-status code -> canonical DutyStatus value.
CREATE TABLE IF NOT EXISTS eld_duty_code_mappings (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    study_id        UUID REFERENCES studies(id) ON DELETE CASCADE,   -- NULL = global default
    provider        TEXT,                                            -- NULL = any provider
    source_code     TEXT NOT NULL,
    canonical_duty  TEXT NOT NULL,                                   -- matches app.enums.DutyStatus
    is_active       BOOLEAN NOT NULL DEFAULT TRUE
);
CREATE INDEX IF NOT EXISTS idx_eld_duty_code_mappings_lookup
    ON eld_duty_code_mappings (study_id, provider, source_code);

COMMENT ON TABLE eld_field_mappings IS
    'ELD CSV header -> canonical-field mapping (RECO-5, §8.7). NULL study_id/'
    'provider = global default. Read by app/workers/tasks.py parse_eld_file.';
COMMENT ON TABLE eld_duty_code_mappings IS
    'ELD source duty-code -> canonical DutyStatus mapping (RECO-5, §8.7). '
    'NULL study_id/provider = global default.';
