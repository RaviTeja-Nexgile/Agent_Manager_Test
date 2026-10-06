-- =============================================================================
-- CCFP IT Solution - Migration 0031: complete ELD extraction + parse diagnostics
-- =============================================================================
-- BRD Jan-2026 Appendix E / documentation §8.7. Two requirements drive this:
--
--   1. "Ability to extract data from ELD output file so the data can be
--      analyzed in the CCFP IT Solution."  The parser previously understood one
--      flat CSV shape (sequence,timestamp,duty,...). A REAL ELD/eRODS output
--      file is the sectioned CSV defined by 49 CFR 395 Appendix A to Subpart B:
--      a header segment, User List, CMV List, ELD Event List, annotations,
--      certifications, malfunction/diagnostic events, login/logout, engine
--      power-up/shut-down, unidentified-driver records and an end-of-file check
--      value. None of that was captured, so a realistic file produced either
--      zero usable data or rows of NULLs.
--
--   2. Nothing may fail silently. Every read, decode, format, mapping, row and
--      value problem is now recorded against the file with a machine-readable
--      code, a human-actionable message and the offending line, so the UI can
--      show WHY a file did not extract instead of an unexplained status.
--
-- Three changes:
--   * eld_files   — parse diagnostics + the header-segment metadata and the
--                   hours-of-service summary extracted from the file.
--   * eld_events  — the ELD-standard event columns (type/code/status/origin,
--                   coordinates provenance, indicators, annotation, check value)
--                   plus the section and source line each row came from.
--   * eld_parse_issues (new) — one aggregated row per distinct problem.
--
-- Additive and idempotent: ADD COLUMN IF NOT EXISTS / CREATE ... IF NOT EXISTS.
-- No existing row is rewritten; every new column is nullable or defaulted.
-- =============================================================================

-- ---------------------------------------------------------------------------
-- eld_files: parse diagnostics
-- ---------------------------------------------------------------------------
-- error_code/error_message are the "actionable message" pair the API and UI
-- surface next to upload_status. error_code is stable and machine-readable
-- (ELD_EMPTY_FILE, ELD_BINARY_FORMAT, ELD_NO_MAPPABLE_COLUMNS, ...) so tests
-- and integrations can branch on it; error_message is written for the person
-- who uploaded the file and names the fix.
ALTER TABLE eld_files ADD COLUMN IF NOT EXISTS error_code        TEXT;
ALTER TABLE eld_files ADD COLUMN IF NOT EXISTS error_message     TEXT;

-- How the file was actually understood. Recorded even on success so an analyst
-- can tell an FMCSA-standard output file from a hand-built spreadsheet export.
ALTER TABLE eld_files ADD COLUMN IF NOT EXISTS file_format       TEXT;
ALTER TABLE eld_files ADD COLUMN IF NOT EXISTS encoding          TEXT;
ALTER TABLE eld_files ADD COLUMN IF NOT EXISTS delimiter         TEXT;
ALTER TABLE eld_files ADD COLUMN IF NOT EXISTS file_size_bytes   BIGINT;
ALTER TABLE eld_files ADD COLUMN IF NOT EXISTS content_sha256    TEXT;
ALTER TABLE eld_files ADD COLUMN IF NOT EXISTS line_count        INT;
ALTER TABLE eld_files ADD COLUMN IF NOT EXISTS row_count         INT;
ALTER TABLE eld_files ADD COLUMN IF NOT EXISTS error_count       INT NOT NULL DEFAULT 0;
ALTER TABLE eld_files ADD COLUMN IF NOT EXISTS warning_count     INT NOT NULL DEFAULT 0;
ALTER TABLE eld_files ADD COLUMN IF NOT EXISTS parse_started_at  TIMESTAMPTZ;
ALTER TABLE eld_files ADD COLUMN IF NOT EXISTS parse_duration_ms INT;
ALTER TABLE eld_files ADD COLUMN IF NOT EXISTS parse_attempts    INT NOT NULL DEFAULT 0;

