"""CRAS-6 — crash timeline surfaces lifecycle-phase milestones.

The timeline (`GET /crashes/{id}/timeline`) is still built from `audit_logs`, but
each entry is now tagged with the lifecycle phase it implies and an `is_milestone`
flag so the UI can render a phase rail. These tests run inside a rolled-back
transaction (see conftest), so they never mutate the development database.
"""
from __future__ import annotations

from tests.conftest import ANALYST_KS, INSPECTOR_KS, PUBLIC

API = "/api/v1"


def _study_id(client, headers) -> str:
    return next(
        s for s in client.get(f"{API}/studies", headers=headers).json() if s["code"] == "PHASE1-HDT"
    )["id"]


def _build_submitted_crash(client, insp, analyst) -> str:
    """Create a KS crash, classify it in-scope, and submit its IIF.

    Yields a crash whose audit log contains the crash CREATE and the IIF SUBMIT —
    the two transitions CRAS-6 turns into timeline milestones.
    """
    study_id = _study_id(client, insp)
    crash = client.post(
        f"{API}/crashes", headers=insp,
        json={"study_id": study_id, "state_code": "KS", "city": "Topeka", "county": "Shawnee",
              "crash_date": "2026-05-02", "num_fatalities": 1},
    ).json()
    cid = crash["id"]
    client.put(f"{API}/crashes/{cid}/scope", headers=analyst,
               json={"is_qualifying": True, "scope": "IN_SCOPE"})
    client.post(f"{API}/crashes/{cid}/incident-vehicles", headers=insp,
                json={"vehicle_number": 1, "is_cmv": True, "us_dot_number": "3192847", "make": "Freightliner"})
    client.put(f"{API}/crashes/{cid}/initial-incident", headers=insp, json={"event_summary": "Test event"})
    submit = client.post(f"{API}/crashes/{cid}/initial-incident/submit", headers=insp).json()
    assert submit["status"] == "ROUTED"
    return cid


def test_timeline_tags_lifecycle_milestones(client, auth):
    insp = auth(INSPECTOR_KS)
    analyst = auth(ANALYST_KS)
    cid = _build_submitted_crash(client, insp, analyst)

    resp = client.get(f"{API}/crashes/{cid}/timeline", headers=insp)
    assert resp.status_code == 200
    entries = resp.json()

    # New fields are present on every entry.
    for e in entries:
        assert "phase" in e and "is_milestone" in e

    by_action = {(e["action"], e["entity_type"]): e for e in entries}

    create = by_action[("CREATE", "crash")]
    assert create["phase"] == "INITIAL_INCIDENT"
    assert create["is_milestone"] is True

    submit = by_action[("SUBMIT", "initial_incident_form")]
    assert submit["phase"] == "NOTIFICATION"
    assert submit["is_milestone"] is True

    # Routine (non-transition) audits remain plain entries — e.g. the
    # AUTO_CLASSIFY_SCOPE row written at create time.
    non_milestones = [e for e in entries if e["is_milestone"] is False]
    assert non_milestones, "expected at least one non-milestone audit entry"
    assert all(e["phase"] is None for e in non_milestones)
    assert any(e["action"] == "AUTO_CLASSIFY_SCOPE" for e in non_milestones)


def test_timeline_ordered_and_milestone_subset(client, auth):
    insp = auth(INSPECTOR_KS)
    analyst = auth(ANALYST_KS)
    cid = _build_submitted_crash(client, insp, analyst)

    entries = client.get(f"{API}/crashes/{cid}/timeline", headers=insp).json()
    # Still ordered by occurred_at (CREATE precedes SUBMIT).
    occurred = [e["occurred_at"] for e in entries]
    assert occurred == sorted(occurred)
    actions = {e["action"] for e in entries}
    assert {"CREATE", "SUBMIT"}.issubset(actions)
    # Milestones are a strict, non-empty subset of all entries.
    milestones = [e for e in entries if e["is_milestone"]]
    assert 0 < len(milestones) < len(entries)
    assert all(e["phase"] for e in milestones)


def test_timeline_denied_without_crash_read(client, auth):
    """Negative / authorization: a Public User lacks `crash:read` -> 403, even
    for a real crash id. We reuse a crash created by an authorized user."""
    insp = auth(INSPECTOR_KS)
    analyst = auth(ANALYST_KS)
    cid = _build_submitted_crash(client, insp, analyst)

    resp = client.get(f"{API}/crashes/{cid}/timeline", headers=auth(PUBLIC))
    assert resp.status_code == 403
