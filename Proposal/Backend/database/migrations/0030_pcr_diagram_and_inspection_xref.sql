-- =============================================================================
-- CCFP IT Solution - Migration 0030: PCR diagram + inspection cross-reference
--                                    (GAP-PCR-06, GAP-PCR-07)
-- =============================================================================
-- GAP-PCR-06 · the new HDTS PCR data form carries an explicit file upload:
--   "Crash Diagram (UPLOAD DIAGRAM DESIGN FILE)".
-- `documents.crash_id` links a document to the CRASH, not to the police crash
-- report it belongs to, so a diagram could be stored but never attributed to
-- the report it was drawn for — and a crash with two State reports could not
-- say which diagram belonged to which. Adds the PCR linkage and a document type
-- for it.
--
-- GAP-PCR-07 · the new form's Crash section also carries a Post Crash
-- Inspection block (Inspecting Agency Name, Report Number, Inspecting Officer
-- Name, Type, Driver OOS?). Those facts already arrive from SafeSpect in
-- `post_crash_inspections`, so the same fact now has two sources and can
-- silently diverge — precisely what the gap analysis warns about.
--
-- The gap's instruction is to treat the PCR block as a CROSS-REFERENCE, not a
-- second record: the PCR-reported values stay as attributes with
-- `source_system = 'PCR'` (C33-C37, seeded by GAP-PCR-02) and a QC rule flags
-- disagreement. For that comparison to be possible at all, the SafeSpect side
-- needs somewhere to put the two facts it currently cannot represent, so
-- `driver_oos` and `inspection_type` are added here.
--
-- Idempotent / additive.
-- =============================================================================

-- ---------------------------------------------------------------------------
-- GAP-PCR-06 · attribute a document to the police crash report it belongs to.
-- ---------------------------------------------------------------------------
ALTER TABLE documents
    ADD COLUMN IF NOT EXISTS pcr_id UUID REFERENCES police_crash_reports(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_documents_pcr
    ON documents(pcr_id) WHERE pcr_id IS NOT NULL;

COMMENT ON COLUMN documents.pcr_id IS
    'The police crash report this document belongs to (GAP-PCR-06). NULL for documents attached to the crash generally. ON DELETE SET NULL so removing a PCR never destroys the uploaded file record.';

-- The form names the diagram specifically, so it gets its own type rather than
-- being filed as a generic IMAGE — the QC rule and the PCR view both need to
-- find "the diagram" without guessing from the filename.
ALTER TYPE document_type ADD VALUE IF NOT EXISTS 'CRASH_DIAGRAM';

-- ---------------------------------------------------------------------------
-- GAP-PCR-07 · give the SafeSpect-sourced inspection row the two facts the PCR
-- block reports, so the two sources are actually comparable.
-- ---------------------------------------------------------------------------
ALTER TABLE post_crash_inspections
    ADD COLUMN IF NOT EXISTS driver_oos      BOOLEAN,
    ADD COLUMN IF NOT EXISTS inspection_type TEXT;

COMMENT ON COLUMN post_crash_inspections.driver_oos IS
    'Driver placed out of service, as reported by the inspection source (GAP-PCR-07). Compared against the PCR-reported C37 by DQ_PCR_INSPECTION_XREF. NULL = not reported, which is not the same as FALSE.';
COMMENT ON COLUMN post_crash_inspections.inspection_type IS
    'Driver | Vehicle, as reported by the inspection source (GAP-PCR-07). Compared against the PCR-reported C36. Plain TEXT, not an enum, so a later phase can extend the vocabulary without a migration.';
