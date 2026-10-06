-- =============================================================================
-- CCFP IT Solution - Migration 0014: PCI single-valued sections (PCI-1)
-- =============================================================================
-- §8.4 / §19.2 (l.841-847): the Post-Crash Investigation (PCI) form's
-- single-valued sections were previously dumped into one untyped
-- post_crash_investigations.sections JSONB blob. This migration models each
-- one-to-one §19.2 section as its own typed child table so the data becomes
-- queryable, validatable, and analyzable.
--
-- Repeating structures (seating positions, axles, tires, trailers) are PCI-4
-- (migration 0016); conditional optional sections (towed units, hazmat) are
-- PCI-5 (migration 0017); per-field required/optional flags are PCI-3
-- (migration 0015); ELD summary columns are PCI-7 (migration 0018).
--
-- Conventions (match incident_persons / PostCrashInspection):
--   * id UUID PK DEFAULT gen_random_uuid()
--   * investigation_id UUID NOT NULL REFERENCES post_crash_investigations(id)
--       ON DELETE CASCADE, UNIQUE (one row per investigation)
--   * created_at / updated_at TIMESTAMPTZ DEFAULT now()
--   * CREATE INDEX on (investigation_id)
-- All section columns are nullable (the form marks most fields optional, §19.2).
-- The existing post_crash_investigations.sections column is KEPT (deprecated).
-- =============================================================================

-- The legacy untyped blob is retained for back-compat with in-flight data.
COMMENT ON COLUMN post_crash_investigations.sections IS
    'DEPRECATED (PCI-1): legacy untyped JSONB blob for §19.2 sections. Superseded '
    'by the typed pci_* child tables. Retained for back-compat with in-flight data.';

-- ---------------------------------------------------------------------------
-- Motor carrier and power unit (§19.2 l.841)
-- ---------------------------------------------------------------------------
CREATE TABLE pci_carrier_power_unit (
    id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    investigation_id            UUID NOT NULL REFERENCES post_crash_investigations(id) ON DELETE CASCADE,
    work_zone                   BOOLEAN,
    work_zone_type              TEXT,
    preclearance_bypass_serial  TEXT,
    fire                        BOOLEAN,
    fire_pre_crash              BOOLEAN,
    fire_post_crash             BOOLEAN,
    carrier_name_displayed      TEXT,
    us_dot_displayed            BOOLEAN,
    nsc_number                  TEXT,
    motor_carrier_name          TEXT,
    motor_carrier_address       TEXT,
    motor_carrier_phone         TEXT,
    owner_name                  TEXT,
    owner_address               TEXT,
    lease_indicator             BOOLEAN,
    year                        INT,
    make                        TEXT,
    model                       TEXT,
    company_unit_number         TEXT,
    manufacture_date            DATE,
    vin                         TEXT,
    color                       TEXT,
    license_plate               TEXT,
    license_plate_state         TEXT,
    registered_gross_weight     NUMERIC,
    gvwr                        NUMERIC,
    annual_inspection           BOOLEAN,
    axles_up                    INT,
    axles_down                  INT,
    remarks                     TEXT,
    created_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (investigation_id)
);
CREATE INDEX idx_pci_carrier_power_unit_inv ON pci_carrier_power_unit(investigation_id);

