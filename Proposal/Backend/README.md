# CCFP Backend API

FastAPI backend for the FMCSA **Crash Causal Factors Program (CCFP) IT Solution**
— Phase 1 Heavy-Duty Truck Study. Implements every capability described in
`Proposal/Documentation/project_documentation.md` (§4, §5, §8, §10, §12, §13, §14)
on top of the existing PostgreSQL schema (the **source of truth**).

## Layout

```
Backend/
  app/
    main.py              # app assembly: mounts all routers under /api/v1, health, CORS
    enums.py             # string enums mirroring the native PG enum types
    models.py            # SQLAlchemy 2.0 ORM for all 38 tables
    common.py            # shared Pydantic base
    core/                # config, database, security (JWT), permissions (RBAC),
                         #   audit, notifications, storage, pagination, errors
    integrations/        # mock external adapters: SafeSpect, CDLIS, MCMIS, eRODS
    workers/             # ELD parse, QC evaluation, completeness evaluation
    features/            # one router module per domain (see Endpoints below)
  database/              # schema migrations + seed data (see database/README.md)
  tests/                 # pytest + httpx API tests (transaction-rolled-back)
  requirements.txt
  pytest.ini
```

## Setup & run

Dependencies are already available in this environment; otherwise:

```bash
pip install -r Backend/requirements.txt
```

The database connection string is read from `Proposal/CLAUDE.md` (or the
`DATABASE_URL` / `CCFP_DATABASE_URL` environment variable) — never hardcoded.
Ensure the schema + seeds are applied first:

```bash
cd Backend/database && python migrate.py up
```

Run the API (from `Backend/`):

```bash
uvicorn app.main:app --reload
# Interactive docs:    http://127.0.0.1:8000/docs
# OpenAPI schema:      http://127.0.0.1:8000/openapi.json
# Health:              http://127.0.0.1:8000/health/db
```

## Authentication (development)

Auth uses a **mock identity provider** issuing JWTs for the seeded users
(production swaps in the DOT-approved OIDC IdP and disables this via
`CCFP_DEV_AUTH_ENABLED=false`).

```bash
# Get a token for a seeded user (all seeded accounts use the dev password Second@123)
curl -s -X POST localhost:8000/api/v1/auth/login \
     -H 'content-type: application/json' \
     -d '{"email":"elliot.fontaine@ccfp.gov","password":"Second@123"}'

# Use it
curl -s localhost:8000/api/v1/crashes -H "Authorization: Bearer <token>"
```

Representative seeded users (all synthetic): `nora.kowalczyk@ccfp.gov`
(KS MCSAP Inspector), `elliot.fontaine@ccfp.gov` (KS State CMV Analyst),
`dana.whitfield@ccfp.gov` (CCFP Project Team),
`avery.thornton@ccfp.gov` (Project Admin),
`omar.haddad@ccfp.gov` (Federal User), `public.demo@ccfp.gov` (Public).

## Authorization model (§4, §14)

Server-side enforcement on every route. A user's effective permissions are
resolved from `user_role_assignments → roles → role_permissions`. In addition:

- **State scope** — State users see only crashes in their State (`scope_filter`).
- **PII** — names/addresses/phones are masked unless the caller holds a
  data-entry/QC permission.
- **CIPSEA** — BTS-protected data requires `bts:read`.
- **Public** — only published, de-identified, PUBLIC reports are exposed, with no
  authentication, under `/api/v1/public/...`.

All state-changing actions write `audit_logs`; lifecycle events create `notifications`.

## Endpoints (88, mounted under `/api/v1`)

