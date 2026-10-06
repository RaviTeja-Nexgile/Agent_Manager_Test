"""Authorization dependencies and query scope filtering.

`require(*codes)` returns a FastAPI dependency that yields the CurrentUser when
it holds at least one of the listed permission codes, else 403. `scope_filter`
narrows crash queries by the user's State scope. Permission codes match the 42
seeded in seeds/0002_rbac_orgs_users.sql.
"""
from __future__ import annotations

from collections.abc import Callable

from fastapi import Depends

from app.core.errors import Forbidden
from app.core.security import CurrentUser, get_current_user
from app.models import Crash


def require(*codes: str) -> Callable[..., CurrentUser]:
    """Dependency factory: require any one of the given permission codes."""

    def dependency(current: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if not current.has_any(*codes):
            raise Forbidden(f"Requires permission: {' or '.join(codes)}")
        return current

    return dependency


def require_all(*codes: str) -> Callable[..., CurrentUser]:
    def dependency(current: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        missing = [c for c in codes if not current.has_permission(c)]
        if missing:
            raise Forbidden(f"Requires permissions: {', '.join(missing)}")
        return current

    return dependency


def scope_crash_query(stmt, current: CurrentUser):
    """Apply State-scope visibility to a crashes SELECT statement."""
    if current.allowed_states is None:
        return stmt
    return stmt.where(Crash.state_code.in_(current.allowed_states))


def scope_org_query(stmt, current: CurrentUser, org_column):
    """Apply organization-scope visibility to a SELECT statement (AUTH-1).

    Additive and default-permissive, mirroring ``scope_crash_query``: a user
    with ``org_ids is None`` (no ORGANIZATION-scoped assignment, or a broadening
    GLOBAL one) is unrestricted and the statement is returned unchanged. Only an
    explicitly org-restricted principal is filtered to ``org_column.in_(...)``.
    """
    if current.org_ids is None:
        return stmt
    return stmt.where(org_column.in_(current.org_ids))


def scope_study_query(stmt, current: CurrentUser):
    """Apply study/study-phase-scope visibility to a crashes SELECT (AUTH-2).

    Additive and default-permissive: a user who is not study-restricted (no
    STUDY-scoped assignment, or a broadening GLOBAL one) sees all studies and
    the statement is returned unchanged. Only an explicitly study-restricted
    principal is filtered to ``Crash.study_id.in_(current.study_ids)``.
    """
    if not current.study_restricted or not current.study_ids:
        return stmt
    return stmt.where(Crash.study_id.in_(current.study_ids))


def assert_crash_access(crash: Crash, current: CurrentUser) -> None:
    """Raise 403 if the user's State scope excludes this crash."""
    if not current.can_access_state(crash.state_code):
        raise Forbidden("Crash is outside your authorized State scope")


def assert_study_access(crash: Crash, current: CurrentUser) -> None:
    """Raise 403 if the user's study scope excludes this crash (AUTH-2)."""
    if not current.can_access_study(crash.study_id):
        raise Forbidden("Crash is outside your authorized study scope")
