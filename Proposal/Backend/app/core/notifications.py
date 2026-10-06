"""Notification helper (documentation §8.11)."""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.enums import NotificationType
from app.models import Notification, Role, User, UserRoleAssignment


def create_notification(
    db: Session,
    *,
    recipient_user_id: uuid.UUID | None,
    notification_type: NotificationType | str,
    title: str,
    message: str | None = None,
    crash_id: uuid.UUID | None = None,
    channel: str = "IN_APP",
    status: str = "SENT",
) -> Notification:
    # Accept either a NotificationType member (preferred, single source of truth
    # per NOTI-9) or a bare string (backward compatibility for existing emitters).
    # `_Str.__str__` renders the bare value, so str() yields the same persisted
    # TEXT value for both a member and a plain string.
    n = Notification(
        recipient_user_id=recipient_user_id,
        notification_type=str(notification_type),
        title=title,
        message=message,
        crash_id=crash_id,
        channel=channel,
        status=status,
    )
    db.add(n)
    return n


def users_with_role(db: Session, role_code: str, state_code: str | None = None) -> list[User]:
    """Find active users holding a role, optionally scoped to a State."""
    stmt = (
        select(User)
        .join(UserRoleAssignment, UserRoleAssignment.user_id == User.id)
        .join(Role, Role.id == UserRoleAssignment.role_id)
        .where(Role.code == role_code, User.status == "ACTIVE")
    )
    if state_code is not None:
        stmt = stmt.where(
            (UserRoleAssignment.state_code == state_code)
            | (UserRoleAssignment.scope_type != "STATE")
        )
    return list(db.scalars(stmt).unique().all())
