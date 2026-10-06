/**
 * Role + permission based access control helpers.
 *
 * `CurrentUser` (from GET /auth/me) carries `roles` (the 12 role codes),
 * `permissions` (the 42 permission codes), and `allowed_states` (null = all
 * States, else the State scope). Gating is permission-first so the UI never
 * offers an action the backend will 403 — see Backend/app/core/permissions.py.
 */

import type { CurrentUser, Groupings } from './types';

export type Role =
  | 'MCSAP_INSPECTOR'
  | 'STATE_CMV_ANALYST'
  | 'CCFP_PROJECT_TEAM'
  | 'CCFP_PROJECT_ADMIN'
  | 'CCFP_DB_ADMIN'
  | 'CCFP_DATA_SCIENTIST'
  // FMCSA Program Office resource, co-holder with the Project Team
  // of CRUD on dashboards, visualizations, reports and tables.
  | 'CCFP_SUPER_USER'
  // Promoted from footnote examples to first-class members of the
  // FMCSA Federal audience tier.
  | 'FMCSA_HQ'
  | 'FMCSA_ENFORCEMENT'
  | 'BTS_CIPSEA_AGENT'
  | 'FMCSA_CIPSEA_AGENT'
  | 'FEDERAL_USER'
  | 'STATE_USER'
  | 'PUBLIC_USER'
  | 'SYSTEM_ADMIN';

export const ROLE_LABEL: Record<Role, string> = {
  MCSAP_INSPECTOR: 'MCSAP CMV Inspector',
  STATE_CMV_ANALYST: 'State CMV Data Analyst',
  CCFP_PROJECT_TEAM: 'CCFP Project Team',
  CCFP_PROJECT_ADMIN: 'CCFP Project Team Administrator',
  CCFP_DB_ADMIN: 'CCFP Database Administrator',
  CCFP_DATA_SCIENTIST: 'CCFP Data Scientist',
  CCFP_SUPER_USER: 'CCFP Super User',
  FMCSA_HQ: 'FMCSA HQ',
  FMCSA_ENFORCEMENT: 'FMCSA Enforcement',
  BTS_CIPSEA_AGENT: 'BTS CIPSEA Agent',
  FMCSA_CIPSEA_AGENT: 'FMCSA CIPSEA Agent',
  FEDERAL_USER: 'Federal User',
  STATE_USER: 'State User',
  PUBLIC_USER: 'Public User',
  SYSTEM_ADMIN: 'System Administrator',
};

// ─────────────── Data-driven role/access groupings (AUTH-8) ───────────────
//
// Groupings and the PII-permission set are served by GET /auth/groupings (the
// single backend source of truth) and loaded once at auth bootstrap via
// `setGroupings`. The frontend no longer authors these — the values below are
// only a SAFE FALLBACK used until the API responds (or if the call fails), so
// the app still renders. `ADMIN_ROLES` (consumed synchronously by router.tsx /
// AppShell.tsx) is a stable array reference that `setGroupings` mutates IN PLACE
// so those consumers pick up the server-provided values without a code change.

/** Default PII permission codes — mirrors the backend `_PII_PERMISSIONS`; used
 * only until the served `pii_permission_codes` replaces it. */
const DEFAULT_PII_PERMISSION_CODES = [
  'initial_incident:read',
  'initial_incident:write',
  'data_mgmt:edit',
  'data_mgmt:read_raw',
  'crash:update',
];

// Mirrors ROLE_GROUPS in Backend/app/core/security.py. The Jan-2026 BRD
// addresses every sharing requirement to one of four audience tiers, so the two
// federal tiers are first-class; FEDERAL is their union, kept so existing
// consumers are unaffected.
const FMCSA_FEDERAL_ROLES: Role[] = [
  'CCFP_PROJECT_TEAM',
  'CCFP_PROJECT_ADMIN',
  'CCFP_DB_ADMIN',
  'CCFP_DATA_SCIENTIST',
  'CCFP_SUPER_USER',
  'FMCSA_CIPSEA_AGENT',
  'FMCSA_HQ',
  'FMCSA_ENFORCEMENT',
];
const OTHER_FEDERAL_ROLES: Role[] = ['BTS_CIPSEA_AGENT', 'FEDERAL_USER'];

/** Server-provided groupings, populated by `setGroupings`. */
let GROUPINGS: Groupings = {
  role_groups: {
    STATE: ['MCSAP_INSPECTOR', 'STATE_CMV_ANALYST', 'STATE_USER'],
    FMCSA_FEDERAL: FMCSA_FEDERAL_ROLES,
    OTHER_FEDERAL: OTHER_FEDERAL_ROLES,
    FEDERAL: [...FMCSA_FEDERAL_ROLES, ...OTHER_FEDERAL_ROLES],
    CIPSEA: ['BTS_CIPSEA_AGENT', 'FMCSA_CIPSEA_AGENT'],
    ADMIN: ['CCFP_PROJECT_ADMIN', 'SYSTEM_ADMIN'],
    PUBLIC: ['PUBLIC_USER'],
  },
  pii_permission_codes: DEFAULT_PII_PERMISSION_CODES,
  cipsea_permission_code: 'bts:read',
};

