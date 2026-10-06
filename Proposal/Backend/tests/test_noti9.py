"""NOTI-9: NotificationType catalog as the single source of truth (§8.11).

Verifies:
  * The `NotificationType(_Str)` enum exposes the full documented §8.11
    vocabulary plus the operational types seeded in 0005 (and the IIF draft
    heads-up emitted by the owned initial_incident emitter).
  * `create_notification` accepts either a `NotificationType` member (preferred)
    or a bare string (backward compatibility) and persists the bare string value
    either way — the DB column stays plain TEXT, so existing string-literal
    callers in other modules keep working unchanged.
  * The IIF submit path emits a notification whose `notification_type` equals
    `NotificationType.NEW_IIF.value`, and it loads back over the API.
  * Negative / authorization: a Public User cannot submit an IIF (403), so no
    NEW_IIF notification is ever emitted by an unauthorized role; and an
    authorized inbox still loads every seeded type with no 500.

All requests/DB writes share the rolled-back transaction from conftest.py, so
nothing escapes to the development database.
"""
from __future__ import annotations

import uuid

from sqlalchemy import select

from app.core.notifications import create_notification
from app.enums import NOTIFICATION_TYPES, NotificationType
from app.models import Notification
from tests.conftest import ANALYST_KS, INSPECTOR_KS, PUBLIC

API = "/api/v1"

# The documented vocabulary (§8.11 catalogue + operational types seeded in 0005),
# plus the IIF draft heads-up emitted by the owned initial_incident emitter.
DOCUMENTED_VOCABULARY = {
    "NEW_IIF",
    "IN_SCOPE_ROUTING",
    "OUT_OF_SCOPE_ROUTING",
    "MISSING_DATA",
    "MISSING_IIF",
    "QC_FAILURE",
    "COMPLETENESS_CHANGE",
    "REPORT_PUBLISHED",
    "REPORT_SHARED",
    "SYSTEM_ALERT",
    "INTEGRATION_STATUS",
    "DATA_MAPPING",
    "DATASET_READY",
    "ELD_UPLOAD_REQUEST",
    "IIF_DRAFT_SAVED",
    # Emitted when an IIF is submitted while the crash still cannot be classified,
    # so it matches neither CIPSEA routing branch. Documented because "routed to
    # nobody" must be announced rather than silent (DL1, §5 Phase 2).
    "SCOPE_UNDETERMINED",
    # BRD Appendix E: an ELD upload is extracted AFTER its response returns, so a
    # failed or partial extraction has no request left to report on. This tells
    # the uploader, with the actionable message, rather than leaving the file in
    # a failed state nobody is told about.
    "ELD_PARSE_FAILED",
}


# --------------------------------------------------------------------------- unit: catalog
def test_every_member_is_in_documented_vocabulary():
    """Every NotificationType member's value is a documented type (no typos / no
    stray members) and the enum covers the full §8.11 vocabulary."""
    members = {t.value for t in NotificationType}
    assert members == DOCUMENTED_VOCABULARY
    # The §8.11 catalogue plus operational seed types must all be present.
    for code in DOCUMENTED_VOCABULARY:
        assert code in members


def test_catalog_constant_matches_enum():
    """The exposed NOTIFICATION_TYPES list is the single source of truth and is
    exactly the enum's values (same set, no duplicates)."""
    assert NOTIFICATION_TYPES == [t.value for t in NotificationType]
    assert set(NOTIFICATION_TYPES) == DOCUMENTED_VOCABULARY
    assert len(NOTIFICATION_TYPES) == len(set(NOTIFICATION_TYPES))


def test_member_renders_as_bare_value():
    """`_Str.__str__` renders the bare value, so str(member) == the stored TEXT."""
    assert str(NotificationType.NEW_IIF) == "NEW_IIF"
    assert NotificationType.NEW_IIF.value == "NEW_IIF"


