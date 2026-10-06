"""CRAS-2: scope-driven Notification & Routing on Initial Incident Form submit.

In-scope, out-of-scope, and supplemental crashes must each route distinctly
(documentation §5 Phase 2). Mirrors tests/test_api.py::test_full_crash_lifecycle;
every test runs inside the conftest rolled-back transaction."""
from __future__ import annotations

import uuid

from sqlalchemy import select

from app.models import Notification
from tests.conftest import ANALYST_KS, INSPECTOR_KS, PUBLIC

API = "/api/v1"


def _study_id(client, headers) -> str:
    return next(s for s in client.get(f"{API}/studies", headers=headers).json() if s["code"] == "PHASE1-HDT")["id"]


def _create_ks_crash(client, insp) -> str:
    study_id = _study_id(client, insp)
    crash = client.post(
        f"{API}/crashes", headers=insp,
        json={"study_id": study_id, "state_code": "KS", "city": "Topeka", "county": "Shawnee",
              "crash_date": "2026-05-01", "num_fatalities": 1},
    ).json()
    return crash["id"]


def _notifications_of_type(db, crash_id: str, ntype: str) -> list[Notification]:
    return list(
        db.scalars(
            select(Notification).where(
                Notification.crash_id == uuid.UUID(crash_id),
                Notification.notification_type == ntype,
            )
        )
    )


def test_in_scope_routes_to_bts(client, auth, db):
    """Regression guard: the in-scope path is unchanged — routed_to_bts True,
    routed_out_of_scope False, and an IN_SCOPE_ROUTING notification exists."""
    insp = auth(INSPECTOR_KS)
    analyst = auth(ANALYST_KS)
    cid = _create_ks_crash(client, insp)

    client.put(f"{API}/crashes/{cid}/scope", headers=analyst,
               json={"is_qualifying": True, "scope": "IN_SCOPE"})
    client.post(f"{API}/crashes/{cid}/incident-vehicles", headers=insp,
                json={"vehicle_number": 1, "is_cmv": True, "us_dot_number": "3192847", "make": "Freightliner"})
    client.put(f"{API}/crashes/{cid}/initial-incident", headers=insp, json={"event_summary": "In scope"})

    submit = client.post(f"{API}/crashes/{cid}/initial-incident/submit", headers=insp).json()
    assert submit["routed_to_bts"] is True
    assert submit["routed_out_of_scope"] is False

    assert _notifications_of_type(db, cid, "IN_SCOPE_ROUTING")
    assert not _notifications_of_type(db, cid, "OUT_OF_SCOPE_ROUTING")


def test_out_of_scope_routes_to_project_team(client, auth, db):
    """OUT_OF_SCOPE submit routes to the CCFP Project Team, not BTS."""
    insp = auth(INSPECTOR_KS)
    analyst = auth(ANALYST_KS)
    cid = _create_ks_crash(client, insp)

    client.put(f"{API}/crashes/{cid}/scope", headers=analyst,
               json={"scope": "OUT_OF_SCOPE", "is_qualifying": False})
    client.post(f"{API}/crashes/{cid}/incident-vehicles", headers=insp,
                json={"vehicle_number": 1, "is_cmv": True, "us_dot_number": "3192847", "make": "Freightliner"})
    client.put(f"{API}/crashes/{cid}/initial-incident", headers=insp, json={"event_summary": "Out of scope"})

    submit = client.post(f"{API}/crashes/{cid}/initial-incident/submit", headers=insp).json()
    assert submit["routed_out_of_scope"] is True
    assert submit["routed_to_bts"] is False

    notes = _notifications_of_type(db, cid, "OUT_OF_SCOPE_ROUTING")
    assert notes
    assert not _notifications_of_type(db, cid, "IN_SCOPE_ROUTING")

    # The notification reaches a seeded CCFP Project Team member.
    from app.core.notifications import users_with_role
    team_ids = {u.id for u in users_with_role(db, "CCFP_PROJECT_TEAM")}
    assert team_ids, "expected seeded CCFP Project Team members"
    assert any(n.recipient_user_id in team_ids for n in notes)


def test_supplemental_routes_out_of_scope_with_message(client, auth, db):
    """A supplemental record is out-of-scope and its message says so."""
    insp = auth(INSPECTOR_KS)
    analyst = auth(ANALYST_KS)
    cid = _create_ks_crash(client, insp)

    client.put(f"{API}/crashes/{cid}/scope", headers=analyst,
               json={"scope": "OUT_OF_SCOPE", "is_supplemental": True})
    client.put(f"{API}/crashes/{cid}/initial-incident", headers=insp, json={"event_summary": "Supplemental"})

    submit = client.post(f"{API}/crashes/{cid}/initial-incident/submit", headers=insp).json()
    assert submit["routed_out_of_scope"] is True
    assert submit["routed_to_bts"] is False

    notes = _notifications_of_type(db, cid, "OUT_OF_SCOPE_ROUTING")
    assert notes
    assert any("supplemental" in (n.message or "").lower() for n in notes)


def test_undetermined_scope_routes_nowhere(client, auth, db):
    """No classification (UNDETERMINED default) -> neither CIPSEA branch runs."""
    insp = auth(INSPECTOR_KS)
    cid = _create_ks_crash(client, insp)

    client.put(f"{API}/crashes/{cid}/initial-incident", headers=insp, json={"event_summary": "Unclassified"})
    submit = client.post(f"{API}/crashes/{cid}/initial-incident/submit", headers=insp).json()
    assert submit["routed_to_bts"] is False
    assert submit["routed_out_of_scope"] is False

    assert not _notifications_of_type(db, cid, "IN_SCOPE_ROUTING")
    assert not _notifications_of_type(db, cid, "OUT_OF_SCOPE_ROUTING")


def test_public_user_cannot_submit_iif(client, auth):
    """Authorization: a Public User lacks initial_incident:submit and is denied."""
    insp = auth(INSPECTOR_KS)
    cid = _create_ks_crash(client, insp)
    client.put(f"{API}/crashes/{cid}/initial-incident", headers=insp, json={"event_summary": "x"})

    resp = client.post(f"{API}/crashes/{cid}/initial-incident/submit", headers=auth(PUBLIC))
    assert resp.status_code == 403
