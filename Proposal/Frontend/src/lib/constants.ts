/** Domain constants: lifecycle phases, option lists, tone maps, demo accounts. */

import type {
  CompletenessStatusValue,
  CrashLifecyclePhase,
  CrashScope,
  InjuryStatus,
  MappingStatus,
  PersonType,
  QcResultStatus,
  RuleSeverity,
} from './types';

type BadgeTone = 'success' | 'warning' | 'danger' | 'progress' | 'neutral' | 'info';

// ─────────────── Crash lifecycle (documentation §5) ───────────────
export interface LifecyclePhaseDef {
  key: CrashLifecyclePhase;
  index: number;
  label: string;
  short: string;
}
export const LIFECYCLE_PHASES: LifecyclePhaseDef[] = [
  { key: 'INITIAL_INCIDENT', index: 0, label: 'Initial Incident', short: 'Incident' },
  { key: 'NOTIFICATION', index: 1, label: 'Notification & Routing', short: 'Routing' },
  { key: 'DATA_COLLECTION', index: 2, label: 'Source Data Collection', short: 'Collection' },
  { key: 'DATA_MAPPING', index: 3, label: 'Mapping & Aggregation', short: 'Mapping' },
  { key: 'QUALITY_CONTROL', index: 4, label: 'Quality Control', short: 'QC' },
  { key: 'ANALYSIS', index: 5, label: 'Analysis & Reporting', short: 'Analysis' },
  { key: 'PUBLICATION', index: 6, label: 'Publication', short: 'Publish' },
];
export const PHASE_INDEX: Record<CrashLifecyclePhase, number> = LIFECYCLE_PHASES.reduce(
  (acc, p) => ({ ...acc, [p.key]: p.index }),
  {} as Record<CrashLifecyclePhase, number>,
);
export const PHASE_LABEL: Record<CrashLifecyclePhase, string> = LIFECYCLE_PHASES.reduce(
  (acc, p) => ({ ...acc, [p.key]: p.label }),
  {} as Record<CrashLifecyclePhase, string>,
);
export const PHASE_TONE: Record<CrashLifecyclePhase, BadgeTone> = {
  INITIAL_INCIDENT: 'neutral',
  NOTIFICATION: 'progress',
  DATA_COLLECTION: 'progress',
  DATA_MAPPING: 'progress',
  QUALITY_CONTROL: 'warning',
  ANALYSIS: 'info',
  PUBLICATION: 'success',
};

// ─────────────── Option lists ───────────────
export const SCOPE_OPTIONS: { value: CrashScope; label: string }[] = [
  { value: 'IN_SCOPE', label: 'In Scope' },
  { value: 'OUT_OF_SCOPE', label: 'Out of Scope' },
  { value: 'UNDETERMINED', label: 'Undetermined' },
];
// FHWA vehicle classes 1-8 — the full vocabulary, deliberately NOT filtered to
// Phase 1. Which classes qualify a crash is study configuration held server-side
// (`vehicle_classes`), so recording a class here stays valid for future phases.
export const VEHICLE_CLASS_OPTIONS: { value: string; label: string }[] = [
  { value: '1', label: 'Class 1 — up to 6,000 lbs' },
  { value: '2', label: 'Class 2 — 6,001–10,000 lbs' },
  { value: '3', label: 'Class 3 — 10,001–14,000 lbs' },
  { value: '4', label: 'Class 4 — 14,001–16,000 lbs' },
  { value: '5', label: 'Class 5 — 16,001–19,500 lbs' },
  { value: '6', label: 'Class 6 — 19,501–26,000 lbs' },
  { value: '7', label: 'Class 7 — 26,001–33,000 lbs' },
  { value: '8', label: 'Class 8 — 33,001 lbs and over' },
];
export const SCOPE_TONE: Record<CrashScope, BadgeTone> = {
  IN_SCOPE: 'success',
  OUT_OF_SCOPE: 'warning',
  UNDETERMINED: 'neutral',
};