# --------------------------------------------------------------------------- unit: create_notification
def test_create_notification_accepts_enum_and_persists_bare_value(db):
    """Passing a NotificationType member persists the bare string value (the
    column is plain TEXT, never a native enum object)."""
    n = create_notification(
        db,
        recipient_user_id=None,
        notification_type=NotificationType.QC_FAILURE,
        title="t",
        message="m",
    )
    db.flush()
    assert n.notification_type == "QC_FAILURE"
    assert isinstance(n.notification_type, str)
    # Round-trips through the DB unchanged.
    fetched = db.get(Notification, n.id)
    assert fetched is not None
    assert fetched.notification_type == NotificationType.QC_FAILURE.value


def test_create_notification_still_accepts_plain_string(db):
    """Backward compatibility: existing string-literal callers (workers/tasks.py,
    crashes.py, reports.py, studies.py, ...) keep working unchanged — a bare
    string is stored as-is, identical to passing the matching enum member."""
    n = create_notification(
        db,
        recipient_user_id=None,
        notification_type="MISSING_DATA",
        title="t",
    )
    db.flush()
    assert n.notification_type == "MISSING_DATA"
    assert n.notification_type == NotificationType.MISSING_DATA.value


# --------------------------------------------------------------------------- API helpers
def _study_id(client, headers) -> str:
    return next(
        s for s in client.get(f"{API}/studies", headers=headers).json()
        if s["code"] == "PHASE1-HDT"
    )["id"]


def _new_crash(client, headers) -> str:
    study_id = _study_id(client, headers)
    resp = client.post(
        f"{API}/crashes",
        headers=headers,
        json={
            "study_id": study_id,
            "state_code": "KS",
            "city": "Topeka",
            "county": "Shawnee",
            "crash_date": "2026-05-02",
            "num_fatalities": 1,
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


# --------------------------------------------------------------------------- API: emitter uses the enum value
def test_iif_submit_emits_new_iif_enum_value(client, auth):
    """The IIF submit path (the owned emitter, now using NotificationType.NEW_IIF)
    persists a notification whose type equals the enum's bare value, and it loads
    back over GET /api/v1/notifications."""
    insp = auth(INSPECTOR_KS)
    analyst = auth(ANALYST_KS)
    cid = _new_crash(client, insp)

    client.put(f"{API}/crashes/{cid}/initial-incident", headers=insp, json={"event_summary": "x"})
    submit = client.post(f"{API}/crashes/{cid}/initial-incident/submit", headers=insp)
    assert submit.status_code == 200, submit.text

    rows = client.get(f"{API}/notifications", headers=analyst)
    assert rows.status_code == 200, rows.text
    new_iif = [r for r in rows.json() if r["crash_id"] == cid and r["notification_type"] == NotificationType.NEW_IIF.value]
    assert len(new_iif) == 1
    # The emitted type is a member of the governed catalog (no free-text drift).
    assert new_iif[0]["notification_type"] in NOTIFICATION_TYPES


def test_authorized_inbox_loads_all_seeded_types(client, auth):
    """Regression: an authorized inbox loads with no 500 and every seeded
    notification carries a non-empty type (the TEXT column still accepts every
    existing value)."""
    rows = client.get(f"{API}/notifications", headers=auth(ANALYST_KS))
    assert rows.status_code == 200, rows.text
    body = rows.json()
    assert all(r["notification_type"] for r in body)


# --------------------------------------------------------------------------- negative / authorization
def test_public_user_cannot_submit_iif_so_no_new_iif_emitted(db, client, auth):
    """Negative/authorization: a Public User lacks initial_incident:submit, so the
    submit endpoint returns 403 and no NEW_IIF notification is ever emitted by an
    unauthorized role."""
    insp = auth(INSPECTOR_KS)
    cid = _new_crash(client, insp)
    client.put(f"{API}/crashes/{cid}/initial-incident", headers=insp, json={"event_summary": "x"})

    resp = client.post(f"{API}/crashes/{cid}/initial-incident/submit", headers=auth(PUBLIC))
    assert resp.status_code == 403, resp.text

    crash_uuid = uuid.UUID(cid)
    new_iif = db.scalars(
        select(Notification).where(
            Notification.crash_id == crash_uuid,
            Notification.notification_type == NotificationType.NEW_IIF.value,
        )
    ).all()
    assert new_iif == []
