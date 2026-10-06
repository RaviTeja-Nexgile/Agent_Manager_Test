-- =============================================================================
-- CCFP IT Solution - Migration 0026: form-label traceability (GAP-PCR-09)
-- =============================================================================
-- Every element on the old KS worksheet carried an MMUCC-aligned code (C01,
-- P18, V19 ...). The application keys `data_attributes.code` on them, and
-- `pcr_field_mapping` maps a State's own field names onto those codes.
--
-- The new HDTS PCR data form has NO codes -- only section headers and field
-- labels. Consequences:
--
--   * The app's codes are now an INTERNAL identifier scheme. That is fine, and
--     they are deliberately retained: they are referenced by
--     crash_attribute_values, attribute_requirements, pcr_field_mapping, and
--     every State mapping already recorded.
--   * But the traceability from "field on the published CCFP PCR form" to
--     `data_attributes.code` became undocumented, and a State mapping its own
--     form has no shared key to map against.
--
-- These columns restore that link by recording the exact header and label text
-- as printed on the form, so the catalog is traceable to the published
-- specification and the data dictionary (item 2 of the gap, which is also the
-- SOO's "Develop a data dictionary" deliverable) can be generated rather than
-- hand-maintained.
--
-- `mmucc_code` records the lineage explicitly instead of leaving it implicit in
-- the internal code, so a future phase can renumber internally without losing
-- the MMUCC provenance.
--
-- Idempotent / additive.
-- =============================================================================

ALTER TABLE data_attributes
    ADD COLUMN IF NOT EXISTS form_section TEXT,
    ADD COLUMN IF NOT EXISTS form_label   TEXT,
    ADD COLUMN IF NOT EXISTS mmucc_code   TEXT;

COMMENT ON COLUMN data_attributes.form_section IS
    'Exact section header text as printed on the HDTS PCR data form (GAP-PCR-09). Traceability to the published specification; pcr_section remains the internal FK.';
COMMENT ON COLUMN data_attributes.form_label IS
    'Exact field label text as printed on the HDTS PCR data form (GAP-PCR-09). The shared key a State uses when mapping its own PCR fields, now that the form carries no codes.';
COMMENT ON COLUMN data_attributes.mmucc_code IS
    'The MMUCC-aligned code this attribute descends from, where one exists. The new form dropped codes entirely, so this records the lineage explicitly rather than relying on data_attributes.code carrying it implicitly.';

CREATE INDEX IF NOT EXISTS idx_data_attributes_form_label
    ON data_attributes(form_label) WHERE form_label IS NOT NULL;
