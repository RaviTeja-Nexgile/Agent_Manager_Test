"""Administration: users, roles, permissions, organizations (documentation §4, §8.1, §10)."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common import ORMModel
from app.core.audit import record_audit
from app.core.database import get_db
from app.core.errors import BadRequest, Conflict, NotFound
from app.core.pagination import Page, PageParams, paginate
from app.core.permissions import require, scope_org_query
from app.core.security import CurrentUser, get_current_user, hash_password
from app.enums import AssignmentScope, OrganizationType, UserStatus
from app.models import (
    Organization,
    Permission,
    RefUsState,
    Role,
    RolePermission,
    Study,
    User,
    UserRoleAssignment,
)

router = APIRouter(tags=["admin"])


# --------------------------------------------------------------------------- schemas
class OrganizationIn(BaseModel):
    name: str
    org_type: OrganizationType
    state_code: str | None = None
    parent_id: uuid.UUID | None = None
    description: str | None = None


class OrganizationOut(ORMModel):
    id: uuid.UUID
    name: str
    org_type: str
    state_code: str | None
    parent_id: uuid.UUID | None
    description: str | None
    is_active: bool


class UserIn(BaseModel):
    email: EmailStr
    full_name: str
    organization_id: uuid.UUID | None = None
    title: str | None = None
    phone: str | None = None
    idp_subject: str | None = None
    piv_cac_required: bool = False
    # Optional initial password for the dev login path; hashed before storage.
    password: str | None = None


class UserUpdate(BaseModel):
    full_name: str | None = None
    organization_id: uuid.UUID | None = None
    title: str | None = None
    phone: str | None = None
    status: UserStatus | None = None
    piv_cac_required: bool | None = None
    # Optional password reset for the dev login path; hashed before storage.
    password: str | None = None


class UserOut(ORMModel):
    id: uuid.UUID
    email: str
    full_name: str
    organization_id: uuid.UUID | None
    title: str | None
    phone: str | None
    status: str
    mfa_enabled: bool
    piv_cac_required: bool


class PermissionOut(ORMModel):
    id: uuid.UUID
    code: str
    name: str
    category: str
    description: str | None


class RoleOut(ORMModel):
    id: uuid.UUID
    code: str
    name: str
    description: str | None
    is_system: bool


class RoleDetail(RoleOut):
    permissions: list[PermissionOut]


class RoleIn(BaseModel):
    code: str
    name: str
    description: str | None = None


class RoleUpdate(BaseModel):
    name: str | None = None
    description: str | None = None


class PermissionIn(BaseModel):
    code: str
    name: str
    category: str
    description: str | None = None


class RolePermissionsIn(BaseModel):
    permission_codes: list[str]


class AssignmentIn(BaseModel):
    role_code: str
    scope_type: AssignmentScope = AssignmentScope.GLOBAL
    state_code: str | None = None
    organization_id: uuid.UUID | None = None
    study_id: uuid.UUID | None = None


class AssignmentOut(ORMModel):
    id: uuid.UUID
    role_id: uuid.UUID
    scope_type: str
    state_code: str | None
    organization_id: uuid.UUID | None
    study_id: uuid.UUID | None


# --------------------------------------------------------------------------- organizations
@router.get("/organizations", response_model=Page[OrganizationOut])
def list_organizations(
    params: PageParams = Depends(),
    org_type: OrganizationType | None = None,
    db: Session = Depends(get_db),
    current: CurrentUser = Depends(get_current_user),
):
    stmt = select(Organization).order_by(Organization.name)
    if org_type:
        stmt = stmt.where(Organization.org_type == org_type.value)
    rows, total = paginate(db, stmt, params)
    return Page(items=rows, total=total, limit=params.limit, offset=params.offset)


@router.post("/organizations", response_model=OrganizationOut, status_code=201)
def create_organization(
    body: OrganizationIn, db: Session = Depends(get_db),
    current: CurrentUser = Depends(require("admin:users", "admin:system")),
):
    org = Organization(**body.model_dump())
    db.add(org)
    db.flush()
    record_audit(db, actor=current, action="CREATE", entity_type="organization", entity_id=org.id)
    db.commit()
    return org


@router.get("/organizations/{org_id}", response_model=OrganizationOut)
def get_organization(org_id: uuid.UUID, db: Session = Depends(get_db), current: CurrentUser = Depends(get_current_user)):
    org = db.get(Organization, org_id)
    if org is None:
        raise NotFound("Organization")
    return org


@router.patch("/organizations/{org_id}", response_model=OrganizationOut)
def update_organization(
    org_id: uuid.UUID, body: OrganizationIn, db: Session = Depends(get_db),
    current: CurrentUser = Depends(require("admin:users", "admin:system")),
):
    org = db.get(Organization, org_id)
    if org is None:
        raise NotFound("Organization")
    for k, v in body.model_dump().items():
        setattr(org, k, v)
    record_audit(db, actor=current, action="UPDATE", entity_type="organization", entity_id=org.id)
    db.commit()
    return org


# --------------------------------------------------------------------------- users
@router.get("/users", response_model=Page[UserOut])
def list_users(
    params: PageParams = Depends(),
    q: str | None = None,
    organization_id: uuid.UUID | None = None,
    db: Session = Depends(get_db),
    current: CurrentUser = Depends(require("admin:users")),
):
    stmt = select(User).order_by(User.full_name)
    # AUTH-1: an org-scoped admin only sees users in their authorized org(s).
    # Additive and default-permissive — an unrestricted admin (org_ids is None)
    # is unaffected and continues to see every user.
    stmt = scope_org_query(stmt, current, User.organization_id)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(User.full_name.ilike(like) | User.email.ilike(like))
    if organization_id:
        stmt = stmt.where(User.organization_id == organization_id)
    rows, total = paginate(db, stmt, params)
    return Page(items=rows, total=total, limit=params.limit, offset=params.offset)


@router.post("/users", response_model=UserOut, status_code=201)
def create_user(
    body: UserIn, db: Session = Depends(get_db), current: CurrentUser = Depends(require("admin:users"))
):
    if db.scalar(select(User).where(User.email == body.email)):
        raise Conflict("A user with that email already exists")
    data = body.model_dump()
    password = data.pop("password", None)
    user = User(**data)
    if password:
        user.password_hash = hash_password(password)
    db.add(user)
    db.flush()
    record_audit(db, actor=current, action="CREATE", entity_type="user", entity_id=user.id)
    db.commit()
    return user


@router.get("/users/{user_id}", response_model=UserOut)
def get_user(user_id: uuid.UUID, db: Session = Depends(get_db), current: CurrentUser = Depends(require("admin:users"))):
    user = db.get(User, user_id)
    if user is None:
        raise NotFound("User")
    return user


@router.patch("/users/{user_id}", response_model=UserOut)
def update_user(
    user_id: uuid.UUID, body: UserUpdate, db: Session = Depends(get_db),
    current: CurrentUser = Depends(require("admin:users")),
):
    user = db.get(User, user_id)
    if user is None:
        raise NotFound("User")
    updates = body.model_dump(exclude_unset=True)
    password = updates.pop("password", None)
    for k, v in updates.items():
        setattr(user, k, v.value if hasattr(v, "value") else v)
    if password:
        user.password_hash = hash_password(password)
    record_audit(db, actor=current, action="UPDATE", entity_type="user", entity_id=user.id)
    db.commit()
    return user


@router.post("/users/{user_id}/deactivate", response_model=UserOut)
def deactivate_user(
    user_id: uuid.UUID, db: Session = Depends(get_db), current: CurrentUser = Depends(require("admin:users"))
):
    user = db.get(User, user_id)
    if user is None:
        raise NotFound("User")
    user.status = UserStatus.INACTIVE.value
    record_audit(db, actor=current, action="DEACTIVATE", entity_type="user", entity_id=user.id)
    db.commit()
    return user


# --------------------------------------------------------------------------- roles & permissions
@router.get("/roles", response_model=list[RoleOut])
def list_roles(db: Session = Depends(get_db), current: CurrentUser = Depends(get_current_user)):
    return list(db.scalars(select(Role).order_by(Role.code)))


@router.get("/roles/{role_id}", response_model=RoleDetail)
def get_role(role_id: uuid.UUID, db: Session = Depends(get_db), current: CurrentUser = Depends(get_current_user)):
    role = db.get(Role, role_id)
    if role is None:
        raise NotFound("Role")
    return role


@router.get("/permissions", response_model=list[PermissionOut])
def list_permissions(db: Session = Depends(get_db), current: CurrentUser = Depends(get_current_user)):
    return list(db.scalars(select(Permission).order_by(Permission.category, Permission.code)))


@router.post("/roles", response_model=RoleOut, status_code=201)
def create_role(
    body: RoleIn, db: Session = Depends(get_db),
    current: CurrentUser = Depends(require("admin:roles")),
):
    if db.scalar(select(Role).where(Role.code == body.code)):
        raise Conflict("A role with that code already exists")
    role = Role(code=body.code, name=body.name, description=body.description, is_system=False)
    db.add(role)
    db.flush()
    record_audit(db, actor=current, action="CREATE", entity_type="role", entity_id=role.id)
    db.commit()
    return role


@router.patch("/roles/{role_id}", response_model=RoleOut)
def update_role(
    role_id: uuid.UUID, body: RoleUpdate, db: Session = Depends(get_db),
    current: CurrentUser = Depends(require("admin:roles")),
):
    role = db.get(Role, role_id)
    if role is None:
        raise NotFound("Role")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(role, k, v)
    record_audit(db, actor=current, action="UPDATE", entity_type="role", entity_id=role.id)
    db.commit()
    return role


@router.delete("/roles/{role_id}", status_code=204)
def delete_role(
    role_id: uuid.UUID, db: Session = Depends(get_db),
    current: CurrentUser = Depends(require("admin:roles")),
):
    role = db.get(Role, role_id)
    if role is None:
        raise NotFound("Role")
    if role.is_system:
        raise BadRequest("System roles cannot be deleted")
    if db.scalar(select(UserRoleAssignment).where(UserRoleAssignment.role_id == role_id)):
        raise Conflict("Role is still assigned to one or more users")
    db.delete(role)
    record_audit(db, actor=current, action="DELETE", entity_type="role", entity_id=role_id)
    db.commit()
    return None


@router.put("/roles/{role_id}/permissions", response_model=RoleDetail)
def set_role_permissions(
    role_id: uuid.UUID, body: RolePermissionsIn, db: Session = Depends(get_db),
    current: CurrentUser = Depends(require("admin:roles")),
):
    role = db.get(Role, role_id)
    if role is None:
        raise NotFound("Role")
    codes = list(dict.fromkeys(body.permission_codes))  # de-duplicate, preserve order
    perms = list(db.scalars(select(Permission).where(Permission.code.in_(codes)))) if codes else []
    found = {p.code for p in perms}
    missing = [c for c in codes if c not in found]
    if missing:
        raise BadRequest(f"Unknown permission code(s): {', '.join(missing)}")
    # Replace the role's permission mappings to match the requested set.
    db.query(RolePermission).filter(RolePermission.role_id == role_id).delete(synchronize_session=False)
    for p in perms:
        db.add(RolePermission(role_id=role_id, permission_id=p.id))
    db.flush()
    # The role.permissions relationship was selectin-loaded; expire it so the
    # response reflects the new mapping rather than the stale cached collection.
    db.expire(role, ["permissions"])
    record_audit(db, actor=current, action="UPDATE", entity_type="role", entity_id=role.id)
    db.commit()
    return role


@router.post("/permissions", response_model=PermissionOut, status_code=201)
def create_permission(
    body: PermissionIn, db: Session = Depends(get_db),
    current: CurrentUser = Depends(require("admin:roles")),
):
    if db.scalar(select(Permission).where(Permission.code == body.code)):
        raise Conflict("A permission with that code already exists")
    perm = Permission(**body.model_dump())
    db.add(perm)
    db.flush()
    record_audit(db, actor=current, action="CREATE", entity_type="permission", entity_id=perm.id)
    db.commit()
    return perm


# --------------------------------------------------------------------------- role assignments
@router.get("/users/{user_id}/roles", response_model=list[AssignmentOut])
def list_user_roles(user_id: uuid.UUID, db: Session = Depends(get_db), current: CurrentUser = Depends(require("admin:users", "admin:roles"))):
    user = db.get(User, user_id)
    if user is None:
        raise NotFound("User")
    return list(db.scalars(select(UserRoleAssignment).where(UserRoleAssignment.user_id == user_id)))


@router.post("/users/{user_id}/roles", response_model=AssignmentOut, status_code=201)
def assign_role(
    user_id: uuid.UUID, body: AssignmentIn, db: Session = Depends(get_db),
    current: CurrentUser = Depends(require("admin:roles")),
):
    user = db.get(User, user_id)
    if user is None:
        raise NotFound("User")
    role = db.scalar(select(Role).where(Role.code == body.role_code))
    if role is None:
        raise BadRequest(f"Unknown role code: {body.role_code}")
    # A scoped assignment without its target would silently resolve to an
    # UNRESTRICTED principal (security._resolve only restricts when the target
    # column is set) — require the target for every non-GLOBAL scope, and
    # reject dangling references outright.
    if body.scope_type == AssignmentScope.STATE and not body.state_code:
        raise BadRequest("state_code is required for a STATE-scoped assignment")
    if body.scope_type == AssignmentScope.ORGANIZATION and body.organization_id is None:
        raise BadRequest("organization_id is required for an ORGANIZATION-scoped assignment")
    if body.scope_type == AssignmentScope.STUDY and body.study_id is None:
        raise BadRequest("study_id is required for a STUDY-scoped assignment")
    if body.state_code is not None and db.get(RefUsState, body.state_code) is None:
        raise BadRequest("Unknown state_code")
    if body.organization_id is not None and db.get(Organization, body.organization_id) is None:
        raise BadRequest("Unknown organization_id")
    if body.study_id is not None and db.get(Study, body.study_id) is None:
        raise BadRequest("Unknown study_id")
    assignment = UserRoleAssignment(
        user_id=user_id, role_id=role.id, scope_type=body.scope_type.value,
        state_code=body.state_code, organization_id=body.organization_id,
        study_id=body.study_id, granted_by=current.id,
    )
    db.add(assignment)
    db.flush()
    record_audit(db, actor=current, action="GRANT_ROLE", entity_type="user_role_assignment", entity_id=assignment.id)
    db.commit()
    return assignment


@router.delete("/users/{user_id}/roles/{assignment_id}", status_code=204)
def revoke_role(
    user_id: uuid.UUID, assignment_id: uuid.UUID, db: Session = Depends(get_db),
    current: CurrentUser = Depends(require("admin:roles")),
):
    assignment = db.get(UserRoleAssignment, assignment_id)
    if assignment is None or assignment.user_id != user_id:
        raise NotFound("Assignment")
    db.delete(assignment)
    record_audit(db, actor=current, action="REVOKE_ROLE", entity_type="user_role_assignment", entity_id=assignment_id)
    db.commit()
    return None
