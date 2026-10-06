-- =============================================================================
-- CCFP IT Solution - Migration 0015: PCI per-field definitions (PCI-3)
-- =============================================================================
-- §19.2 (l.840): the PCI form marks not-required fields in orange (orange =
-- optional) and "the configurable form must support per-field required/optional
-- flags". This is a SEPARATE store from attribute_requirements (which governs
-- the analytic data_attributes catalog, not PCI form fields).
--
-- Keyed by study_id + section_code + field_code so it stays per-study
-- configurable (no Phase-1 hardcoding). field_code values match the structured
-- field/column keys created in PCI-1/4/5 so submit-time validation can look them
-- up directly in the stored sections. Mirrors attribute_requirements.
-- =============================================================================

CREATE TABLE pci_field_definitions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    study_id        UUID NOT NULL REFERENCES studies(id) ON DELETE CASCADE,
    section_code    TEXT NOT NULL,   -- e.g. CARRIER_POWER_UNIT
    field_code      TEXT NOT NULL,   -- matches a structured column/field key from PCI-1/4/5
    label           TEXT,
    is_required     BOOLEAN NOT NULL DEFAULT false,
    is_optional     BOOLEAN NOT NULL DEFAULT true,
    display_order   INT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (study_id, section_code, field_code)
);
CREATE INDEX idx_pci_field_definitions_study ON pci_field_definitions(study_id);

CREATE TRIGGER trg_pci_field_definitions_updated_at BEFORE UPDATE ON pci_field_definitions
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