-- ---------------------------------------------------------------------------
-- Driver / load information (§19.2 l.843) -- excludes per-seating-position
-- belt/airbag (PCI-4) and hazmat (PCI-5).
-- ---------------------------------------------------------------------------
CREATE TABLE pci_driver_load (
    id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    investigation_id            UUID NOT NULL REFERENCES post_crash_investigations(id) ON DELETE CASCADE,
    driver_name                 TEXT,
    driver_present              BOOLEAN,
    driver_address              TEXT,
    license_state               TEXT,
    license_province            TEXT,
    license_number              TEXT,
    license_class               TEXT,
    license_endorsements        TEXT,
    license_restrictions        TEXT,
    license_issue_date          DATE,
    license_expiration_date     DATE,
    lenses_required             BOOLEAN,
    lenses_worn                 BOOLEAN,
    shipper                     TEXT,
    bill_of_lading              TEXT,
    manifest_load_weight        NUMERIC,
    cargo_loaded                TEXT,
    cargo_destination           TEXT,
    load_securement             BOOLEAN,
    securement_contributed      BOOLEAN,
    securement_proper_use       BOOLEAN,
    securement_exceeded_wll     BOOLEAN,
    securement_type             TEXT,
    remarks                     TEXT,
    created_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (investigation_id)
);
CREATE INDEX idx_pci_driver_load_inv ON pci_driver_load(investigation_id);

-- ---------------------------------------------------------------------------
-- Medical certificate (§19.2 l.843)
-- ---------------------------------------------------------------------------
CREATE TABLE pci_medical_certificate (
    id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    investigation_id            UUID NOT NULL REFERENCES post_crash_investigations(id) ON DELETE CASCADE,
    examination_date            DATE,
    expiration_date             DATE,
    lenses                      BOOLEAN,
    hearing_aid                 BOOLEAN,
    waiver                      BOOLEAN,
    medic_alert                 BOOLEAN,
    cert_state                  TEXT,
    cert_province               TEXT,
    remarks                     TEXT,
    created_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (investigation_id)
);
CREATE INDEX idx_pci_medical_certificate_inv ON pci_medical_certificate(investigation_id);

-- ---------------------------------------------------------------------------
-- Driver hours of service (§19.2 l.844) -- ELD download/last-duty detail is
-- PCI-7 (on eld_files), not here.
-- ---------------------------------------------------------------------------
CREATE TABLE pci_hours_of_service (
    id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    investigation_id            UUID NOT NULL REFERENCES post_crash_investigations(id) ON DELETE CASCADE,
    on_duty_not_driving_hours   NUMERIC,
    driving_hours               NUMERIC,
    total_on_duty_hours         NUMERIC,
    miles_driven                NUMERIC,
    kilometers_driven           NUMERIC,
    record_of_duty_status       BOOLEAN,
    timecard                    BOOLEAN,
    violations                  TEXT,
    onboard_computer_eld        BOOLEAN,
    eld_present                 BOOLEAN,
    co_driver                   BOOLEAN,
    last_8_days_present         BOOLEAN,
    approved_eld                BOOLEAN,
    driver_history              TEXT,
    road_familiarity            TEXT,
    years_experience            NUMERIC,
    previous_cmv_crashes        INT,
    purpose_of_trip             TEXT,
    trip_destination            TEXT,
    driver_condition_remarks    TEXT,
    created_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (investigation_id)
);
CREATE INDEX idx_pci_hours_of_service_inv ON pci_hours_of_service(investigation_id);

-- ---------------------------------------------------------------------------
-- Exemptions (§19.2 l.845)
-- ---------------------------------------------------------------------------
CREATE TABLE pci_exemptions (
    id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    investigation_id            UUID NOT NULL REFERENCES post_crash_investigations(id) ON DELETE CASCADE,
    exemption_14_hour           BOOLEAN,
    exemption_11_hour           BOOLEAN,
    exemption_split_sleeper     BOOLEAN,
    exemption_60_70_hour        BOOLEAN,
    exemption_34_hour_restart   BOOLEAN,
    exemption_federal           BOOLEAN,
    exemption_state             BOOLEAN,
    exemption_oilfield          BOOLEAN,
    exemption_agricultural      BOOLEAN,
    exemption_150_air_mile      BOOLEAN,
    exemption_temporary         BOOLEAN,
    docket_or_state_number      TEXT,
    emergency_declaration       BOOLEAN,
    emergency_jurisdiction      TEXT,
    emergency_federal_number    TEXT,
    emergency_state_number      TEXT,
    service_center              TEXT,
    other_description           TEXT,
    created_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (investigation_id)
);
CREATE INDEX idx_pci_exemptions_inv ON pci_exemptions(investigation_id);

