-- =============================================================================
-- CCFP IT Solution - Initial Schema (Phase 1 Heavy-Duty Truck Study)
-- Source of truth: Proposal/Documentation/project_documentation.md (§11) + CLAUDE.md
-- Target: PostgreSQL 18
-- =============================================================================
-- Conventions:
--   * UUID primary keys via built-in gen_random_uuid().
--   * created_at / updated_at timestamptz on mutable tables; updated_at kept
--     current by the set_updated_at() trigger.
--   * Crash-owned child rows cascade on crash delete; reference FKs restrict.
--   * Native ENUM types for stable bounded domains; reference tables for
--     extensible catalogs (states, PCR sections, contributing-factor groups).
-- =============================================================================

-- ---------------------------------------------------------------------------
-- 0. Helper trigger function
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION set_updated_at() RETURNS trigger AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- ---------------------------------------------------------------------------
-- 1. Enumerated types
-- ---------------------------------------------------------------------------
DO $$ BEGIN
    CREATE TYPE organization_type AS ENUM
        ('FMCSA','BTS','STATE_AGENCY','VOLPE','NHTSA','FHWA','NOAA','AAMVA','EXTERNAL','OTHER');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE TYPE user_status AS ENUM ('ACTIVE','INACTIVE','SUSPENDED','PENDING');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE TYPE assignment_scope AS ENUM ('GLOBAL','ORGANIZATION','STATE','STUDY');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE TYPE study_status AS ENUM ('PLANNING','ACTIVE','CLOSED','PUBLISHED');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE TYPE crash_scope AS ENUM ('IN_SCOPE','OUT_OF_SCOPE','UNDETERMINED');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE TYPE crash_lifecycle_phase AS ENUM
        ('INITIAL_INCIDENT','NOTIFICATION','DATA_COLLECTION','DATA_MAPPING',
         'QUALITY_CONTROL','ANALYSIS','PUBLICATION');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE TYPE form_status AS ENUM ('DRAFT','SUBMITTED','ROUTED','DELETED');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE TYPE person_type AS ENUM ('DRIVER','OCCUPANT','NON_MOTORIST','WITNESS');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE TYPE injury_status AS ENUM ('FATAL','INJURY','NO_INJURY','UNKNOWN');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE TYPE mapping_status AS ENUM ('PENDING','MAPPED','REVIEWED');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE TYPE coding_status AS ENUM ('PENDING','IN_PROGRESS','CODED');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE TYPE eld_upload_status AS ENUM ('UPLOADED','PARSING','PARSED','FAILED');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE TYPE duty_status AS ENUM ('OFF_DUTY','SLEEPER_BERTH','DRIVING','ON_DUTY_NOT_DRIVING');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE TYPE qc_result_status AS ENUM ('PASS','FAIL','WARNING','NOT_EVALUATED');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE TYPE rule_severity AS ENUM ('INFO','WARNING','ERROR','CRITICAL');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE TYPE completeness_status AS ENUM ('COMPLETE','INCOMPLETE');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE TYPE attribute_data_type AS ENUM
        ('TEXT','NUMBER','DATE','DATETIME','BOOLEAN','CODE','JSON');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE TYPE data_sensitivity AS ENUM ('PUBLIC','INTERNAL','PII','SENSITIVE','CIPSEA');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE TYPE document_type AS ENUM
        ('DOCUMENT','IMAGE','VIDEO','PDF','ELD_CSV','SPREADSHEET','REPORT','OTHER');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE TYPE malware_scan_status AS ENUM ('PENDING','CLEAN','INFECTED','ERROR');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE TYPE report_type AS ENUM ('DASHBOARD','REPORT','TABLE','VISUALIZATION');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE TYPE report_visibility AS ENUM ('PRIVATE','ORGANIZATION','FEDERAL','STATE','PUBLIC');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE TYPE notification_status AS ENUM ('PENDING','SENT','DELIVERED','READ','FAILED');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- =============================================================================
