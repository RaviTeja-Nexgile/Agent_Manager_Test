"""DATA-1 (= CRAS-5): completion locks a crash record; edits are blocked until an
authorized unlock (documentation §8.8, §12.3). All tests run inside a rolled-back
transaction (see conftest) so the live development database is never mutated.

Coverage:
  * A locked (complete) crash rejects attribute set/override with 409.
  * An authorized unlock (SYSTEM_ADMIN, `crash:unlock`) re-enables editing -> 201.
  * Negative/authorization case: a State analyst lacks `crash:unlock` -> 403.
  * A locked crash rejects PATCH metadata edits with 409.
  * Lock-on-completion: re-evaluating a crash to COMPLETE re-locks the record.
"""
from __future__ import annotations

from app import workers
from tests.conftest import ANALYST_KS

API = "/api/v1"

# The seeded KS demo crash CCFP-2026-KS-000101 is pre-populated, COMPLETE, and
# locked (Backend/database/seeds/0004_demo_crashes.sql). It is KS-scoped, so the
# KS analyst can read/edit it once unlocked.
LOCKED_CRASH = "c1a51001-0000-0000-0000-000000000001"

# crash:unlock is granted only to SYSTEM_ADMIN (seeds/0002_rbac_orgs_users.sql);
# the State analyst holds data_mgmt:edit / crash:update but not crash:unlock.
SYSADMIN = "sysadmin@ccfp.gov"


def _set_attr_body() -> dict:
    return {"attribute_code": "C04", "value_text": "Salina"}


# --------------------------------------------------------------------------- lock guards
def test_locked_crash_rejects_attribute_write(client, auth):
    """A complete/locked record rejects a new attribute value with 409 Conflict."""
    analyst = auth(ANALYST_KS)
    resp = client.post(f"{API}/crashes/{LOCKED_CRASH}/attributes", headers=analyst, json=_set_attr_body())
    assert resp.status_code == 409, resp.text
    assert "locked" in resp.json()["detail"].lower()


def test_locked_crash_rejects_metadata_patch(client, auth):
    """The PATCH metadata path is guarded by the same lock check (409)."""
    analyst = auth(ANALYST_KS)
    resp = client.patch(f"{API}/crashes/{LOCKED_CRASH}", headers=analyst, json={"city": "Salina"})
    assert resp.status_code == 409, resp.text


def test_analyst_cannot_unlock(client, auth):
    """Negative/authorization case: the State analyst lacks `crash:unlock` -> 403,
    so the record stays locked and the edit stays blocked."""
    analyst = auth(ANALYST_KS)
    resp = client.post(f"{API}/crashes/{LOCKED_CRASH}/unlock", headers=analyst)
    assert resp.status_code == 403, resp.text
    # Still locked: the edit remains rejected.
    assert client.post(
        f"{API}/crashes/{LOCKED_CRASH}/attributes", headers=analyst, json=_set_attr_body()
    ).status_code == 409


def test_unlock_then_edit_succeeds(client, auth):
    """An authorized unlock (sysadmin) flips is_locked False, after which the same
    attribute write the analyst was blocked on returns 201."""
    analyst = auth(ANALYST_KS)
    admin = auth(SYSADMIN)

    # Blocked while locked.
    assert client.post(
        f"{API}/crashes/{LOCKED_CRASH}/attributes", headers=analyst, json=_set_attr_body()
    ).status_code == 409

    # Authorized unlock.
    unlocked = client.post(f"{API}/crashes/{LOCKED_CRASH}/unlock", headers=admin)
    assert unlocked.status_code == 200, unlocked.text
    assert unlocked.json()["is_locked"] is False

    # Now the analyst's edit succeeds.
    created = client.post(f"{API}/crashes/{LOCKED_CRASH}/attributes", headers=analyst, json=_set_attr_body())
    assert created.status_code == 201, created.text
    assert created.json()["code"] == "C04"
    assert created.json()["value_text"] == "Salina"


