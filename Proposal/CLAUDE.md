# CLAUDE.md

Guidance for Claude Code when working in this repository.

## Project Overview

**Crash Causal Factors Program (CCFP) IT Solution** — a scalable FMCSA platform
for collecting, integrating, managing, analyzing, and sharing data about
commercial-motor-vehicle crashes.

**Phase 1 — Heavy-Duty Truck Study:** fatal crashes involving Class 7/8 trucks
(GVWR ≥ 26,001 lbs). The platform ingests data automatically or by manual entry,
consolidates structured and unstructured crash data, identifies complete crash
records, supports quality control and causal-factor
analysis, and publishes role-appropriate outputs (federal, State, BTS, public).
It must stay **configurable for future phases** (medium-duty, buses,
serious-injury, more States/attributes/sources) without a rebuild — avoid
hardcoding Phase 1 assumptions into schemas, rules, or UI.

> Source of truth: [`Documentation/project_documentation.md`](Documentation/project_documentation.md).
> Read it before making design decisions and flag/confirm any deviation. This
> file is a condensed working reference, not a replacement.

## Repository Structure

```
Proposal/
  Documentation/project_documentation.md   # full specification (source of truth)
  Backend/                                  # FastAPI API (see Backend/README.md)
    app/  core/ features/ integrations/ workers/  models.py enums.py main.py
    database/                               # SQL migrations + synthetic seeds
    tests/  requirements.txt
  Frontend/                                 # React + Vite + TS app (see Frontend/README.md)
    src/  app/ components/ lib/ pages/ styles/
```

## Running locally

- **Backend** (from `Backend/`): `python -m uvicorn app.main:app --reload`
  → http://127.0.0.1:8000 (docs `/docs`, health `/health` and `/health/db`).
- **Frontend** (from `Frontend/`): `npm install` then `npm run dev`
  → http://localhost:5173 (Vite proxies `/api` → `127.0.0.1:8000`).
- **Dev auth:** no real IdP yet — `POST /api/v1/auth/login` with a seeded
  email + password issues a JWT (bcrypt-verified against `users.password_hash`).
  Disabled in production via `CCFP_DEV_AUTH_ENABLED=false`, which swaps in the
  DOT-approved OIDC provider (MFA/PIV/CAC).

### Dev login credentials (synthetic — one per role)

All seeded accounts share the password **`Second@123`**. Use these to sign in at
http://localhost:5173/login (handy for browser verification via the Chrome MCP).
State-scoped users only see their State's data.

| Role | Email | Password | Scope |
|------|-------|----------|-------|
| System Administrator | `sysadmin@ccfp.gov` | `Second@123` | — |
| CCFP Project Team Administrator | `avery.thornton@ccfp.gov` | `Second@123` | — |
| CCFP Project Team | `dana.whitfield@ccfp.gov` | `Second@123` | — |
| CCFP Data Scientist | `priya.ramanathan@ccfp.gov` | `Second@123` | — |
| CCFP Database Administrator | `victor.delacruz@ccfp.gov` | `Second@123` | — |
| BTS CIPSEA Agent | `helena.brandt@ccfp.gov` | `Second@123` | — |
| FMCSA CIPSEA Agent | `marcus.ellingsworth@ccfp.gov` | `Second@123` | — |
| Federal User | `omar.haddad@ccfp.gov` | `Second@123` | — |
| MCSAP CMV Inspector | `nora.kowalczyk@ccfp.gov` | `Second@123` | KS |
| State CMV Data Analyst | `elliot.fontaine@ccfp.gov` | `Second@123` | KS |
| State User | `tomasz.bialek@ccfp.gov` | `Second@123` | KS |
| Public User | `public.demo@ccfp.gov` | `Second@123` | — |
| CCFP Super User | `imogen.sandoval@ccfp.gov` | `Second@123` | — |
| FMCSA HQ | `desmond.okafor@ccfp.gov` | `Second@123` | — |
| FMCSA Enforcement | `bernadette.kruse@ccfp.gov` | `Second@123` | — |
| Federal User (NTSB org) | `soren.vasquez@ccfp.gov` | `Second@123` | — |

The last four come from the January 2026 BRD's rewritten authorization model
: the CCFP Super User is an FMCSA Program Office resource,
FMCSA HQ and FMCSA Enforcement are first-class members of the **FMCSA Federal**
audience tier, and the NTSB account exercises the **Other Federal** tier.

