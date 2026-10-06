-- =============================================================================
-- CCFP IT Solution - Migration 0018: ELD summary fields (PCI-7)
-- =============================================================================
-- §8.4 (l.269) / §19.2 (l.844): the PCI form captures ELD download status and
-- last-duty-status detail -- whether the ELD was downloaded, the last entry,
-- the last duty status, and the last stop (arrived/departed). These are small
-- additive nullable columns on the existing eld_files table.
--
-- last_duty_status values align with app.enums.DutyStatus but the column is
-- plain TEXT (no DB enum), matching the existing provider/model/version columns.
-- Idempotent / additive: ADD COLUMN IF NOT EXISTS.
-- =============================================================================

ALTER TABLE eld_files ADD COLUMN IF NOT EXISTS eld_downloaded         BOOLEAN;
ALTER TABLE eld_files ADD COLUMN IF NOT EXISTS last_entry_at          TIMESTAMPTZ;
ALTER TABLE eld_files ADD COLUMN IF NOT EXISTS last_duty_status       TEXT;
ALTER TABLE eld_files ADD COLUMN IF NOT EXISTS last_stop_arrived_at   TIMESTAMPTZ;
ALTER TABLE eld_files ADD COLUMN IF NOT EXISTS last_stop_departed_at  TIMESTAMPTZ;

COMMENT ON COLUMN eld_files.eld_downloaded IS
    'PCI-7 (§19.2 l.844): was the ELD successfully downloaded.';
COMMENT ON COLUMN eld_files.last_duty_status IS
    'PCI-7 (§19.2 l.844): last recorded duty status. Values align with '
    'app.enums.DutyStatus (plain TEXT, no DB enum).';
