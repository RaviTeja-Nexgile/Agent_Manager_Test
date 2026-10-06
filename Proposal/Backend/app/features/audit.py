"""Audit log access (documentation §10, §14)."""
from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common import ORMModel
from app.core.database import get_db
from app.core.pagination import Page, PageParams, paginate
from app.core.permissions import require
from app.core.security import CurrentUser
from app.models import AuditLog

router = APIRouter(tags=["audit"])


class AuditOut(ORMModel):
    id: uuid.UUID
    actor_user_id: uuid.UUID | None
    action: str
    entity_type: str
    entity_id: uuid.UUID | None
    crash_id: uuid.UUID | None
    after_state: Any | None
    occurred_at: dt.datetime


@router.get("/audit-logs", response_model=Page[AuditOut])
def list_audit_logs(
    params: PageParams = Depends(),
    crash_id: uuid.UUID | None = None,
    entity_type: str | None = None,
    actor_user_id: uuid.UUID | None = None,
    action: str | None = None,
    date_from: dt.datetime | None = None,
    date_to: dt.datetime | None = None,
    db: Session = Depends(get_db),
    current: CurrentUser = Depends(require("audit:read")),
):
    stmt = select(AuditLog).order_by(AuditLog.occurred_at.desc())
    if crash_id:
        stmt = stmt.where(AuditLog.crash_id == crash_id)
    if entity_type:
        stmt = stmt.where(AuditLog.entity_type == entity_type)
    if actor_user_id:
        stmt = stmt.where(AuditLog.actor_user_id == actor_user_id)
    if action:
        stmt = stmt.where(AuditLog.action == action)
    if date_from:
        stmt = stmt.where(AuditLog.occurred_at >= date_from)
    if date_to:
        stmt = stmt.where(AuditLog.occurred_at <= date_to)
    rows, total = paginate(db, stmt, params)
    return Page(items=rows, total=total, limit=params.limit, offset=params.offset)
