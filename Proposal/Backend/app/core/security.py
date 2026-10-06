"""Authentication: JWT issuance/validation and the current-user context.

Dev mode uses a mock-IdP login (POST /api/v1/auth/dev-login) that issues a JWT
for a seeded user. The structure is OIDC-swap-ready: replace `get_current_user`
token validation with the DOT-approved identity provider's JWKS verification and
disable `dev_auth_enabled`.
"""
from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass, field

import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.errors import Unauthorized
from app.enums import DataSensitivity
from app.models import User

bearer_scheme = HTTPBearer(auto_error=False)

# Password hashing for the dev email+password login path. bcrypt hashes are
# interchangeable with PostgreSQL pgcrypto's crypt(...gen_salt('bf')) form.
# Production replaces password verification with the DOT-approved OIDC provider.
_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain: str) -> str:
    return _pwd_context.hash(plain)


def verify_password(plain: str, hashed: str | None) -> bool:
    if not hashed:
        return False
    try:
        return _pwd_context.verify(plain, hashed)
    except (ValueError, TypeError):
        return False

# Permissions that grant visibility of restricted data categories. PII is
# visible to the roles that collect/manage crash records (inspectors, State
# analysts, project team) — not to report-only Federal/State/Public users
# (documentation §4, §14: "PII access only where authorized").
_PII_PERMISSIONS = {
    "initial_incident:read",
    "initial_incident:write",
    "data_mgmt:edit",
    "data_mgmt:read_raw",
    "crash:update",
}
_CIPSEA_PERMISSION = "bts:read"

# AUTH-8: role groupings, served to the frontend so the UI no longer hardcodes
# them. This is the single backend source of truth for which role codes belong
# to which audience grouping (mirrors the seeded role codes in
# seeds/0002_rbac_orgs_users.sql). Kept here next to _PII_PERMISSIONS so the
# sensitivity metadata and groupings are exposed from one place.
#
# The Jan-2026 BRD replaced the old footnoted user list with a
# formal four-tier addressing model — FMCSA Federal Users / Other Federal Users
# (BTS, NHTSA, NTSB) / Participating State Users / Public Users — and addresses
# every sharing requirement to one of them. FMCSA_FEDERAL and OTHER_FEDERAL are
# therefore first-class groupings. FEDERAL is retained as the union of the two
# so existing consumers (and FEDERAL-visibility reports) are unaffected.
FMCSA_FEDERAL_ROLES: list[str] = [
    "CCFP_PROJECT_TEAM",
    "CCFP_PROJECT_ADMIN",
    "CCFP_DB_ADMIN",
    # Still an FMCSA role and still analytically privileged. The BRD stopped
    # *naming* the Data Scientist among Federal Users; that is an omission in a
    # list, not an instruction to strip an existing role.
    "CCFP_DATA_SCIENTIST",
    "CCFP_SUPER_USER",
    "FMCSA_CIPSEA_AGENT",
    "FMCSA_HQ",
    "FMCSA_ENFORCEMENT",
]
# BTS, NHTSA and NTSB consume through BTS_CIPSEA_AGENT and the generic
# FEDERAL_USER role (omar.haddad sits in NHTSA, soren.vasquez in NTSB), so the
# tier is expressed by grouping rather than by a bespoke role per agency.
OTHER_FEDERAL_ROLES: list[str] = ["BTS_CIPSEA_AGENT", "FEDERAL_USER"]

ROLE_GROUPS: dict[str, list[str]] = {
    "STATE": ["MCSAP_INSPECTOR", "STATE_CMV_ANALYST", "STATE_USER"],
    "FMCSA_FEDERAL": FMCSA_FEDERAL_ROLES,
    "OTHER_FEDERAL": OTHER_FEDERAL_ROLES,
    # Union of the two federal tiers — retained so existing callers that ask for
    # "FEDERAL" keep getting the whole federal audience.
    "FEDERAL": FMCSA_FEDERAL_ROLES + OTHER_FEDERAL_ROLES,
    "CIPSEA": ["BTS_CIPSEA_AGENT", "FMCSA_CIPSEA_AGENT"],
    "ADMIN": ["CCFP_PROJECT_ADMIN", "SYSTEM_ADMIN"],
    "PUBLIC": ["PUBLIC_USER"],
}


