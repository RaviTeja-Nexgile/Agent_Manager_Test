"""Authentication & user context (documentation §12.1)."""
from __future__ import annotations

import datetime as dt
import uuid

from fastapi import APIRouter, Depends, Request, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common import ORMModel
from app.core.audit import record_audit
from app.core.config import settings
from app.core.database import get_db
from app.core.errors import Forbidden, Unauthorized
from app.core.security import (
    ROLE_GROUPS,
    CurrentUser,
    create_access_token,
    get_current_user,
    verify_password,
    _CIPSEA_PERMISSION,
    _PII_PERMISSIONS,
)
from app.models import User

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserSummary(ORMModel):
    id: uuid.UUID
    email: str
    full_name: str
    title: str | None = None
    organization_id: uuid.UUID | None = None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in_minutes: int
    user: UserSummary


class GroupingsResponse(BaseModel):
    """Role/access-group + sensitivity metadata served to the frontend (AUTH-8).

    Lets the UI derive its role groupings and PII-permission set from the backend
    instead of hardcoding them, so future phases/roles need no frontend change.
    ``pii_permission_codes`` is built from the single backend source
    ``_PII_PERMISSIONS`` so the API and ``can_view_sensitivity`` cannot drift.
    """

    role_groups: dict[str, list[str]]
    pii_permission_codes: list[str]
    cipsea_permission_code: str


class MeResponse(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str
    organization_id: uuid.UUID | None
    roles: list[str]
    permissions: list[str]
    # AUTH-3: access-group codes the caller belongs to (e.g. "PII", "NOPII",
    # "CIPSEA", "PUBLIC"). The frontend derives PII visibility from membership
    # in the "PII" group instead of re-listing permission codes.
    access_groups: list[str]
    allowed_states: list[str] | None
    study_ids: list[uuid.UUID]
    # AUTH-1: org scope (null == unrestricted by organization), mirroring
    # allowed_states. AUTH-2: study_restricted distinguishes a study-bound
    # principal from one that merely carries study_ids for display.
    org_ids: list[uuid.UUID] | None
    study_restricted: bool


@router.post("/login", response_model=TokenResponse)
def login(
    body: LoginRequest, request: Request, db: Session = Depends(get_db)
) -> TokenResponse:
    """Email + password login for development. Issues a JWT on success.

    The password is verified (bcrypt) against `users.password_hash`. In
    production this is replaced by the DOT-approved OIDC provider (PIV/CAC, MFA)
    and must be disabled (`CCFP_DEV_AUTH_ENABLED=false`).

    Every login attempt is audited (§10.1) — a ``LOGIN`` row on success and a
    ``LOGIN_FAILED`` row on failure. The submitted password is never recorded.
    """
    if not settings.dev_auth_enabled:
        raise Forbidden("Password login is disabled; use the configured identity provider.")
    ip = request.client.host if request.client else None
    ua = request.headers.get("user-agent")
    user = db.scalar(select(User).where(User.email == body.email))
    # Constant-ish behaviour: do not reveal whether the email exists.
    if user is None or not verify_password(body.password, user.password_hash):
        record_audit(
            db, actor=None, action="LOGIN_FAILED", entity_type="user",
            entity_id=user.id if user else None,
            after={"email": body.email, "reason": "invalid_credentials"},
            ip_address=ip, user_agent=ua,
        )
        db.commit()
        raise Unauthorized("Invalid email or password")
    if user.status != "ACTIVE":
        record_audit(
            db, actor=None, action="LOGIN_FAILED", entity_type="user",
            entity_id=user.id,
            after={"email": body.email, "reason": "inactive"},
            ip_address=ip, user_agent=ua,
        )
        db.commit()
        raise Unauthorized("User account is not active")
    user.last_login_at = dt.datetime.now(dt.timezone.utc)
    record_audit(
        db, actor=None, action="LOGIN", entity_type="user", entity_id=user.id,
        after={"email": user.email}, ip_address=ip, user_agent=ua,
    )
    db.commit()
    return TokenResponse(
        access_token=create_access_token(user),
        expires_in_minutes=settings.jwt_ttl_minutes,
        user=UserSummary.model_validate(user),
    )


@router.get("/me", response_model=MeResponse)
def me(current: CurrentUser = Depends(get_current_user)) -> MeResponse:
    return MeResponse(
        id=current.id,
        email=current.user.email,
        full_name=current.user.full_name,
        organization_id=current.organization_id,
        roles=sorted(current.role_codes),
        permissions=sorted(current.permissions),
        access_groups=sorted(current.access_groups),
        allowed_states=sorted(current.allowed_states) if current.allowed_states is not None else None,
        study_ids=sorted(current.study_ids),
        org_ids=sorted(current.org_ids) if current.org_ids is not None else None,
        study_restricted=current.study_restricted,
    )


@router.get("/groupings", response_model=GroupingsResponse)
def groupings(current: CurrentUser = Depends(get_current_user)) -> GroupingsResponse:
    """Serve the role-grouping map and PII-sensitivity permission codes (AUTH-8).

    Read-only and auth-gated like the other metadata routes (``list_roles`` /
    ``list_permissions``). No state change, so no audit row. The frontend loads
    this once at auth bootstrap and derives its groupings from it rather than
    hardcoding STATE/FEDERAL/CIPSEA/ADMIN arrays or the PII-code list.
    """
    return GroupingsResponse(
        role_groups={group: list(codes) for group, codes in ROLE_GROUPS.items()},
        pii_permission_codes=sorted(_PII_PERMISSIONS),
        cipsea_permission_code=_CIPSEA_PERMISSION,
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(current: CurrentUser = Depends(get_current_user)) -> None:
    """Stateless logout. The client discards the token; tokens expire by TTL.

    A production deployment would add a server-side token/refresh revocation list.
    """
    return None
