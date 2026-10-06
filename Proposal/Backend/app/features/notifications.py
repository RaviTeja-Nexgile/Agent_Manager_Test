"""Notifications (documentation §8.11)."""
from __future__ import annotations

import datetime as dt
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common import ORMModel
from app.core.database import get_db
from app.core.errors import NotFound
from app.core.security import CurrentUser, get_current_user
from app.models import Notification

router = APIRouter(prefix="/notifications", tags=["notifications"])


class NotificationOut(ORMModel):
    id: uuid.UUID
    notification_type: str
    crash_id: uuid.UUID | None
    title: str
    message: str | None
    channel: str
    status: str
    created_at: dt.datetime
    read_at: dt.datetime | None


@router.get("", response_model=list[NotificationOut])
def my_notifications(
    unread_only: bool = False, db: Session = Depends(get_db), current: CurrentUser = Depends(get_current_user)
):
    stmt = select(Notification).where(Notification.recipient_user_id == current.id).order_by(Notification.created_at.desc())
    if unread_only:
        stmt = stmt.where(Notification.read_at.is_(None))
    return list(db.scalars(stmt))


@router.patch("/{notification_id}/read", response_model=NotificationOut)
def mark_read(notification_id: uuid.UUID, db: Session = Depends(get_db), current: CurrentUser = Depends(get_current_user)):
    n = db.get(Notification, notification_id)
    if n is None or n.recipient_user_id != current.id:
        raise NotFound("Notification")
    n.read_at = dt.datetime.now(dt.timezone.utc)
    n.status = "READ"
    db.commit()
    return n


@router.post("/read-all")
def mark_all_read(db: Session = Depends(get_db), current: CurrentUser = Depends(get_current_user)):
    now = dt.datetime.now(dt.timezone.utc)
    updated = (
        db.query(Notification)
        .filter(Notification.recipient_user_id == current.id, Notification.read_at.is_(None))
        .update({"read_at": now, "status": "READ"})
    )
    db.commit()
    return {"marked_read": updated}