-- ---------------------------------------------------------------------------
-- Vehicle condition and equipment (§19.2 l.846)
-- ---------------------------------------------------------------------------
CREATE TABLE pci_vehicle_condition (
    id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    investigation_id            UUID NOT NULL REFERENCES post_crash_investigations(id) ON DELETE CASCADE,
    compartment_condition       TEXT,
    drivers_view                TEXT,
    wipers                      TEXT,
    wiper_switch_position       TEXT,
    heater_defroster            TEXT,
    mirrors                     TEXT,
    rearward_camera             BOOLEAN,
    fender_mirrors              BOOLEAN,
    odometer                    NUMERIC,
    engine_hours                NUMERIC,
    engine_manufacturer         TEXT,
    fuel_type                   TEXT,
    ecm_serial                  TEXT,
    adas                        TEXT,
    steering_type               TEXT,
    steering_wheel_diameter     NUMERIC,
    steering_lash               TEXT,
    steering_checked_running    BOOLEAN,
    transmission_type           TEXT,
    transmission_model          TEXT,
    transmission_serial         TEXT,
    transmission_gear_position  TEXT,
    transmission_forward_gears  INT,
    drive_line_notes            TEXT,
    drive_axle_ratio            TEXT,
    radio                       BOOLEAN,
    cb                          BOOLEAN,
    dash_camera                 BOOLEAN,
    audio_technology            BOOLEAN,
    headphones                  BOOLEAN,
    bluetooth                   BOOLEAN,
    remarks                     TEXT,
    created_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (investigation_id)
);
CREATE INDEX idx_pci_vehicle_condition_inv ON pci_vehicle_condition(investigation_id);

-- ---------------------------------------------------------------------------
-- Brake systems summary (§19.2 l.847) -- per-axle air-brake data is PCI-4.
-- ---------------------------------------------------------------------------
CREATE TABLE pci_brake_system (
    id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    investigation_id            UUID NOT NULL REFERENCES post_crash_investigations(id) ON DELETE CASCADE,
    brake_type                  TEXT,
    abs_type                    TEXT,
    engine_brake_type           TEXT,
    engine_brake_position       TEXT,
    air_leaks                   BOOLEAN,
    application_loss            BOOLEAN,
    low_air_vacuum_warning      BOOLEAN,
    low_air_vacuum_warning_psi  NUMERIC,
    hydraulic_master_cylinder_secure BOOLEAN,
    hydraulic_fluid_level       TEXT,
    hydraulic_fluid_seepage     BOOLEAN,
    hydraulic_line_condition    TEXT,
    electric_controller_mfr     TEXT,
    electric_gain_setting       TEXT,
    electric_breakaway_device   BOOLEAN,
    electric_battery_wiring     TEXT,
    surge_breakaway_device      BOOLEAN,
    surge_fluid_leak            BOOLEAN,
    power_assist                BOOLEAN,
    parking_brake               BOOLEAN,
    wheel_end_weight_note       TEXT,
    remarks                     TEXT,
    created_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (investigation_id)
);
CREATE INDEX idx_pci_brake_system_inv ON pci_brake_system(investigation_id);

-- ---------------------------------------------------------------------------
-- updated_at triggers (reuse the existing set_updated_at() function).
-- ---------------------------------------------------------------------------
DO $$
DECLARE t TEXT;
BEGIN
    FOREACH t IN ARRAY ARRAY[
        'pci_carrier_power_unit','pci_driver_load','pci_medical_certificate',
        'pci_hours_of_service','pci_exemptions','pci_vehicle_condition',
        'pci_brake_system'
    ]
    LOOP
        EXECUTE format(
            'CREATE TRIGGER trg_%1$s_updated_at BEFORE UPDATE ON %1$s '
            'FOR EACH ROW EXECUTE FUNCTION set_updated_at();', t);
    END LOOP;
END $$;
