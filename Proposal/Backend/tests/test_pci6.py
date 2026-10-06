"""PCI-6 — post-crash inspection 7-day upload-window (§8.3) SLA indicator.

The inspection-ingest endpoints now derive an `is_overdue` / `days_to_upload`
flag from `inspection_date` vs. the upload date (the upload happens "now" at
ingest, so an inspection dated >7 days ago is overdue). The indicator is
visibility only — late uploads are still accepted (201), never blocked.

These tests run inside a rolled-back transaction (see conftest), so they never
mutate the development database.
"""
from __future__ import annotations

import datetime as dt

from tests.conftest import ANALYST_KS, INSPECTOR_KS, PUBLIC

API = "/api/v1"


def _study_id(client, headers) -> str:
    return next(
        s for s in client.get(f"{API}/studies", headers=headers).json() if s["code"] == "PHASE1-HDT"
    )["id"]


def _new_crash(client, insp) -> str:
    """Create a fresh KS crash the inspector can add inspections to."""
    study_id = _study_id(client, insp)
    crash = client.post(
        f"{API}/crashes", headers=insp,
        json={"study_id": study_id, "state_code": "KS", "city": "Topeka", "county": "Shawnee",
              "crash_date": "2026-05-02", "num_fatalities": 1},
    ).json()
    return crash["id"]


def test_inspection_more_than_7_days_old_is_overdue(client, auth):
    insp = auth(INSPECTOR_KS)
    cid = _new_crash(client, insp)
    old_date = (dt.date.today() - dt.timedelta(days=10)).isoformat()

    resp = client.post(
        f"{API}/crashes/{cid}/post-crash-inspections", headers=insp,
        json={"inspection_number": "INS-OVERDUE", "inspection_date": old_date},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["is_overdue"] is True
    assert body["days_to_upload"] == 10


def test_inspection_today_is_on_time(client, auth):
    insp = auth(INSPECTOR_KS)
    cid = _new_crash(client, insp)
    today = dt.date.today().isoformat()

    resp = client.post(
        f"{API}/crashes/{cid}/post-crash-inspections", headers=insp,
        json={"inspection_number": "INS-ONTIME", "inspection_date": today},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["is_overdue"] is False
    assert body["days_to_upload"] == 0


def test_inspection_exactly_at_window_boundary_not_overdue(client, auth):
    """7 days elapsed is within the window (overdue requires > 7)."""
    insp = auth(INSPECTOR_KS)
    cid = _new_crash(client, insp)
    boundary = (dt.date.today() - dt.timedelta(days=7)).isoformat()

    resp = client.post(
        f"{API}/crashes/{cid}/post-crash-inspections", headers=insp,
        json={"inspection_number": "INS-BOUNDARY", "inspection_date": boundary},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["days_to_upload"] == 7
    assert body["is_overdue"] is False


def test_inspection_without_date_has_null_days_and_not_overdue(client, auth):
    insp = auth(INSPECTOR_KS)
    cid = _new_crash(client, insp)

    resp = client.post(
        f"{API}/crashes/{cid}/post-crash-inspections", headers=insp,
        json={"inspection_number": "INS-NODATE"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["days_to_upload"] is None
    assert body["is_overdue"] is False


def test_list_inspections_surfaces_sla_fields(client, auth):
    """The indicator is available wherever inspections are returned (list view)."""
    insp = auth(INSPECTOR_KS)
    cid = _new_crash(client, insp)
    old_date = (dt.date.today() - dt.timedelta(days=20)).isoformat()
    client.post(
        f"{API}/crashes/{cid}/post-crash-inspections", headers=insp,
        json={"inspection_number": "INS-LIST", "inspection_date": old_date},
    )

    rows = client.get(f"{API}/crashes/{cid}/post-crash-inspections", headers=insp).json()
    assert len(rows) == 1
    assert rows[0]["is_overdue"] is True
    assert rows[0]["days_to_upload"] == 20


def test_analyst_can_read_sla_indicator(client, auth):
    """A KS analyst (source_data:read) sees the derived indicator too."""
    insp = auth(INSPECTOR_KS)
    analyst = auth(ANALYST_KS)
    cid = _new_crash(client, insp)
    old_date = (dt.date.today() - dt.timedelta(days=9)).isoformat()
    rec = client.post(
        f"{API}/crashes/{cid}/post-crash-inspections", headers=insp,
        json={"inspection_number": "INS-READ", "inspection_date": old_date},
    ).json()

    got = client.get(f"{API}/crashes/{cid}/post-crash-inspections/{rec['id']}", headers=analyst).json()
    assert got["is_overdue"] is True
    assert got["days_to_upload"] == 9


def test_public_cannot_ingest_inspection(client, auth):
    """Negative / authorization: a Public User lacks `source_data:ingest` -> 403."""
    insp = auth(INSPECTOR_KS)
    cid = _new_crash(client, insp)

    resp = client.post(
        f"{API}/crashes/{cid}/post-crash-inspections", headers=auth(PUBLIC),
        json={"inspection_number": "INS-FORBIDDEN", "inspection_date": dt.date.today().isoformat()},
    )
    assert resp.status_code == 403
