-- =============================================================================
-- CCFP IT Solution - Migration 0016: PCI repeating structures (PCI-4)
-- =============================================================================
-- §19.2 (l.842-850): the PCI form has repeating groups -- seat-belt/airbag per
-- seating position, tires per axle/side/inner-outer, axle-level air-brake data,
-- and trailers 1..3 (+ converter dolly). These are modeled as child tables with
-- a position/index column (NOT fixed numbered columns) so they stay configurable
-- for future phases (no hardcoded Phase-1 maxima as DB constraints).
--
-- Conventions: id UUID PK, investigation_id FK CASCADE, created_at/updated_at,
-- index on (investigation_id). All section columns nullable.
-- =============================================================================

-- ---------------------------------------------------------------------------
-- Seat-belt / airbag per seating position (§19.2 l.843)
--   position: DRIVER | PASSENGER_1 | PASSENGER_2 | SLEEPER_BERTH (text; no DB
--   enum, stays study-configurable).
-- ---------------------------------------------------------------------------
CREATE TABLE pci_seating_positions (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    investigation_id    UUID NOT NULL REFERENCES post_crash_investigations(id) ON DELETE CASCADE,
    position            TEXT,
    seat_belt_equipped  BOOLEAN,
    seat_belt_used      BOOLEAN,
    seat_belt_condition TEXT,
    airbag_equipped     BOOLEAN,
    airbag_deployed     BOOLEAN,
    remarks             TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (investigation_id, position)
);
CREATE INDEX idx_pci_seating_positions_inv ON pci_seating_positions(investigation_id);

-- ---------------------------------------------------------------------------
-- Axle-level air-brake data (§19.2 l.848, l.850) -- axle_index 1..11 etc.
-- ---------------------------------------------------------------------------
CREATE TABLE pci_axles (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    investigation_id    UUID NOT NULL REFERENCES post_crash_investigations(id) ON DELETE CASCADE,
    axle_index          INT,
    abs                 BOOLEAN,
    slack_adjuster_type TEXT,
    slack_adjuster_length NUMERIC,
    push_rod_stroke_available NUMERIC,
    push_rod_stroke_applied   NUMERIC,
    air_pressure        TEXT,
    chamber_type        TEXT,
    drum_rotor          TEXT,
    brake_friction_code TEXT,
    rolling_radius      NUMERIC,
    wheel_end_weight    NUMERIC,
    total_end_weight    NUMERIC,
    remarks             TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (investigation_id, axle_index)
);
CREATE INDEX idx_pci_axles_inv ON pci_axles(investigation_id);

-- ---------------------------------------------------------------------------
-- Tire data (§19.2 l.850) -- per axle, side (LEFT|RIGHT), inner/outer
-- (INSIDE|OUTSIDE).
-- ---------------------------------------------------------------------------
CREATE TABLE pci_tires (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    investigation_id    UUID NOT NULL REFERENCES post_crash_investigations(id) ON DELETE CASCADE,
    axle_index          INT,
    side                TEXT,
    inner_outer         TEXT,
    size                TEXT,
    make                TEXT,
    model_design        TEXT,
    tin_dot             TEXT,
    rated_psi           NUMERIC,
    rated_weight        NUMERIC,
    inspection_psi      NUMERIC,
    retread_tin_dot     TEXT,
    repair              BOOLEAN,
    repair_location     TEXT,
    speed_rating        TEXT,
    tread_depth         NUMERIC,
    wheel_hub_remarks   TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (investigation_id, axle_index, side, inner_outer)
);
CREATE INDEX idx_pci_tires_inv ON pci_tires(investigation_id);

-- ---------------------------------------------------------------------------
-- Trailer and converter dolly records (§19.2 l.842) -- trailer_index 1..3.
-- ---------------------------------------------------------------------------
CREATE TABLE pci_trailers (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    investigation_id        UUID NOT NULL REFERENCES post_crash_investigations(id) ON DELETE CASCADE,
    trailer_index           INT,
    owner_name              TEXT,
    owner_address           TEXT,
    trailer_type            TEXT,
    intermodal_indicator    BOOLEAN,
    unit_number             TEXT,
    year                    INT,
    make                    TEXT,
    model                   TEXT,
    vin                     TEXT,
    color                   TEXT,
    license_plate           TEXT,
    expiration              DATE,
    registered_gross_weight NUMERIC,
    gvwr                    NUMERIC,
    axle_weight_rating      NUMERIC,
    annual_inspection       BOOLEAN,
    axles_up                INT,
    axles_down              INT,
    converter_dolly         BOOLEAN,
    converter_dolly_details TEXT,
    remarks                 TEXT,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (investigation_id, trailer_index)
);
CREATE INDEX idx_pci_trailers_inv ON pci_trailers(investigation_id);

-- ---------------------------------------------------------------------------
-- updated_at triggers (reuse the existing set_updated_at() function).
-- ---------------------------------------------------------------------------
DO $$
DECLARE t TEXT;
BEGIN
    FOREACH t IN ARRAY ARRAY[
        'pci_seating_positions','pci_axles','pci_tires','pci_trailers'
    ]
    LOOP
        EXECUTE format(
            'CREATE TRIGGER trg_%1$s_updated_at BEFORE UPDATE ON %1$s '
            'FOR EACH ROW EXECUTE FUNCTION set_updated_at();', t);
    END LOOP;
END $$;
