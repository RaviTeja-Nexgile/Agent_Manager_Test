# Crash Causal Factors Program (CCFP) IT Solution - Project Documentation

**Document Version:** 2.0
**Last Updated:** August 2026
**Status:** Draft for Review

**Revision note (v2.0) — realignment to the January 2026 specification set.** This
version replaces the September 2025 source baseline with the current documents in
`Documentation/New_Docs`. The substantive changes are:

- **New BRD (January 2026).** The former "Data Management, Analysis, and Sharing"
  section is superseded by two sections — **Data Admin Functionality** and **Data
  Analysis and Sharing** (Manage/Share · Analyze · Visualize). Two new first-class
  concepts are introduced: **CCFP Aggregated Data** and the **CCFP Analysis
  Environment**. New role (**CCFP Super User**), new consumer (**NTSB**), a formal
  four-tier audience taxonomy, refresh cadences, statistical-analysis and
  visualization functional requirements, and three new Appendix D data sources
  (MCMIS, National Registry of Certified Medical Examiners, SafeSpect Inspections).
  The September 30, 2025 / January 2026 delivery sentence was removed.
- **New Statement of Objectives (SOO).** A document with no prior counterpart. It
  adds binding constraints absent from every earlier source: **integration with and
  architectural alignment to FMCSA SafeSpect** (including SafeSpect's role
  hierarchy), an **offline-first** responsive web application, crash-reconstruction
  **file uploads** (narratives, images, videos), **PCR ingestion as a firm
  deliverable**, post-submission **supplemental information**, and the delivery
  schedule, review gates, and A&A/ATO obligations.
- **New PCR data form.** The Kansas readiness worksheet is replaced by the
  State-agnostic **HDTS Police Crash Report (PCR) Data Form** (SOO Attachment C).
  "Dynamic Data Elements" is retired; "Primary Contributing Factors" becomes a form
  section; multi-select caps and repeating groups are now explicit.
- **Collection forms unchanged.** The Initial Incident Form and the Post-Crash
  Investigation Form were verified field-for-field identical to their 2025 versions
  (the PCI form matches at the AcroForm level — 2,190 widgets, 1,633 unique field
  names, identical ordered field list). Sections 8.2, 8.4, 19.1 and 19.2 are
  unchanged and remain in force.

The superseded sources remain in `Documentation/Old_Docs` so any change recorded here can
be traced back to the document it came from.