| Module | Coverage |
|--------|----------|
| `auth` | login, me, logout (§12.1) |
| `admin` | users, roles, permissions, organizations, role assignments (§4, §8.1) |
| `studies` | studies, states, parameters, attribute requirements, completeness rules, data-attribute catalog, PCR coverage (§12.2, §8.1, §8.5) |
| `crashes` | CRUD, CCFP identifier, scope, aggregated attributes, QC, completeness, unlock, timeline, sources (§12.3, §5, §8.8) |
| `initial_incident` | IIF save/submit/delete + DOT validation + routing, incident vehicles & persons (§12.4, §8.2, §19.1) |
| `source_data` | inspections, investigations, PCR + mapping, reconstruction, ELD upload + events (§12.5, §8.3–8.7) |
| `data_management` | raw view, **CCFP Aggregated Data** document + Appendix D external-system catalog and crash links, QC rules, contributing-factor groups & selection (§8.8, §5) |
| `analytics` | dashboards, whitelisted parameterized queries (§12.6, §8.9) |
| `analysis_environment` | **CCFP Analysis Environment** — versioned dataset snapshots, refresh-on-open, four-audience shares, export |
| `analysis_statistics` | **statistical analysis** — crash-level cohorts, central tendency/dispersion, distributions, thematic analysis, case-control risk modelling, comparative & trend analysis, saved investigations, Python/R/SAS export |
| `reports` | CRUD, share, publish (de-identified), download (§12.6, §8.9) |
| `public` | published de-identified outputs, no auth (§3, §7, §14) |
| `documents` | upload (malware scan), metadata, signed-URL download (§8, §14) |
| `notifications` | list, mark read (§8.11) |
| `search` | cross-entity search, scope/PII-aware (§8.10) |
| `audit` | audit-log query (§10, §14) |
| `integrations` | SafeSpect / CDLIS / MCMIS adapters + status (§13) |

## Background processing

`app/workers/` runs ELD extraction, QC evaluation, and completeness evaluation
via FastAPI `BackgroundTasks` (also callable synchronously by the `.../evaluate`
and `.../reparse` endpoints). Functions are structured to be Celery-swappable.

`workers/eld_format.py` holds the ELD decode / format-detect / extract logic as
**pure functions** (no session, no I/O), so the same code backs both the
background parse and the synchronous pre-upload validation endpoint. It reads the
sectioned ELD output file defined by 49 CFR 395 Appendix A to Subpart B — the
file a driver transfers to eRODS — as well as a flat hours-of-service CSV mapped
through the configurable `eld_field_mappings` / `eld_duty_code_mappings` rows.
Every decode fallback, unrecognized section, unmappable column, unparseable
value, duplicate sequence number and truncation is recorded in
`eld_parse_issues` with a stable code and a message naming the fix, and the file
always ends `PARSED`, `PARSED_WITH_ERRORS` or `FAILED` — never silently.

Analysis Environment materialization also lives here. `analysis.py` writes the
aggregated dataset rows and `cohorts.py` the crash-level cohort members; both run
in the **same** refresh under one PostgreSQL advisory lock, so the two views of
the environment always share a point in time. `statistics.py` computes the method
families over those snapshots — aggregation in SQL, test statistics in Python —
and `app/core/statsmath.py` supplies the normal, chi-square and Student-t
distributions in pure stdlib `math`, deliberately avoiding a SciPy dependency
that requirements.txt does not declare.

## External integrations

`app/integrations/` provides deterministic **mock** adapters behind stable
interfaces, feature-flagged by `CCFP_INTEGRATION_*_LIVE`. Replace each with a real
client to go live; callers are unaffected.

## Tests

```bash
cd Backend && python -m pytest
```

Each test runs inside a transaction that is rolled back, so the development
database is never mutated. Coverage includes auth, RBAC denials, State scoping,
the full crash lifecycle (create → IIF submit → source data → contributing
factors → QC/completeness), search, and public de-identification.

## Production notes (out of scope here)

Swap the mock IdP for the DOT-approved OIDC provider (MFA/PIV/CAC); replace
local object storage with encrypted cloud storage + real malware scanning;
replace `BackgroundTasks` with Celery/Redis; tighten CORS; and introduce Alembic
for ongoing migrations. No credentials are stored in code — they come from
`CLAUDE.md` / environment.