-- 2. Reference data tables
-- =============================================================================
CREATE TABLE ref_us_states (
    code        CHAR(2) PRIMARY KEY,
    name        TEXT NOT NULL,
    is_territory BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE ref_pcr_sections (
    code        TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    sort_order  INT NOT NULL DEFAULT 0
);

-- BRD-specified contributing-factor groups for the analyst top-three prompt.
CREATE TABLE ref_contributing_factor_groups (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    code        TEXT NOT NULL UNIQUE,
    name        TEXT NOT NULL,
    applies_to  TEXT NOT NULL,          -- ROADWAY | VEHICLE | DRIVER | NON_MOTORIST
    sort_order  INT NOT NULL DEFAULT 0
);

-- =============================================================================
-- 3. Identity & Access (organizations, users, roles, permissions, assignments)
-- =============================================================================
CREATE TABLE organizations (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name        TEXT NOT NULL,
    org_type    organization_type NOT NULL,
    state_code  CHAR(2) REFERENCES ref_us_states(code),
    parent_id   UUID REFERENCES organizations(id) ON DELETE SET NULL,
    description TEXT,
    is_active   BOOLEAN NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_organizations_type ON organizations(org_type);
CREATE INDEX idx_organizations_state ON organizations(state_code);

CREATE TABLE users (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email         TEXT NOT NULL UNIQUE,
    full_name     TEXT NOT NULL,
    idp_subject   TEXT UNIQUE,            -- identity-provider subject (OIDC sub)
    organization_id UUID REFERENCES organizations(id) ON DELETE SET NULL,
    title         TEXT,
    phone         TEXT,
    status        user_status NOT NULL DEFAULT 'ACTIVE',
    mfa_enabled   BOOLEAN NOT NULL DEFAULT TRUE,
    piv_cac_required BOOLEAN NOT NULL DEFAULT FALSE,
    last_login_at TIMESTAMPTZ,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_users_org ON users(organization_id);
CREATE INDEX idx_users_status ON users(status);

CREATE TABLE roles (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    code        TEXT NOT NULL UNIQUE,
    name        TEXT NOT NULL,
    description TEXT,
    is_system   BOOLEAN NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE permissions (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    code        TEXT NOT NULL UNIQUE,     -- e.g. crash:read, initial_incident:submit
    name        TEXT NOT NULL,
    category    TEXT NOT NULL,            -- module grouping
    description TEXT
);
CREATE INDEX idx_permissions_category ON permissions(category);

CREATE TABLE role_permissions (
    role_id       UUID NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
    permission_id UUID NOT NULL REFERENCES permissions(id) ON DELETE CASCADE,
    PRIMARY KEY (role_id, permission_id)
);

-- Forward-declared FK to studies is added after studies exists (see ALTER below).
CREATE TABLE user_role_assignments (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id       UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role_id       UUID NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
    scope_type    assignment_scope NOT NULL DEFAULT 'GLOBAL',
    organization_id UUID REFERENCES organizations(id) ON DELETE CASCADE,
    state_code    CHAR(2) REFERENCES ref_us_states(code),
    study_id      UUID,                   -- FK added after studies table
    granted_by    UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id, role_id, scope_type, organization_id, state_code, study_id)
);
CREATE INDEX idx_ura_user ON user_role_assignments(user_id);
CREATE INDEX idx_ura_role ON user_role_assignments(role_id);
CREATE INDEX idx_ura_state ON user_role_assignments(state_code);

-- =============================================================================
-- 4. Study configuration
-- =============================================================================
CREATE TABLE studies (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    code            TEXT NOT NULL UNIQUE,         -- e.g. PHASE1-HDT
    name            TEXT NOT NULL,
    phase_number    INT NOT NULL,
    vehicle_type    TEXT NOT NULL,                -- e.g. Heavy-Duty Truck (Class 7/8)
    crash_severity  TEXT NOT NULL,                -- e.g. Fatal
    description     TEXT,
    start_date      DATE,
    end_date        DATE,
    pilot_start_date DATE,
    status          study_status NOT NULL DEFAULT 'PLANNING',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Resolve the forward-declared study FKs now that studies exists.
ALTER TABLE user_role_assignments
    ADD CONSTRAINT fk_ura_study FOREIGN KEY (study_id)
    REFERENCES studies(id) ON DELETE CASCADE;

CREATE TABLE study_states (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    study_id        UUID NOT NULL REFERENCES studies(id) ON DELETE CASCADE,
    state_code      CHAR(2) NOT NULL REFERENCES ref_us_states(code),
    is_participating BOOLEAN NOT NULL DEFAULT FALSE,
    agreement_status TEXT NOT NULL DEFAULT 'PENDING', -- PENDING|SIGNED|EXPIRED
    onboarded_at    DATE,
    notes           TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (study_id, state_code)
);
CREATE INDEX idx_study_states_state ON study_states(state_code);

CREATE TABLE study_parameters (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    study_id    UUID NOT NULL REFERENCES studies(id) ON DELETE CASCADE,
    param_key   TEXT NOT NULL,        -- e.g. min_gvwr_lbs, vehicle_classes, scope_rules
    param_value JSONB NOT NULL,
    description TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (study_id, param_key)
);

CREATE TABLE data_attributes (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    code          TEXT NOT NULL UNIQUE,        -- canonical CCFP/PCR code (e.g. C01, V01)
    name          TEXT NOT NULL,
    category      TEXT NOT NULL,               -- module/group
    pcr_section   TEXT REFERENCES ref_pcr_sections(code),
    data_type     attribute_data_type NOT NULL DEFAULT 'TEXT',
    sensitivity   data_sensitivity NOT NULL DEFAULT 'INTERNAL',
    description   TEXT,
    is_active     BOOLEAN NOT NULL DEFAULT TRUE,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_data_attributes_section ON data_attributes(pcr_section);
CREATE INDEX idx_data_attributes_category ON data_attributes(category);

CREATE TABLE attribute_requirements (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    study_id      UUID NOT NULL REFERENCES studies(id) ON DELETE CASCADE,
    attribute_id  UUID NOT NULL REFERENCES data_attributes(id) ON DELETE CASCADE,
    is_required   BOOLEAN NOT NULL DEFAULT FALSE,
    is_optional   BOOLEAN NOT NULL DEFAULT TRUE,
    is_read_only  BOOLEAN NOT NULL DEFAULT FALSE,
    is_editable   BOOLEAN NOT NULL DEFAULT TRUE,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (study_id, attribute_id)
);

-- =============================================================================
-- 5. Crash core
-- =============================================================================
CREATE TABLE crashes (
    id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ccfp_identifier    TEXT NOT NULL UNIQUE,        -- stable unique CCFP id
    study_id           UUID NOT NULL REFERENCES studies(id) ON DELETE RESTRICT,
    local_report_number TEXT,
    crash_date         DATE,
    crash_time         TIME,
    city               TEXT,
    county             TEXT,
    state_code         CHAR(2) REFERENCES ref_us_states(code),
    street_highway     TEXT,
    latitude           NUMERIC(9,6),
    longitude          NUMERIC(9,6),
    num_vehicles       INT CHECK (num_vehicles IS NULL OR num_vehicles >= 0),
    num_persons        INT CHECK (num_persons IS NULL OR num_persons >= 0),
    num_fatalities     INT CHECK (num_fatalities IS NULL OR num_fatalities >= 0),
    lifecycle_phase    crash_lifecycle_phase NOT NULL DEFAULT 'INITIAL_INCIDENT',
    created_by         UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_crashes_study ON crashes(study_id);
CREATE INDEX idx_crashes_state ON crashes(state_code);
CREATE INDEX idx_crashes_phase ON crashes(lifecycle_phase);
CREATE INDEX idx_crashes_date ON crashes(crash_date);

CREATE TABLE crash_scope_classifications (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    crash_id        UUID NOT NULL UNIQUE REFERENCES crashes(id) ON DELETE CASCADE,
    is_qualifying   BOOLEAN NOT NULL DEFAULT FALSE,
    scope           crash_scope NOT NULL DEFAULT 'UNDETERMINED',
    is_supplemental BOOLEAN NOT NULL DEFAULT FALSE,
    classification_reason TEXT,
    classified_by   UUID REFERENCES users(id) ON DELETE SET NULL,
    classified_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE initial_incident_forms (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    crash_id        UUID NOT NULL UNIQUE REFERENCES crashes(id) ON DELETE CASCADE,
    status          form_status NOT NULL DEFAULT 'DRAFT',
    event_summary   TEXT,
    dot_number_validated BOOLEAN NOT NULL DEFAULT FALSE,
    dot_validation_source TEXT,                    -- e.g. SafeSpect
    submitted_by    UUID REFERENCES users(id) ON DELETE SET NULL,
    submitted_at    TIMESTAMPTZ,
    routed_at       TIMESTAMPTZ,
    created_by      UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE incident_vehicles (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    crash_id        UUID NOT NULL REFERENCES crashes(id) ON DELETE CASCADE,
    vehicle_number  INT NOT NULL,
    is_cmv          BOOLEAN NOT NULL DEFAULT FALSE,
    us_dot_number   TEXT,
    make            TEXT,
    num_occupants   INT CHECK (num_occupants IS NULL OR num_occupants >= 0),
    num_injured_occupants INT CHECK (num_injured_occupants IS NULL OR num_injured_occupants >= 0),
    carrier_name    TEXT,
    carrier_phone   TEXT,
    is_supplemental BOOLEAN NOT NULL DEFAULT FALSE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (crash_id, vehicle_number)
);
CREATE INDEX idx_incident_vehicles_crash ON incident_vehicles(crash_id);

CREATE TABLE incident_persons (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    crash_id        UUID NOT NULL REFERENCES crashes(id) ON DELETE CASCADE,
    person_type     person_type NOT NULL,
    related_vehicle_number INT,             -- links occupant/non-motorist to a vehicle
    full_name       TEXT,
    is_minor        BOOLEAN,
    primary_language TEXT,
    address         TEXT,
    phone_primary   TEXT,
    phone_secondary TEXT,
    phone_type      TEXT,                   -- HOME | CELL | WORK
    injury          injury_status,
    is_supplemental BOOLEAN NOT NULL DEFAULT FALSE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_incident_persons_crash ON incident_persons(crash_id);
CREATE INDEX idx_incident_persons_type ON incident_persons(person_type);

-- =============================================================================
-- 6. Source data collection
-- =============================================================================
CREATE TABLE post_crash_inspections (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    crash_id        UUID NOT NULL REFERENCES crashes(id) ON DELETE CASCADE,
    source_system   TEXT NOT NULL DEFAULT 'SafeSpect',
    inspection_number TEXT,
    inspection_date DATE,
    inspector_name  TEXT,
    violations_count INT DEFAULT 0,
    defects_count   INT DEFAULT 0,
    details         JSONB,
    linked_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_pci_crash ON post_crash_inspections(crash_id);

CREATE TABLE post_crash_investigations (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    crash_id        UUID NOT NULL REFERENCES crashes(id) ON DELETE CASCADE,
    case_number     TEXT,
    inspection_number TEXT,
    officer_name    TEXT,
    officer_id      TEXT,
    post_crash_date DATE,
    status          form_status NOT NULL DEFAULT 'DRAFT',
    -- Structured sections per documentation §8.4 / §19.2 (carrier, power unit,
    -- trailers, driver/load, HOS, exemptions, vehicle condition, brakes, air
    -- brake data, lighting, tires, axles, measurements).
    sections        JSONB,
    created_by      UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_pci_inv_crash ON post_crash_investigations(crash_id);

CREATE TABLE police_crash_reports (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    crash_id        UUID NOT NULL REFERENCES crashes(id) ON DELETE CASCADE,
    state_code      CHAR(2) REFERENCES ref_us_states(code),
    source_repository TEXT,               -- MCMIS | State repository name
    pcr_number      TEXT,
    report_date     DATE,
    mapping_status  mapping_status NOT NULL DEFAULT 'PENDING',
    mapped_by       UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_pcr_crash ON police_crash_reports(crash_id);
CREATE INDEX idx_pcr_state ON police_crash_reports(state_code);

CREATE TABLE reconstruction_reports (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    crash_id        UUID NOT NULL REFERENCES crashes(id) ON DELETE CASCADE,
    title           TEXT,
    received_date   DATE,
    document_id     UUID,                 -- FK added after documents table
    coding_status   coding_status NOT NULL DEFAULT 'PENDING',
    coded_by        UUID REFERENCES users(id) ON DELETE SET NULL,
    coded_findings  JSONB,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_recon_crash ON reconstruction_reports(crash_id);

CREATE TABLE eld_files (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    crash_id        UUID NOT NULL REFERENCES crashes(id) ON DELETE CASCADE,
    file_name       TEXT NOT NULL,
    document_id     UUID,                 -- FK added after documents table
    ccfp_code_in_file TEXT,               -- unique CCFP code embedded in ELD comment
    provider        TEXT,
    model           TEXT,
    version         TEXT,
    upload_status   eld_upload_status NOT NULL DEFAULT 'UPLOADED',
    event_count     INT DEFAULT 0,
    uploaded_by     UUID REFERENCES users(id) ON DELETE SET NULL,
    parsed_at       TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_eld_files_crash ON eld_files(crash_id);

CREATE TABLE eld_events (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    eld_file_id     UUID NOT NULL REFERENCES eld_files(id) ON DELETE CASCADE,
    event_sequence  INT NOT NULL,
    event_timestamp TIMESTAMPTZ,
    duty            duty_status,
    event_type      TEXT,
    location        TEXT,
    latitude        NUMERIC(9,6),
    longitude       NUMERIC(9,6),
    miles_driven    NUMERIC(10,2),
    engine_hours    NUMERIC(10,2),
    ignition_status TEXT,
    raw             JSONB,
    UNIQUE (eld_file_id, event_sequence)
);
CREATE INDEX idx_eld_events_file ON eld_events(eld_file_id);

-- Generic raw source-record registry with provenance for any ingested system.
CREATE TABLE source_records (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    crash_id        UUID NOT NULL REFERENCES crashes(id) ON DELETE CASCADE,
    source_system   TEXT NOT NULL,        -- SafeSpect, MCMIS, KS-CRASH, eRODS, ...
    source_type     TEXT NOT NULL,        -- INSPECTION | PCR | ELD | RECON | INTERVIEW
    external_id     TEXT,
    raw_zone_uri    TEXT,                 -- pointer into Data Lake Raw Zone
    provenance_note TEXT,
    received_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_source_records_crash ON source_records(crash_id);
CREATE INDEX idx_source_records_system ON source_records(source_system);

-- =============================================================================
-- 7. Mapping / canonical aggregated values
-- =============================================================================
CREATE TABLE crash_attribute_values (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    crash_id        UUID NOT NULL REFERENCES crashes(id) ON DELETE CASCADE,
    attribute_id    UUID NOT NULL REFERENCES data_attributes(id) ON DELETE RESTRICT,
    value_text      TEXT,
    value_json      JSONB,
    source_record_id UUID REFERENCES source_records(id) ON DELETE SET NULL,
    source_system   TEXT,
    confidence      NUMERIC(5,2) CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 100)),
    is_current      BOOLEAN NOT NULL DEFAULT TRUE,
    is_edited       BOOLEAN NOT NULL DEFAULT FALSE,
    edited_by       UUID REFERENCES users(id) ON DELETE SET NULL,
    edited_at       TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_cav_crash ON crash_attribute_values(crash_id);
CREATE INDEX idx_cav_attribute ON crash_attribute_values(attribute_id);
-- One current canonical value per (crash, attribute).
CREATE UNIQUE INDEX uq_cav_current ON crash_attribute_values(crash_id, attribute_id)
    WHERE is_current;

-- =============================================================================
-- 8. Quality control & completeness
-- =============================================================================
CREATE TABLE data_quality_rules (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    code            TEXT NOT NULL UNIQUE,
    name            TEXT NOT NULL,
    rule_type       TEXT NOT NULL,        -- MISSING | FORMAT | COMPLIANCE | CROSS_FIELD
    attribute_id    UUID REFERENCES data_attributes(id) ON DELETE SET NULL,
    severity        rule_severity NOT NULL DEFAULT 'WARNING',
    definition      JSONB,
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE data_quality_results (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    crash_id        UUID NOT NULL REFERENCES crashes(id) ON DELETE CASCADE,
    rule_id         UUID NOT NULL REFERENCES data_quality_rules(id) ON DELETE CASCADE,
    attribute_id    UUID REFERENCES data_attributes(id) ON DELETE SET NULL,
    status          qc_result_status NOT NULL DEFAULT 'NOT_EVALUATED',
    message         TEXT,
    evaluated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_dqr_crash ON data_quality_results(crash_id);
CREATE INDEX idx_dqr_rule ON data_quality_results(rule_id);
CREATE INDEX idx_dqr_status ON data_quality_results(status);

CREATE TABLE completeness_rules (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    study_id        UUID NOT NULL REFERENCES studies(id) ON DELETE CASCADE,
    name            TEXT NOT NULL,
    description     TEXT,
    definition      JSONB,                -- required sections/attributes for completeness
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_completeness_rules_study ON completeness_rules(study_id);

-- Append-only completeness status with history; is_current flags the latest.
CREATE TABLE crash_completeness_status (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    crash_id        UUID NOT NULL REFERENCES crashes(id) ON DELETE CASCADE,
    status          completeness_status NOT NULL DEFAULT 'INCOMPLETE',
    is_current      BOOLEAN NOT NULL DEFAULT TRUE,
    is_locked       BOOLEAN NOT NULL DEFAULT FALSE,
    missing_summary JSONB,
    changed_by      UUID REFERENCES users(id) ON DELETE SET NULL,
    changed_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_ccs_crash ON crash_completeness_status(crash_id);
CREATE UNIQUE INDEX uq_ccs_current ON crash_completeness_status(crash_id) WHERE is_current;

CREATE TABLE contributing_factor_selections (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    crash_id        UUID NOT NULL REFERENCES crashes(id) ON DELETE CASCADE,
    factor_group_id UUID REFERENCES ref_contributing_factor_groups(id) ON DELETE SET NULL,
    factor_value    TEXT NOT NULL,
    rank            INT NOT NULL CHECK (rank BETWEEN 1 AND 3),
    selected_by     UUID REFERENCES users(id) ON DELETE SET NULL,
    selected_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (crash_id, rank)
);
CREATE INDEX idx_cfs_crash ON contributing_factor_selections(crash_id);

-- Per-state PCR coverage tracking (documentation §8.5 / §19.3).
CREATE TABLE state_pcr_coverage (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    study_id          UUID NOT NULL REFERENCES studies(id) ON DELETE CASCADE,
    state_code        CHAR(2) NOT NULL REFERENCES ref_us_states(code),
    pcr_section_code  TEXT NOT NULL REFERENCES ref_pcr_sections(code),
    required_collected INT NOT NULL DEFAULT 0,
    total_required     INT NOT NULL DEFAULT 0,
    optional_collected INT NOT NULL DEFAULT 0,
    total_optional     INT NOT NULL DEFAULT 0,
    completion_pct     NUMERIC(5,2) GENERATED ALWAYS AS (
        CASE WHEN total_required > 0
             THEN round(required_collected * 100.0 / total_required, 2)
             ELSE 0 END
    ) STORED,
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (study_id, state_code, pcr_section_code)
);

-- =============================================================================
-- 9. Documents, reports, audit, notifications
-- =============================================================================
CREATE TABLE documents (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    crash_id        UUID REFERENCES crashes(id) ON DELETE CASCADE,
    doc_type        document_type NOT NULL DEFAULT 'DOCUMENT',
    file_name       TEXT NOT NULL,
    mime_type       TEXT,
    storage_uri     TEXT NOT NULL,        -- object-storage key (signed-URL access)
    size_bytes      BIGINT,
    sensitivity     data_sensitivity NOT NULL DEFAULT 'INTERNAL',
    malware_scan    malware_scan_status NOT NULL DEFAULT 'PENDING',
    uploaded_by     UUID REFERENCES users(id) ON DELETE SET NULL,
    uploaded_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_documents_crash ON documents(crash_id);
CREATE INDEX idx_documents_type ON documents(doc_type);

-- Resolve forward-declared document FKs.
ALTER TABLE reconstruction_reports
    ADD CONSTRAINT fk_recon_document FOREIGN KEY (document_id)
    REFERENCES documents(id) ON DELETE SET NULL;
ALTER TABLE eld_files
    ADD CONSTRAINT fk_eld_document FOREIGN KEY (document_id)
    REFERENCES documents(id) ON DELETE SET NULL;

CREATE TABLE reports (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            TEXT NOT NULL,
    report_type     report_type NOT NULL DEFAULT 'REPORT',
    study_id        UUID REFERENCES studies(id) ON DELETE SET NULL,
    description     TEXT,
    definition      JSONB,
    visibility      report_visibility NOT NULL DEFAULT 'PRIVATE',
    is_published    BOOLEAN NOT NULL DEFAULT FALSE,
    is_deidentified BOOLEAN NOT NULL DEFAULT FALSE,
    owner_id        UUID REFERENCES users(id) ON DELETE SET NULL,
    published_at    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_reports_study ON reports(study_id);
CREATE INDEX idx_reports_visibility ON reports(visibility);

CREATE TABLE report_shares (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    report_id       UUID NOT NULL REFERENCES reports(id) ON DELETE CASCADE,
    shared_with_user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    shared_with_role_id UUID REFERENCES roles(id) ON DELETE CASCADE,
    shared_with_org_id  UUID REFERENCES organizations(id) ON DELETE CASCADE,
    can_download    BOOLEAN NOT NULL DEFAULT FALSE,
    shared_by       UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (shared_with_user_id IS NOT NULL
           OR shared_with_role_id IS NOT NULL
           OR shared_with_org_id IS NOT NULL)
);
CREATE INDEX idx_report_shares_report ON report_shares(report_id);

CREATE TABLE audit_logs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    actor_user_id   UUID REFERENCES users(id) ON DELETE SET NULL,
    action          TEXT NOT NULL,        -- CREATE | UPDATE | DELETE | SUBMIT | LOGIN ...
    entity_type     TEXT NOT NULL,
    entity_id       UUID,
    crash_id        UUID REFERENCES crashes(id) ON DELETE SET NULL,
    before_state    JSONB,
    after_state     JSONB,
    ip_address      INET,
    user_agent      TEXT,
    occurred_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_audit_actor ON audit_logs(actor_user_id);
CREATE INDEX idx_audit_entity ON audit_logs(entity_type, entity_id);
CREATE INDEX idx_audit_crash ON audit_logs(crash_id);
CREATE INDEX idx_audit_occurred ON audit_logs(occurred_at);

CREATE TABLE notifications (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    recipient_user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    notification_type TEXT NOT NULL,      -- NEW_IIF | IN_SCOPE_ROUTING | QC_FAILURE ...
    crash_id        UUID REFERENCES crashes(id) ON DELETE CASCADE,
    title           TEXT NOT NULL,
    message         TEXT,
    channel         TEXT NOT NULL DEFAULT 'IN_APP', -- IN_APP | EMAIL
    status          notification_status NOT NULL DEFAULT 'PENDING',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    read_at         TIMESTAMPTZ
);
CREATE INDEX idx_notifications_recipient ON notifications(recipient_user_id);
CREATE INDEX idx_notifications_status ON notifications(status);
CREATE INDEX idx_notifications_crash ON notifications(crash_id);

-- =============================================================================
-- 10. updated_at triggers
-- =============================================================================
DO $$
DECLARE t TEXT;
BEGIN
    FOR t IN SELECT unnest(ARRAY[
        'organizations','users','studies','study_states','study_parameters',
        'data_attributes','attribute_requirements','crashes',
        'crash_scope_classifications','initial_incident_forms','incident_vehicles',
        'incident_persons','post_crash_inspections','post_crash_investigations',
        'police_crash_reports','reconstruction_reports','eld_files',
        'crash_attribute_values','data_quality_rules','completeness_rules',
        'reports'
    ])
    LOOP
        EXECUTE format(
            'CREATE TRIGGER trg_%1$s_updated_at BEFORE UPDATE ON %1$s '
            'FOR EACH ROW EXECUTE FUNCTION set_updated_at();', t);
    END LOOP;
END $$;
