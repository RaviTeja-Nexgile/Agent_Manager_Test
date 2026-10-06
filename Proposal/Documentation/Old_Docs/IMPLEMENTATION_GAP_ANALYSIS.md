# CCFP IT Solution — Functional Implementation Gap Analysis

**Date:** June 2, 2026
**Scope:** Functional gaps between the source-of-truth specification
([`project_documentation.md`](project_documentation.md)) and the current implementation
(Backend FastAPI + Frontend React), verified against the actual code.
**Status:** Working analysis for sprint planning.

---

## 1. Purpose & Ground Rules

This document lists **only functional gaps that can be closed within the current
technology stack** — no infrastructure changes and no production swaps. Every fix
below is achievable with the software already in use:

- **Frontend:** React, TypeScript, Vite, React Router, Tailwind, Recharts.
- **Backend:** Python FastAPI, Pydantic, SQLAlchemy, PyJWT, FastAPI `BackgroundTasks`.
- **Data store:** PostgreSQL only (also backs analytics, search via SQL, and document
  metadata; uploaded files on local disk).
- **Dev auth:** JWT issued after bcrypt password verification.

**Explicitly out of scope** (and listed in [Appendix A](#appendix-a--items-excluded-as-out-of-scope)
so they are not lost): cloud object storage, real external system adapters/integrations,
external email/SMS delivery, MFA/PIV-CAC/OIDC identity provider, at-rest encryption/KMS,
separate analytical data-lake zones, OpenSearch/Elasticsearch, Celery/Redis, and
load/scalability hardening. These are valid production concerns but require infra or
external systems and are deliberately deferred here.

Each gap states the requirement (with spec §), the current state with **`file:line`
evidence**, and a **fix that stays inside the current stack**. Severities and evidence
were produced by a 13-domain audit with adversarial verification of every finding.

**Legend** — Severity: 🔴 Critical · 🟠 High · 🟡 Medium · ⚪ Low.
Effort: **S** (hours) · **M** (1–3 days) · **L** (1–2 weeks) · **XL** (multi-week).

---

## 2. Summary

**73 functional gaps** in scope: **🔴 3 critical · 🟠 19 high · 🟡 30 medium · ⚪ 21 low.**

| # | Area | 🔴 | 🟠 | 🟡 | ⚪ | Headline |
|---|------|----|----|----|----|----------|
| 1 | Auth / RBAC / Authorization | – | – | 4 | 1 | Org & study scope resolved but not enforced; no login audit |
| 2 | Study Admin & Console | – | 1 | 3 | – | Roles/permissions read-only; completeness vocabulary fixed |
| 3 | Crash Records, Scope & Lifecycle | – | 1 | 2 | 3 | Scope is manual; lifecycle never advances past NOTIFICATION |
| 4 | Initial Incident Form | – | – | 4 | 5 | Missing several mandated §19.1 fields |
| 5 | Post-Crash Investigation/Inspection | 2 | 2 | 2 | 1 | §19.2 inventory is a JSON blob + 5-field form |
| 6 | PCR Mapping & State Coverage | 1 | 2 | 2 | 1 | No State-field→CCFP mapping; coverage read-only & static |
| 7 | Reconstruction & ELD | – | 2 | 1 | 3 | Coded findings never reach attributes; ELD link is faked |
| 8 | Data Management, QC & Completeness | – | 2 | 3 | 1 | Record locking dead; QC rules ignore their definitions |
| 9 | Analytics, Reports & Public Outputs | – | 1 | 5 | 2 | Share/visibility tiers inert; no open-data metadata |
| 10 | Notifications & Routing | – | 5 | 2 | 1 | Only 2 of 8 triggers fire |
| 11 | Search | – | – | 1 | 1 | Metadata-only; columns hardcoded |
| 12 | Federal Compliance (UI/DB) | – | 3 | – | 1 | No .gov banner / OMB number; audit not DB-enforced |
| 13 | Integrations wiring (existing code) | – | – | 1 | 1 | CDLIS adapter present but not called by its QC check |
| | **Total** | **3** | **19** | **30** | **21** | |

### Recommended sequencing

1. **Quick-win wiring (Theme A "stored-but-not-enforced")** — highest value per effort:
   fire the dead notification triggers, enforce record-locking on edit, make report
   sharing/visibility actually grant access, drive QC rules from their `definition`,
   populate provenance lineage. Mostly **S/M** against models that already exist.
2. **Scope & lifecycle engine** — auto-classify qualifying/in-scope/out-of-scope from
   study config and advance `lifecycle_phase` through the workflow (unblocks routing).
3. **Federal compliance quick wins** — `.gov` banner, OMB control number, per-page
   titles, DB-level audit immutability. Small, high audit visibility.
4. **The two big builds** — structured Post-Crash Investigation (§19.2) model + form,
   and the PCR State-field→CCFP mapping interface with live coverage computation.

---

## 3. Functional Gaps by Domain

### 3.1 Authentication, RBAC & Authorization

| ID | Sev | Functional gap (spec §) | Evidence (`file:line`) | Fix within current stack | Effort |
|----|-----|-------------------------|------------------------|--------------------------|--------|
| AUTH-1 | 🟡 | Authorization not enforced by **organization**, though `ORGANIZATION`-scoped assignments exist (§4 l.140, §10.1) | `core/security.py:132-135` collapses non-STATE scope to `unrestricted`; `organization_id` persisted (`admin.py:282-285`) but only used for report share-visibility | Extend `_resolve` to carry `org_ids`; apply an org filter in the relevant feature queries (mirror `scope_crash_query`) | M |
| AUTH-2 | 🟡 | Authorization not enforced by **study / study phase**; `study_ids` resolved but unused (§4 l.140, §10.1) | `core/security.py:136-142` sets `unrestricted=True` for STUDY scope; `study_ids` echoed only in `/auth/me` (`auth.py:93`) | Add a study-scope filter helper; constrain crash/report queries by `current.study_ids` when present | M |
| AUTH-3 | 🟡 | **Federal(PII)/State(NoPII)/Public** access groups not a first-class concept (§4 l.142) | PII keyed off hardcoded `_PII_PERMISSIONS` (`core/security.py:50-56,118-119`); frontend has ad-hoc `STATE_ROLES/FMCSA_ROLES` (`lib/permissions.ts:42-51`); no access-group table | Add an `access_groups` + membership model (PostgreSQL); derive PII/visibility from group membership; expose via `/auth/me` | M |
| AUTH-6 | 🟡 | **Login events not audited** (§10.1 l.447, §14.2) | `auth.py:74-80` sets `last_login_at` and commits with no `record_audit`; `record_audit` import absent | Call existing `record_audit` on successful and failed login (LOGIN/LOGIN_FAILED actions) | S |
| AUTH-8 | ⚪ | Frontend role/access groupings **hardcoded** for Phase-1 (§3.4 configurability) | `lib/permissions.ts:42-67` static arrays; `canViewPii` duplicates backend's 5 PII codes (`:122-130`) | Serve group/sensitivity metadata from the API; derive frontend groupings from it | S |

### 3.2 Study Administration & Admin Console

| ID | Sev | Functional gap (spec §) | Evidence (`file:line`) | Fix within current stack | Effort |
|----|-----|-------------------------|------------------------|--------------------------|--------|
| STUD-1 | 🟠 | **Roles & permissions are read-only** — no create/edit-role, edit-role-permissions, or create-permission API/UI (§4 l.130). *User↔role assignment already works.* | `admin.py:244-259` only GET roles/permissions; `RolesPage.tsx` is a read-only viewer; mappings static in `seeds/0002` | Add `POST/PATCH/DELETE` for roles, `role_permissions`, and permissions; add create/edit UI on `RolesPage` | L |
| STUD-3 | 🟡 | Data-attribute catalog **create/edit has no admin UI** (backend exists) (§8.1, §3.4) | `studies.py:416,439` create/update exist; `endpoints.ts:169-172` define `.create/.update`; `DataAttributesPage.tsx:29-71` is read-only | Wire create/edit dialog on `DataAttributesPage` to the existing endpoints | M |
| STUD-4 | 🟡 | Completeness rules limited to a **fixed 5-token vocabulary**, and thresholds (≥3 factors, ≥1 fatality, inspection-exists) are hardcoded (§3.4, §8.1) | `workers/tasks.py:243-258` builds a fixed `checks` dict; unknown tokens silently unmet; `StudyCompletenessTab.tsx:60` free-text JSON with no validation | Make checks data-driven (token registry + parameterized thresholds read from rule `definition`); validate tokens in the UI builder | M |
| STUD-5 | 🟡 | **No study-level publication settings** (§8.1, §5 Phase 7) | `models.py:179-193` Study has no publication columns; `StudyDetailPage.tsx:14-21` has no publication tab | Add publication-settings columns to `studies` (e.g. de-id policy, public scope) + a Publication tab | M |

### 3.3 Crash Records, Scope & Lifecycle

| ID | Sev | Functional gap (spec §) | Evidence (`file:line`) | Fix within current stack | Effort |
|----|-----|-------------------------|------------------------|--------------------------|--------|
| CRAS-1 | 🟠 | **No automated qualifying / in-scope / out-of-scope classification** from study-configured criteria; scope is purely manual (§3.1, §5 Phase 0/2). *(= STUD-2/STUD-7.)* | `crashes.py:238` inserts blank classification; `:273-287` stores user-supplied flags verbatim; no rule reads `study_parameters` | Add a classification function: read fatality count, vehicle class, participating State, and study qualifying-criteria params → derive scope on create/update | L |
| CRAS-3 | 🟡 | Crash-metadata **edit (PATCH) has backend + API client but no UI** (§8.8, §12.3) | `crashes.py:253-260` `update_crash`; `endpoints.ts:192` `crashApi.update`; no call site in `Frontend/src`; `CrashOverviewTab.tsx:55-71` read-only | Add an edit form on `CrashOverviewTab` calling the existing `crashApi.update` | M |
| CRAS-4 | 🟡 | **Lifecycle phase never advances past NOTIFICATION** — phases 3–7 are dead (§5) | only two assignments: `crashes.py:233` (INITIAL_INCIDENT), `initial_incident.py:162` (NOTIFICATION); later enums never set | Advance `lifecycle_phase` at the right workflow points (source-data added, mapping, QC, completeness, publication) with allowed-transition validation | M |
| CRAS-2 | ⚪ | **Out-of-scope routing not differentiated** — no `OUT_OF_SCOPE_ROUTING` type/branch; `is_supplemental` drives no workflow (§5 Phase 2). *(Analyst IS already notified for all crashes.)* | `initial_incident.py:165-184` emits only NEW_IIF + conditional IN_SCOPE_ROUTING | Add a distinct out-of-scope/supplemental notification type and routing branch | S |
| CRAS-6 | ⚪ | Timeline shows **audit logs only**, not lifecycle transitions as milestones (§12.3) | `crashes.py:411-418` builds entries from `AuditLog` only; `CrashTimelineTab.tsx:27-41` renders generic badges | Emit/merge lifecycle-phase events into the timeline; render a phase rail | M |
| CRAS-7 | ⚪ | CCFP identifier **format hardcodes Phase-1** (year+US-state+seq) and is race-prone (§3.4, §11.3) | `crashes.py:174-181` literal prefix + `COUNT(*)+1` sequence; not study-aware | Make the scheme configurable via `study_parameters`; use a DB sequence/serial to avoid the race | S |

### 3.4 Initial Incident Form

| ID | Sev | Functional gap (spec §) | Evidence (`file:line`) | Fix within current stack | Effort |
|----|-----|-------------------------|------------------------|--------------------------|--------|
| INIT-1 | 🟡 | Person name not captured as **last / first / middle** (§19.1 l.828-830) | `models.py:352` single `full_name`; `CrashInitialIncidentTab.tsx:316` single input | Add `name_last/first/middle` columns + form fields (keep `full_name` derived) | S |
| INIT-2 | 🟡 | **Two phones each with home/cell/work type** not modeled (§19.1) | `models.py:356-358` one shared `phone_type`; UI binds only `phone_primary` (`CrashInitialIncidentTab.tsx:325`) | Add per-number type columns; surface both phones + type selects in `PersonDialog` | S |
| INIT-3 | 🟡 | Non-motorist **occupant-vs-pedestrian indicator** missing (§19.1 l.829) | `enums.py:48-49` PersonType lacks sub-flag; `models.py:344-362` no discriminator | Add a `non_motorist_kind` column + conditional select in the form | S |
| INIT-4 | 🟡 | IIF tab **cannot edit general-info / location fields** after creation (§8.2, §19.1). *(Editable via PATCH /crashes; just no UI on the tab.)* | `IIFIn` exposes only `event_summary` (`initial_incident.py:34-36`); fields edited only in `NewCrashDialog` | Surface the crash general-info/location fields on the IIF tab via `crashApi.update` | M |
| INIT-6 | ⚪ | "Notify State analyst after form is **saved**" fires only on submit (§5 Phase 2) — debatable requirement | notifications only in `submit_iif` (`initial_incident.py:165-184`); `save_iif` does not notify | Optional: emit a draft-saved notification, or confirm submit-time is the intended trigger | S |
| INIT-7 | ⚪ | Delete **business rules minimal** — only blocks ROUTED form; child deletes unguarded (§8.2 l.251) | `initial_incident.py:198-200`; vehicle/person deletes have no status guard (`:240-248,304-313`) | Add status/role guards to IIF and child-record deletes | S |
| INIT-8 | ⚪ | **Supplemental** vehicle/non-motorist/witness groups not surfaced in UI (§19.1 l.832-834) | `is_supplemental` round-trips on backend (`models.py:339,360`) but dialogs omit it (`CrashInitialIncidentTab.tsx:210-219,273-282`) | Add a "supplemental" toggle + grouped display in the UI | S |
| INIT-10 | ⚪ | Submit **DOT-validated flag conflates** "not applicable" vs "failed" for non-CMV crashes (§8.2 l.245) | `initial_incident.py:152-155` empty DOT list → `validated=False` | Distinguish N/A (no CMV) from failed validation (tri-state or null) | S |
| INIT-5 | ⚪ | Crash time **AM/PM indicator** (§19.1 l.825) — *trivial: 24h time already encodes it; presentation-only* | `models.py:268` `Time` column; `NewCrashDialog.tsx:135` `type=time` | Optional: render AM/PM on display. No data change needed | S |

### 3.5 Post-Crash Investigation & Inspection

| ID | Sev | Functional gap (spec §) | Evidence (`file:line`) | Fix within current stack | Effort |
|----|-----|-------------------------|------------------------|--------------------------|--------|
| PCI-1 | 🔴 | **§19.2 field inventory not modeled** — investigation stored as one untyped `sections JSONB` (carrier/power-unit, trailers, driver/license, medical cert, load/cargo, hazmat, HOS, exemptions, vehicle condition, brakes, air-brake axle data, lighting, tires, measurements) | `0001_initial_schema.sql:416-433` (6 header cols + `sections JSONB`); §19.2 only a comment | Design typed PostgreSQL tables/columns + child tables for the documented sections (incremental, section by section) | XL |
| PCI-2 | 🔴 | Investigation **form UI captures only 5 header fields** (§8.4, §19.2) | `CrashSourceDataTab.tsx:118,123,155-161` (5 inputs; payload omits `sections`) | Build a multi-section React form bound to the new structured model (phase the sections) | XL |
| PCI-3 | 🟠 | **Per-field required/optional** configurability for the PCI form absent (§19.2 l.840) | only required/optional store is `attribute_requirements` keyed to `data_attributes`, not PCI fields; no validation in `source_data.py:107-113` | Add a form-field-definition table with per-field required/optional flags; validate on submit | L |
| PCI-4 | 🟠 | **Per-seating-position seatbelt/airbag and per-axle/per-tire/trailer repeating structures** not supported (§19.2 l.842-850) | no positional tables; `0001_initial_schema.sql:416-433` is the only investigation table | Add child tables (seating positions, axles 1–11, tires, trailers 1–3, towed units) in PostgreSQL + repeatable UI groups | XL |
| PCI-5 | 🟡 | **Optional towed-unit & hazmat pages** not implemented as conditional sections (§19.2 l.840,852) | no conditional-section concept (`source_data.py:107-177`, `CrashSourceDataTab.tsx:113-168`) | Model optional sections + conditional rendering toggles | L |
| PCI-7 | 🟡 | ELD **download status / last-duty-status detail** fields not stored on the file record (§8.4 l.269, §19.2 l.844) | `models.py:444-458` stores only provider/model/version/upload_status | Add ELD summary columns (downloaded, last entry, last duty status, last stop) to `eld_files` | M |
| PCI-6 | ⚪ | §8.3 **7-day inspection upload window** not enforced or surfaced (§8.3 l.255) | `source_data.py:72-81` no date-window check | Compute/flag overdue against `inspection_date` and show an SLA indicator | S |

### 3.6 PCR Mapping & State Coverage

| ID | Sev | Functional gap (spec §) | Evidence (`file:line`) | Fix within current stack | Effort |
|----|-----|-------------------------|------------------------|--------------------------|--------|
| PCR-1 | 🔴 | **No State-PCR→CCFP field mapping interface or model** — the core of §8.5 (map a State's existing PCR fields to CCFP attributes without changing the State form) | `models.py:406-421` header-only; `source_data.py:238-248` `/map` only stamps status; `CrashSourceDataTab.tsx:204` posts nothing | Add a `pcr_field_mapping` model (State field/position → CCFP attribute code) + a mapping UI; the MMUCC catalog already exists to map against | XL |
| PCR-2 | 🟠 | **State feedback loop absent** — coverage is read-only; no reconcile path (§8.5 l.294) | only `GET /studies/{id}/pcr-coverage` (`studies.py:388-399`); `endpoints.ts:161-162` read-only | Add `POST/PATCH` coverage endpoints + a reconcile workflow (States report what they already collect) and a UI to edit | L |
| PCR-3 | 🟠 | **No per-attribute colour-coded status** (required-collected / required-not-collected / optional-not-collected) (§8.5 l.294) | coverage is section-grain counts only (`models.py:611-630`); dashboard colours whole-section % (`StudyCoverageTab.tsx:22-27`) | Add per-State, per-attribute `is_collected` data + render the three-way colour status per attribute | L |
| PCR-4 | 🟡 | **Two ingestion paths not modeled** as structured concepts (MCMIS round-trip vs direct State connection) — *in-stack part only* (§8.5 l.289-292) | `source_data.py:207-210` free-text `source_repository` default 'MCMIS'; no path enum | Add an `ingestion_path` enum + capture it on PCR records (the live connectors themselves are out of scope) | M |
| PCR-6 | 🟡 | Section coverage counts are **static seed values**, not derived from collected data (§8.5 l.294) | hardcoded counts (`seeds/0003:180-192`); `studies.py:388-399` returns verbatim; no recompute | Recompute `required_collected/total_required` from attribute-collection facts; `completion_pct` already auto-derives | M |
| PCR-5 | ⚪ | Coverage dashboard **omits optional-coverage figures** from the table (§8.5, §19.3) | API carries `optional_collected/total_optional` (`studies.py:163-171`); `StudyCoverageTab.tsx:54-62` renders only required+completion | Add the optional columns to the dashboard table | S |

### 3.7 Reconstruction & ELD

| ID | Sev | Functional gap (spec §) | Evidence (`file:line`) | Fix within current stack | Effort |
|----|-----|-------------------------|------------------------|--------------------------|--------|
| RECO-1 | 🟠 | Reconstruction **findings never coded into CCFP attributes** (§8.6) | `source_data.py:300-311` writes free-JSON `coded_findings` only; never creates `CrashAttributeValue` | Make the coding action write `crash_attribute_values` (with provenance); replace raw-JSON input with an attribute picker | L |
| RECO-2 | 🟠 | ELD CSV→crash link via **Output File Comment code is faked**, not parsed/validated (§8.7 l.300-304) | `source_data.py:367` stamps `ccfp_code_in_file = crash.ccfp_identifier`; parser reads no comment (`workers/tasks.py:50-98`); QC check is a tautology (`:151-155,176-177`) | Parse the CCFP code from the CSV's comment/Output-File-Comment; validate it matches the crash; make the QC check real | M |
| RECO-3 | 🟡 | Reconstruction **"upload" accepts no file**; binary lives only in the generic Documents tab (§12.5 l.569, §8.6) | `source_data.py:252-288` JSON-only `add_recon`; dialog never sets `document_id` (`CrashSourceDataTab.tsx:241-245`) | Wire the recon dialog to attach a file via existing local storage and set `document_id` (FK already exists) | M |
| RECO-4 | ⚪ | ELD event **lat/long columns unpopulated** by parser (§8.7, §11.1) | `models.py:479-480` lat/long exist; parser inserts only free-text `location` (`workers/tasks.py:75-88`) | Map lat/long from the CSV when present; include in `EldEventOut` | S |
| RECO-5 | ⚪ | ELD CSV **header/column mapping hardcoded** to one assumed schema (§3.4) | hardcoded `_DUTY_MAP` (`tasks.py:35-40`) and fixed aliases (`:74-85`) | Make the column/duty mapping configurable (per-study/provider mapping table) | M |
| RECO-6 | ⚪ | ELD parse **failure not surfaced** — missing object silently marks the file PARSED with 0 events (FAILED enum exists, never set) | `tasks.py:64-67` `FileNotFoundError → b''` then `:91-92` PARSED; `enums.py:65` FAILED unused | Set `upload_status=FAILED` on parse errors/empty content; surface it in the UI | S |

### 3.8 Data Management, QC & Completeness

| ID | Sev | Functional gap (spec §) | Evidence (`file:line`) | Fix within current stack | Effort |
|----|-----|-------------------------|------------------------|--------------------------|--------|
| DATA-1 | 🟠 | **Record locking is non-functional** — `is_locked` is never set true, and edits don't check it, so "unlock to edit a complete record" is unenforced (§8.8, §12.3). *(= CRAS-5.)* | `workers/tasks.py:267` always `is_locked=False`; `set_attribute`/`update_crash` never read it (`crashes.py:317-340,253-260`) | Set `is_locked=True` on completion; block attribute/metadata edits when locked unless unlocked | M |
| DATA-2 | 🟠 | **Configurable QC rule engine ignores rule definitions** — evaluators switch on hardcoded codes; admin-created rules return `NOT_EVALUATED` (§5 Phase 5, §8.8) | `workers/tasks.py:157-180` literal-code switch; `rule.definition` never read; create/update accept an unused `definition` (`data_management.py:40-97`) | Interpret `rule.definition` (e.g. `{pattern}`, `{required_attr}`, `{source}`) generically so configured rules actually run | L |
| DATA-3 | 🟡 | **No UI to view raw source data** from all source systems (backend exists) (§8.8 l.310, §12.3 l.547) | `data_management.py:101-137` + `crashes.py:421-424` exist; `endpoints.ts:289-296` wrappers unused | Add a "Raw / Aggregated" view on the crash Source-Data tab calling the existing endpoints | M |
| DATA-5 | 🟡 | **Source-record lineage not populated** on aggregated/edited attribute values (§11.3 l.505, §5 Phase 4) | `models.py:516-518` `source_record_id` FK exists; `set_attribute` writes only `source_system` text (`crashes.py:327-331`) | Populate `source_record_id` on attribute writes; add it to `AttributeValueIn` and the aggregation path | M |
| DATA-7 | 🟡 | Top-three contributing factor uses **free-text**, not a structured per-group value catalog (§5 Phase 6 l.174-176) | `CrashFactorsTab.tsx:87-90` free Input; `FactorIn.factor_value` unconstrained (`data_management.py:142-144`); no per-group value catalog | Add a per-group factor-value catalog (PostgreSQL ref table) + dropdown; optionally surface PCR-section context | M |
| DATA-6 | ⚪ | Attribute **version history retained but not viewable** — no history/diff endpoint or UI (§8.8 l.316) | history kept via `is_current=False` (`crashes.py:322-326`); `get_attributes` returns current only (`:297`) | Add a history endpoint (include superseded rows) + a per-attribute history/diff view | M |

### 3.9 Analytics, Reports & Public Outputs

| ID | Sev | Functional gap (spec §) | Evidence (`file:line`) | Fix within current stack | Effort |
|----|-----|-------------------------|------------------------|--------------------------|--------|
| ANAL-3 | 🟠 | **Role-based report sharing grants no visibility** — share dialog offers only role shares, but the visibility filter matches only user-id/org-id shares (§8.9, Phase-6) | `reports.py:139-149` stores `shared_with_role_id`; `_visible_filter` (`:69-75`) ignores it; `ReportsPage.tsx:200-228` role-only dialog | Add role-id matching to `_visible_filter` (join the caller's roles) | M |
| ANAL-12 | 🟡 | Report visibility tiers **FEDERAL / STATE are inert** — offered in UI, never matched server-side (§3 l.180, §8.9) | `_visible_filter` (`reports.py:64-76`) only matches owner/published/ORGANIZATION/shares; FEDERAL/STATE never matched | Implement FEDERAL/STATE visibility matching against caller role/scope | M |
| ANAL-4 | 🟡 | Per-share **`can_download` not enforced** (§8.9 l.326, Phase-6) | persisted (`reports.py:61,149`) but `download_report` checks only the global permission (`:171-180`) | Check `ReportShare.can_download` for the caller in `download_report` | M |
| ANAL-6 | 🟡 | Ad-hoc query is **four canned aggregations**, no query builder (§8.9 l.322-324, Phase-6) | `analytics.py:21-26` 4 fixed `ALLOWED_QUERIES`; report `definition` never executed | Build a constrained query builder (field/filter/aggregation selection over whitelisted columns) — keep whitelisting for safety | L |
| ANAL-7 | 🟡 | **Dashboards/visualizations/tables can't be composed** — `report_type` is a label only (§8.9 l.324, Phase-6) | `analytics.py:40-43` filters by `report_type=='DASHBOARD'`; no panel/definition builder/renderer | Define a dashboard/panel schema in `report.definition` + a Recharts-based renderer | L |
| ANAL-9 | 🟡 | Published outputs carry **no open-data metadata** (§14.1 l.644, Phase-7) | `PublicReportOut` exposes only basic fields (`public.py:23-30`); no catalog route | Add metadata fields (license, keywords, publisher, contact, cadence) + a `data.json`-style catalog endpoint | M |
| ANAL-5 | ⚪ | Single-report **GET bypasses visibility/share scoping** (still requires `report:read`) (§8.9) | `get_report` (`reports.py:107-109`) returns without `_visible_filter`; `list_reports` applies it | Apply `_visible_filter` (or an explicit access check) in `get_report` | S |
| ANAL-10 | ⚪ | Download produces a **JSON echo of the definition**, not a rendered artifact (§8.9 l.326, Phase-6) | `download_report` returns `{...,definition}` (`reports.py:171-180`); FE wraps as Blob | Render reports/tables to CSV (in-app, no new infra); add a public download route | M |

> **Cross-ref:** report publish/share **notifications** are tracked under **NOTI-6** (§3.10).

### 3.10 Notifications & Routing

Only 2 of the 8 §8.11 triggers fire today (both in `submit_iif`); the rest exist only as
seed rows. The model, helper (`core/notifications.py`), read/mark-read API, and inbox/bell
UI are complete — these are pure trigger-wiring gaps.

| ID | Sev | Functional gap (spec §) | Evidence (`file:line`) | Fix within current stack | Effort |
|----|-----|-------------------------|------------------------|--------------------------|--------|
| NOTI-1 | 🟠 | **Out-of-scope routing not differentiated** — `OUT_OF_SCOPE_ROUTING` never emitted (§8.11 l.339, §5 Phase 2) | `initial_incident.py:164-184` emits only NEW_IIF + conditional IN_SCOPE_ROUTING | Add the out-of-scope/supplemental notification branch on submit | S |
| NOTI-2 | 🟠 | **QC-failure notifications never generated** (§8.11 l.342) | `workers/tasks.py:122-200` writes results only; no `create_notification` | Emit a QC_FAILURE notification when evaluation produces failures | M |
| NOTI-3 | 🟠 | **Completed-record status-change notifications never generated** (§8.11 l.343) | `workers/tasks.py:206-275` writes status, no notification | Emit COMPLETENESS_CHANGE on COMPLETE/INCOMPLETE transitions | M |
| NOTI-5 | 🟠 | **Crashes-missing-IIF has no detector** within 24–48h (§8.11 l.341) | only the per-crash `DQ_MISSING_IIF` QC check (`tasks.py:158`); no scan | Add an in-process detector: an admin-triggered/opportunistic scan query (no external scheduler) that flags crashes past the window and notifies | L |
| NOTI-6 | 🟠 | **Report publication / sharing notifications never generated** (§8.11 l.344). *(= ANAL-8.)* | `reports.py:135-168` audit-only; no `create_notification` | Call the existing `create_notification` helper in `share_report`/`publish_report` | M |
| NOTI-4 | 🟡 | **Missing-required-data notifications never generated** (§8.11 l.340) | `tasks.py:167-169` records a QC result only | Emit MISSING_DATA to the responsible analyst when required attributes are missing | M |
| NOTI-7 | 🟡 | BTS in-scope routing **silently skipped when scope is absent/undetermined** at submit; no re-trigger when scope is set later (§8.11 l.338, §5 Phase 2) | `initial_incident.py:174-176`; `set_scope` (`crashes.py:273-287`) only audits | Re-trigger BTS routing when scope is set to IN_SCOPE after submit | M |
| NOTI-9 | ⚪ | Notification types are **free-text**, not a configurable catalog (§3.4, §11.1) | `models.py:724` `Text` column; literals hardcoded (`initial_incident.py:168,179`) | Introduce a `NotificationType` enum / catalog table; reference it from emitters | M |

### 3.11 Search

| ID | Sev | Functional gap (spec §) | Evidence (`file:line`) | Fix within current stack | Effort |
|----|-----|-------------------------|------------------------|--------------------------|--------|
| SEAR-2 | 🟡 | **Metadata-only substring search**; no full-text / unstructured content search (§9.2 l.395, §15 l.674) | ILIKE on a few columns (`search.py:46,51,57,64,71,75`); `documents` has no content column | Use **PostgreSQL native full-text** (`to_tsvector`/`pg_trgm`, no new infra); broaden searched columns; add extracted-text column for documents where feasible | M |
| SEAR-3 | ⚪ | Searchable entities/columns **hardcoded**, not configurable per study/phase (§3.4, §15 l.670) | `search.py:22` constant set; fixed per-entity branches (`:49-78`) | Drive the searchable entity/column set from configuration/attribute metadata | M |

### 3.12 Federal Compliance (UI / DB, in-stack)

| ID | Sev | Functional gap (spec §) | Evidence (`file:line`) | Fix within current stack | Effort |
|----|-----|-------------------------|------------------------|--------------------------|--------|
| COMP-1 | 🟠 | **No .gov government banner** ("An official website of the United States government") (§14.1). *(= ANAL-2 / DB-C-1.)* | none in `Frontend/src`; `AppShell.tsx:114-142` no banner; `index.html` no banner markup | Add a USWDS-style banner component to the app shell + public pages | S |
| COMP-2 | 🟠 | **No OMB/PRA control number** displayed before public information collection (§14.1). *(= ANAL-1 / DB-C-2.)* | no OMB text anywhere in `Frontend/src`; `PublicOutputsPage.tsx` has no notice | Render the OMB control number / PRA language on public + collection surfaces (config-driven string) | S |
| COMP-3 | 🟠 | **Audit-log immutability is application-level only** — no DB enforcement (§14.2, §11.1) | `audit_logs` has no REVOKE/rule/trigger (`0001_initial_schema.sql:687-703`); app connects as owner | Add a PostgreSQL-native rule/trigger to block UPDATE/DELETE on `audit_logs` (or REVOKE on a dedicated role) | M |
| COMP-4 | ⚪ | **No per-page descriptive titles** — one static `<title>` for all routes (§14.1) | `index.html:8` single title; no `document.title` updates | Add a `useDocumentTitle` hook / per-route titles | S |

### 3.13 Integrations Wiring (existing code only)

> Real external connectors are out of scope (Appendix A). These two items only wire
> software that already exists in the codebase.

| ID | Sev | Functional gap (spec §) | Evidence (`file:line`) | Fix within current stack | Effort |
|----|-----|-------------------------|------------------------|--------------------------|--------|
| INTE-2 | 🟡 | **CDLIS QC check doesn't call the existing CDLIS adapter** — `DQ_CDLIS_CHECK` only checks a driver row exists (§10.1 l.439) | `workers/tasks.py:173-175`; `cdlis.verify_driver` reachable only via manual endpoint (`integrations.py:44`) | Have the QC rule call the already-present `cdlis` adapter (stays mock until a live client is configured) | M |
| INTE-8 | ⚪ | Existing **CDLIS/MCMIS lookup endpoints not surfaced in the UI** (dead client code) (§13) | `IntegrationsPage.tsx:22,28-31` calls only `list()`+`validateDot()`; `endpoints.ts:383-386` `verifyCdlis`/`lookupMcmis` unused | Add UI controls on the Integrations page for the existing lookup endpoints | S |

---

## Appendix A — Items Excluded as Out of Scope

These are **real gaps from the full audit** but require infrastructure, external systems,
or production swaps, so they are **intentionally excluded** from the functional backlog
above (per the agreed ground rules). Recorded here so nothing is lost.

| Excluded item | Reason out of scope |
|---------------|---------------------|
| MFA / PIV-CAC enforcement; production OIDC identity provider (AUTH-4/5, DB-C-6) | External identity provider / production auth swap |
| Real external adapters for 13 of 17 sources — ACE, DataQs, DIR, DACH, DSMS, SMS, TPR, HPMS/MIRE, Google, NHTSA Recalls, HRRR, live State repos, BTS secure DB (INTE-1,3,4,5,6,7,9) | External system integrations |
| SafeSpect/COTS automated **inspection-data ingestion** (PCI-8) | External adapter (manual entry already works) |
| "View **BTS-shared data**" interface (DATA-4) | Depends on the external BTS secure-DB exchange |
| External **email/SMS notification delivery** (NOTI-8) | External email/messaging service (in-app inbox already works) |
| Separate analytical **data-lake zones** (raw/mapped/curated/analytical/published) (ANAL-11, DB-C-7) | Storage/infrastructure (single PostgreSQL is the agreed store) |
| **Object storage** + at-rest encryption / KMS (DB-C-5) | Cloud storage / infrastructure (local disk is the agreed store) |
| Malware-scan **service** + async quarantine/retry workflow (DB-C-8) | External scanning service / infrastructure |
| **OpenSearch/Elasticsearch** engine (SEAR-4) | Search infrastructure (in-stack PostgreSQL full-text covered by SEAR-2) |
| External / legacy **FMCSA system search** (SEAR-1) | External system integrations |
| **1,000-concurrent / 24-7 / horizontal-scaling** hardening; Celery/Redis (DB-C-10) | Infrastructure / NFR |
| Privacy Act (PTA/PIA/SORN) & NARA **records-retention** controls (DB-C-9) | Largely legal/process artifacts (excluded per request) |

---

*Generated from a 13-domain spec-vs-code audit with adversarial verification of every
finding. Severities and `file:line` evidence reflect the verified results. IDs are stable
for traceability back to the audit.*
