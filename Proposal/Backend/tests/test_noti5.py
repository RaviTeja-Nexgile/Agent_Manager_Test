"""NOTI-5: in-process detector for crashes missing an Initial Incident Form.

Per §8.11 / §12.4 the platform must flag crashes that have aged past the IIF
window (24-48 h) with no submitted IIF. These tests cover the reusable worker
`scan_crashes_missing_iif` and the admin-triggered endpoint:

  * positive      — a stale crash (backdated created_at) with no submitted IIF is
                    flagged and a MISSING_IIF notification reaches the State analyst;
  * negative      — a crash WITH a submitted IIF, and a crash NEWER than the
                    window, are NOT flagged and produce no MISSING_IIF;
  * idempotency   — re-running does not duplicate the notification;
  * authorization — POST /crashes/scan-missing-iif is 200 for the project admin
                    and 403 for a user lacking the gating permission (public).

All tests run inside the rolled-back `db` session fixture; setup rows are
committed first (commit() is a SAVEPOINT release in test mode) so the worker's
own commit nests inside the test transaction. Robust to seed drift: each crash is
created in-transaction (only PHASE1-HDT is assumed seeded) and assertions scope to
the crash created here, so pre-existing stale seed crashes never make them flaky.
"""
from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import select

from app import workers
from app.core.notifications import users_with_role
from app.models import Crash, InitialIncidentForm, Notification, Study
from tests.conftest import ADMIN, ANALYST_KS, PUBLIC


API = "/api/v1"


def _make_crash(db, *, age_hours: float, state_code: str = "KS") -> Crash:
    """Create a crash whose created_at is `age_hours` in the past."""
    study = db.scalar(select(Study).where(Study.code == "PHASE1-HDT"))
    assert study is not None, "PHASE1-HDT study must be seeded"
    crash = Crash(
        ccfp_identifier=f"CCFP-TEST-{uuid.uuid4().hex[:12]}",
        study_id=study.id,
        state_code=state_code,
        num_fatalities=1,
        created_at=dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=age_hours),
    )
    db.add(crash)
    db.flush()
    return crash


def _missing_iif_notifs(db, crash_id: uuid.UUID) -> list[Notification]:
    return list(
        db.scalars(
            select(Notification).where(
                Notification.crash_id == crash_id,
                Notification.notification_type == "MISSING_IIF",
            )
        )
    )


# --------------------------------------------------------------------------- positive
def test_stale_crash_without_iif_is_flagged(db):
    crash = _make_crash(db, age_hours=72)  # older than a 1h window
    db.commit()

    result = workers.scan_crashes_missing_iif(db=db, window_hours=1)
    assert result["flagged"] >= 1

    notifs = _missing_iif_notifs(db, crash.id)
    assert len(notifs) >= 1
    # The notification reaches a State CMV Data Analyst in the crash's State.
    analyst_ids = {a.id for a in users_with_role(db, "STATE_CMV_ANALYST", state_code="KS")}
    assert analyst_ids, "expected at least one KS analyst seeded"
    assert {n.recipient_user_id for n in notifs} & analyst_ids


# --------------------------------------------------------------------------- negative: submitted IIF
def test_crash_with_submitted_iif_is_not_flagged(db):
    crash = _make_crash(db, age_hours=72)
    db.add(InitialIncidentForm(crash_id=crash.id, status="SUBMITTED"))
    db.flush()
    db.commit()

    workers.scan_crashes_missing_iif(db=db, window_hours=1)
    assert _missing_iif_notifs(db, crash.id) == []


# --------------------------------------------------------------------------- negative: newer than window
def test_recent_crash_is_not_flagged(db):
    crash = _make_crash(db, age_hours=0)  # just created -> inside any positive window
    db.commit()

    workers.scan_crashes_missing_iif(db=db, window_hours=48)
    assert _missing_iif_notifs(db, crash.id) == []


# --------------------------------------------------------------------------- idempotency
def test_rescan_does_not_duplicate(db):
    crash = _make_crash(db, age_hours=72)
    db.commit()

    workers.scan_crashes_missing_iif(db=db, window_hours=1)
    first = len(_missing_iif_notifs(db, crash.id))
    assert first >= 1

    # Re-running must not spam duplicates for the same (still-unread) crash.
    workers.scan_crashes_missing_iif(db=db, window_hours=1)
    second = len(_missing_iif_notifs(db, crash.id))
    assert second == first


# --------------------------------------------------------------------------- endpoint authorization
def test_scan_endpoint_authorization(client, auth):
    # Project Team Administrator holds admin:* / study:configure -> 200.
    admin = auth(ADMIN)
    ok = client.post(f"{API}/crashes/scan-missing-iif", headers=admin)
    assert ok.status_code == 200, ok.text
    body = ok.json()
    assert "flagged" in body and "window_hours" in body

    # Public user lacks the gating permission -> 403.
    pub = auth(PUBLIC)
    denied = client.post(f"{API}/crashes/scan-missing-iif", headers=pub)
    assert denied.status_code == 403, denied.text


# --------------------------------------------------------------------------- endpoint delivers notification
def test_scan_endpoint_emits_notification_to_analyst(client, auth, db):
    crash = _make_crash(db, age_hours=72)
    db.commit()

    admin = auth(ADMIN)
    # window=1h so the just-backdated crash is flagged via the HTTP path.
    resp = client.post(f"{API}/crashes/scan-missing-iif", headers=admin, params={"window_hours": 1})
    assert resp.status_code == 200, resp.text
    assert resp.json()["flagged"] >= 1

    # The KS analyst sees a MISSING_IIF notification for this crash in their inbox.
    analyst = auth(ANALYST_KS)
    inbox = client.get(f"{API}/notifications", headers=analyst, params={"unread_only": True}).json()
    matching = [n for n in inbox if n.get("crash_id") == str(crash.id) and n.get("notification_type") == "MISSING_IIF"]
    assert matching, "expected a MISSING_IIF notification for the stale KS crash"
