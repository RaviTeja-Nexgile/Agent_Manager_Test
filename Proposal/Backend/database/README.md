# CCFP Database — Schema, Migrations & Seed Data

This directory contains the PostgreSQL schema, migrations, and synthetic seed
data for the CCFP IT Solution (Phase 1 Heavy-Duty Truck Study). It is derived
directly from `Proposal/Documentation/project_documentation.md` (§4, §5, §8,
§11, §12, §19) and the conventions in `Proposal/CLAUDE.md`.

## Layout

```
database/
  migrate.py                 # dependency-light runner (psycopg2 only)
  migrations/
    0001_initial_schema.sql  # enums, tables, FKs, indexes, constraints, triggers
  seeds/
    0001_reference_data.sql      # US states, PCR sections, contributing-factor groups
    0002_rbac_orgs_users.sql     # roles, permissions, orgs, synthetic users, assignments
    0003_study_attributes_rules.sql  # studies, params, PCR attribute catalog, QC/completeness rules
    0004_demo_crashes.sql        # synthetic end-to-end demo crash records
```

## Connection string

The connection string is **always read from `Proposal/CLAUDE.md`** (or the
`DATABASE_URL` environment variable if explicitly set). It is never hardcoded in
this directory. See the "Database Configuration" section of `CLAUDE.md`.

## Usage

Requires Python 3 with `psycopg2`.

```bash
cd Proposal/Backend/database

python migrate.py status     # list applied / pending files
python migrate.py migrate    # apply schema migrations only
python migrate.py seed       # apply seed files only
python migrate.py up         # apply migrations then seeds (default)
```

Every `.sql` file is applied exactly once and tracked in the
`ccfp_schema_migrations` table; each file runs inside its own transaction. The
seeds are idempotent (`ON CONFLICT DO NOTHING`) so re-running is safe.

## Schema overview (38 tables, 23 enum types)

| Area | Tables |
|------|--------|
| Reference | `ref_us_states`, `ref_pcr_sections`, `ref_contributing_factor_groups`, `ref_external_systems` |
| Identity & Access | `organizations`, `users`, `roles`, `permissions`, `role_permissions`, `user_role_assignments` |
| Study config | `studies`, `study_states`, `study_parameters`, `data_attributes`, `attribute_requirements` |
| Crash core | `crashes`, `crash_scope_classifications`, `initial_incident_forms`, `incident_vehicles`, `incident_persons` |
| Source data | `post_crash_inspections`, `post_crash_investigations`, `police_crash_reports`, `reconstruction_reports`, `eld_files`, `eld_events`, `source_records`, `crash_external_links` |
| Mapping / QC / completeness | `crash_attribute_values`, `data_quality_rules`, `data_quality_results`, `completeness_rules`, `crash_completeness_status`, `contributing_factor_selections`, `state_pcr_coverage` |
| Documents / reports / audit | `documents`, `reports`, `report_shares`, `audit_logs`, `notifications` |

Key design points:

- UUID primary keys (`gen_random_uuid()`), `created_at`/`updated_at` with an
  `updated_at` trigger.
- Crash-owned child rows cascade on crash delete; reference FKs restrict.
- The stable **CCFP identifier** is `crashes.ccfp_identifier` (unique).
- Source provenance via `source_records` + `crash_attribute_values.source_*`.
- **CCFP Aggregated Data** = those CCFP-collected sources plus
  `crash_external_links` to the Appendix D systems in `ref_external_systems`.
  Unlinking is append-only (`is_current = FALSE`), so linkage history survives
  and `uq_cel_current` still allows a later re-link.
- Per-study attribute requirements and configurable completeness rules.
- One current canonical value per `(crash, attribute)` and one current
  completeness status per crash (enforced by partial unique indexes).
- PII/CIPSEA/sensitive data tagged via `data_sensitivity` on attributes,
  documents, and reports.

## ⚠️ Seed data is 100% synthetic

All seeded users, names, emails, addresses, phone numbers, carriers, USDOT
numbers, VINs, license plates, and crash records are **fictitious** and exist
only for development, testing, and demonstration. Emails use a fictitious
`@ccfp.gov` domain (not deliverable addresses). No real PII or
production data is included. Do not load this seed data into a production
environment.

### What is seeded

- 54 US states/territories, 8 MMUCC PCR sections, 7 BRD contributing-factor groups.
- 12 roles + 42 permissions with role→permission mappings.
- 12 organizations and 15 synthetic users covering every role.
- 2 studies (Phase 1 active, Phase 2 planning), 5 study-state participations,
  6 study parameters.
- 109 CCFP/PCR data attributes (documentation §19.4) with per-study requirements.
- Kansas PCR coverage summary (documentation §19.3).
- 8 data-quality rules, 5 completeness rules.
- 4 end-to-end demo crashes (KS complete, TX in-collection, CA initial-incident,
  MO out-of-scope supplemental) with vehicles, persons, inspections,
  investigation, PCRs, reconstruction, ELD file + events, source records,
  canonical attribute values, QC results, completeness status, contributing
  factors, documents, notifications, reports, and audit logs.