**Sources (current):** CCFP BRD January 2026; DRAFT Statement of Objectives — CCFP
Reporting and Analysis Solution (25 Aug 2025); HDTS Police Crash Report (PCR) Data
Form; HDTS Initial Incident Form; HDTS Post-Crash Investigation Form (508).
**Superseded sources:** CCFP BRD September 2025; Kansas Sample Study Inclusion — For
States. Retained in `Documentation/Old_Docs` for traceability only.

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Program Background](#2-program-background)
3. [Project Scope](#3-project-scope)
4. [User Roles and Access](#4-user-roles-and-access)
5. [Target Lifecycle](#5-target-lifecycle)
6. [System Architecture](#6-system-architecture)
7. [Technology Stack](#7-technology-stack)
8. [Functional Modules](#8-functional-modules)
9. [Frontend Architecture](#9-frontend-architecture)
10. [Backend Architecture](#10-backend-architecture)
11. [Database and Data Lake Design](#11-database-and-data-lake-design)
12. [API Design](#12-api-design)
13. [External Integrations](#13-external-integrations)
14. [Security, Privacy, and Compliance](#14-security-privacy-and-compliance)
15. [Non-Functional Requirements](#15-non-functional-requirements)
16. [Delivery Schedule and Implementation Roadmap](#16-delivery-schedule-and-implementation-roadmap)
17. [Open Questions and Assumptions](#17-open-questions-and-assumptions)
18. [Appendix A - Source Coverage Matrix](#18-appendix-a---source-coverage-matrix)
19. [Appendix B - Detailed Form and Data Inventory](#19-appendix-b---detailed-form-and-data-inventory)
20. [Appendix C - Acronyms and Glossary](#20-appendix-c---acronyms-and-glossary)

---

## 1. Executive Summary

The Crash Causal Factors Program (CCFP) IT Solution is a scalable FMCSA platform for
collecting, integrating, managing, analyzing, and sharing data about crashes involving
commercial motor vehicles. Phase 1 — referred to in the SOO as the **Heavy-Duty Truck
Study (HDTS)** — focuses on fatal crashes involving Class 7 and Class 8 vehicles, and
establishes the data collection foundation for future studies such as medium-duty
truck, bus, and additional crash-severity phases.

The solution must reduce the burden on States by adapting to their existing
crash-reporting systems and data formats. It must support both automated ingestion and
manual data entry, consolidate structured and unstructured crash information into a
CCFP Data Lake, link that data with records from external systems to form **CCFP
Aggregated Data**, identify complete crash records, support quality control, enable
causal-factor analysis in a **CCFP Analysis Environment**, and publish role-appropriate
outputs for FMCSA federal users, other federal users, participating State users, and
the public.

Per the SOO, the solution is a **CCFP reporting and analysis solution that integrates
with FMCSA's existing SafeSpect platform**, and is delivered as an **offline-first,
responsive web application** so field data collection continues without connectivity.

The project includes four major technical layers:

- **Frontend:** Offline-capable, responsive, role-specific web application for
  incident entry, crash record management, quality control, analytics, dashboards,
  reports, user administration, and public de-identified data access.
- **Backend:** Secure API and services layer for workflow orchestration, validation,
  integrations, notifications, data matching, aggregation, access control, and audit
  logging.
- **Database/Data Lake:** Transactional database plus analytical data lake for crash
  records, form data, source-system extracts, documents, media, ELD files, BTS summary
  data, quality-control results, study configuration, and published outputs.
- **CCFP Analysis Environment:** A distinct tier into which CCFP Aggregated Data and
  summary BTS data are shared on a refresh cadence, where derived data/views are
  created, analyzed, visualized, and shared outward to each audience tier.

---

## 2. Program Background

FMCSA's CCFP is a multi-year, multi-phase data collection and research program intended
to identify the key factors that contribute to crashes involving commercial motor
vehicles. The program supports evidence-based countermeasures, policy decisions,
enforcement planning, and State safety activities.

### 2.1 Statutory Basis

Per the SOO: on December 27, 2020 the Consolidated Appropriations Act, 2021
appropriated **$30 million** to FMCSA to "carry out [a] study of the cause[s] of large
truck crashes." On November 14, 2021 the Infrastructure Investment and Jobs Act (IIJA)
was signed into law; **Section 23006, "Study of Commercial Motor Vehicle Crash
Causation,"** requires the Secretary to "carry out a comprehensive study to determine
the causes of, and contributing factors to, crashes that involve a commercial motor
vehicle," scoped to all CMVs as defined in 49 U.S.C. § 31132. The CCFP is FMCSA's
program to meet that requirement.

The CCFP collects detailed information from a **statistically representative sample of
crashes in selected States**. The newly collected data supplements existing USDOT crash
data and provides carriers, States, federal agencies, and other stakeholders with
enhanced insights for developing policies, technologies, operating practices, and other
methods targeted at reducing CMV crashes.

### 2.2 Phase 1 Definition

Phase 1 is the Heavy-Duty Truck Study (HDTS). A Phase 1 **qualifying crash** is a crash
involving at least one fatality and at least one heavy-duty truck, meaning a Class 7 or
Class 8 vehicle with a GVWR of 26,001 pounds or more. An **in-scope crash** is a
qualifying crash within a participating State jurisdiction. The solution must also
support **out-of-scope** crash records for supplemental analysis, including qualifying
crashes in non-participating States and serious-injury (non-qualifying) heavy-duty truck
crashes from any State that conducted an advanced investigation. For out-of-scope
crashes the program does not collect all CCFP-required data; these records supplement
analysis and provide a baseline for comparison.

Future phases are **dependent on administrative priorities and future funding** (BRD
January 2026, footnote 1). No fixed phase roadmap may be hardcoded.

The CCFP IT Solution exists because required data is spread across many actors and
systems: MCSAP inspectors, State CMV data analysts, State crash repositories,
SafeSpect, MCMIS, PCR systems, post-crash investigation workflows, crash reconstruction
reports, ELD/eRODS files, BTS CIPSEA interview data, FMCSA systems, and external
federal or third-party data sources. The system must bring these inputs into one
controlled environment for analysis and sharing.

---

## 3. Project Scope

### 3.1 Goals

The project will deliver a configurable CCFP IT Solution that:

**Collection and record management**

- Creates and manages crash records using a unique CCFP identifier.
- Supports electronic Initial Incident Form creation within 24-48 hours after a
  qualifying crash.
- Validates U.S. DOT numbers from the Initial Incident Form against SafeSpect.
- Routes new in-scope crash records to State CMV Data Analysts and BTS CIPSEA Agents.
- Routes out-of-scope supplemental crash records to State CMV Data Analysts.
- Notifies specified users **immediately** upon submission of an Initial Incident Form
  (SOO).
- Ingests post-crash inspection data from SafeSpect or approved inspection software.
- Ingests or manually captures post-crash investigation data.
- **Imports/ingests CCFP-required PCR data elements and attributes from States'
  existing PCRs** (SOO), with the primary goal of minimizing data-sharing burden.
- Supports State-specific PCR mapping without forcing States to significantly change
  their forms or formats.
- **Uploads and stores crash reconstruction files — including but not limited to
  narrative reports, images, and videos, in various file formats — and associates them
  with a specific CCFP crash record** (SOO).
- Uploads and parses ELD/eRODS CSV output files against the associated crash record.
- Stores documents, videos, images, forms, structured data, and other crash artifacts.
- **Manages and edits CCFP records, and accepts supplemental information related to a
  CCFP crash post-submission** (SOO).
- Functions and collects data normally **when not connected to the Internet**
  (offline-first, SOO).

**Aggregation, quality, and completeness**

- **Aggregates all relevant data associated with a specific CCFP crash** and links CCFP
  crash data with data from external systems to form **CCFP Aggregated Data**.
- Identifies complete and incomplete crash records against configurable rules.
- Provides quality-control rules for missing data, invalid formats, compliance checks,
  and data-entry issues.
- Provides **data validations for the completeness and accuracy of reports** (SOO).
- Supports CDLIS checks for driver information.
- Generates PCR-derived summaries and prompts State CMV Data Analysts to select the top
  three primary contributing factors.

**Analysis, visualization, and sharing**

- Provides a **CCFP Analysis Environment** for authorized users to view, manage/share,
  analyze, and visualize CCFP Aggregated Data and, as allowable and applicable,
  aggregated BTS data.
- Performs **regular refreshes (daily or hourly)** of CCFP Aggregated Data and summary
  BTS data into the Analysis Environment, and regular refreshes (cadence determined by
  the CCFP Project Team) of data shared with other federal, State, and public users.
- Supports descriptive, exploratory, and statistical analyses — both descriptive and
  inferential.
- Provides visualization including maps, charts, tables, time-series, geospatial
  layers, interactive filters, dashboards, and canned or custom reports.
- Enables authorized users to view, download, and share outputs according to role and
  data-sensitivity rules, with participating State users seeing **only their own
  State's data**.
- Supports public access to summarized, de-identified study data after publication.

**Platform**

- **Integrates with FMCSA's existing SafeSpect platform**, with data architecture and
  business process management aligned to SafeSpect components, and **role-based access
  aligned with the hierarchy of roles established in SafeSpect** (SOO).
- Provides administrative tools for users, roles, study parameters, data attributes
  (including attribute definitions), and complete-record rules.
- Maintains audit logging for record updates and user activity.
- Complies with federal design, accessibility, privacy, records, open data, and domain
  requirements.

### 3.2 Non-Goals

The project does not replace State crash reporting systems, SafeSpect, MCMIS, BTS
secure systems, CDLIS, eRODS, or other authoritative systems. It does not force States
to standardize their PCR processes before participation. It does not expose confidential
BTS respondent data unless a compliant access model is approved. It does not make policy
decisions or automatically determine legal causation; it provides data, analysis tools,
and workflow support for authorized users.

**The analysis and sharing capabilities must not modify original data from CCFP
(SafeSpect) or any other system** (BRD January 2026). The analysis tier is read-only
with respect to ingested source data.

### 3.3 Phase 1 Scope

Phase 1 covers the Heavy-Duty Truck Study:

- Fatal crashes involving Class 7/8 trucks.
- Initial Incident Form.
- Post-crash inspection integration.
- Post-crash investigation form support.
- Crash reconstruction artifact upload, storage, and coding.
- PCR data ingestion, mapping, and coverage tracking.
- ELD/eRODS file upload and extraction.
- BTS notification and integration planning.
- CCFP Data Lake, CCFP Aggregated Data, CCFP Analysis Environment, and the data
  administration interface.
- Offline-capable field data collection.

### 3.4 Future Scope

The solution must be configurable for future CCFP phases, including:

- Medium-duty truck studies.
- Bus studies.
- Serious-injury or other crash-severity studies.
- Additional States.
- Additional crash data attributes.
- Additional external data sources.
- New completeness rules and study parameters.

Because future phases depend on administrative priorities and funding, phase
progression must be a configuration concern, never a schema or code assumption.

---

## 4. User Roles and Access

### 4.1 Operational Roles

| Role | Description | Primary Access |
|------|-------------|----------------|
| **MCSAP CMV Inspector** | Responding inspector or designated officer responsible for the Initial Incident Form and inspection inputs. | Create, read, update, and conditionally delete Initial Incident Forms; upload ELD files; view assigned crash records. Works offline in the field. |
| **State CMV Data Analyst** | State role responsible for coordinating data collection, QC, coding, and State-level analysis. | Read/update incident forms, enter missing data, edit crash records, manage complete/incomplete status, select primary contributing factors. |
| **CCFP Project Team** | FMCSA staff and the U.S. DOT Volpe Center support team as determined by the CCFP FMCSA Project Lead. | Broad read/update access; QC; creates derived data/views in the Analysis Environment; runs analyses; creates and shares dashboards, visualizations, reports, and tables. |
| **CCFP Project Team Administrator** | Administrative role within the CCFP Project Team. | Manage users, groups, roles, interface and data access permissions; study parameters; data attribute settings **including attribute definitions**; completeness rules. |
| **CCFP Database Administrator** | FMCSA CTO resource responsible for data mapping and platform data management. | CRUD for external-to-CCFP attribute mappings; views raw data; **creates CCFP Aggregated Data by linking crash data to external-system records**; **owns outward data sharing** to the Analysis Environment and to every external audience. |
| **CCFP Super User** | FMCSA Program Office resource. *(New in BRD January 2026.)* | Creates and shares dashboards, visualizations, reports, and tables with FMCSA users, other federal users, participating State users, and public users as determined by the CCFP Project Team (CRUD). |
| **CCFP Data Scientist** | Federal analytical role for crash causal-factor research. | Analyze CCFP data and generate models, tables, dashboards, and reports as permitted. |
| **BTS CIPSEA Agent** | BTS role conducting confidential driver, carrier, and witness interviews for in-scope crashes. | Receives in-scope crash notifications; access governed by BTS/CIPSEA rules. |
| **FMCSA CIPSEA Agent** | FMCSA role authorized to view protected BTS data where permitted. | Access depends on BTS agreement and CIPSEA controls. |
| **FMCSA HQ** | FMCSA headquarters consumer. *(Named as a first-class member of the FMCSA Federal tier in BRD January 2026.)* | View/download dashboards, visualizations, reports, and tables (PII where authorized). |
| **FMCSA Enforcement** | FMCSA enforcement consumer. *(Named as a first-class member of the FMCSA Federal tier.)* | View/download dashboards, visualizations, reports, and tables (PII where authorized). |
| **State User** | State enforcement, reconstructionist, investigator, or other State participant. | View/download non-PII outputs; **only their own State's data**. |
| **Public User** | Public consumer of published CCFP outputs. | Read summarized, de-identified published data only. |
| **System Administrator** | Technical operations administrator. | Manage system configuration, environments, audit access, and operational support. |

Authorization must be enforced server-side by role, organization, State, study phase,
crash scope, data sensitivity, and resource-level permissions. Per the SOO, the role
model must **align with the hierarchy of roles established in SafeSpect**, so the role
structure must support hierarchy (parent/child role relationships), not only a flat set
of role codes.

The BRD suggests **leveraging the FMCSA Drug and Alcohol Clearinghouse (DACH) user
permissions model** as a reference architecture.

### 4.2 Audience Tiers

The January 2026 BRD replaces the earlier informal Federal/State/Public grouping with a
formal four-tier taxonomy. These tiers are the addressing model for every sharing
requirement and must be represented explicitly in the authorization model — the two
federal tiers receive data through **different** sharing actions with different
authorization rows, and must not be collapsed into a single "federal" audience.

| Tier | Members | Data rules |
|------|---------|------------|
| **FMCSA Federal Users** | CCFP Project Team; CCFP Database Administrator; FMCSA HQ; FMCSA Enforcement | PII where authorized. |
| **Other Federal Users** | BTS; NHTSA; **NTSB** | PII where authorized; shared by the CCFP Database Administrator. |
| **Participating State Users** | State CMV Data Analysts; MCSAP CMV Inspectors; State Enforcement; State Crash Reconstructionists/Post-Crash Investigators | **No PII. State-specific — only view own data.** |
| **Public Users** | — | **No PII. Summary, de-identified data only.** |

### 4.3 Data Admin Access Rules (BRD January 2026)

| User Requirement | Users | Access |
|---|---|---|
| Manage the mapping and analysis of data attributes coming from external systems to CCFP data attributes | CCFP Database Administrator | Create, Read, Update, Delete |
| Manage data attribute settings: required vs. not required; read-only vs. editable; **attribute definitions**; future attributes for forthcoming phases | CCFP Project Team (Administrator Role) | Read, Update |
| Identify data elements and develop business rules that **define** a "complete" crash | CCFP Project Team (Administrator Role) | Create, Read, Update, Delete |
| Manage users, groups, roles, interface, and data access permissions | CCFP Project Team (Administrator Role) | Create, Read, Update, Delete |
| Define and manage study parameters (qualifying, in-scope, out-of-scope crash settings; study duration) | CCFP Project Team (Administrator Role) | Create, Read, Update, Delete |
| Review and edit data attributes as part of QC | CCFP Project Team; State CMV Data Analyst | Read, Update |
| View and edit a crash record's complete/incomplete status | CCFP Project Team; State CMV Data Analyst | Read, Update |
| View, unlock, and edit a "complete" crash record | CCFP Project Team; State CMV Data Analyst | Read, Update |
| View raw data from all data sources | CCFP Database Administrator; CCFP Project Team | Read |
| **Create CCFP Aggregated Data** by linking raw CCFP crash data and data from external systems associated with a specific crash | CCFP Database Administrator | Create, Update, Read |

### 4.4 Analysis and Sharing Access Rules (BRD January 2026)

**Manage/Share**

| User Requirement | Users | Access |
|---|---|---|
| Share CCFP Aggregated Data and summary BTS data (as allowable and applicable) with the CCFP Project Team via the CCFP Analysis Environment | CCFP Database Administrator | Create, Read, Update, Delete |
| Create new derived data/views of CCFP Aggregated Data and summary BTS data in the CCFP Analysis Environment | CCFP Project Team | Create, Read, Update, Delete |
| Share CCFP Aggregated Data and Analysis Environment data with **Other Federal Users (BTS, NHTSA, NTSB)** | CCFP Database Administrator | Create, Read |
| Share with **participating States** (State-specific, no PII) | CCFP Database Administrator | Create, Read |
| Share with the **Public** (no PII, summary de-identified only) | CCFP Database Administrator | Create, Read |

**Analyze**

| User Requirement | Users | Access |
|---|---|---|
| Run queries and analyze CCFP data stored in the designated Analysis Environment | CCFP Project Team | Create, Read, Update, Delete |
| Conduct descriptive statistics analysis in the designated Analysis Environment | CCFP Project Team | Create, Read, Update, Delete |
| Create statistical summaries (central tendency and dispersion, data distributions, thematic analysis, statistical risk modeling) | CCFP Project Team | Create, Read, Update, Delete |

**Visualize**

| User Requirement | Users | Access |
|---|---|---|
| Create and share dashboards, visualizations, reports, and tables with FMCSA users, other federal users, participating State users, and public users as determined by the CCFP Project Team | CCFP Project Team; **CCFP Super User** | Create, Read, Update, Delete |
| View and download dashboards, visualizations, reports, and tables | FMCSA Users and Other Federal Users (PII); Participating State Users (No PII, **only view own data**); Public Users (No PII, summary de-identified only) | Read |

Further coordination with BTS is needed to determine access requirements for BTS data.

---

## 5. Target Lifecycle

### Phase 0 - Study Setup

CCFP administrators define study parameters: vehicle type, crash severity, participating
States, study start/end dates, qualifying/in-scope/out-of-scope criteria, required
attributes, optional attributes, attribute definitions, and completeness rules.

### Phase 1 - Crash Identification and Initial Incident

A MCSAP CMV Inspector or State-designated user creates the electronic Initial Incident
Form within 24-48 hours after the crash — **including with no network connectivity**,
with queued writes replayed on reconnect. The system assigns a unique CCFP identifier
and captures crash date/time/location, local crash report number, vehicles, drivers,
motor carriers, non-motorists, witnesses, injury/fatality indicators, and a short event
description.

### Phase 2 - Notification and Routing

After the Initial Incident Form is saved, the system **immediately** notifies the State
CMV Data Analyst. For in-scope crashes, it also notifies BTS CIPSEA Agents so the
confidential interview workflow can begin, and the form is routed to the BTS secure
database (subject to the approved BTS access model). Out-of-scope supplemental crashes
are routed only to the State CMV Data Analyst.

### Phase 3 - Source Data Collection

The system receives or captures post-crash inspection data, post-crash investigation
data, crash reconstruction artifacts (narratives, images, videos), PCR data, ELD files,
and other data artifacts. Data may arrive through automated integrations, file uploads,
direct State connections, API submissions, or manual entry.

### Phase 4 - Data Mapping and Aggregation

The system maps State-specific and external source attributes to CCFP attributes, links
all source records to the CCFP crash identifier, and builds the aggregated crash record.
It preserves source provenance so analysts can trace every value back to its origin.

The CCFP Database Administrator **creates CCFP Aggregated Data** by linking raw CCFP
crash data (post-crash inspections, PCRs, post-crash investigations, crash
reconstructions) with data from external systems (SafeSpect Inspections, Drug and
Alcohol Clearinghouse, and the other Appendix D sources) related to that specific crash.

### Phase 5 - Quality Control and Completeness

The system applies configurable quality-control rules, validates formats and
**cardinality** (multi-select caps), checks for missing data, flags crashes missing
Initial Incident Forms, performs compliance checks against authoritative systems, and
determines whether the crash record is complete or incomplete. Validation supports both
completeness **and accuracy** of reports.

Records may be edited post-submission, and **supplemental information** may be attached
to a crash after submission without overwriting the original record.

### Phase 6 - Analysis and Reporting

CCFP Aggregated Data and summary BTS data are refreshed into the **CCFP Analysis
Environment** on a daily or hourly cadence. Within that environment the CCFP Project
Team creates derived data/views, runs queries, conducts descriptive statistics, and
creates statistical summaries — central tendency and dispersion, data distributions,
thematic analysis, and statistical risk modeling (given the availability of a control
population such as non-fatal crashes). The CCFP Project Team and CCFP Super User create
and share dashboards, visualizations, reports, and tables.

The State CMV Data Analyst reviews selected PCR sections and, coordinating with the
State investigation team, selects the top three primary contributing factors. The
PCR-derived contributing-factor prompt must summarize these BRD-specified groups:
contributing circumstances for roadways, vehicles, and non-motorists; driver actions at
the time of crash; driver conditions at the time of crash; driver and non-motorists
distracted by; and non-motorist actions at the time of crash. **Primary Contributing
Factors is also a section of the PCR data form itself**, carrying Primary Contributing
Factor 1, 2, and 3.

### Phase 7 - Publication and Data Sharing

The CCFP Database Administrator shares CCFP Aggregated Data and Analysis Environment
data outward on a cadence determined by the CCFP Project Team: to Other Federal Users
(BTS, NHTSA, NTSB), to participating States (State-specific, no PII), and to the Public
(no PII, summary de-identified only). Published outputs are de-identified and separated
from operational records.

---

## 6. System Architecture

The CCFP IT Solution uses a three-tier application architecture with a distinct
analysis tier, integrated with FMCSA SafeSpect:

```text
Users (offline-capable clients)
  |
  v
Frontend Web Application  ── service worker + local store + sync outbox
  |
  v
Backend API and Workflow Services
  |
  +--> Transactional Database
  +--> CCFP Data Lake / Analytical Store
  |       └── CCFP Aggregated Data (crash data linked to external-system records)
  +--> CCFP Analysis Environment          <-- scheduled refresh from Aggregated Data
  |       ├── derived data / views
  |       ├── analysis + statistical summaries
  |       └── audience-scoped shares (FMCSA Federal / Other Federal / State / Public)
  +--> Object Storage for documents, images, videos, ELD files, and reports
  +--> Integration adapters for SafeSpect, State, FMCSA, BTS, and external systems
  +--> Background workers for ingestion, mapping, validation, notifications,
       scheduled refresh, and report generation
```

The frontend communicates with the backend over HTTPS using JSON APIs, and continues to
function without connectivity by serving a precached application shell, reading from a
local store, and queueing writes for replay. The backend enforces authentication,
authorization, validation, workflow rules, audit logging, and integration processing.
The transactional database manages application state and workflow records. The CCFP Data
Lake stores normalized and source-preserved data for analysis. Object storage contains
large artifacts and generated documents.

**SafeSpect alignment (SOO).** The solution integrates with FMCSA's existing SafeSpect
platform. Data architecture and business process management must align with SafeSpect
components, and role-based access must align with the SafeSpect role hierarchy. An
anti-corruption layer between the SafeSpect identity/role model and the CCFP internal
model is recommended so the internal model remains stable as SafeSpect evolves.

**Analysis Environment separation.** The Analysis Environment is addressed separately
from the Data Lake: data is *shared into* it on a cadence, derived views live *in* it,
and requirements are written against "CCFP Aggregated Data **and** CCFP Analysis
Environment data" as two distinct things that are shared separately. Whether the
environment is implemented inside the platform or as an approved external BI/analytics
service is an open question (Section 17.1) to be settled during SOO Task 2 Discovery.

---

## 7. Technology Stack

The final stack should align with FMCSA/DOT enterprise standards. A practical
implementation stack is:

| Layer | Recommended Technology |
|-------|------------------------|
| Frontend | React, TypeScript, React Router, TanStack Query, React Hook Form, Zod, Tailwind or DOT-approved design system components |
| Offline | Service worker (precached shell, cache-first static assets), local structured store (IndexedDB), sync outbox with idempotent replay |
| Backend | Python FastAPI, Pydantic, SQLAlchemy, Celery or equivalent background workers |
| Transactional Database | PostgreSQL |
| Data Lake / Analytics | Cloud object storage plus analytical warehouse/lakehouse service approved for DOT use |
| Object Storage | Encrypted cloud object storage with versioning; chunked/resumable upload and ranged download for video |
| Search | OpenSearch, Elasticsearch, or approved enterprise search service |
| Queue/Cache/Scheduler | Redis or cloud-native queue, cache, and scheduled-job services |
| Visualization | Embedded BI/dashboard capability or custom React dashboards |
| Authentication | DOT-approved identity provider with MFA/PIV/CAC where applicable; federated with SafeSpect identity |
| Deployment | Containerized services on DOT-approved cloud or hosting platform |
| Infrastructure | Terraform or approved infrastructure-as-code tooling |

### 7.1 Example Supporting Tools (BRD January 2026)

The BRD names example tools for each capability and states that **final tools will be
determined in discovery**. These are illustrative, not mandated:

| Capability | Examples named in the BRD |
|---|---|
| Manage/Share | Database querying tools (e.g., MySQL); data manipulation tools (e.g., Python) |
| Analyze | Statistical summary tools (e.g., Python, SAS, R); data visualization/report builder tools (e.g., Tableau, ArcGIS (Esri), LaTeX) |
| Visualize | Data visualization tools (e.g., Tableau, ArcGIS (Esri)) |

Data must be **exportable** to any statistical summary or visualization/report builder
tool, which constrains the export formats the platform must offer regardless of which
tool is selected.

---

## 8. Functional Modules

### 8.1 Study Administration

Administrators define study phases, participating States, qualifying criteria, in-scope
and out-of-scope rules, study duration, required attributes, optional attributes,
read-only/editable attributes, **attribute definitions**, completeness rules, and
publication settings.

Example study/crash settings from the BRD include: CMV type (heavy-duty truck,
medium-duty truck, bus, etc.); crash type (fatal; severe-injury convenience sample);
crash location (State, county); and study duration (starting/ending date).

### 8.2 Initial Incident Form

*Unchanged from the 2025 form — verified field-for-field identical.*

The electronic Initial Incident Form is developed as part of what the source calls the
CCFP Reporting Module and Database, and is completed by the responding MCSAP CMV
Inspector or designated officer. It supports:

- Local crash report number.
- Crash date and time.
- Number of vehicles and persons involved.
- City, county, State, street, highway, and location details.
- Vehicle records for CMV and non-CMV vehicles.
- U.S. DOT number, vehicle make, occupants, injured occupants, and carrier phone number.
- Driver name, minor indicator, primary language, address, phone numbers, and injury
  status.
- Non-motorist records for occupants and pedestrians.
- Witness names, addresses, and phone numbers.
- Short event summary.
- Supplemental vehicle, non-motorist, and witness entries.
- Save, update, delete according to business rules, and submit workflow.

Per the SOO, this form must be completable **offline** and must notify specified users
**immediately** on submission. Because offline clients replay queued writes, create
operations must be **idempotent** — a replayed submission must not produce a duplicate
record. This matters beyond tidiness: duplicated person records carry injury status, and
fatality counts feed the qualifying-crash rule, so a duplicate can change whether a crash
is in the study at all.

### 8.3 Post-Crash Inspection

The system ingests post-crash inspection data from SafeSpect or approved inspection
software. These records document violations and defects discovered at inspection time and
must be linked to the crash record within the CCFP Data Lake. The MCSAP CMV Inspector
collects this data via SafeSpect or approved commercial off-the-shelf (COTS) software and
uploads it to FMCSA within 7 days of the inspection.

The PCR data form also carries a **Post Crash Inspection** block (inspecting agency name,
report number, inspecting officer name, inspection type of Driver or Vehicle, and Driver
Out of Service indicator). These are PCR-reported values and must be treated as a
cross-reference to the authoritative SafeSpect-sourced inspection record, not as a second
source of truth; disagreement between the two should raise a quality-control finding.

### 8.4 Post-Crash Investigation Form

*Unchanged from the 2025 form — verified identical at the AcroForm field level (2,190
widgets, 1,633 unique field names, identical ordered field list). The only difference in
the reissued PDF is 508 remediation.*

The system supports the Heavy-Duty Truck Study post-crash investigation form and captures
or stores (see Appendix B, 19.2, for the full field-level inventory, including
per-seating-position seat belt/airbag capture and the form's required vs. not-required
field flags):

- Motor carrier and power-unit information.
- Trailer and converter dolly information.
- Driver and license information.
- Medical certificate information.
- Seat belt and airbag information (per seating position).
- Load and cargo information.
- Hazardous material information.
- Driver hours of service.
- ELD provider, model, version, download status, and last duty status details.
- Exemptions and emergency declarations.
- Vehicle condition.
- Brake system and air brake measurements.
- Lighting and reflector information.
- Tire data, axle data, measurements, and remarks.

### 8.5 Police Crash Report Data

The PCR module supports ingestion of CCFP-required PCR data elements from States'
existing PCRs and State-specific mapping to the CCFP attribute model.

**Sections of the HDTS PCR Data Form (January 2026):**

- Crash Data Elements.
- Fatal Data Elements.
- Large Vehicle and Hazardous Material (HM) Data Elements.
- Person Data Elements.
- Vehicle Data Elements.
- Non-Motorist Data Elements.
- Roadway Data Elements.
- **Primary Contributing Factors.**

> **Changed from the prior specification.** "Dynamic Data Elements" and its sole element
> (motor vehicle automated driving systems) are **retired**. "Primary Contributing
> Factors" is **added** as a form section. Section names were reworded ("… Section" → "…
> Data Elements") and reordered. Historical values for retired elements must be preserved
> rather than deleted.

**Structural requirements introduced by the new form:**

- **Repeating groups are explicit.** Trailers repeat by position (1st, 2nd, 3rd behind
  the tractor); the Vehicle section repeats keyed by Vehicle Sequential Number; the
  Person section repeats keyed by Sequential Identifying Number, with an occupant's
  Vehicle Number as the link. The canonical value model must therefore address a value by
  (crash, attribute, unit type, unit number) — not by (crash, attribute) alone.
- **Conditional populations.** Person fields apply to distinct populations: All Persons
  Involved, All Occupants, All Drivers, CMV Drivers, All Drivers and Non-Motorists, and
  All Injured. This is a visibility and validation specification, not merely grouping.
- **Multi-select caps are explicit and must be enforced.** Examples: Light Condition and
  First Harmful Event "check only 1"; Weather Conditions, Roadway Surface Condition,
  Cargo Body Type, Restraint Systems, Location of Damaged Areas, Relation to Junction,
  Non-Motorist Action Prior, Roadway Functional Class "up to 3"; Seating Position, Air Bag
  Deployment Type, Distracted by Action "up to 2"; Drug Test Results, Distracted by
  Source, Traffic Control Signs, Sequence of Events, Vehicle Contributing Circumstances
  "up to 4"; Endorsements, Violations, Traffic Control Signals, Non-Motorist Contributing
  Actions, Non-Motorist Safety Equipment "up to 5"; Roadway Contributing Circumstances,
  Driver Actions, Driver License Restrictions, Condition at Time of Crash "up to 6".
- **Attachments and public-facing text.** The form carries a **Crash Diagram** (upload
  diagram design file) and a **Public Narrative** written for and available to the public
  — deliberately separate from the internal Crash Description so it can be released
  without redaction. The public narrative must be tagged public-releasable; the internal
  description must not be published.
- **No optional tier.** The new form has no optional attribute tier and no per-State
  colour coding — everything shown on it is CCFP-required. The required/optional
  distinction now lives entirely in the platform's per-study attribute configuration.
- **No element codes.** The new form carries no MMUCC element codes. The platform's
  attribute codes become an internal identifier scheme, so each attribute must record its
  form section and form label to stay traceable to the published specification, and the
  data dictionary becomes the shared key for State mapping.

**PCR data reaches CCFP through two paths:**

- **FMCSA crash data:** the PCR is uploaded to the State crash repository, and the MCSAP
  Analyst uploads a subset of that PCR data to FMCSA's SafeSpect Crash Reporting Module
  within 45 days of the crash, after which it becomes available in MCMIS for ingestion
  into the CCFP Data Lake.
- **Direct connection to the State crash repository:** the CCFP Project Team establishes a
  direct connection (CCFP web service or other electronic data-sharing method) so the PCR
  is integrated into the Data Lake without the MCMIS round-trip.

Per the SOO, PCR ingestion is a **firm deliverable**, not an exploration: the solution
must import/ingest CCFP-required PCR data elements and attributes from States' existing
PCRs, with the primary goal of minimizing data-sharing burden to the States. This implies
per-State transform profiles, a preview/dry-run mode, and ingestion run history with row
counts and rejects.

**Per-State coverage.** Coverage of CCFP-required attributes must be tracked per State and
per PCR section. Coverage figures must be derived from the current attribute
configuration rather than stored as fixed counts, and must be stamped with the
specification version they belong to — figures are **not comparable across PCR
specification versions**. States review flagged attributes they do not yet collect and
report attributes they already collect, so per-State coverage status must be correctable
via State feedback.

### 8.6 Reconstruction and Narrative Coding

Crash reconstruction reports are expected 90-120 days after a crash and may be narrative
in nature. Per the SOO, the system must **upload and store crash reconstruction files —
including but not limited to narrative reports, images, and videos, in various file
formats — and associate them with a specific CCFP crash record**. A reconstruction is
therefore a *set* of artifacts, not a single document. The system must also support
review and manual coding of findings into CCFP research attributes.

Handling large media implies chunked/resumable upload, ranged download so video streams
rather than fully buffers, server-side MIME verification, and malware scanning before any
download is permitted.

### 8.7 ELD/eRODS Data

The system supports upload of ELD output files in CSV format and extraction of
hours-of-service data for analysis. Uploaded files must be linked to the associated CCFP
crash record, using a unique CCFP code in the ELD output file comment where available.

Upstream of CCFP ingestion, drivers transfer hours-of-service data via an ELD output file
to eRODS — electronically through a telematics ELD (web service or email) or through a
local ELD (**USB** or Bluetooth). The MCSAP CMV Inspector verifies the file submission at
roadside in eRODS and saves the file locally; if a driver is unable to transfer a file
post-crash, the inspector works with the motor carrier to obtain the ELD output file. For
the Heavy-Duty Truck Study, drivers/motor carriers enter the unique CCFP code as an Output
File Comment when submitting the file (example format:
`CCFP-State-Post-Crash-Inspection-Code`), which the system uses to link the upload to the
correct crash record.

### 8.8 Data Admin Functionality

*Replaces the former "Data Management and Quality Control" section, per BRD January 2026.*

The CCFP IT Solution must be able to manage CCFP data, users, permissions, and study
settings, and must link all CCFP crash data and data from external systems related to a
specific crash. That linked result is **CCFP Aggregated Data**.

**Users:** CCFP Project Team; CCFP Database Administrator (FMCSA CTO resource).

**System requirements:**

- Manage users, roles, permissions, data attribute settings, and study scope settings via
  an administrative functions interface.
- Leverage the FMCSA Drug and Alcohol Clearinghouse user permissions model (suggested).
- Access and view raw data from all data sources.
- **Create CCFP Aggregated Data** by linking raw CCFP crash data and data from external
  systems (SafeSpect Inspections, Drug and Alcohol Clearinghouse, etc.) associated with a
  specific crash.

Supporting capabilities carried forward: reviewing and editing data attributes during QC;
managing complete/incomplete status; unlocking and editing complete crash records;
viewing BTS-shared data where permitted; and tracking every update by user and timestamp.

The external systems available for linkage are the Appendix D sources (Section 13). The
linkable source vocabulary must be configuration-driven so sources can be added — the BRD
notes that some MCMIS information **may shift to Motus or other systems** as FMCSA
modernizes its legacy IT.

### 8.9 Data Analysis and Sharing

*Replaces the former "Analysis, Dashboards, and Reporting" section, per BRD January 2026.*

The CCFP IT Solution must include an **Analysis Environment** for authorized users to
view, manage/share, analyze, and visualize CCFP Aggregated Data and, as allowable and
applicable, aggregated BTS data.

**Core capabilities required:**

- **Manage/Share Data:** view all CCFP Aggregated Data; view data shared by BTS; share
  CCFP Aggregated Data to the CCFP Analysis Environment and with the CCFP Project Team;
  share CCFP Aggregated Data and Analysis Environment data with internal and external
  users; query and create new data/views derived from CCFP Aggregated Data in the Analysis
  Environment; manage the Analysis Environment.
- **Analyze Data:** query, aggregate, analyze, and create new views and reports of CCFP
  Aggregated Data and CCFP Analysis Environment data.
- **Visualize Data:** create visualizations including, but not limited to, maps, charts,
  tables, dashboards, and canned or custom reports of CCFP Aggregated Data, summary BTS
  data (as applicable), and CCFP Analysis Environment data.

**These core capabilities must not modify original data from CCFP (SafeSpect) or any
other system.**

#### 8.9.1 Manage/Share CCFP Data

- Share CCFP Aggregated Data and summary BTS data with the CCFP Project Team and to the
  CCFP Analysis Environment.
- Share CCFP Aggregated Data and Analysis Environment data with FMCSA federal users, other
  federal users, participating State users (no PII, State-specific), and public users (no
  PII, summary de-identified only).
- Perform **regular refreshes (daily or hourly)** of CCFP Aggregated Data and summary BTS
  data into the CCFP Analysis Environment.
- Perform **regular refreshes (cadence determined by the CCFP Project Team)** of CCFP
  Aggregated Data and Analysis Environment data for other federal, participating State,
  and public users.
- Allow the CCFP Project Team to create new data/views derived from CCFP Aggregated Data
  and summary BTS data.
- **Manage the Analysis Environment.**

Refresh must be **time-driven**, not dependent on user activity: an environment with no
traffic must still refresh on its stated cadence.

#### 8.9.2 Analyze CCFP Data

Provide tools supporting descriptive, exploratory, and statistical analyses — both
descriptive and inferential — of data in the CCFP Data Lake and CCFP Analysis
Environment:

- Descriptive statistics and visualization-ready outputs, presenting data "as is" for user
  exploration through maps, charts, and similar.
- Statistical summaries: **central tendency and dispersion, data distributions, thematic
  analysis, and statistical risk modeling** — the last "given the availability of control
  such as non-fatal crashes," which implies the data model must be able to express a
  comparison cohort.

Data must be exportable to any statistical summary or visualization/report builder tool.

#### 8.9.3 Visualize CCFP Data

Provide broad visualization capabilities for internal teams, external partners, and the
public, with appropriate PII controls; support multiple visualization types, handle large
datasets with low performance impact, and enable canned and custom reporting.
Visualization is performed on data shared with users as described in 8.9.1.

**Functional requirements:**

- Low- or no-cost licensing for FMCSA users.
- Support for maps, charts, tables, time-series, **geospatial layers**, and interactive
  filters.
- Multi-user web-based dashboards and **self-service** tools for authorized users.
- Ability to **embed or link dashboards to secure portals and public websites** (with
  appropriate data filters).
- Ability to integrate with and display **large datasets/databases** (the full CCFP data
  set) with minimal performance impact.
- Ability to **create, schedule, and export canned reports**, and allow users to create
  custom ad-hoc reports.
- **Role-based access to data sets** (e.g., State-limited views).

### 8.10 Search

The application must include search across CCFP content and support searching internal and
external FMCSA systems/databases, including legacy systems where integrated.

### 8.11 Notifications

The system sends notifications for:

- New Initial Incident Forms (immediately on submission).
- In-scope crash routing to BTS CIPSEA Agents.
- Out-of-scope routing to State CMV Data Analysts.
- Missing required data.
- Crashes missing Initial Incident Forms.
- QC failures.
- Completed record status changes.
- Analysis Environment dataset refresh completion.
- Report publication or sharing.

---

## 9. Frontend Architecture

The frontend is an **offline-first**, responsive web application organized by user
workflow and study context, accessible via laptops, tablets, and smartphones.

### 9.1 Frontend Modules

```text
frontend/
  src/
    app/                 # routing, auth shell, layouts, error boundaries
    features/
      studies/           # study setup and parameters
      crashes/           # crash list, detail, lifecycle, CCFP identifier
      initial-incident/  # Initial Incident Form (offline-capable)
      pci/               # Post-Crash Investigation form/workspace
      pcr/               # PCR ingestion, mapping, coverage, and data entry
      inspections/       # SafeSpect/post-crash inspection views
      reconstruction/    # reconstruction artifacts (narrative/image/video) and coding
      eld/               # ELD upload and extracted data views
      data-admin/        # raw data, aggregated data, external links, QC, completeness
      analysis/          # Analysis Environment: datasets, derived views, refresh, shares
      analytics/         # dashboards, maps, reports, visualizations
      admin/             # users, roles, permissions, attributes, rules
      public/            # de-identified public study outputs
      notifications/
    offline/             # local store, sync outbox, connectivity state
    shared/
      components/
      forms/
      api/
      auth/
      utils/
```

### 9.2 Key Frontend Requirements

Items below combine source-derived requirements (accessibility, plain language,
offline-first, configurable forms, search, role-aware access) with recommended UX
capabilities authored by this documentation (e.g., autosave, crash timeline) that are not
separately mandated by the source documents.

- Role-specific navigation and permissions-aware UI.
- Responsive and device-agnostic interface across laptops, tablets, and smartphones.
- **Offline-first:** the application functions and collects data normally when not
  connected to the Internet, and leverages cached resources and components first to
  optimize load time and user experience (SOO). This requires a precached application
  shell, a local structured store for drafts, a replay queue for writes, idempotent create
  endpoints, conflict handling, and a visible connectivity/sync state.
- Section 508 accessibility (the source requirement); WCAG 2.1 AA is the documentation's
  recommended technical conformance target. **Formal 508 sign-off is required before any
  deployment to production** (SOO).
- Plain-language labels and instructions.
- Configurable forms for evolving study attributes, including per-field required/optional
  flags and per-attribute definitions.
- Multi-select controls that enforce the PCR form's per-attribute selection caps and show
  remaining capacity.
- Repeatable field groups for vehicles, trailers, persons, non-motorists, witnesses, axles,
  tires, and hazardous materials, presented grouped by unit rather than as a flat list.
- Autosave for long forms.
- Upload controls for documents, images, videos, ELD CSVs, crash diagrams, and reports,
  with progress and resumability for large media.
- Data-quality indicators and completeness status.
- State PCR coverage view with an explicit note that figures are not comparable across PCR
  specification versions.
- Crash timeline, source-data provenance, and post-submission supplemental entries.
- Maps and geospatial views with no external tile or host dependency (`.gov` / CSP
  posture).
- Search across crashes, people, motor carriers, reports, and source artifacts.
- Export/download controls based on user permissions.

---

## 10. Backend Architecture

The backend exposes REST APIs and background services for workflow, validation,
integration, and data processing.

```text
backend/
  app/
    core/                 # config, auth, permissions, database, logging
    features/
      studies/
      users/
      crashes/
      initial_incident/
      post_crash_inspection/
      post_crash_investigation/
      police_crash_report/
      reconstruction/
      eld/
      data_mapping/
      data_quality/
      aggregation/          # CCFP Aggregated Data: external links, aggregated read model
      analysis_environment/ # datasets, derived views, refresh, audience shares
      analytics/
      reports/
      notifications/
      integrations/
      audit/
    workers/              # async ingestion, validation, extraction, scheduled refresh, reports
    main.py
  migrations/
  tests/
```

### 10.1 Backend Responsibilities

- Authenticate users through the approved identity provider, federated with SafeSpect
  identity where applicable.
- Enforce role, State, study, crash, resource-level, and **audience-tier** authorization
  server-side on every request, honouring the SafeSpect role hierarchy.
- Validate form submissions and uploaded data, including cardinality caps, at write time
  as well as in background QC.
- Assign unique CCFP identifiers.
- Accept idempotent creates so offline clients can safely replay queued writes.
- Route crash records based on in-scope and out-of-scope rules.
- Validate U.S. DOT numbers against SafeSpect.
- Validate driver information against CDLIS where integrated.
- Ingest SafeSpect, MCMIS, State repository, PCR, ELD, BTS, and external source data.
- Map source attributes to CCFP canonical attributes, addressed per repeating unit where
  the attribute repeats.
- Preserve source provenance and data lineage, and guarantee ingested source records are
  not mutated by downstream processing.
- **Link crash data to external-system records to produce CCFP Aggregated Data.**
- Apply configurable QC and completeness rules.
- Materialize and **refresh Analysis Environment datasets on a schedule**.
- Compute descriptive and inferential statistical summaries.
- Generate summaries of selected PCR sections.
- Support analyst selection of top three primary contributing factors.
- Generate reports, exports, and public de-identified outputs.
- Track every state-changing action in audit logs.

---

## 11. Database and Data Lake Design

The solution should separate transactional workflow state from analytical data storage
while keeping them linked through stable identifiers. The specific tables and Data Lake
zone names below are an illustrative, recommended design — the source mandates the
capabilities (integrate, map, aggregate, store, identify complete crash records, share to
an Analysis Environment), not a particular schema or zone taxonomy.

### 11.1 Core Transactional Tables

| Table | Purpose |
|-------|---------|
| `users` | User profile, identity provider subject, status. |
| `organizations` | FMCSA, BTS, NHTSA, NTSB, State agencies, external entities. |
| `roles` | Role definitions, including parent/child hierarchy aligned to SafeSpect. |
| `permissions` | Permission catalog. |
| `user_role_assignments` | User role assignments scoped by organization, State, or study. |
| `studies` | Study phase configuration. |
| `study_states` | Participating State configuration, including pilot vs. full participation. |
| `study_parameters` | Vehicle type, crash type, location, dates, and scope rules. |
| `data_attributes` | CCFP attribute catalog, including definition text, repeat unit, selection cap, applicable population, form section/label traceability, and supersession. |
| `attribute_requirements` | Required/optional/read-only/editable settings by study. |
| `ref_attribute_values` | Allowed values per coded attribute, versioned by specification with active/superseded state. |
| `crashes` | Main crash record and CCFP identifier. |
| `crash_scope_classifications` | Qualifying, in-scope, out-of-scope, supplemental flags. |
| `initial_incident_forms` | Initial Incident Form header and submission state. |
| `incident_vehicles` | Vehicles captured in the Initial Incident Form. |
| `incident_persons` | Drivers, occupants, non-motorists, and witnesses. |
| `post_crash_inspections` | Inspection metadata and linked source records. |
| `post_crash_investigations` | PCI form metadata and structured sections. |
| `police_crash_reports` | PCR metadata, ingestion path, and State source linkage. |
| `pcr_field_mapping` | State PCR field to CCFP attribute correspondence. |
| `reconstruction_reports` | Reconstruction metadata and coded findings. |
| `reconstruction_documents` | The set of artifacts (narrative, image, video, diagram) belonging to a reconstruction. |
| `eld_files` | Uploaded ELD/eRODS file metadata. |
| `eld_events` | Extracted ELD event rows. |
| `source_records` | Raw source record references and provenance. Append-only. |
| `ref_external_systems` | Catalog of Appendix D external systems available for linkage. |
| `crash_external_links` | Links from a crash to external-system records — the linkage that constitutes CCFP Aggregated Data. |
| `crash_attribute_values` | Canonical CCFP values addressed by crash, attribute, and repeating unit, with source provenance and edit state. |
| `crash_addenda` | Supplemental information supplied after submission, without overwriting the original record. |
| `data_quality_rules` | QC rule definitions, including missing, format, compliance, cross-field, and cardinality rules. |
| `data_quality_results` | Rule outcomes by crash and attribute. |
| `completeness_rules` | Rules defining a complete crash record. |
| `crash_completeness_status` | Complete/incomplete status and history. |
| `contributing_factor_selections` | Top three primary contributing factors selected by analyst. |
| `state_pcr_coverage` | Per-State, per-section coverage, stamped with PCR specification version. |
| `documents` | Metadata for uploaded documents, images, videos, PDFs, crash diagrams, and generated files. |
| `analysis_environments` | Analysis Environment definition, refresh cadence, and next-due state. |
| `analysis_datasets` | Derived data/views created from CCFP Aggregated Data and summary BTS data. |
| `analysis_dataset_versions` | Materialized snapshots produced by each refresh. |
| `analysis_shares` | Audience-scoped shares (FMCSA Federal, Other Federal, State, Public) with their own refresh cadence. |
| `analysis_refresh_runs` | Refresh execution history, status, and row counts. |
| `reports` | Dashboard/report/table definitions, State binding, and publication state. |
| `report_shares` | Share grants by user, role, organization, or audience tier. |
| `audit_logs` | Immutable audit event records. |
| `notifications` | Notification events and delivery status. |

### 11.2 Data Lake Zones

| Zone | Purpose |
|------|---------|
| **Raw Zone** | Original files, extracts, and source-system payloads exactly as received. Immutable. |
| **Mapped Zone** | Source data mapped to CCFP canonical attributes. |
| **Curated Zone** | QC-reviewed, aggregated crash records — CCFP Aggregated Data — ready for analysis. |
| **Analytical Zone** | The CCFP Analysis Environment: refreshed datasets and derived views for dashboards, reports, tables, and causal-factor analysis. |
| **Published Zone** | Summarized, de-identified outputs available for public access. |

### 11.3 Data Model Principles

- Every crash must have one stable CCFP identifier.
- Every source value must retain provenance.
- **Ingested source data must never be mutated by the analysis or sharing tiers**;
  corrections are recorded as new canonical values with edit history, not by rewriting the
  source.
- Canonical attribute values must be addressable **per repeating unit** (vehicle, person,
  trailer, non-motorist), not only per crash.
- Attribute cardinality (selection caps) and applicable population must be data-driven
  configuration, not hardcoded validation.
- Canonical CCFP attributes must support study-specific required/optional settings and
  editable attribute definitions.
- Allowed-value catalogs must be **versioned by specification**; values retired by a new
  specification must be marked superseded rather than deleted, so historical records stay
  resolvable.
- Complete-record logic must be configurable by study.
- PII, sensitive data, and CIPSEA-protected data must be tagged and access controlled.
  Public-releasable text (the PCR public narrative) must be tagged distinctly from
  internal narrative.
- Coverage metrics must be derived from current configuration and stamped with the
  specification version they belong to.
- Data Lake storage must support structured, semi-structured, and unstructured data.
- Published outputs must be de-identified and separated from operational records.

---

## 12. API Design

All APIs require authentication except health checks and public published-data endpoints.
APIs return JSON and enforce authorization server-side. The endpoints below are an
illustrative/proposed REST design; the source requires API-accessible data ("make APIs the
new default") but does not define these specific routes.

### 12.1 Authentication and User Context

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/api/v1/auth/me` | Current user, roles, permissions, organization, State scope. |
| `POST` | `/api/v1/auth/logout` | End user session. |

### 12.2 Studies and Administration

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/api/v1/studies` | List studies. |
| `POST` | `/api/v1/studies` | Create study. |
| `GET` | `/api/v1/studies/{studyId}` | Study detail. |
| `PATCH` | `/api/v1/studies/{studyId}` | Update study settings. |
| `GET` | `/api/v1/studies/{studyId}/attributes` | List study attributes. |
| `PATCH` | `/api/v1/studies/{studyId}/attributes/{attributeId}` | Update requirement/editability settings. |
| `PATCH` | `/api/v1/data-attributes/{attributeId}` | Update attribute settings and **definition** (partial update). |
| `GET` | `/api/v1/studies/{studyId}/completeness-rules` | List completeness rules. |
| `POST` | `/api/v1/studies/{studyId}/completeness-rules` | Create completeness rule. |
| `GET` | `/api/v1/studies/{studyId}/pcr-coverage` | Per-State PCR coverage, derived. |

### 12.3 Crash Records

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/api/v1/crashes` | List visible crashes with filters. |
| `POST` | `/api/v1/crashes` | Create crash shell and CCFP identifier. |
| `GET` | `/api/v1/crashes/{crashId}` | Crash detail. |
| `PATCH` | `/api/v1/crashes/{crashId}` | Update crash metadata. |
| `GET` | `/api/v1/crashes/{crashId}/timeline` | Crash lifecycle and audit timeline. |
| `GET` | `/api/v1/crashes/{crashId}/sources` | Source records linked to crash. |
| `GET` | `/api/v1/crashes/{crashId}/attributes` | Canonical attributes, addressed per repeating unit. |
| `POST` | `/api/v1/crashes/{crashId}/attributes` | Set a canonical value for a crash or unit. |
| `GET` | `/api/v1/crashes/{crashId}/quality` | QC rule results. |
| `GET` | `/api/v1/crashes/{crashId}/completeness` | Complete/incomplete status. |
| `POST` | `/api/v1/crashes/{crashId}/unlock` | Unlock completed record for authorized edit. |
| `GET` `POST` | `/api/v1/crashes/{crashId}/addenda` | Post-submission supplemental information. |

### 12.4 Initial Incident Form

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/api/v1/crashes/{crashId}/initial-incident` | Get form. |
| `PUT` | `/api/v1/crashes/{crashId}/initial-incident` | Save form (idempotent upsert). |
| `POST` | `/api/v1/crashes/{crashId}/initial-incident/submit` | Submit and route form. |
| `DELETE` | `/api/v1/crashes/{crashId}/initial-incident` | Delete where business rules allow. |
| `POST` | `/api/v1/crashes/{crashId}/incident-vehicles` | Add vehicle (accepts client idempotency key). |
| `POST` | `/api/v1/crashes/{crashId}/incident-persons` | Add person (accepts client idempotency key). |

### 12.5 Source Data and Forms

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/api/v1/crashes/{crashId}/post-crash-inspections` | Add or link inspection data. |
| `POST` | `/api/v1/crashes/{crashId}/post-crash-investigations` | Save PCI form data. |
| `POST` | `/api/v1/crashes/{crashId}/police-crash-reports` | Add PCR source data. |
| `POST` | `/api/v1/police-crash-reports/import` | Ingest CCFP-required PCR elements from a State extract. |
| `POST` | `/api/v1/crashes/{crashId}/reconstruction-reports` | Create reconstruction record. |
| `POST` | `/api/v1/crashes/{crashId}/reconstruction-reports/{id}/documents` | Attach narrative, image, or video artifacts. |
| `POST` | `/api/v1/crashes/{crashId}/eld-files` | Upload ELD CSV. |
| `GET` | `/api/v1/crashes/{crashId}/eld-events` | View extracted ELD events. |

### 12.6 Aggregation, Analysis, and Reports

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/api/v1/external-systems` | Appendix D source catalog available for linkage. |
| `GET` | `/api/v1/crashes/{crashId}/aggregated` | CCFP Aggregated Data document for a crash. |
| `GET` `POST` `DELETE` | `/api/v1/crashes/{crashId}/external-links` | Manage external-system links. |
| `GET` `POST` | `/api/v1/analysis-environments` | Manage the Analysis Environment. |
| `POST` | `/api/v1/analysis-environments/{id}/refresh` | Trigger a refresh. |
| `GET` | `/api/v1/analysis-environments/{id}/refresh-runs` | Refresh history and status. |
| `GET` `POST` | `/api/v1/analysis-datasets` | Create and list derived data/views. |
| `GET` | `/api/v1/analysis-datasets/{id}/rows` | Read materialized dataset rows. |
| `GET` | `/api/v1/analysis-datasets/{id}/statistics` | Descriptive and dispersion statistics. |
| `GET` | `/api/v1/analysis-datasets/{id}/export` | Export for Python/SAS/R and BI tools. |
| `GET` `POST` `DELETE` | `/api/v1/analysis-datasets/{id}/shares` | Audience-scoped shares. |
| `GET` | `/api/v1/analytics/dashboards` | List dashboards visible to caller. |
| `POST` | `/api/v1/analytics/queries` | Run authorized query. |
| `GET` | `/api/v1/analytics/geo/crashes` | Scoped crash positions for maps. |
| `GET` | `/api/v1/reports` | List reports. |
| `POST` | `/api/v1/reports` | Create report. |
| `POST` | `/api/v1/reports/{reportId}/share` | Share report to a user, role, organization, or audience tier. |
| `GET` | `/api/v1/public/studies/{studyId}/outputs` | Public de-identified outputs. |

---

## 13. External Integrations

### 13.1 FMCSA-Owned Sources

*Three sources were added in the January 2026 BRD and are marked below.*

| Source | Relevant Data |
|--------|---------------|
| ACE | Investigation reports and carrier files. |
| DataQs | Requests for data review and Crash Preventability determinations. |
| DIR | Driver inspection history, crash history, and DACH information. |
| DACH | CDL driver drug/alcohol violations and carrier queries. |
| DSMS | Driver inspection results, investigation results, crash history, and driver safety percentiles. |
| ELD/eRODS | Hours of service, engine hours, ignition status, location, and miles driven. |
| **MCMIS** *(added)* | Motor carrier registration data, inspection and crash history, compliance review and other post-crash enforcement data. **Note:** some information may shift to **Motus** or other systems as FMCSA modernizes its legacy IT systems, so this source must be swappable by configuration. |
| **National Registry of Certified Medical Examiners** *(added)* | Driver medical certificate information. |
| **SafeSpect Inspections** *(added)* | Inspection data related to vehicles, drivers, carriers, cargo, and enforcement actions and outcomes. Uploaded to the FMCSA SafeSpect system. |
| SMS | Carrier exposure, inspections, investigations, crash history, and carrier safety percentiles. |
| TPR | Entry-level driver training records. |
| SafeSpect | U.S. DOT number validation, inspection/crash reporting data, and — per the SOO — the host platform for integration and the source of the role hierarchy. |

### 13.2 Non-FMCSA Sources

*Unchanged from the prior specification.*

| Source | Owner | Relevant Data |
|--------|-------|---------------|
| CCFP BTS Secure Database | BTS | Aggregated/anonymized interview data, subject to CIPSEA restrictions. |
| CDLIS | AAMVA or FMCSA | CDL records, driver status, and driver history. |
| HPMS/MIRE | FHWA | Roadway extent, condition, performance, use, and characteristics. |
| Google Maps/Earth | Google | Location context and aerial views where approved. |
| NHTSA Recalls Database | NHTSA | Vehicle and component recall data. |
| HRRR Database | NOAA | Real-time weather: solar radiation (W/m2), relative humidity (%), wind speed (mph), air temperature (°F), precipitation (inches), and visibility (miles). |
| State Crash Repositories | States | State PCR data. |

### 13.3 Integration Patterns

The solution must support multiple integration patterns:

- API/web service ingestion.
- Secure file transfer.
- Manual upload.
- Manual data entry.
- Read-only lookup.
- Exportable summary data.
- Data Lake to external secure database transfer where approved.

For BTS specifically, access options span all four directions — read-only access to BTS
data, exportable summary data, integration from the BTS secure database into the CCFP
Data Lake, and integration from the CCFP Data Lake to the BTS secure database — and may
require a Memorandum of Understanding (MOU) with BTS specifying the data being shared (for
example, summary data excluding driver PII), security protocols, and the access method.
See BTS's Confidentiality Policy: <https://www.bts.gov/confidentiality>.

---

## 14. Security, Privacy, and Compliance

The CCFP IT Solution must comply with federal requirements and DOT best practices.

### 14.1 Required Compliance Areas

- Section 508 accessibility, with **formal sign-off of 508 compliance before deploying to
  production** (SOO).
- Federal website standards, including government banner, descriptive page titles, and
  metadata.
- DOTGOV Online Trust in Government Act, using `.gov` or `.mil` domains for official
  services.
- Paperwork Reduction Act, including OMB approval and display of OMB control number before
  public information collection.
- Plain Writing Act.
- Privacy Act documentation, including PTA, PIA, and SORN where required.
- NARA records management guidance.
- Open government/data requirements for discoverable, reusable, metadata-tagged public
  data.
- Information quality, objectivity, utility, and integrity requirements.
- Copyright/property-right protections for private-sector information.
- CIPSEA restrictions for BTS interview data.
- **All FMCSA IT Security Policies and applicable FMCSA and NIST standards and
  guidelines**, and other government-wide laws and regulations for the protection and
  security of information technology (SOO).

### 14.2 Security Controls

- MFA for all users; PIV/CAC where required for federal users.
- Server-side authorization on every request, honouring the SafeSpect role hierarchy and
  the four audience tiers.
- Encryption in transit and at rest.
- Object storage encryption and signed URL access.
- Immutable audit logs for state-changing actions.
- **Immutability of ingested source data** — the analysis and sharing tiers must not
  modify original CCFP (SafeSpect) or other source-system data.
- PII and sensitive-data tagging, with public-releasable text tagged distinctly.
- Least-privilege access by role, State, study, and data category. Role- and
  permission-based data access is managed in the administrative interface; the BRD
  suggests leveraging the FMCSA Drug and Alcohol Clearinghouse (DACH) user permissions
  model as a reference architecture.
- Data-sharing agreements before State participation; FMCSA IT and the Privacy Office work
  with each State to establish the required agreements before onboarding.
- Malware scanning for uploads, enforced before any download is permitted.
- Offline clients must not retain PII or CIPSEA-protected data beyond the authenticated
  session; local caches must be scoped per user and cleared on session teardown.
- Logging, monitoring, and alerting for security events.

### 14.3 Assessment and Authorization

Per the SOO, the contractor shall support the **Security Assessment and Authorization
(A&A)** process to obtain an **Authority to Operate (ATO)** in accordance with FMCSA and
DOT security policy, and support development of system security documentation including
the **System Security Plan (SSP)** and **Security Impact Analysis (SIA)**.

---

## 15. Non-Functional Requirements

| Requirement | Target |
|-------------|--------|
| Availability | 24/7 except scheduled maintenance and updates. |
| Performance | Support at least 1,000 concurrent users without negative response-time impact. |
| Large-data performance | Integrate with and display large datasets/databases (the full CCFP data set) with minimal performance impact. |
| Scalability | Support additional users, States, data attributes, source systems, and future studies. |
| Maintainability | Modular services and clear system documentation. |
| Accessibility | Section 508 (the source requirement), with formal sign-off before production; WCAG 2.1 AA recommended by this documentation as the technical conformance target. |
| Responsiveness | Mobile responsive and device agnostic across laptops, tablets, and smartphones. |
| **Offline operation** | The application functions and collects data normally when not connected to the Internet, and leverages cached resources and components first to optimize load time and user experience. |
| Data Flexibility | Support structured, semi-structured, and unstructured data. |
| Data Freshness | Analysis Environment refreshed daily or hourly; audience shares refreshed on a cadence determined by the CCFP Project Team. |
| Auditability | Track record updates, user actions, data provenance, and complete/incomplete changes. |
| Searchability | Search across application content and integrated internal/external systems. |
| Licensing | Low- or no-cost licensing for FMCSA users of visualization capability. |
| Quality Management | Quality assurance and quality management best practices providing the foundation for increasing and controlling the quality of IT products and services delivered to FMCSA (SOO). |
| Verification | Test plans with instructions and user acceptance criteria, test reports, and a dedicated test/UAT environment; formal UAT sign-off before any code goes to production (SOO). |
| Documentation | Data dictionary, data coding manual, and user guide supporting the CCFP Data Coding and Entry Training for CMV Data Analysts, plus interface control documents, technical specifications, and operations documentation. |
| Training | Role-specific training for core workflows, policies, and system tasks, plus a **training environment** to assist State onboarding and training (SOO). |

---

## 16. Delivery Schedule and Implementation Roadmap

### 16.1 Contract Schedule (SOO)

The SOO supersedes the prior September 30, 2025 / January 2026 milestone language, which
was removed from the January 2026 BRD. The period of performance is a base period of 12
months plus two option periods, exercised only on successful completion of all tasks in
the previous period.

| Task | Content | Duration |
|------|---------|----------|
| **Task 1** — Kickoff and Project Management Plan | Draft and final PMP, kickoff meeting within 14 days of award, briefing slides, meeting notes. | 4 weeks |
| **Task 2** — Discovery | One-week in-person discovery session; user story map; product backlog; product roadmap; release plan; development and pre-production environment readiness; FMCSA-approved business requirements. | 4 weeks |
| **Task 3** — Monitoring and Control | Work breakdown structure to feature level; cost estimation and tracking; weekly schedule reporting; monthly progress reports; contractual review gates. | Continuous |
| **Task 4** — Development | Fully functional solution integrated with SafeSpect, delivered in two-week sprints, deployed to pre-production every sprint; UAT and usability testing; 508 sign-off before production. | 8 months |
| **Task 5** — Pilot Deployment and Refinements | Three-month pilot study with **nine States**; end-to-end process and system testing; weekly pilot meetings with the CCFP project team and pilot States. | 3 months |
| **Task 6** — Post-Pilot Adjustments | Document and address outstanding bugs and issues. | 1 month |
| **Task 7** — Full-Scale Deployment and Sustainment | Full-scale deployment to all States; continued feedback, backlog, and release management. | 24 months |

**Recurring deliverables (Tasks 4-7).** Each of the development, pilot, post-pilot, and
full-scale tasks carries the same deliverable set, which must be produced every cycle
rather than once:

- Prioritized product backlog.
- **Test plans with instructions and user acceptance criteria.**
- **Test reports.**
- Sprint grooming/refinement sessions.
- Sprint demonstrations.
- Production deployment of all planned releases.
- Test environment (Task 4) and **user onboarding** (Task 4).

**Quality management.** The contractor shall follow **quality assurance and quality
management best practices** that provide the foundation for increasing and controlling the
quality of IT products and services to FMCSA. A quality management plan, configuration
management plan, document management and version control plan, and risk management plan
are components of the Project Management Plan (Task 1).

**Retrospectives.** After each release, **structured retrospectives** are conducted with
the FMCSA PM, FMCSA PO, and other stakeholders identified by FMCSA, to capture lessons
learned and reduce future risks. The software development process must also mature itself
through retrospectives at the sprint level.

**Feedback and defect handling.** Feedback from user iteration reviews must be captured,
systematically documented, classified, validated, and prioritized for resolution, and
there must be a systematic process for identifying, documenting, prioritizing, and
addressing bugs in a manner that supports timely releases.

**Review gates.** Contractual review gates are held at (1) discovery, (2) development
(intervals set by the product roadmap and release plans), (3) pilot study kick-off, and
(4) full study data collection kick-off. Each gate has predefined success criteria agreed
by both parties; at each gate FMCSA decides **Continue** or **Refine and Continue**.

**Key personnel.** IT Project Manager (Senior, 10+ years); Database Architect/Engineer
(Senior, 8+ years); Software Developer (Senior, 8+ years).

The Government may add or remove requirements or features as business priorities require,
done collaboratively so the net impact of additions and removals is zero.

### 16.2 Engineering Sequencing

The phase structure below is proposed engineering sequencing, not a plan defined by the
source. It maps into SOO Task 4.

**Phase 1 - Foundation, Security, and SafeSpect Alignment**

- Application shell; authentication and role model **including role hierarchy**.
- Organizations, States, users, and permissions across the four audience tiers.
- Study setup; audit logging; document/object storage foundation.
- SafeSpect integration pattern and identity/role mapping.

**Phase 2 - Initial Incident, Crash Record Creation, and Offline**

- Initial Incident Form; unique CCFP identifier.
- Qualifying/in-scope/out-of-scope classification; SafeSpect U.S. DOT validation.
- Routing and immediate notifications to State CMV Data Analysts and BTS CIPSEA Agents.
- Offline shell, local store, sync outbox, idempotent creates, conflict handling.

**Phase 3 - Data Collection Interfaces**

- Post-crash inspection ingestion; post-crash investigation form module.
- Reconstruction multi-artifact upload (narrative, image, video) and coding.
- ELD CSV upload and extraction; manual missing-data entry.
- Post-submission supplemental information.

**Phase 4 - PCR Ingestion, Mapping, and State Adaptability**

- HDTS PCR attribute catalog with repeating units, selection caps, and applicable
  populations.
- PCR importer with per-State transform profiles, preview mode, and run history.
- Required attribute coverage tracking, derived and specification-versioned.
- MCMIS and State repository ingestion patterns; CDLIS validation workflow.

**Phase 5 - Data Lake, Aggregation, QC, and Completeness**

- Raw, mapped, curated, analytical, and published zones with source immutability enforced.
- Source provenance and lineage; external-system linkage and CCFP Aggregated Data.
- Configurable QC rules including cardinality; complete/incomplete logic; missing Initial
  Incident Form detection.

**Phase 6 - Analysis Environment, Analytics, and Visualization**

- Analysis Environment: datasets, derived views, scheduled refresh, audience shares.
- Descriptive and inferential statistics; control cohort support; export for Python/SAS/R.
- Dashboards, maps and geospatial layers, time-series, self-service authoring, embedding,
  and scheduled canned reports.
- Top-three contributing factor selection; role-based report sharing and downloads.

**Phase 7 - Public De-Identified Outputs**

- Publication workflow; de-identification controls; public summary data access; open data
  metadata; public narrative publication.

**Phase 8 - Hardening and Launch**

- Accessibility testing and formal 508 sign-off; performance testing for 1,000 concurrent
  users; security assessment supporting A&A/ATO; training materials and training
  environment; operations documentation; production launch.

---

## 17. Open Questions and Assumptions

### 17.1 Open Questions

Items marked **[Discovery]** are the highest-priority questions for SOO Task 2, because
the answers can invalidate architectural assumptions.

- **[Discovery]** What is the SafeSpect integration pattern — API, SSO, shared data, or
  embedded module — and what interface control documentation governs it?
- **[Discovery]** What is the SafeSpect role hierarchy that CCFP role-based access must
  align with?
- **[Discovery]** Is the CCFP Analysis Environment built within the platform, or is an
  external DOT-approved BI/analytics service procured? This determines whether the work is
  datasets-and-refresh or an export/refresh API.
- **[Discovery]** What is the scope of offline operation — field data collection only, or
  the whole application?
- **[Discovery]** What control population supports statistical risk modeling, and how are
  non-fatal comparison crashes represented in the data model?
- What DOT-approved technology stack and hosting environment must be used?
- Which identity provider will support State and non-federal users?
- What exact data-sharing agreements are required for each participating State?
- Which nine States participate in the pilot, and what determines pilot readiness?
- What BTS data exchange model will be approved under CIPSEA, and will BTS data be
  read-only, summary export, integrated into the CCFP Data Lake, or exchanged through
  another secure mechanism?
- Which State crash repositories will support direct API or file-based integration?
- What is the authoritative approach for CDLIS integration?
- What public de-identification standard will be applied before study publication, and
  what review governs the PCR public narrative before release?
- What final OMB/PRA approval language and control number must be displayed?
- The Roadway Data Elements section of the HDTS PCR Data Form opens with the header "Unit
  Number of Motor Vehicle Striking Non-Motorist", duplicated from the Non-Motorist
  section. This appears to be a source defect and should be confirmed with FMCSA before
  implementation.
- NTSB is named in the January 2026 BRD body but is absent from its acronym list; confirm
  the intended scope of NTSB access.

### 17.2 Assumptions

- Development will use an agile approach with regular stakeholder review and UAT,
  delivered by one Scrum team on **two-week sprints**.
- The CCFP Project Team will participate in all user acceptance testing during sprint
  development, and **formal UAT sign-off is required before any code goes into
  production**.
- A Product Roadmap — covering product features, documentation deliverables, and a
  high-level timeline including sprint and testing schedules — will be provided to the
  entire CCFP Project Team and FMCSA Leadership to align vision and direction.
- The requirements backlog is maintained in the FMCSA-provided requirements management
  system (e.g., Atlassian Jira) and prioritized by the Product Owner or their designee.
- Detailed requirements may evolve during discovery and pilot feedback; the BRD is to be
  satisfied "with any mutually agreed-upon modifications documented during discovery."
- States should not be required to make major changes to existing systems or formats, and
  participating States' development, functional-testing, and data-validation requirements
  will be minimal.
- Approved data-sharing agreements must be in place before States begin using the
  solution.
- The platform must be configurable for future study phases without major rebuild, and
  future phases depend on administrative priorities and funding.
- Public users will only receive summarized, de-identified data.
- Participating State users will only receive their own State's data, without PII.

---

## 18. Appendix A - Source Coverage Matrix

| Source Document | Status | Covered In This Documentation |
|-----------------|--------|-------------------------------|
| **CCFP BRD January 2026** | Current | Program background, assumptions, constraints, federal design requirements, general requirements, data collection scope, CCFP Data Lake integration/storage, Data Admin Functionality, Data Analysis and Sharing (Manage/Share, Analyze, Visualize), roles and audience tiers, external integrations, ELD requirements, acronyms, and glossary. |
| **DRAFT SOO — CCFP Reporting and Analysis Solution (25 Aug 2025)** | Current | Statutory basis, SafeSpect integration and role alignment, offline-first requirement, reconstruction file uploads, PCR ingestion, post-submission supplemental information, data validations, delivery schedule and review gates, 508/UAT sign-off gates, A&A/ATO and security documentation, data dictionary/user guide/training environment. |
| **HDTS Police Crash Report (PCR) Data Form** | Current | PCR section set, repeating groups, conditional populations, selection caps, crash diagram and public narrative, Primary Contributing Factors section, attribute inventory (Appendix B, 19.4). |
| **HDTS Initial Incident Form** | Current (unchanged) | Initial Incident Form workflow, field groups, supplemental vehicle/non-motorist/witness forms, 24-48 hour submission timing, crash creation, notification, and database entities. |
| **HDTS Post-Crash Investigation Form (508)** | Current (unchanged) | Post-crash investigation module, PCI form sections, power unit/trailer details, driver/load details, HOS, exemptions, vehicle condition, brakes, lighting, tire, axle, and vehicle measurement data. |
| CCFP BRD September 2025 | **Superseded** | Retained in `Old_Docs` for traceability. The substantive differences are summarized in the revision note at the head of this document. |
| Kansas Sample Study Inclusion - For States | **Superseded** | Retained in `Old_Docs`. Its coverage figures are preserved in 19.3 as historical context only. |

### 18.1 BRD Requirement Traceability

| BRD Area (January 2026) | Documentation Location |
|----------|------------------------|
| Document purpose and structure | Sections 1-3 and this appendix. |
| Program overview | Sections 1-2. |
| CCFP IT Solution objectives | Sections 1, 3, 6, 8. |
| Assumptions and constraints | Section 17. |
| Design requirements | Sections 14-15. |
| General requirements | Sections 3, 6, 7, 15. |
| CCFP Incident Data | Sections 5, 8.2, 9, 10, 11, 12. |
| Inspection Data | Sections 8.3, 10, 11, 12, 13. |
| Post-Crash Investigation Data | Sections 8.4, 10, 11, 12, Appendix B. |
| Reconstructionist Data | Sections 8.6, 10, 11, 12. |
| PCR Data | Sections 8.5, 10, 11, 12, Appendix B. |
| Additional Crash Data | Sections 3, 5, 8.8, 10, 11. |
| BTS Data | Sections 4, 5, 13, 14, 17. |
| Data Lake integration and storage | Sections 6, 8.8, 10, 11. |
| **Data Admin Functionality** | Sections 4.3, 8.8, 9, 10, 11, 12. |
| **Data Analysis and Sharing — Core Capabilities** | Sections 4.4, 8.9, 6. |
| **Manage/Share CCFP Data** | Sections 4.4, 8.9.1, 11, 12.6. |
| **Analyze CCFP Data** | Sections 4.4, 8.9.2, 12.6. |
| **Visualize CCFP Data** | Sections 4.4, 8.9.3, 9.2, 12.6. |
| Appendix D external sources | Section 13 and Appendix B, 19.5. |
| Appendix E ELD requirements | Sections 8.7, 10, 11, 12, 13. |
| Appendix C diagrams and Figure 1 | BRD Appendix C provides Diagram 1 (Data Collection) and Diagram 2 (Data Integration, Analysis & Management, and Sharing); their data flows are reflected in Sections 5 and 6. BRD Figure 1 (CCFP Planned Studies by Phase) maps to Section 3.4. These figures were verified pixel-identical to the September 2025 versions and are referenced, not reproduced, here. **Note:** because the diagrams were not updated alongside the rewritten Analysis and Sharing section, Diagram 2 does not depict the Analysis Environment tier as the January 2026 text describes it; the text governs. |

### 18.2 SOO Requirement Traceability

| SOO Area | Documentation Location |
|----------|------------------------|
| Objectives and Scope | Sections 1, 3, 6. |
| SafeSpect integration and role alignment | Sections 4.1, 6, 10.1, 13.1, 17.1. |
| Offline-first responsive application | Sections 3.1, 5, 8.2, 9, 15. |
| Initial incident capture and immediate notification | Sections 5, 8.2, 8.11. |
| PCR import/ingest (Attachment C) | Sections 8.5, 12.5, 16.2 Phase 4. |
| Post-crash investigation capture (Attachment D) | Sections 8.4, 19.2. |
| Crash reconstruction file upload and association | Sections 8.6, 11.1, 12.5. |
| Manage/edit records and supplemental information | Sections 5, 8.8, 11.1, 12.3. |
| Aggregate all relevant data for a crash | Sections 5, 8.8, 11.1, 12.6. |
| Internal/external source integration and matching | Section 13. |
| Analysis environment and web application | Sections 6, 8.9. |
| Data structures and data validations | Sections 8.5, 8.9, 11, 10.1. |
| Specific Tasks 1-7, review gates, key personnel | Section 16.1. |
| 508 and UAT sign-off gates | Sections 14.1, 17.2. |
| A&A / ATO, SSP, SIA, NIST | Section 14.3. |
| Data dictionary, user guide, training environment | Section 15. |
| Appendix A agile key terms | Not reproduced; GAO Agile Assessment Guide GAO-24-105506 is the reference. |

---

## 19. Appendix B - Detailed Form and Data Inventory

### 19.1 Initial Incident Form Inventory

*Unchanged. Verified field-for-field identical between the 2025 DOCX and the current 508
PDF.*

The Initial Incident Form module must support these source-form fields and repeatable
groups:

- General information: local crash report number, crash date, crash time with AM/PM
  indicator, number of vehicles involved, number of persons involved.
- Crash location: city, county, State, street or highway name.
- Vehicle group: vehicle number, CMV/non-CMV indicator, U.S. DOT number when CMV, make of
  vehicle, number of occupants, number of injured occupants, carrier phone number.
- Driver group: driver name (last, first, middle), minor indicator, primary language,
  address, two phone numbers each with home/cell/work type, injury status of
  fatality/injury/no injury.
- Non-motorist group: occupant or pedestrian indicator, related vehicle number where
  applicable, name (last, first, middle), minor indicator, primary language, address, two
  phone numbers each with home/cell/work type, injury status.
- Witness group: witness name (last, first, middle), address, two phone numbers each with
  home/cell/work type. (Witnesses are individuals who saw the crash occur and can describe
  the events first-hand.)
- Event summary: short description of event — a short summary, not intended as a full
  report narrative — including sensitive details where relevant (e.g., the fatal crash
  involves a child, fire).
- Supplemental vehicle form: repeatable vehicle records beyond the base form.
- Supplemental non-motorist form: repeatable non-motorist records beyond the base form.
- Supplemental witness form: repeatable witness records beyond the base form.

### 19.2 Post-Crash Investigation Form Inventory

*Unchanged. Verified identical at the AcroForm field level.*

The PCI module must support the source PDF's sections:

- Header: post-crash date, crash date, investigation form case number, inspection number,
  officer name, officer ID. The form marks not-required fields in orange
  (orange-highlighted fields are optional) and the last three pages (additional towed units
  and hazardous material) are optional, so the configurable form must support per-field
  required/optional flags.
- Motor carrier and power unit: work zone and type of work zone, preclearance bypass serial
  number, fire (yes/no), fire pre-crash, fire post-crash, carrier name displayed, U.S. DOT
  number properly displayed, NSC number, motor carrier responsible (name, address, phone),
  a separate owner name and owner address, lease indicator, year, make, model, company unit
  number, manufacture date, VIN, color, license plate and State, registered gross weight,
  GVWR, annual inspection, axles up/down.
- Trailer and converter dolly records: trailer owner, owner address, type, intermodal
  indicator, unit number, year/make/model, VIN, color, license plate, expiration, registered
  gross weight, GVWR, axle weight rating, annual inspection, axles up/down, trailer 1
  through trailer 3, converter dolly details.
- Driver/load information: driver name, driver present, address, license State/province,
  license number, class, endorsements, restrictions, issue/expiration dates, lenses
  required/worn, medical certificate information (examination date, expiration date, lenses,
  hearing aid, waiver, medic alert, State/province of medical certificate to operate), seat
  belt equipment/use and airbag equipped/deployed recorded per seating position (driver,
  passenger 1, passenger 2, sleeper berth), seat belt condition, shipper, cargo bill of
  lading, manifest/load weight, cargo loaded and destination details, load securement with
  evaluation flags (contributed to crash, proper use, exceeded working load limit), load
  securement type, hazardous material presence/type/placards/spill/leak by truck and
  trailers, remarks.
- Driver hours of service: date-level on-duty not-driving hours, driving hours, total
  on-duty/driving hours, miles/kilometers driven, record of duty status, timecard,
  violations, onboard computer/ELD, co-driver, last 8 days present, approved ELD, ELD
  downloaded, provider, model, version, last entry, last stop arrived/departed, purpose of
  trip/destination, driver history, road familiarity, years of driving experience, previous
  CMV crashes, driver condition remarks.
- Exemptions: 14-hour workday, 11-hour driving period, split sleeper berth 10-hour break,
  60/70-hour week, 34-hour restart, federal/state/oilfield/agricultural/150-air-mile/temporary
  exemptions, docket or State number, emergency declarations (jurisdiction: national,
  regional, service center, or State, with federal and State declaration numbers), service
  center, other description.
- Vehicle condition and equipment: driver's compartment condition, driver's view, windshield
  wipers and position of wiper switch, heater/defroster, mirrors, rearward camera, fender
  mirrors, odometer, engine hours, engine manufacturer and engine-powered-by (fuel type), ECM
  serial number, ADAS, steering (type power/manual, steering wheel diameter, lash, steering
  checked with motor running), transmission (type, model number, serial number, gear position,
  number of forward gears, drive line notes), drive axle ratio, radio/CB/dash camera/audio
  technology/headphones/Bluetooth.
- Brake systems: brake type, ABS type, engine brake (type and position), air leaks, brake
  application loss, low-air/vacuum warning device (audible/warning signal and the PSI at which
  it activates), hydraulic brakes (master cylinder secure, fluid level, fluid seepage,
  line/hose/connection condition states), hydraulic lines/hoses/connections, electric brakes
  (controller manufacturer, gain setting, breakaway device, battery/wiring condition), surge
  brakes (breakaway device, fluid leak/seepage), power assist, parking brake, wheel-end weight
  note.
- Air brake data: axle-level ABS, slack adjuster (type and length), push rod stroke (available
  and applied), air pressure (inches/fractions), chamber type, drum/rotor, brake friction code,
  rolling radius, wheel-end weight, total end weight, remarks.
- Lighting: power unit low/high beams, turn signals, ID lamps, clearance lights, stop lamps,
  tail lamps, four-way flashers, reflectors, conspicuity tape, side marker lights (left/right),
  electrical power disabled due to crash or by emergency workers, lighting connection between
  units, towed units 1 through 4 (each capturing front/rear clearance, side marker (L/R), turn
  signals, stop lamps, ID lamps, tail lamps, reflectors, and conspicuity tape).
- Tire data: axles 1 through 11, left/right and inside/outside tire positions, size, make,
  model/design, TIN/DOT number, rated PSI, rated weight, inspection PSI, retread TIN/DOT,
  repair, repair location, speed rating, tread depth, wheel/hub remarks.
- Vehicle measurements: tractor height, fifth-wheel height, trailer width, additional axle
  positioning (distance in front of axle 2 for the tractor; distance from the rear for
  trailers/towed units), rear protection/bumper measurements (distance from rear of trailer,
  distance from ground, distance from side of trailer, and width of rear protection from edge
  of bumper to edge of bumper), towed units 1 through 3, all measurements in inches.
- Optional pages: additional towed units and hazardous material pages must be supported as
  conditional sections.

### 19.3 Historical Per-State PCR Coverage (Superseded)

> **Superseded.** The table below is from the Kansas Sample Study Inclusion worksheet and
> is retained for historical traceability only. It counted **attribute values** against the
> 2025 worksheet, including a "Dynamic Data Elements" section that no longer exists and an
> optional tier the current PCR data form does not define. Coverage figures under the
> current specification are **not comparable** with these and must be derived from the
> current attribute configuration.

| PCR Section (2025 worksheet) | Required Collected | Total Required | Required Complete | Optional Collected | Total Optional |
|-------------|--------------------|----------------|-------------------|--------------------|----------------|
| Crash | 129 | 202 | 63.86% | 0 | 6 |
| Dynamic Data Elements | 0 | 21 | 0.00% | 0 | 0 |
| Fatal Section | 2 | 46 | 4.35% | 0 | 8 |
| Large Vehicles & Hazardous Materials | 92 | 168 | 54.76% | 0 | 1 |
| Non-Motorist Section | 34 | 69 | 49.28% | 0 | 1 |
| Person | 155 | 294 | 52.72% | 0 | 17 |
| Roadway | 11 | 16 | 68.75% | 0 | 0 |
| Vehicle | 213 | 378 | 56.35% | 0 | 17 |
| Total | 636 | 1194 | 53.27% | 0 | 50 |

### 19.4 PCR Attribute Catalog (HDTS PCR Data Form)

The PCR module must support the elements below. Codes are the platform's **internal**
identifiers — the current form carries no element codes, so each attribute must also record
its form section and form label (Section 8.5). Codes shown in parentheses preserve the MMUCC
lineage inherited from the superseded worksheet.

**Crash Data Elements.** Crash identifiers — State-specific identifier, local case number,
**case/report number**; source of information (law enforcement agency, NCIC originating
agency identifier, civilian, officer badge number); weather conditions; light condition;
roadway surface condition; roadway contributing circumstances; relation to junction (within
interchange area, at intersection, specific location, distance from junction, intersecting
roadway name); type of intersection (number of approaches, geometry, overall traffic control
device); crash severity; crash classification (trafficway characteristics, secondary crash);
number of entities/fatalities involved (motor vehicles, motorists, non-fatally injured
persons, fatalities); alcohol involvement; drug involvement; crash date and time, time zone,
and **time of roadway clearance**; crash city/county/State; crash location including
highway/street name, **route number**, **milepost**, latitude/longitude, and **roadway
direction**; first harmful event; location of first harmful event relative to the trafficway;
manner of crash/collision impact; override/underride; crash description; **crash diagram
(uploaded file)**; **public narrative (written for and available to the public)**;
**direction in which crash initiated**; **post-crash inspection block** (inspecting agency
name, report number, inspecting officer name, inspection type of driver or vehicle, driver
out of service); property damage description (excluding vehicle); **reportable crash
indicators** (FMCSA reportable, State reportable).

**Fatal Data Elements.** Attempted avoidance maneuver; alcohol test status, type, and
results (including actual value); drug test status, type, and results; **federally
reportable crash**; **air bag in vehicle** (in vehicle, deployed); person information (full
name, **height**, sex, date of birth).

**Large Vehicle and Hazardous Material (HM) Data Elements.** Trailer license plate number
**and plate State** per position; trailer VINs; trailer model years; **trailer owner** (name,
street address, city, ZIP) per position; trailer sizing (GVWR, length); trailer type; motor
carrier identification (identification type, U.S. DOT number, motor carrier name, State
number, MC/MX, other number, identification number, address including P.O. box, county code,
ZIP, **colony**, and country, address-same-as-owner, phone, phone-same-as-owner, **email
address**, type of carrier, source of information); vehicle configuration; **special sizing
and permitted status**; total number of axles per unit (truck tractor, trailers 1-3, total);
cargo body type; **cargo load indicator**; **cargo type** (including last known commodity);
hazardous materials (HazMat ID number, class, common name, placard displayed, **total HazMat
types transported**, carrying HazMat, release of hazardous materials per trailer position).

> *Retired:* trailer model (LV05) — only trailer **model year** appears on the current form.

**Person Data Elements.** Organized by applicable population — All Persons Involved, All
Occupants, All Drivers, CMV Drivers, All Drivers and Non-Motorists, All Injured.
**Sequential identifying number**; person name (first, middle, last, **suffix**); date of
birth and **age**; sex; race; **phone number**; address, city, State/province, ZIP, country;
person type (motorist — driver, **co-driver**, passenger, occupant of MV not in transport;
non-motorist — bicyclist, other cyclist, pedalcyclist, pedestrian, other pedestrian, occupant
of a non-motor-vehicle transportation device; **incident responder** — police,
transportation, EMS, fire; **witness indicator**); **driver presence**; person injury status;
vehicle number the occupant was in; ejection status and **ejection path**; seating position
(row and seat); restraint systems; motorcycle helmet use; **seat belt use indicator**;
indication of improper use; airbag deployment and deployment type; jurisdiction type and
name; license number and class; endorsements; restrictions; driver license status (type
applicable, **issued date**, **expiration date**, **withdrawal action pending**, status);
enforcement actions (violation description, State violation code, no violations, citation
issued, citation number); driver actions at time of crash; CMV license status; compliance
with CDL endorsements; **distracted by action** and **distracted by source**; **vision
obscured by**; condition at time of crash; law enforcement suspects alcohol use; law
enforcement suspects drug use; alcohol test (status, type, BAC result); drug test (status,
type, result); injury area and **injury severity**; transported to medical facility (medical
transport, source of transport, EMS response agency identifier, EMS response run number,
medical facility receiving patient).

**Vehicle Data Elements.** Vehicle sequential number; VIN; make, model, model year,
**color**; **motor vehicle type** (in transport, parked, working vehicle/equipment); license
plate number, **country identifier**, registration State and year; **vehicle owner** (name,
city, State, full street address, same as carrier); **vehicle size and weight** (size class,
GVWR, GVWR registered, GVWR/GCWR rating); vehicle body type category; **number of trailers**;
**CMV indicator**; **truck/bus involvement**; total occupants; special function of vehicle in
transport; **bus indicator** and **truck indicator**; emergency motor vehicle use; **HM
placard displayed**; trafficway description (travel directions, divided status, **barrier
type**); horizontal alignment and grade; total lanes in roadway including **auxiliary lanes**;
traffic control devices (signs, signals, **pavement markings**, person); **inoperative or
missing traffic control devices**; direction of travel before crash; posted/statutory speed
limit; hit and run; towed due to disabling damage; vehicle maneuver/actions; sequence of
events (including non-harmful events and free-text description); most harmful event; vehicle
damage (initial point of contact, location of damaged areas, **fire indicator**, extent of
damage, **most damaged area**); vehicle contributing circumstances.

**Non-Motorist Data Elements.** Unit number of motor vehicle striking non-motorist;
non-motorist action/circumstance prior to crash; **origin/destination**; non-motorist
contributing actions/circumstances; non-motorist location at time of crash; non-motorist
safety equipment; initial contact point on non-motorist; non-motorist unit type; non-motorist
direction of travel.

**Roadway Data Elements.** Roadway functional class (rural and urban); width of lanes,
shoulders, and median; access control; **roadway lighting**; **presence/type of bicycle
facility**; **mainline number of lanes at intersection**; **cross-street number of lanes at
intersection**; **roadway surface type** (main roadway and shoulder); railway crossing
identification (State-specific ID, position); **warning device type** (signs, gates,
crossbucks, **number of stop signs**, **number of yield signs**, signals, flashing lights,
wigwags/bells, four-quad gates, non-train-activated special protection).

**Primary Contributing Factors.** The solution generates a summary of the selections made in
the five BRD-specified source groups, and the CMV Data Analyst — coordinating with the State
investigation team — selects **Primary Contributing Factor 1, 2, and 3**.

> *Retired:* Dynamic Data Elements and motor vehicle automated driving systems (DV01).

### 19.5 External Data Source Inventory

| Source | Owner | Required Data Coverage |
|--------|-------|------------------------|
| Activity Center for Enforcement (ACE) | FMCSA | Investigation reports and carrier files. |
| DataQs | FMCSA | Requests for data reviews and results, including Crash Preventability determinations. |
| Driver Information Resource (DIR) | FMCSA | Driver inspection history, crash history, and DACH information. |
| Drug and Alcohol Clearinghouse (DACH) | FMCSA | CDL driver drug and alcohol violations and current carrier queries. |
| Driver Safety Measurement System (DSMS) | FMCSA | Driver inspection results, investigation results, crash history, and DSMS percentiles. |
| ELD/eRODS | FMCSA | Driving time, hours of service, engine hours, ignition status, location, and miles driven. |
| **Motor Carrier Management Information System (MCMIS)** | FMCSA | Motor carrier registration data, inspection and crash history, compliance review and other post-crash enforcement data. Some information may shift to Motus or other systems. |
| **National Registry of Certified Medical Examiners** | FMCSA | Driver medical certificate information. |
| **SafeSpect Inspections** | FMCSA | Inspection data related to vehicles, drivers, carriers, cargo, and enforcement actions and outcomes. |
| Safety Measurement System (SMS) | FMCSA | Carrier exposure data, VMT per average power unit, inspection results, investigation results, crash history, and SMS percentiles. |
| Training Provider Registry (TPR) | FMCSA | Driver training records for mandated entry-level driver training. |
| CCFP BTS Secure Database | BTS | Aggregated, anonymized data from confidential interviews of drivers, carriers, and witnesses involved in qualifying crashes. |
| CDLIS | AAMVA or FMCSA | CDL records, driver status, and driver history. |
| HPMS/MIRE | FHWA | Roadway extent, condition, performance, use, and operating characteristics. |
| Google Maps/Earth | Google | Location information and aerial views. |
| NHTSA Recalls Database | NHTSA | Recall data for vehicle parts and accessories from original equipment manufacturers. |
| HRRR Database | NOAA | Real-time weather: solar radiation (W/m2), relative humidity (%), wind speed (mph), air temperature (°F), precipitation (inches), and visibility (miles). |

---

## 20. Appendix C - Acronyms and Glossary

### 20.1 Acronyms

| Term | Definition |
|------|------------|
| A&A | Security Assessment and Authorization |
| ACE | Activity Center for Enforcement |
| AAMVA | American Association of Motor Vehicle Administrators |
| API | Application Programming Interface |
| ATO | Authority to Operate |
| BTS | Bureau of Transportation Statistics |
| CCFP | Crash Causal Factors Program |
| CDL | Commercial Driver's License |
| CDLIS | Commercial Driver's License Information System |
| CIPSEA | Confidential Information Protection and Statistical Efficiency Act |
| CMV | Commercial Motor Vehicle |
| COR | Contracting Officer's Representative |
| CVSA | Commercial Vehicle Safety Alliance |
| CVSP | Commercial Vehicle Safety Plan |
| DACH | Drug and Alcohol Clearinghouse |
| DIR | Driver Information Resource |
| DSMS | Driver Safety Measurement System |
| ELD | Electronic Logging Device |
| eRODS | Electronic Record of Duty Status |
| FARS | Fatality Analysis Reporting System |
| FHWA | Federal Highway Administration |
| FMCSA | Federal Motor Carrier Safety Administration |
| FOIA | Freedom of Information Act |
| FY | Fiscal Year |
| GAO | Government Accountability Office |
| GVWR | Gross Vehicle Weight Rating |
| HDTS | Heavy-Duty Truck Study (CCFP Phase 1) |
| HM | Hazardous Material |
| HPMS | Highway Performance Monitoring System |
| HRRR | High-Resolution Rapid Refresh |
| IIJA | Infrastructure Investment and Jobs Act |
| IT | Information Technology |
| MCMIS | Motor Carrier Management Information System |
| MCSAP | Motor Carrier Safety Assistance Program |
| MIRE | Model Inventory of Roadway Elements |
| MMUCC | Model Minimum Uniform Crash Criteria |
| MOU | Memorandum of Understanding |
| NARA | National Archives and Records Administration |
| NCIC | National Crime Information Center |
| NCSA | National Center for Statistics and Analysis |
| NHTSA | National Highway Traffic Safety Administration |
| NIST | National Institute of Standards and Technology |
| NOAA | National Oceanic and Atmospheric Administration |
| NRCME | National Registry of Certified Medical Examiners |
| **NTSB** | National Transportation Safety Board *(used in the January 2026 BRD body; absent from its acronym list)* |
| OMB | Office of Management and Budget |
| OOS | Out of Service |
| PCR | Police Crash Report |
| PIA | Privacy Impact Assessment |
| PM | Project Manager |
| PO | Product Owner |
| PRA | Paperwork Reduction Act |
| PTA | Privacy Threshold Analysis |
| PU | Power Unit |
| SIA | Security Impact Analysis |
| SMS | Safety Measurement System |
| SOO | Statement of Objectives |
| SORN | System of Records Notice |
| SSP | System Security Plan |
| TPR | Training Provider Registry |
| UAT | User Acceptance Testing |
| U.S. DOT | United States Department of Transportation |
| VMT | Vehicle Miles Traveled |
| WBS | Work Breakdown Structure |

### 20.2 Glossary

| Term | Definition |
|------|------------|
| BTS CIPSEA Agent | Agent responsible for confidential interviews with drivers, carriers, and witnesses within 24-48 hours after an in-scope crash notification. Interviews are limited to in-scope crashes, and the Initial Incident Form triggers the interview process. |
| **CCFP Aggregated Data** | Linked CCFP crash data (e.g., data from post-crash inspections, PCRs, post-crash investigations, and crash reconstructions), **and data from external systems** (e.g., SafeSpect Inspections, Drug and Alcohol Clearinghouse, etc.) that are related to a specific crash. *(Added in the January 2026 BRD.)* |
| **CCFP Analysis Environment** | The tier into which CCFP Aggregated Data and summary BTS data are shared on a refresh cadence, in which derived data and views are created, analyzed, and visualized, and from which data is shared outward to each audience tier. |
| CCFP Data Lake | Central repository for ingesting, storing, processing, and securing structured, semi-structured, and unstructured CCFP data. |
| CCFP IT Solution | Scalable platform that minimizes State burden, dynamically collects data, integrates source systems, and supports causal-factor analysis and sharing. |
| CCFP Project Team | FMCSA staff and U.S. DOT Volpe Center support team as determined by the CCFP FMCSA Project Lead. |
| **CCFP Super User** | FMCSA Program Office resource authorized, alongside the CCFP Project Team, to create and share dashboards, visualizations, reports, and tables with FMCSA, other federal, participating State, and public users. *(Added in the January 2026 BRD.)* |
| Crash Reconstruction | Advanced investigation using physical, electronic, video, audio, and testimonial evidence to determine how and why a crash occurred. |
| Crash Reconstructionist | Trained law enforcement officer or contracted party who completes crash reconstruction. |
| FARS Analyst | State role that collects, translates, and transmits State data to NCSA's standard format and uploads data into FARS within 90 days after a crash. |
| FMCSA CIPSEA Agent | Member of the FMCSA CCFP Project Team granted access to protected BTS data where permitted. |
| **Heavy-Duty Truck Study (HDTS)** | The SOO's name for CCFP Phase 1 — fatal crashes involving Class 7/8 trucks. |
| Heavy-Duty Truck | Class 7/8 truck with GVWR of 26,001 pounds or more. Examples: truck-tractor semi-trailers, furniture trucks, garbage trucks, and cement trucks. |
| Initial Incident Form | New electronic form completed within 24-48 hours after a crash and used to create the initial CCFP crash record. |
| In-Scope Crash | A qualifying crash within a participating State jurisdiction. |
| MCSAP CMV Inspector | Federal inspector certified by CVSA, responsible for crash inspection response and Initial Incident Form completion. |
| Medium-Duty Truck | Class 3-6 truck with GVWR of 10,001-26,000 pounds. Examples: bucket trucks, box trucks, city delivery vans, and full-size pickup trucks. |
| MMUCC | Voluntary minimum standardized crash-data variable set used to identify traffic safety problems and design countermeasures. |
| **Offline-first** | Design principle from the SOO: the application functions and collects data normally when not connected to the Internet, and leverages cached resources and components first to optimize load time and user experience. |
| Out-of-Scope Crash | A qualifying crash in a non-participating State, or a non-qualifying heavy-duty truck serious-injury crash with advanced investigation data. |
| PCR | Police Crash Report completed by law enforcement and uploaded to a State crash repository. |
| Post-Crash Inspection | Inspection by an MCSAP CMV Inspector documenting violations and defects at the time of inspection. |
| Post-Crash Investigation | More thorough investigation than a standard PCR, but less expansive than a crash reconstruction. |
| Post-Crash Investigator | Law enforcement officer who performs a post-crash investigation. |
| **Public Narrative** | Crash narrative on the PCR data form written for and available to the public, deliberately separate from the internal crash description so it can be released without redaction. |
| Qualifying Crash | For Phase 1, a crash involving at least one fatality and at least one heavy-duty Class 7/8 truck. |
| **SafeSpect** | FMCSA's existing inspection and crash-reporting platform. Per the SOO, the CCFP reporting and analysis solution integrates with SafeSpect, aligns its data architecture and business process management to SafeSpect components, and aligns role-based access with the SafeSpect role hierarchy. |
| State CMV Data Analyst | State role responsible for data collection coordination, QC, report interpretation, standard-format submission, and causal-factor analysis support. |

---

*End of Document*