-- ---------------------------------------------------------------------------
-- eld_files: data extracted from the ELD file header segment
-- ---------------------------------------------------------------------------
-- 49 CFR 395 App. A §4.8.2.1 header segment. These are the identifiers an
-- analyst needs to tie hours-of-service data to the driver, carrier and power
-- unit involved in the crash, so they are first-class columns rather than JSON.
-- output_file_comment is the raw comment text; ccfp_code_in_file (existing
-- column) keeps the CCFP code lifted out of it, which is what links the upload
-- to the crash record.
ALTER TABLE eld_files ADD COLUMN IF NOT EXISTS driver_name            TEXT;
ALTER TABLE eld_files ADD COLUMN IF NOT EXISTS driver_license_number  TEXT;
ALTER TABLE eld_files ADD COLUMN IF NOT EXISTS driver_license_state   TEXT;
ALTER TABLE eld_files ADD COLUMN IF NOT EXISTS co_driver_name         TEXT;
ALTER TABLE eld_files ADD COLUMN IF NOT EXISTS carrier_name           TEXT;
ALTER TABLE eld_files ADD COLUMN IF NOT EXISTS carrier_usdot          TEXT;
ALTER TABLE eld_files ADD COLUMN IF NOT EXISTS vin                    TEXT;
ALTER TABLE eld_files ADD COLUMN IF NOT EXISTS power_unit_number      TEXT;
ALTER TABLE eld_files ADD COLUMN IF NOT EXISTS trailer_numbers        TEXT;
ALTER TABLE eld_files ADD COLUMN IF NOT EXISTS time_zone_offset       TEXT;
ALTER TABLE eld_files ADD COLUMN IF NOT EXISTS eld_registration_id    TEXT;
ALTER TABLE eld_files ADD COLUMN IF NOT EXISTS eld_identifier         TEXT;
ALTER TABLE eld_files ADD COLUMN IF NOT EXISTS output_file_comment    TEXT;
ALTER TABLE eld_files ADD COLUMN IF NOT EXISTS file_data_check_value  TEXT;

-- Per-section row counts ({"EVENT_LIST": 42, "UNIDENTIFIED_DRIVER": 3, ...}),
-- the raw header block, and the User/CMV lists. JSONB because the set of
-- sections is a property of the source file, not of the CCFP schema, and must
-- stay open for future providers/phases (§3.4 configurability).
ALTER TABLE eld_files ADD COLUMN IF NOT EXISTS sections        JSONB;
ALTER TABLE eld_files ADD COLUMN IF NOT EXISTS header_metadata JSONB;

-- Derived hours-of-service roll-up (duty-status hours, first/last event,
-- events by type, distinct days, mileage/engine-hour span). This is the
-- "so the data can be analyzed" half of Appendix E: the analyst gets the
-- summary without re-deriving it from eld_events on every read.
ALTER TABLE eld_files ADD COLUMN IF NOT EXISTS hos_summary     JSONB;

COMMENT ON COLUMN eld_files.error_code IS
    'Stable machine-readable parse-failure code (ELD_EMPTY_FILE, '
    'ELD_BINARY_FORMAT, ELD_NO_MAPPABLE_COLUMNS, ...). NULL when the file '
    'extracted without a blocking error.';
COMMENT ON COLUMN eld_files.error_message IS
    'Human-actionable failure message shown to the uploader. Paired with '
    'error_code; detail per problem lives in eld_parse_issues.';
COMMENT ON COLUMN eld_files.file_format IS
    'How the file was interpreted: FMCSA_ELD_OUTPUT (sectioned 49 CFR 395 '
    'App. A output file), FLAT_CSV (single-header tabular export), or UNKNOWN.';
COMMENT ON COLUMN eld_files.hos_summary IS
    'Derived hours-of-service roll-up extracted from the file (BRD Appendix E).';

-- ---------------------------------------------------------------------------
-- eld_events: the ELD-standard event columns
-- ---------------------------------------------------------------------------
-- The original table modelled a simplified event (sequence/timestamp/duty/
-- location/lat/lon/miles/engine-hours/ignition). A real ELD event record also
-- carries the numeric event type + code, whether the record is active or was
-- edited, who/what originated it, the distance since the last valid GPS fix,
-- malfunction and data-diagnostic indicators, the driver/CMV it belongs to and
-- a per-line data check value. Discarding those was the "partial extraction"
-- half of the defect: duty status alone cannot support an HOS analysis, because
-- an inactive (edited-out) record must not be counted the same as an active one.
ALTER TABLE eld_events ADD COLUMN IF NOT EXISTS section                    TEXT;
ALTER TABLE eld_events ADD COLUMN IF NOT EXISTS line_number                INT;
ALTER TABLE eld_events ADD COLUMN IF NOT EXISTS event_type_code            INT;
ALTER TABLE eld_events ADD COLUMN IF NOT EXISTS event_code                 INT;
ALTER TABLE eld_events ADD COLUMN IF NOT EXISTS record_status              TEXT;
ALTER TABLE eld_events ADD COLUMN IF NOT EXISTS record_origin              TEXT;
ALTER TABLE eld_events ADD COLUMN IF NOT EXISTS distance_since_last_coords NUMERIC(10,2);
ALTER TABLE eld_events ADD COLUMN IF NOT EXISTS malfunction_indicator      TEXT;
ALTER TABLE eld_events ADD COLUMN IF NOT EXISTS diagnostic_indicator       TEXT;
ALTER TABLE eld_events ADD COLUMN IF NOT EXISTS annotation                 TEXT;
ALTER TABLE eld_events ADD COLUMN IF NOT EXISTS driver_identifier          TEXT;
ALTER TABLE eld_events ADD COLUMN IF NOT EXISTS cmv_identifier             TEXT;
ALTER TABLE eld_events ADD COLUMN IF NOT EXISTS data_check_value           TEXT;
ALTER TABLE eld_events ADD COLUMN IF NOT EXISTS is_duplicate               BOOLEAN NOT NULL DEFAULT FALSE;

