"""IIF guard tests (INIT-6, INIT-7, INIT-10).

Covers:
  * INIT-7  — child vehicle/person deletes are blocked once the parent IIF is
              ROUTED, but allowed while the form is a draft.
  * INIT-10 — DOT validation is a tri-state outcome: VALIDATED, FAILED, and
              NOT_APPLICABLE (no CMV) — N/A is never reported as a failure.
  * INIT-6  — a one-time IIF_DRAFT_SAVED notification fires on first save (not on
              repeated saves), and the NEW_IIF routing notification fires on
              submit.

All requests share the rolled-back transaction provided by the `client`/`db`
fixtures, so nothing escapes to the development database.
"""
from __future__ import annotations

from tests.conftest import ANALYST_KS, INSPECTOR_KS

API = "/api/v1"


def _study_id(client, headers) -> str:
    return next(s for s in client.get(f"{API}/studies", headers=headers).json() if s["code"] == "PHASE1-HDT")["id"]


def _new_crash(client, headers) -> str:
    study_id = _study_id(client, headers)
    resp = client.post(
        f"{API}/crashes", headers=headers,
        json={"study_id": study_id, "state_code": "KS", "city": "Topeka",
              "county": "Shawnee", "crash_date": "2026-05-02", "num_fatalities": 1},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


# --------------------------------------------------------------------------- INIT-7
def test_child_deletes_blocked_after_routing(client, auth):
    """Once the IIF is submitted/routed, its vehicles and persons are locked."""
    insp = auth(INSPECTOR_KS)
    cid = _new_crash(client, insp)

    veh = client.post(f"{API}/crashes/{cid}/incident-vehicles", headers=insp,
                      json={"vehicle_number": 1, "is_cmv": True, "us_dot_number": "3192847"})
    assert veh.status_code == 201, veh.text
    veh_id = veh.json()["id"]

    person = client.post(f"{API}/crashes/{cid}/incident-persons", headers=insp,
                         json={"person_type": "DRIVER", "full_name": "Test Driver", "injury": "NO_INJURY"})
    assert person.status_code == 201, person.text
    person_id = person.json()["id"]

    client.put(f"{API}/crashes/{cid}/initial-incident", headers=insp, json={"event_summary": "draft"})
    submit = client.post(f"{API}/crashes/{cid}/initial-incident/submit", headers=insp)
    assert submit.status_code == 200, submit.text
    assert submit.json()["status"] == "ROUTED"

    # Both child deletes are now rejected with the routed-lock conflict.
    del_veh = client.delete(f"{API}/crashes/{cid}/incident-vehicles/{veh_id}", headers=insp)
    assert del_veh.status_code == 409, del_veh.text
    del_person = client.delete(f"{API}/crashes/{cid}/incident-persons/{person_id}", headers=insp)
    assert del_person.status_code == 409, del_person.text


def test_child_deletes_allowed_on_draft(client, auth):
    """Positive control: while the form is a draft, child deletes still succeed."""
    insp = auth(INSPECTOR_KS)
    cid = _new_crash(client, insp)

    veh_id = client.post(f"{API}/crashes/{cid}/incident-vehicles", headers=insp,
                         json={"vehicle_number": 1, "is_cmv": False}).json()["id"]
    person_id = client.post(f"{API}/crashes/{cid}/incident-persons", headers=insp,
                            json={"person_type": "DRIVER", "full_name": "Draft Driver"}).json()["id"]

    # Save a draft IIF (not submitted) so the form is not routed.
    client.put(f"{API}/crashes/{cid}/initial-incident", headers=insp, json={"event_summary": "draft"})

    assert client.delete(f"{API}/crashes/{cid}/incident-vehicles/{veh_id}", headers=insp).status_code == 204
    assert client.delete(f"{API}/crashes/{cid}/incident-persons/{person_id}", headers=insp).status_code == 204


# --------------------------------------------------------------------------- INIT-10
def test_dot_validation_not_applicable_for_non_cmv(client, auth):
    """A crash with no CMV vehicle yields NOT_APPLICABLE, never a failure."""
    insp = auth(INSPECTOR_KS)
    cid = _new_crash(client, insp)

    # A non-CMV vehicle: there are no DOT numbers to validate.
    client.post(f"{API}/crashes/{cid}/incident-vehicles", headers=insp,
                json={"vehicle_number": 1, "is_cmv": False})
    client.put(f"{API}/crashes/{cid}/initial-incident", headers=insp, json={"event_summary": "x"})

    submit = client.post(f"{API}/crashes/{cid}/initial-incident/submit", headers=insp).json()
    assert submit["dot_validation_status"] == "NOT_APPLICABLE"
    # N/A is not the same as a failure.
    assert submit["dot_number_validated"] is False

    # The persisted form reflects the same tri-state outcome.
    iif = client.get(f"{API}/crashes/{cid}/initial-incident", headers=insp).json()
    assert iif["dot_validation_status"] == "NOT_APPLICABLE"


def test_dot_validation_validated_for_valid_cmv(client, auth):
    insp = auth(INSPECTOR_KS)
    cid = _new_crash(client, insp)

    client.post(f"{API}/crashes/{cid}/incident-vehicles", headers=insp,
                json={"vehicle_number": 1, "is_cmv": True, "us_dot_number": "3192847"})
    client.put(f"{API}/crashes/{cid}/initial-incident", headers=insp, json={"event_summary": "x"})

    submit = client.post(f"{API}/crashes/{cid}/initial-incident/submit", headers=insp).json()
    assert submit["dot_validation_status"] == "VALIDATED"
    assert submit["dot_number_validated"] is True


def test_dot_validation_failed_for_invalid_cmv(client, auth):
    """Negative case: a CMV with a DOT number the mock rejects is FAILED, not N/A."""
    insp = auth(INSPECTOR_KS)
    cid = _new_crash(client, insp)

    # Non-numeric DOT number -> SafeSpect mock returns valid=False.
    client.post(f"{API}/crashes/{cid}/incident-vehicles", headers=insp,
                json={"vehicle_number": 1, "is_cmv": True, "us_dot_number": "NOT-A-NUMBER"})
    client.put(f"{API}/crashes/{cid}/initial-incident", headers=insp, json={"event_summary": "x"})

    submit = client.post(f"{API}/crashes/{cid}/initial-incident/submit", headers=insp).json()
    assert submit["dot_validation_status"] == "FAILED"
    assert submit["dot_number_validated"] is False


# --------------------------------------------------------------------------- INIT-6
def test_draft_save_notifies_analyst_once(client, auth):
    """First save emits one IIF_DRAFT_SAVED notification; repeated saves do not."""
    insp = auth(INSPECTOR_KS)
    analyst = auth(ANALYST_KS)
    cid = _new_crash(client, insp)

    def _draft_rows():
        rows = client.get(f"{API}/notifications", headers=analyst).json()
        return [r for r in rows if r["notification_type"] == "IIF_DRAFT_SAVED" and r["crash_id"] == cid]

    assert _draft_rows() == []  # nothing before the first save

    # First save -> exactly one draft-saved notification.
    assert client.put(f"{API}/crashes/{cid}/initial-incident", headers=insp,
                      json={"event_summary": "first"}).status_code == 200
    assert len(_draft_rows()) == 1

    # Second save (anti-spam) -> still exactly one; no duplicate.
    assert client.put(f"{API}/crashes/{cid}/initial-incident", headers=insp,
                      json={"event_summary": "second"}).status_code == 200
    assert len(_draft_rows()) == 1


def test_submit_notifies_analyst_but_save_does_not_emit_new_iif(client, auth):
    """The NEW_IIF routing notification fires on submit, not on plain save."""
    insp = auth(INSPECTOR_KS)
    analyst = auth(ANALYST_KS)
    cid = _new_crash(client, insp)

    def _new_iif_rows():
        rows = client.get(f"{API}/notifications", headers=analyst).json()
        return [r for r in rows if r["notification_type"] == "NEW_IIF" and r["crash_id"] == cid]

    # A plain save must NOT emit the submit-time routing notification.
    client.put(f"{API}/crashes/{cid}/initial-incident", headers=insp, json={"event_summary": "draft"})
    assert _new_iif_rows() == []

    # Submitting routes the form and emits exactly one NEW_IIF notification.
    submit = client.post(f"{API}/crashes/{cid}/initial-incident/submit", headers=insp)
    assert submit.status_code == 200, submit.text
    assert len(_new_iif_rows()) == 1
