# CCFP Frontend

Production-ready React web application for the FMCSA **Crash Causal Factors
Program (CCFP)** — Phase 1 Heavy-Duty Truck Study. It implements every screen and
workflow in `Proposal/Documentation/project_documentation.md`, fully wired to the
CCFP FastAPI backend (`Proposal/Backend`), with comprehensive role-based access
control.

## Stack

Vite 5 · React 18 · TypeScript (strict) · React Router 6 · Tailwind CSS 3 ·
Recharts · lucide-react · Public Sans (USWDS/DOT theme). Data layer: a small typed
`fetch` wrapper (`lib/api.ts`) + `useApi` hook + one-function-per-route
`lib/endpoints.ts`. No heavy state/query libraries.

Theme, design tokens, and component patterns mirror the DOT Grants reference
portal (USWDS/DOT federal palette) — appropriate for an FMCSA/DOT application.

## Setup & run

```bash
cd Proposal/Frontend
npm install

# Backend must be running on :8000 (Vite proxies /api → http://127.0.0.1:8000)
cd ../Backend && uvicorn app.main:app --port 8000   # in another shell

cd ../Frontend
npm run dev      # http://localhost:5173
npm run build    # tsc -b + vite build (production bundle)
npm run preview  # serve the production build
```

`VITE_API_BASE` defaults to `/api/v1` (see `.env`).

## Authentication (development)

The backend exposes a **dev mock identity provider**. The login page offers an
email field plus a one-click list of the 15 seeded demo accounts (grouped by
role) so every role can be explored. In production this is replaced by the
DOT-approved OIDC provider (MFA/PIV/CAC). The access token is stored in
`localStorage` (`ccfp.access_token`); `GET /auth/me` hydrates the user's roles,
permissions, and State scope.

## Role-based access control

RBAC is **permission-first**, mirroring the backend's 42 permission codes so the
UI never offers an action the API would reject:

- **`RequirePermission`** guards routes (any-of permission codes / roles) and
  renders an explicit "Access restricted" page on denial.
- **SideNav** items and in-page action buttons are gated by permission.
- **State scope** — State users see only their State's crashes (the list hides
  the State filter and the server enforces the scope).
- **PII / CIPSEA** — the backend redacts restricted fields (`pii_redacted`,
  `redacted`); the UI renders "Restricted" placeholders accordingly.
- **Per-role dashboards** — the dashboard adapts to the user's primary role
  (program / state / CIPSEA / federal / public personas).

## Structure

```
src/
  app/            AppShell (nav + mobile drawer), auth provider, router
  lib/            api, useApi, endpoints (all 88 routes), types, permissions, constants, format, utils
  components/
    ui/           shadcn-style primitives (button, card, dialog, table, tabs, …)
    shell/        TopBar, SideNav, PageHeader, StatTile, status badges, NotificationsBell
    charts/       Recharts chart library (donut, bars, line, gauge, funnel, …)
    dashboards/   shared dashboard widgets
    auth/         RequirePermission
    crash/        crash-specific helpers (DefList)
  pages/
    auth/         LoginPage
    crashes/      list, detail + 9 tabs (overview, initial-incident, source-data,
                  attributes, quality, completeness, contributing-factors, documents, timeline)
    studies/      list, detail + 6 tabs (overview, states, parameters, attribute-requirements,
                  completeness-rules, pcr-coverage)
    admin/        users (+ role assignment), organizations, roles, audit log, admin hub
    analytics/ reports/ public/ notifications/ search/ integrations/ reference/
```

## Coverage (every documented capability)

Crash lifecycle (create → CCFP id → IIF submit with SafeSpect DOT validation +
routing → source data: inspections / investigations / PCR + mapping /
reconstruction coding / ELD upload + parsed events → canonical attributes → QC →
completeness + unlock → top-3 contributing factors → documents → audit timeline);
study configuration (states, parameters, attribute requirements, completeness
rules, PCR coverage); admin (users, role assignment, organizations, roles &
permissions, audit log); analytics dashboards & whitelisted queries; reports
(create, share, publish, download); public de-identified outputs; notifications;
cross-entity search; and external-integration tools (SafeSpect/CDLIS/MCMIS).

## Production notes

Swap the dev IdP for the DOT-approved OIDC provider; tighten CORS to the approved
origin; serve the static `dist/` behind the agency's edge. No secrets live in the
frontend — it talks only to `/api/v1`.