-- The Event Sequence ID Number is a per-file counter that the ELD rule allows to
-- wrap (0000-FFFF), and the unidentified-driver section restarts its own
-- numbering. UNIQUE (eld_file_id, event_sequence) therefore rejected valid
-- real-world files with an integrity error that surfaced as a whole-file parse
-- failure. Duplicates are now KEPT (no data loss), flagged with is_duplicate,
-- and reported as a WARNING issue naming the repeated sequence.
ALTER TABLE eld_events DROP CONSTRAINT IF EXISTS eld_events_eld_file_id_event_sequence_key;
CREATE INDEX IF NOT EXISTS idx_eld_events_file_seq ON eld_events (eld_file_id, event_sequence);
CREATE INDEX IF NOT EXISTS idx_eld_events_file_ts  ON eld_events (eld_file_id, event_timestamp);

COMMENT ON COLUMN eld_events.section IS
    'Source section of the ELD output file (EVENT_LIST, UNIDENTIFIED_DRIVER, '
    'ENGINE_POWER, LOGIN_LOGOUT, MALFUNCTIONS, CERTIFICATIONS) or FLAT_CSV.';
COMMENT ON COLUMN eld_events.record_status IS
    'ACTIVE | INACTIVE_CHANGED | INACTIVE_CHANGE_REQUESTED | '
    'INACTIVE_CHANGE_REJECTED (49 CFR 395 App. A event record status).';
COMMENT ON COLUMN eld_events.record_origin IS
    'AUTOMATIC | DRIVER_EDIT | OTHER_USER_EDIT | UNIDENTIFIED_DRIVER '
    '(49 CFR 395 App. A event record origin).';
COMMENT ON COLUMN eld_events.is_duplicate IS
    'TRUE when an earlier row in the same file/section already used this event '
    'sequence number. The row is retained; the repetition is reported as a '
    'WARNING issue rather than dropped.';

-- ---------------------------------------------------------------------------
-- eld_parse_issues: every parse/validation/mapping problem, addressable
-- ---------------------------------------------------------------------------
-- One row per DISTINCT problem, not per occurrence: a 50,000-row file with a
-- systematically bad timestamp column produces ONE issue with occurrences =
-- 50000 and up to 20 sample line numbers in `details`, instead of 50,000 rows.
-- That keeps the diagnostic complete (nothing is hidden) and bounded (a bad
-- file cannot flood the table).
CREATE TABLE IF NOT EXISTS eld_parse_issues (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    eld_file_id  UUID NOT NULL REFERENCES eld_files(id) ON DELETE CASCADE,
    severity     TEXT NOT NULL,   -- ERROR | WARNING | INFO
    code         TEXT NOT NULL,   -- stable machine-readable code
    message      TEXT NOT NULL,   -- human-actionable description
    section      TEXT,            -- ELD output-file section, when applicable
    line_number  INT,             -- first offending line (1-based, whole file)
    column_name  TEXT,            -- offending column, when applicable
    raw_value    TEXT,            -- the value that could not be interpreted
    occurrences  INT NOT NULL DEFAULT 1,
    details      JSONB,           -- {"sample_lines": [...], "sample_values": [...]}
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_eld_parse_issues_file
    ON eld_parse_issues (eld_file_id, severity);

COMMENT ON TABLE eld_parse_issues IS
    'Per-file ELD parse/validation/mapping diagnostics (BRD Appendix E, §8.7). '
    'One aggregated row per distinct problem so nothing fails silently and a '
    'pathological file cannot flood the table. Rewritten on every (re)parse.';