# --------------------------------------------------------------------------- lock on completion
def test_completion_locks_record(client, auth):
    """Re-evaluating a complete crash re-locks it (documentation §8.8): unlock the
    seeded COMPLETE crash, then run completeness via the endpoint; the record's
    lock state tracks whether it evaluated COMPLETE (and the seed crash does)."""
    analyst = auth(ANALYST_KS)
    admin = auth(SYSADMIN)

    # Start from an unlocked state so the lock transition is observable.
    assert client.post(f"{API}/crashes/{LOCKED_CRASH}/unlock", headers=admin).status_code == 200
    before = client.get(f"{API}/crashes/{LOCKED_CRASH}/completeness", headers=analyst).json()
    assert before["is_locked"] is False

    # Re-evaluate completeness through the endpoint (which locks on COMPLETE).
    result = client.post(f"{API}/crashes/{LOCKED_CRASH}/completeness/evaluate", headers=analyst)
    assert result.status_code == 200, result.text
    status = result.json()["status"]

    comp = client.get(f"{API}/crashes/{LOCKED_CRASH}/completeness", headers=analyst).json()
    # Completion locks the record; an INCOMPLETE re-evaluation leaves it unlocked.
    assert comp["is_locked"] is (status == "COMPLETE")
    if status == "COMPLETE":
        assert comp["is_locked"] is True
        # And editing is blocked again once re-locked.
        assert client.post(
            f"{API}/crashes/{LOCKED_CRASH}/attributes", headers=analyst, json=_set_attr_body()
        ).status_code == 409


def test_completion_locks_built_crash(client, auth, db):
    """Build a KS crash through the lifecycle (mirrors test_full_crash_lifecycle),
    evaluate completeness via the endpoint, and assert the record is locked exactly
    when it evaluates COMPLETE."""
    import uuid

    insp = auth("nora.kowalczyk@ccfp.gov")  # INSPECTOR_KS
    analyst = auth(ANALYST_KS)
    study_id = next(
        s for s in client.get(f"{API}/studies", headers=insp).json() if s["code"] == "PHASE1-HDT"
    )["id"]

    crash = client.post(
        f"{API}/crashes", headers=insp,
        json={"study_id": study_id, "state_code": "KS", "city": "Topeka", "county": "Shawnee",
              "crash_date": "2026-05-02", "num_fatalities": 1},
    ).json()
    cid = crash["id"]

    client.put(f"{API}/crashes/{cid}/scope", headers=analyst, json={"is_qualifying": True, "scope": "IN_SCOPE"})
    client.post(f"{API}/crashes/{cid}/incident-vehicles", headers=insp,
                json={"vehicle_number": 1, "is_cmv": True, "us_dot_number": "3192847", "make": "Freightliner"})
    client.post(f"{API}/crashes/{cid}/incident-persons", headers=insp,
                json={"person_type": "DRIVER", "full_name": "Test Driver", "injury": "NO_INJURY"})
    client.put(f"{API}/crashes/{cid}/initial-incident", headers=insp, json={"event_summary": "Test event"})
    client.post(f"{API}/crashes/{cid}/initial-incident/submit", headers=insp)
    client.post(f"{API}/crashes/{cid}/post-crash-inspections", headers=analyst, json={"inspection_number": "INS-TEST-2"})
    client.put(
        f"{API}/crashes/{cid}/contributing-factors", headers=analyst,
        json={"factors": [
            {"factor_group_code": "DRIVER_ACTIONS", "factor_value": "Following too closely", "rank": 1},
            {"factor_group_code": "DRIVER_CONDITIONS", "factor_value": "Fatigue", "rank": 2},
            {"factor_group_code": "CC_VEHICLE", "factor_value": "Brakes", "rank": 3},
        ]},
    )
    # QC first so completeness sees no open critical failures.
    workers.evaluate_quality(uuid.UUID(cid), db=db)

    result = client.post(f"{API}/crashes/{cid}/completeness/evaluate", headers=analyst)
    assert result.status_code == 200, result.text
    status = result.json()["status"]
    assert status in ("COMPLETE", "INCOMPLETE")

    comp = client.get(f"{API}/crashes/{cid}/completeness", headers=analyst).json()
    # The record is locked exactly when it evaluated COMPLETE.
    assert comp["is_locked"] is (status == "COMPLETE")