Extra State-scoped accounts (same roles, different States) for testing scope
isolation: `rosa.menendez@ccfp.gov` (Inspector, TX),
`grant.holloway@ccfp.gov` (Analyst, TX),
`linh.tran@ccfp.gov` (Analyst, CA). Passwords are seeded by
`Backend/database/seeds/0005_dev_passwords.sql` (and, for the four accounts
above, `0020_authorization_model_rewrite.sql`) — **synthetic / dev only.**

## Database

Transactional DB is **PostgreSQL**. Connection string:

```
postgresql://dot_ccfp_user:7uWYun7kM8XEeVR3@217.217.251.161:8100/dot_ccfp_app
```

> **Access rule:** whenever DB access is needed, **read the connection string
> from this file** rather than hardcoding it elsewhere. In code, load it from a
> single config source (e.g. a `DATABASE_URL` env var seeded from this value).
> Do not commit additional copies of the credentials.

Schema, migrations, and **100% synthetic** seed data live in `Backend/database/`
(PostgreSQL 18; see its `README.md`). Apply with the dependency-light runner:

```bash
cd Backend/database
python migrate.py up        # apply migrations then seeds (idempotent)
python migrate.py status    # list applied / pending
```

Seed identities use a fictitious `@ccfp.gov` domain — synthetic, dev/test/demo
only, never production. (No real PII; emails are not deliverable addresses.)

## Technology Stack

Implemented stack (production swaps in DOT-approved equivalents):

| Layer | Implemented | Production target |
|-------|-------------|-------------------|
| Frontend | React, TypeScript, Vite, React Router, Tailwind, Recharts | DOT-approved design system |
| Backend | Python FastAPI, Pydantic, SQLAlchemy, PyJWT; `BackgroundTasks` for async work | Celery/Redis; DOT-approved OIDC IdP (MFA/PIV/CAC) |
| Data store | **PostgreSQL only** — also backs analytics, search (SQL `ILIKE`), and document metadata (uploaded files go to local disk) | DOT-approved managed PostgreSQL |

## Architecture & Conventions

Three-tier: **React app → FastAPI API & workflow services → PostgreSQL.**
PostgreSQL is the **sole data store** — analytics, search, and document metadata
all live in it (uploaded files are written to local disk). External integration
adapters are currently mocks, and async work runs in-process via FastAPI
`BackgroundTasks`. Frontend ↔ backend over HTTPS/JSON.

- REST, JSON, versioned under `/api/v1/...`.
- All endpoints require auth **except** health checks and public published data
  (`/api/v1/public/...`).
- **Authorization is enforced server-side on every request** by role,
  organization, State, study phase, crash scope, data sensitivity, and
  resource-level permissions.
- State-changing actions write `audit_logs`; lifecycle events create
  `notifications`.
- Data model: one stable **CCFP identifier** per crash; provenance retained on
  every source value; canonical attributes are per-study required/optional/
  read-only; complete-record logic is per-study; PII/CIPSEA data is tagged and
  access-controlled; published outputs are de-identified and separated from
  operational records.

## Key Domain Concepts

- **Qualifying crash (Phase 1):** ≥1 fatality and ≥1 heavy-duty Class 7/8 truck.
- **In-scope:** qualifying crash in a participating State.
  **Out-of-scope:** non-participating State, or a heavy-duty serious-injury crash
  with advanced investigation data.
- **Initial Incident Form:** created within 24–48 h of a crash; creates the CCFP
  crash record and triggers routing/notifications.
- **Lifecycle:** Study Setup → Crash Identification/Initial Incident →
  Notification & Routing → Source Data Collection → Data Mapping & Aggregation →
  QC & Completeness → Analysis & Reporting → Publication & Data Sharing.

## User Roles

MCSAP CMV Inspector, State CMV Data Analyst, CCFP Project Team (+ Administrator),
CCFP Database Administrator, CCFP Data Scientist, BTS CIPSEA Agent, FMCSA CIPSEA
Agent, Federal User, State User, Public User, System Administrator.

## Compliance (must-haves)

Section 508 / WCAG 2.1 AA; `.gov`/`.mil` + federal website standards + OMB/PRA
control numbers; Privacy Act (PTA/PIA/SORN) and NARA records management;
**CIPSEA** protection for BTS interview data; MFA (PIV/CAC for federal);
encryption in transit and at rest; signed-URL object access; immutable audit
logs; least privilege; upload malware scanning; data-sharing agreements before
State onboarding. Targets: 24/7 availability, ≥1,000 concurrent users,
horizontally scalable, mobile-responsive.