export const PERSON_TYPES: { value: PersonType; label: string }[] = [
  { value: 'DRIVER', label: 'Driver' },
  { value: 'OCCUPANT', label: 'Occupant' },
  { value: 'NON_MOTORIST', label: 'Non-Motorist' },
  { value: 'WITNESS', label: 'Witness' },
];
export const INJURY_OPTIONS: { value: InjuryStatus; label: string }[] = [
  { value: 'FATAL', label: 'Fatal' },
  { value: 'INJURY', label: 'Injury' },
  { value: 'NO_INJURY', label: 'No Injury' },
  { value: 'UNKNOWN', label: 'Unknown' },
];
// Per-number phone type (INIT-2) and non-motorist kind (INIT-3) — small fixed
// vocabularies surfaced as <Select> options on the Initial Incident Form.
export const PHONE_TYPES: { value: string; label: string }[] = [
  { value: 'HOME', label: 'Home' },
  { value: 'CELL', label: 'Cell' },
  { value: 'WORK', label: 'Work' },
];
export const NON_MOTORIST_KINDS: { value: string; label: string }[] = [
  { value: 'OCCUPANT', label: 'Occupant' },
  { value: 'PEDESTRIAN', label: 'Pedestrian' },
];
export const INJURY_TONE: Record<InjuryStatus, BadgeTone> = {
  FATAL: 'danger',
  INJURY: 'warning',
  NO_INJURY: 'success',
  UNKNOWN: 'neutral',
};

export const QC_STATUS_TONE: Record<QcResultStatus, BadgeTone> = {
  PASS: 'success',
  FAIL: 'danger',
  WARNING: 'warning',
  NOT_EVALUATED: 'neutral',
};
export const SEVERITY_TONE: Record<RuleSeverity, BadgeTone> = {
  INFO: 'info',
  WARNING: 'warning',
  ERROR: 'danger',
  CRITICAL: 'danger',
};
export const COMPLETENESS_TONE: Record<CompletenessStatusValue, BadgeTone> = {
  COMPLETE: 'success',
  INCOMPLETE: 'warning',
};
export const MAPPING_TONE: Record<MappingStatus, BadgeTone> = {
  PENDING: 'neutral',
  MAPPED: 'progress',
  REVIEWED: 'success',
};
export const SENSITIVITY_TONE: Record<string, BadgeTone> = {
  PUBLIC: 'success',
  INTERNAL: 'neutral',
  PII: 'warning',
  SENSITIVE: 'warning',
  CIPSEA: 'danger',
};

// ─────────────── Analytics queries (whitelisted server-side) ───────────────
export const ANALYTICS_QUERIES: { value: string; label: string }[] = [
  { value: 'crash_counts_by_state', label: 'Crash counts by State' },
  { value: 'crash_counts_by_phase', label: 'Crash counts by lifecycle phase' },
  { value: 'fatalities_by_state', label: 'Fatalities by State' },
  { value: 'qc_failure_summary', label: 'QC failures by rule' },
];