def create_access_token(user: User) -> str:
    now = dt.datetime.now(dt.timezone.utc)
    payload = {
        "sub": str(user.id),
        "email": user.email,
        "name": user.full_name,
        "iat": now,
        "exp": now + dt.timedelta(minutes=settings.jwt_ttl_minutes),
        "iss": "ccfp-dev-idp",
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except jwt.PyJWTError as exc:  # noqa: BLE001
        raise Unauthorized(f"Invalid token: {exc}") from exc


@dataclass
class CurrentUser:
    """Authenticated principal with resolved permissions and scopes."""

    user: User
    permissions: set[str]
    allowed_states: set[str] | None  # None == unrestricted by state
    study_ids: set[uuid.UUID] = field(default_factory=set)
    role_codes: set[str] = field(default_factory=set)
    # AUTH-3: access-group codes (e.g. "PII", "NOPII", "CIPSEA", "PUBLIC")
    # resolved from the caller's roles. Data-sensitivity reach is derived from
    # this set, not from a hardcoded permission list. Seeded so today's
    # can_view_sensitivity answers are preserved exactly for every role.
    access_groups: set[str] = field(default_factory=set)
    # AUTH-1: organizations this principal is confined to. None == unrestricted
    # by organization (mirrors `allowed_states`). Populated only when the user
    # holds an ORGANIZATION-scoped assignment and no broader (GLOBAL) one.
    org_ids: set[uuid.UUID] | None = None
    # AUTH-2: True only when the user holds a STUDY-scoped assignment and no
    # broader (GLOBAL) one. When True the principal sees only `study_ids`;
    # when False the user is unrestricted by study (default-permissive).
    study_restricted: bool = False

    @property
    def id(self) -> uuid.UUID:
        return self.user.id

    @property
    def organization_id(self) -> uuid.UUID | None:
        return self.user.organization_id

    @property
    def is_public_only(self) -> bool:
        return self.role_codes == {"PUBLIC_USER"}

    def has_permission(self, code: str) -> bool:
        return code in self.permissions

    def has_any(self, *codes: str) -> bool:
        return any(c in self.permissions for c in codes)

    def can_access_state(self, state_code: str | None) -> bool:
        if self.allowed_states is None:
            return True
        return state_code in self.allowed_states

    def can_access_org(self, org_id: uuid.UUID | None) -> bool:
        if self.org_ids is None:
            return True
        return org_id in self.org_ids

    def can_access_study(self, study_id: uuid.UUID | None) -> bool:
        if not self.study_restricted:
            return True
        return study_id in self.study_ids

    def can_view_sensitivity(self, level: str) -> bool:
        # AUTH-3: data-sensitivity reach is derived from access-group
        # membership (seeded to preserve today's per-role behaviour exactly),
        # not from a hardcoded permission set. PUBLIC/INTERNAL are visible to
        # every authenticated principal; CIPSEA needs the CIPSEA group;
        # PII/SENSITIVE need the PII group.
        if level in (DataSensitivity.PUBLIC.value, DataSensitivity.INTERNAL.value):
            return True
        if level == DataSensitivity.CIPSEA.value:
            return "CIPSEA" in self.access_groups
        # PII / SENSITIVE
        return "PII" in self.access_groups


def role_chain(role) -> list:
    """The role plus every ancestor, nearest first.

    The SOO requires "role-based access aligned with the hierarchy of roles
    established in SafeSpect". `roles.parent_role_id` (migration 0021) carries
    that hierarchy; a role inherits its ancestors' permissions and access groups.

    Every seeded role currently has `parent_role_id IS NULL`, so this returns a
    single-element list and resolution is byte-for-byte the old flat behaviour.
    It only starts doing work once FMCSA supplies the real hierarchy.

    Cycle-safe: a visited set stops A -> B -> A from looping even though a DB
    trigger already rejects cycles at write time. Defence in depth, because an
    infinite loop here would hang every authenticated request.
    """
    chain = []
    seen: set[uuid.UUID] = set()
    node = role
    while node is not None and node.id not in seen:
        seen.add(node.id)
        chain.append(node)
        node = getattr(node, "parent", None)
    return chain


def _resolve(user: User) -> CurrentUser:
    permissions: set[str] = set()
    role_codes: set[str] = set()
    access_groups: set[str] = set()
    allowed_states: set[str] = set()
    study_ids: set[uuid.UUID] = set()
    org_ids: set[uuid.UUID] = set()
    unrestricted = False  # State: any non-STATE assignment leaves State unbound
    # AUTH-1/AUTH-2: an explicitly *broadening* assignment (GLOBAL) makes the
    # principal unrestricted by org and by study. ORGANIZATION/STUDY scope is
    # additive and default-permissive: it only restricts when no GLOBAL
    # assignment is present (mirrors the existing `allowed_states` pattern).
    global_scope = False
    org_restricting = False
    study_restricting = False
    for a in user.assignments:
        role_codes.add(a.role.code)
        # Walk the role and its ancestors so an inherited permission counts as
        # held. With every role's parent NULL (today) the chain is just the role
        # itself and this is identical to the previous direct lookup.
        for role in role_chain(a.role):
            for p in role.permissions:
                permissions.add(p.code)
            # AUTH-3: collect the role's access groups (eager-loaded like
            # permissions) so data-sensitivity reach is group-derived.
            for g in role.access_groups:
                access_groups.add(g.code)
        if a.scope_type == "STATE" and a.state_code:
            allowed_states.add(a.state_code)
        else:
            unrestricted = True  # GLOBAL / ORGANIZATION / STUDY scope = not state-bound
        if a.scope_type == "ORGANIZATION" and a.organization_id:
            org_ids.add(a.organization_id)
            org_restricting = True
        elif a.scope_type == "STUDY" and a.study_id:
            study_restricting = True
        elif a.scope_type == "GLOBAL":
            global_scope = True
        if a.study_id:
            study_ids.add(a.study_id)
    return CurrentUser(
        user=user,
        permissions=permissions,
        allowed_states=None if unrestricted or not allowed_states else allowed_states,
        study_ids=study_ids,
        role_codes=role_codes,
        access_groups=access_groups,
        # Restrict by org only when an ORGANIZATION assignment exists and no
        # GLOBAL assignment broadens it back to unrestricted.
        org_ids=None if (global_scope or not org_restricting) else org_ids,
        study_restricted=study_restricting and not global_scope,
    )


def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> CurrentUser:
    if creds is None or not creds.credentials:
        raise Unauthorized()
    payload = decode_token(creds.credentials)
    try:
        user_id = uuid.UUID(payload["sub"])
    except (KeyError, ValueError) as exc:
        raise Unauthorized("Malformed token subject") from exc
    user = db.get(User, user_id)
    if user is None:
        raise Unauthorized("User no longer exists")
    if user.status != "ACTIVE":
        raise Unauthorized("User account is not active")
    return _resolve(user)