/** Stable reference consumed by router.tsx / AppShell.tsx; mutated in place by
 * `setGroupings` so the admin-nav grouping stays data-driven. */
export const ADMIN_ROLES: Role[] = [...((GROUPINGS.role_groups.ADMIN ?? []) as Role[])];

/** Replace the live array's contents (preserve the reference). */
function replaceInPlace(target: Role[], next: Role[]): void {
  target.length = 0;
  target.push(...next);
}

/** Load the server-provided groupings (call once at auth bootstrap). Falls back
 * to the defaults above if `next` is missing/partial so the app always renders. */
export function setGroupings(next: Groupings | null | undefined): void {
  if (!next) return;
  GROUPINGS = {
    role_groups: next.role_groups ?? GROUPINGS.role_groups,
    pii_permission_codes: next.pii_permission_codes ?? GROUPINGS.pii_permission_codes,
    cipsea_permission_code: next.cipsea_permission_code ?? GROUPINGS.cipsea_permission_code,
  };
  replaceInPlace(ADMIN_ROLES, (GROUPINGS.role_groups.ADMIN ?? []) as Role[]);
}

/** Read a role grouping (STATE / FEDERAL / CIPSEA / ADMIN / PUBLIC) as Role[]. */
export function roleGroup(group: string): Role[] {
  return (GROUPINGS.role_groups[group] ?? []) as Role[];
}

// Display priority when a user holds multiple roles.
const PRIMARY_ROLE_PRIORITY: Role[] = [
  'SYSTEM_ADMIN',
  'CCFP_PROJECT_ADMIN',
  'CCFP_SUPER_USER',
  'CCFP_PROJECT_TEAM',
  'CCFP_DATA_SCIENTIST',
  'CCFP_DB_ADMIN',
  'FMCSA_CIPSEA_AGENT',
  'BTS_CIPSEA_AGENT',
  'STATE_CMV_ANALYST',
  'MCSAP_INSPECTOR',
  'FMCSA_HQ',
  'FMCSA_ENFORCEMENT',
  'FEDERAL_USER',
  'STATE_USER',
  'PUBLIC_USER',
];

// ─────────────── Role helpers ───────────────
export function hasRole(user: CurrentUser | null | undefined, allowed: Role[]): boolean {
  if (!user) return false;
  if (!allowed || allowed.length === 0) return true;
  const set = new Set(user.roles);
  return allowed.some((r) => set.has(r));
}

export function getPrimaryRole(user: CurrentUser | null | undefined): Role | null {
  if (!user || !user.roles?.length) return null;
  const set = new Set(user.roles as Role[]);
  for (const r of PRIMARY_ROLE_PRIORITY) if (set.has(r)) return r;
  return (user.roles[0] as Role) ?? null;
}

export function getPrimaryRoleLabel(user: CurrentUser | null | undefined): string {
  const r = getPrimaryRole(user);
  return r ? ROLE_LABEL[r] : 'User';
}

// ─────────────── Permission helpers (preferred) ───────────────
export function hasPermission(user: CurrentUser | null | undefined, code: string): boolean {
  if (!user) return false;
  return user.permissions?.includes(code) ?? false;
}

export function hasAnyPermission(
  user: CurrentUser | null | undefined,
  codes: string[],
): boolean {
  if (!user) return false;
  if (!codes || codes.length === 0) return true;
  const set = new Set(user.permissions ?? []);
  return codes.some((c) => set.has(c));
}

// ─────────────── Scope helpers ───────────────
/** State scope: null allowed_states = unrestricted (all States). */
export function canViewState(
  user: CurrentUser | null | undefined,
  stateCode: string | null | undefined,
): boolean {
  if (!user) return false;
  if (user.allowed_states === null) return true;
  if (!stateCode) return true;
  return user.allowed_states.includes(stateCode);
}

export function isStateScoped(user: CurrentUser | null | undefined): boolean {
  return Boolean(user && user.allowed_states !== null);
}

export function canViewPii(user: CurrentUser | null | undefined): boolean {
  // AUTH-3: PII visibility is derived from access-group membership served by
  // /auth/me (single source of truth shared with the backend) instead of
  // re-listing the PII permission codes.
  return (user?.access_groups ?? []).includes("PII");
}

export function isPublicOnly(user: CurrentUser | null | undefined): boolean {
  return Boolean(user && user.roles.length === 1 && user.roles[0] === 'PUBLIC_USER');
}
