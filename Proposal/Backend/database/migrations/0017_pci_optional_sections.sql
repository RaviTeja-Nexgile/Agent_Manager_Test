-- =============================================================================
-- CCFP IT Solution - Migration 0017: PCI optional / conditional sections (PCI-5)
-- =============================================================================
-- §19.2 (l.840, l.852): "the last three pages (additional towed units and
-- hazardous material) are optional" and "must be supported as conditional
-- sections." A boolean presence flag on the parent decides whether the optional
-- page is shown and whether its child rows are written.
--
-- Adds two presence flags to post_crash_investigations and two child tables.
-- Conventions: id UUID PK, investigation_id FK CASCADE, created_at/updated_at,
-- index on (investigation_id). All section columns nullable.
-- =============================================================================

-- Presence flags (additive, idempotent).
ALTER TABLE post_crash_investigations
    ADD COLUMN IF NOT EXISTS has_additional_towed_units BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE post_crash_investigations
    ADD COLUMN IF NOT EXISTS has_hazmat BOOLEAN NOT NULL DEFAULT false;

COMMENT ON COLUMN post_crash_investigations.has_additional_towed_units IS
    'PCI-5: presence flag for the optional additional-towed-units page; gates '
    'whether pci_additional_towed_units rows are persisted.';
COMMENT ON COLUMN post_crash_investigations.has_hazmat IS
    'PCI-5: presence flag for the optional hazardous-material page; gates whether '
    'pci_hazmat rows are persisted.';

-- ---------------------------------------------------------------------------
-- Hazardous material (§19.2 l.843) -- presence/type/placards/spill/leak by
-- truck and trailers (unit_scope: TRUCK | TRAILER_1 ...).
-- ---------------------------------------------------------------------------
CREATE TABLE pci_hazmat (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    investigation_id    UUID NOT NULL REFERENCES post_crash_investigations(id) ON DELETE CASCADE,
    unit_scope          TEXT,
    hazmat_present      BOOLEAN,
    hazmat_type         TEXT,
    placards            TEXT,
    spill               BOOLEAN,
    leak                BOOLEAN,
    remarks             TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_pci_hazmat_inv ON pci_hazmat(investigation_id);

-- ---------------------------------------------------------------------------
-- Additional towed units (§19.2 l.849, l.851) -- optional towed-unit pages:
-- lighting and measurement detail, indexed by towed_index.
-- ---------------------------------------------------------------------------
CREATE TABLE pci_additional_towed_units (
    id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    investigation_id            UUID NOT NULL REFERENCES post_crash_investigations(id) ON DELETE CASCADE,
    towed_index                 INT,
    owner_name                  TEXT,
    owner_address               TEXT,
    unit_type                   TEXT,
    unit_number                 TEXT,
    vin                         TEXT,
    -- Lighting detail (§19.2 l.849): towed-unit lamps.
    front_clearance             TEXT,
    rear_clearance              TEXT,
    side_marker_left            TEXT,
    side_marker_right           TEXT,
    turn_signals                TEXT,
    stop_lamps                  TEXT,
    id_lamps                    TEXT,
    tail_lamps                  TEXT,
    reflectors                  TEXT,
    conspicuity_tape            TEXT,
    -- Measurement detail (§19.2 l.851), all in inches.
    distance_from_rear          NUMERIC,
    rear_protection_from_rear   NUMERIC,
    rear_protection_from_ground NUMERIC,
    rear_protection_from_side   NUMERIC,
    rear_protection_width       NUMERIC,
    remarks                     TEXT,
    created_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (investigation_id, towed_index)
);
CREATE INDEX idx_pci_additional_towed_units_inv ON pci_additional_towed_units(investigation_id);

-- ---------------------------------------------------------------------------
-- updated_at triggers (reuse the existing set_updated_at() function).
-- ---------------------------------------------------------------------------
DO $$
DECLARE t TEXT;
BEGIN
    FOREACH t IN ARRAY ARRAY['pci_hazmat','pci_additional_towed_units']
    LOOP
        EXECUTE format(
            'CREATE TRIGGER trg_%1$s_updated_at BEFORE UPDATE ON %1$s '
            'FOR EACH ROW EXECUTE FUNCTION set_updated_at();', t);
    END LOOP;
END $$;
