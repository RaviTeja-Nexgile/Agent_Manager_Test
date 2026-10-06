"""Audit logging helper (documentation §10, §14 — immutable audit of state changes)."""
from __future__ import annotations

import ipaddress
import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.core.security import CurrentUser
from app.models import AuditLog


def _valid_ip(value: str | None) -> str | None:
    if not value:
        return None
    try:
        ipaddress.ip_address(value)
        return value
    except ValueError:
        return None


def record_audit(
    db: Session,
    *,
    actor: CurrentUser | None,
    action: str,
    entity_type: str,
    entity_id: uuid.UUID | None = None,
    crash_id: uuid.UUID | None = None,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> AuditLog:
    """Append an audit log row. Caller commits within its own transaction."""
    log = AuditLog(
        actor_user_id=actor.id if actor else None,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        crash_id=crash_id,
        before_state=before,
        after_state=after,
        ip_address=_valid_ip(ip_address),
        user_agent=user_agent,
    )
    db.add(log)
    return log