// ─────────────── US states / territories (static reference) ───────────────
export const US_STATES: { code: string; name: string }[] = [
  { code: 'AL', name: 'Alabama' }, { code: 'AK', name: 'Alaska' }, { code: 'AZ', name: 'Arizona' },
  { code: 'AR', name: 'Arkansas' }, { code: 'CA', name: 'California' }, { code: 'CO', name: 'Colorado' },
  { code: 'CT', name: 'Connecticut' }, { code: 'DE', name: 'Delaware' }, { code: 'FL', name: 'Florida' },
  { code: 'GA', name: 'Georgia' }, { code: 'HI', name: 'Hawaii' }, { code: 'ID', name: 'Idaho' },
  { code: 'IL', name: 'Illinois' }, { code: 'IN', name: 'Indiana' }, { code: 'IA', name: 'Iowa' },
  { code: 'KS', name: 'Kansas' }, { code: 'KY', name: 'Kentucky' }, { code: 'LA', name: 'Louisiana' },
  { code: 'ME', name: 'Maine' }, { code: 'MD', name: 'Maryland' }, { code: 'MA', name: 'Massachusetts' },
  { code: 'MI', name: 'Michigan' }, { code: 'MN', name: 'Minnesota' }, { code: 'MS', name: 'Mississippi' },
  { code: 'MO', name: 'Missouri' }, { code: 'MT', name: 'Montana' }, { code: 'NE', name: 'Nebraska' },
  { code: 'NV', name: 'Nevada' }, { code: 'NH', name: 'New Hampshire' }, { code: 'NJ', name: 'New Jersey' },
  { code: 'NM', name: 'New Mexico' }, { code: 'NY', name: 'New York' }, { code: 'NC', name: 'North Carolina' },
  { code: 'ND', name: 'North Dakota' }, { code: 'OH', name: 'Ohio' }, { code: 'OK', name: 'Oklahoma' },
  { code: 'OR', name: 'Oregon' }, { code: 'PA', name: 'Pennsylvania' }, { code: 'RI', name: 'Rhode Island' },
  { code: 'SC', name: 'South Carolina' }, { code: 'SD', name: 'South Dakota' }, { code: 'TN', name: 'Tennessee' },
  { code: 'TX', name: 'Texas' }, { code: 'UT', name: 'Utah' }, { code: 'VT', name: 'Vermont' },
  { code: 'VA', name: 'Virginia' }, { code: 'WA', name: 'Washington' }, { code: 'WV', name: 'West Virginia' },
  { code: 'WI', name: 'Wisconsin' }, { code: 'WY', name: 'Wyoming' }, { code: 'DC', name: 'District of Columbia' },
  { code: 'PR', name: 'Puerto Rico' }, { code: 'GU', name: 'Guam' }, { code: 'VI', name: 'U.S. Virgin Islands' },
];

// ─────────────── Demo accounts (dev mock-IdP quick-pick) ───────────────
// Mirrors Backend/database/seeds/0002_rbac_orgs_users.sql — 100% synthetic.
export interface DemoAccount {
  email: string;
  name: string;
  role: string;
  scope?: string;
}
export const DEMO_ACCOUNTS: DemoAccount[] = [
  { email: 'sysadmin@ccfp.gov', name: 'Morgan Castellano', role: 'System Administrator' },
  { email: 'avery.thornton@ccfp.gov', name: 'Avery Thornton', role: 'CCFP Project Team Administrator' },
  { email: 'dana.whitfield@ccfp.gov', name: 'Dana Whitfield', role: 'CCFP Project Team' },
  { email: 'priya.ramanathan@ccfp.gov', name: 'Priya Ramanathan', role: 'CCFP Data Scientist' },
  { email: 'victor.delacruz@ccfp.gov', name: 'Victor De La Cruz', role: 'CCFP Database Administrator' },
  { email: 'helena.brandt@ccfp.gov', name: 'Helena Brandt', role: 'BTS CIPSEA Agent' },
  { email: 'marcus.ellingsworth@ccfp.gov', name: 'Marcus Ellingsworth', role: 'FMCSA CIPSEA Agent' },
  { email: 'nora.kowalczyk@ccfp.gov', name: 'Nora Kowalczyk', role: 'MCSAP CMV Inspector', scope: 'KS' },
  { email: 'elliot.fontaine@ccfp.gov', name: 'Elliot Fontaine', role: 'State CMV Data Analyst', scope: 'KS' },
  { email: 'tomasz.bialek@ccfp.gov', name: 'Tomasz Bialek', role: 'State User', scope: 'KS' },
  { email: 'rosa.menendez@ccfp.gov', name: 'Rosa Menendez', role: 'MCSAP CMV Inspector', scope: 'TX' },
  { email: 'grant.holloway@ccfp.gov', name: 'Grant Holloway', role: 'State CMV Data Analyst', scope: 'TX' },
  { email: 'linh.tran@ccfp.gov', name: 'Linh Tran', role: 'State CMV Data Analyst', scope: 'CA' },
  { email: 'omar.haddad@ccfp.gov', name: 'Omar Haddad', role: 'Federal User' },
  { email: 'public.demo@ccfp.gov', name: 'Public Demo Account', role: 'Public User' },
];
