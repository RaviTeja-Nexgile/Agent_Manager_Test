"""Crash scope auto-classification, lifecycle advance, and scope-routing tests.

Covers:
  * CRAS-1  — scope auto-classification from the study's configured criteria:
              a qualifying KS crash (participating) -> IN_SCOPE; a qualifying MO
              crash (non-participating) -> OUT_OF_SCOPE; a non-qualifying crash ->
              OUT_OF_SCOPE; authorization (a user without crash:update is 403).
  * CRAS-4  — POST /advance-phase moves the crash forward, rejects a backward /
              no-op target with 400, and enforces crash:update authorization.
  * NOTI-1  — setting scope OUT_OF_SCOPE emits OUT_OF_SCOPE_ROUTING to the State
              CMV Data Analyst.
  * NOTI-7  — setting scope IN_SCOPE after the IIF is submitted re-triggers the
              BTS IN_SCOPE_ROUTING notification, idempotently (only on transition).

All requests share the rolled-back transaction provided by the `client`/`db`
fixtures, so nothing escapes to the development database.
"""
from __future__ import annotations

from sqlalchemy import select

from app.models import Notification, User
from tests.conftest import ANALYST_KS, FEDERAL, INSPECTOR_KS

API = "/api/v1"

# BTS CIPSEA Agent (seeded) — recipient of in-scope BTS routing.
BTS_AGENT = "helena.brandt@ccfp.gov"
# System Administrator: GLOBAL scope + all permissions; can create / classify a
# crash in any State (used for the non-participating-State case).
SYSADMIN = "sysadmin@ccfp.gov"


def _study_id(client, headers) -> str:
    return next(s for s in client.get(f"{API}/studies", headers=headers).json() if s["code"] == "PHASE1-HDT")["id"]


def _new_crash(client, headers, *, state_code: str = "KS", num_fatalities: int = 1) -> str:
    study_id = _study_id(client, headers)
    resp = client.post(
        f"{API}/crashes", headers=headers,
        json={"study_id": study_id, "state_code": state_code, "city": "Topeka",
              "county": "Shawnee", "crash_date": "2026-05-02", "num_fatalities": num_fatalities},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _notif_rows(db, crash_id: str, notification_type: str) -> list[Notification]:
    return list(db.scalars(
        select(Notification).where(
            Notification.crash_id == crash_id,
            Notification.notification_type == notification_type,
        )
    ).all())


# --------------------------------------------------------------------------- CRAS-1
def test_reclassify_qualifying_ks_crash_is_in_scope(client, auth):
    """A qualifying crash (>=1 fatality + CMV) in participating KS -> IN_SCOPE."""
    insp = auth(INSPECTOR_KS)
    analyst = auth(ANALYST_KS)  # holds crash:update for the reclassify call
    cid = _new_crash(client, insp, state_code="KS", num_fatalities=1)

    # A fresh crash has no vehicles yet -> auto-classify resolves UNDETERMINED.
    scope = client.get(f"{API}/crashes/{cid}/scope", headers=insp).json()
    assert scope["scope"] == "UNDETERMINED"

    client.post(f"{API}/crashes/{cid}/incident-vehicles", headers=insp,
                json={"vehicle_number": 1, "is_cmv": True, "us_dot_number": "3192847"})

    reclass = client.post(f"{API}/crashes/{cid}/scope/reclassify", headers=analyst)
    assert reclass.status_code == 200, reclass.text
    body = reclass.json()
    assert body["is_qualifying"] is True
    assert body["scope"] == "IN_SCOPE"


def test_reclassify_non_participating_state_is_out_of_scope(client, auth):
    """A qualifying crash in a non-participating State (MO) -> OUT_OF_SCOPE."""
    # INSPECTOR_KS is KS-scoped and cannot create an MO crash, so a GLOBAL-scoped
    # sysadmin creates it; reclassify still derives OUT_OF_SCOPE for MO.
    admin = auth(SYSADMIN)
    cid = _new_crash(client, admin, state_code="MO", num_fatalities=1)

    client.post(f"{API}/crashes/{cid}/incident-vehicles", headers=admin,
                json={"vehicle_number": 1, "is_cmv": True, "us_dot_number": "3192847"})

    reclass = client.post(f"{API}/crashes/{cid}/scope/reclassify", headers=admin)
    assert reclass.status_code == 200, reclass.text
    body = reclass.json()
    # Qualifying on facts, but MO is not a participating State for PHASE1-HDT.
    assert body["is_qualifying"] is True
    assert body["scope"] == "OUT_OF_SCOPE"


def test_reclassify_non_qualifying_crash_is_out_of_scope(client, auth):
    """No CMV present -> not qualifying -> OUT_OF_SCOPE even in participating KS."""
    insp = auth(INSPECTOR_KS)
    analyst = auth(ANALYST_KS)
    cid = _new_crash(client, insp, state_code="KS", num_fatalities=1)

    # Only a non-CMV vehicle: the qualifying rule needs a heavy-duty truck.
    client.post(f"{API}/crashes/{cid}/incident-vehicles", headers=insp,
                json={"vehicle_number": 1, "is_cmv": False})

    reclass = client.post(f"{API}/crashes/{cid}/scope/reclassify", headers=analyst)
    assert reclass.status_code == 200, reclass.text
    body = reclass.json()
    assert body["is_qualifying"] is False
    assert body["scope"] == "OUT_OF_SCOPE"


def test_reclassify_requires_crash_update_permission(client, auth):
    """A Federal user lacks crash:update -> reclassify is 403."""
    insp = auth(INSPECTOR_KS)
    fed = auth(FEDERAL)
    cid = _new_crash(client, insp, state_code="KS", num_fatalities=1)

    resp = client.post(f"{API}/crashes/{cid}/scope/reclassify", headers=fed)
    assert resp.status_code == 403, resp.text


# --------------------------------------------------------------------------- CRAS-4
def test_advance_phase_moves_forward(client, auth):
    """advance-phase moves a crash forward through the lifecycle order."""
    insp = auth(INSPECTOR_KS)
    analyst = auth(ANALYST_KS)  # holds crash:update; KS-scoped like the crash
    cid = _new_crash(client, insp)

    # New crash starts at INITIAL_INCIDENT.
    assert client.get(f"{API}/crashes/{cid}", headers=analyst).json()["lifecycle_phase"] == "INITIAL_INCIDENT"

    resp = client.post(f"{API}/crashes/{cid}/advance-phase", headers=analyst,
                       json={"target_phase": "DATA_COLLECTION"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["lifecycle_phase"] == "DATA_COLLECTION"

    # And further forward to the terminal PUBLICATION phase.
    resp = client.post(f"{API}/crashes/{cid}/advance-phase", headers=analyst,
                       json={"target_phase": "PUBLICATION"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["lifecycle_phase"] == "PUBLICATION"


def test_advance_phase_rejects_backward_transition(client, auth):
    """A backward / no-op target is rejected with 400 and the phase is unchanged."""
    insp = auth(INSPECTOR_KS)
    analyst = auth(ANALYST_KS)
    cid = _new_crash(client, insp)

    client.post(f"{API}/crashes/{cid}/advance-phase", headers=analyst,
                json={"target_phase": "QUALITY_CONTROL"})

    backward = client.post(f"{API}/crashes/{cid}/advance-phase", headers=analyst,
                           json={"target_phase": "INITIAL_INCIDENT"})
    assert backward.status_code == 400, backward.text
    # Phase unchanged by the rejected call.
    assert client.get(f"{API}/crashes/{cid}", headers=analyst).json()["lifecycle_phase"] == "QUALITY_CONTROL"


def test_advance_phase_requires_crash_update_permission(client, auth):
    """A Federal user lacks crash:update -> advance-phase is 403."""
    insp = auth(INSPECTOR_KS)
    fed = auth(FEDERAL)
    cid = _new_crash(client, insp)

    resp = client.post(f"{API}/crashes/{cid}/advance-phase", headers=fed,
                       json={"target_phase": "DATA_COLLECTION"})
    assert resp.status_code == 403, resp.text


# --------------------------------------------------------------------------- NOTI-1
def test_set_scope_out_of_scope_emits_routing_notification(client, auth, db):
    """Setting scope OUT_OF_SCOPE emits OUT_OF_SCOPE_ROUTING to State analysts."""
    insp = auth(INSPECTOR_KS)
    analyst = auth(ANALYST_KS)
    cid = _new_crash(client, insp)

    assert _notif_rows(db, cid, "OUT_OF_SCOPE_ROUTING") == []

    resp = client.put(f"{API}/crashes/{cid}/scope", headers=analyst,
                      json={"is_qualifying": False, "scope": "OUT_OF_SCOPE"})
    assert resp.status_code == 200, resp.text

    rows = _notif_rows(db, cid, "OUT_OF_SCOPE_ROUTING")
    assert len(rows) >= 1


def test_set_scope_in_scope_emits_no_out_of_scope_routing(client, auth, db):
    """Negative control: an IN_SCOPE classification emits no OUT_OF_SCOPE_ROUTING."""
    insp = auth(INSPECTOR_KS)
    analyst = auth(ANALYST_KS)
    cid = _new_crash(client, insp)

    resp = client.put(f"{API}/crashes/{cid}/scope", headers=analyst,
                      json={"is_qualifying": True, "scope": "IN_SCOPE"})
    assert resp.status_code == 200, resp.text

    assert _notif_rows(db, cid, "OUT_OF_SCOPE_ROUTING") == []


# --------------------------------------------------------------------------- NOTI-7
def test_set_scope_in_scope_after_submit_retriggers_bts_routing(client, auth, db):
    """Setting scope IN_SCOPE after the IIF is submitted re-runs BTS routing."""
    insp = auth(INSPECTOR_KS)
    analyst = auth(ANALYST_KS)
    cid = _new_crash(client, insp)

    # Submit with only a non-CMV vehicle so the crash derives OUT_OF_SCOPE and no
    # BTS routing happens on submit. (Before the scope-refresh fix this case was
    # written with a CMV vehicle and relied on the crash being stuck at
    # UNDETERMINED — the very defect under repair, so it can no longer be used to
    # reach "submitted but not routed to BTS".)
    client.post(f"{API}/crashes/{cid}/incident-vehicles", headers=insp,
                json={"vehicle_number": 1, "is_cmv": False})
    client.put(f"{API}/crashes/{cid}/initial-incident", headers=insp, json={"event_summary": "x"})
    submit = client.post(f"{API}/crashes/{cid}/initial-incident/submit", headers=insp)
    assert submit.status_code == 200, submit.text
    assert submit.json()["routed_to_bts"] is False
    assert _notif_rows(db, cid, "IN_SCOPE_ROUTING") == []

    # Now set scope to IN_SCOPE -> BTS routing re-triggers.
    resp = client.put(f"{API}/crashes/{cid}/scope", headers=analyst,
                      json={"is_qualifying": True, "scope": "IN_SCOPE"})
    assert resp.status_code == 200, resp.text
    after_first = _notif_rows(db, cid, "IN_SCOPE_ROUTING")
    assert len(after_first) >= 1

    # The BTS agent can see the notification through the inbox.
    bts = auth(BTS_AGENT)
    inbox = client.get(f"{API}/notifications", headers=bts).json()
    assert any(n["notification_type"] == "IN_SCOPE_ROUTING" and n["crash_id"] == cid for n in inbox)

    # Idempotent: re-setting IN_SCOPE (no transition) adds no second notification.
    resp = client.put(f"{API}/crashes/{cid}/scope", headers=analyst,
                      json={"is_qualifying": True, "scope": "IN_SCOPE"})
    assert resp.status_code == 200, resp.text
    assert len(_notif_rows(db, cid, "IN_SCOPE_ROUTING")) == len(after_first)


def test_set_scope_in_scope_without_submit_emits_no_bts_routing(client, auth, db):
    """No submitted IIF -> setting IN_SCOPE emits nothing to BTS."""
    insp = auth(INSPECTOR_KS)
    analyst = auth(ANALYST_KS)
    cid = _new_crash(client, insp)

    resp = client.put(f"{API}/crashes/{cid}/scope", headers=analyst,
                      json={"is_qualifying": True, "scope": "IN_SCOPE"})
    assert resp.status_code == 200, resp.text

    assert _notif_rows(db, cid, "IN_SCOPE_ROUTING") == []


# --------------------------------------------------------------------------- DL2 / DL8: scope re-derivation
# Regression tests for the defect in which classification ran exactly once, at
# crash creation — before any incident vehicle could exist — and was never
# re-invoked, so every crash stayed UNDETERMINED and matched neither routing
# branch on submit.
def test_scope_auto_resolves_when_qualifying_vehicle_is_added(client, auth):
    """Recording the heavy-duty truck re-derives scope with no manual step."""
    insp = auth(INSPECTOR_KS)
    cid = _new_crash(client, insp, state_code="KS", num_fatalities=1)

    assert client.get(f"{API}/crashes/{cid}/scope", headers=insp).json()["scope"] == "UNDETERMINED"

    client.post(f"{API}/crashes/{cid}/incident-vehicles", headers=insp,
                json={"vehicle_number": 1, "is_cmv": True, "us_dot_number": "1234567",
                      "make": "Freightliner", "vehicle_class": "8"})

    scope = client.get(f"{API}/crashes/{cid}/scope", headers=insp).json()
    assert scope["scope"] == "IN_SCOPE"
    assert scope["is_qualifying"] is True


def test_inspector_end_to_end_iif_routes_to_bts(client, auth, db):
    """The reported repro: an Inspector files a qualifying KS crash end-to-end and
    the submitted form reaches BTS instead of stranding at UNDETERMINED."""
    insp = auth(INSPECTOR_KS)
    cid = _new_crash(client, insp, state_code="KS", num_fatalities=1)

    client.post(f"{API}/crashes/{cid}/incident-vehicles", headers=insp,
                json={"vehicle_number": 1, "is_cmv": True, "us_dot_number": "1234567",
                      "make": "Freightliner", "vehicle_class": "8",
                      "carrier_name": "Synthetic Freight LLC"})
    client.post(f"{API}/crashes/{cid}/incident-persons", headers=insp,
                json={"person_type": "DRIVER", "injury": "FATAL", "related_vehicle_number": 1})
    client.put(f"{API}/crashes/{cid}/initial-incident", headers=insp,
               json={"event_summary": "Fatal Class 8 crash"})

    submit = client.post(f"{API}/crashes/{cid}/initial-incident/submit", headers=insp)
    assert submit.status_code == 200, submit.text
    assert submit.json()["routed_to_bts"] is True
    assert submit.json()["routed_out_of_scope"] is False
    # The visible symptom in the defect report was the submit banner reading
    # "notified 1 user(s)" — the State analyst alone. DL1 requires an in-scope
    # crash to reach BOTH recipients, so the count itself is the regression
    # guard: anything that silently stops routing to BTS drops it back to 1.
    assert submit.json()["notified_users"] == 2, submit.json()

    assert client.get(f"{API}/crashes/{cid}/scope", headers=insp).json()["scope"] == "IN_SCOPE"
    assert len(_notif_rows(db, cid, "IN_SCOPE_ROUTING")) >= 1

    # ...and it reaches the BTS CIPSEA Agent specifically, on the EMAIL channel —
    # not merely "some notification row exists". The defect report's inbox check
    # is what this asserts, at the recipient level.
    bts_agent = db.scalar(select(User).where(User.email == BTS_AGENT))
    routed = _notif_rows(db, cid, "IN_SCOPE_ROUTING")
    assert [n.recipient_user_id for n in routed] == [bts_agent.id]
    assert routed[0].channel == "EMAIL"

    # The State CMV Data Analyst keeps their own notification: in-scope routing
    # is additive, never a substitution of one recipient for the other.
    analyst = db.scalar(select(User).where(User.email == ANALYST_KS))
    new_iif = _notif_rows(db, cid, "NEW_IIF")
    assert [n.recipient_user_id for n in new_iif] == [analyst.id]


def test_recorded_vehicle_class_outside_study_does_not_qualify(client, auth):
    """A CMV that is not a Class 7/8 truck must not qualify the crash: the study's
    configured vehicle_classes now actually govern, rather than the is_cmv flag."""
    insp = auth(INSPECTOR_KS)
    cid = _new_crash(client, insp, state_code="KS", num_fatalities=1)

    client.post(f"{API}/crashes/{cid}/incident-vehicles", headers=insp,
                json={"vehicle_number": 1, "is_cmv": True, "us_dot_number": "1234567",
                      "vehicle_class": "3"})

    scope = client.get(f"{API}/crashes/{cid}/scope", headers=insp).json()
    assert scope["is_qualifying"] is False
    assert scope["scope"] == "OUT_OF_SCOPE"


def test_gvwr_below_study_minimum_does_not_qualify(client, auth):
    """With no class recorded, GVWR is evaluated against the study's min_gvwr_lbs."""
    insp = auth(INSPECTOR_KS)
    light = _new_crash(client, insp, state_code="KS", num_fatalities=1)
    client.post(f"{API}/crashes/{light}/incident-vehicles", headers=insp,
                json={"vehicle_number": 1, "is_cmv": True, "gvwr_lbs": 19500})
    assert client.get(f"{API}/crashes/{light}/scope", headers=insp).json()["is_qualifying"] is False

    heavy = _new_crash(client, insp, state_code="KS", num_fatalities=1)
    client.post(f"{API}/crashes/{heavy}/incident-vehicles", headers=insp,
                json={"vehicle_number": 1, "is_cmv": True, "gvwr_lbs": 80000})
    assert client.get(f"{API}/crashes/{heavy}/scope", headers=insp).json()["is_qualifying"] is True


def test_scope_follows_its_inputs_back_down(client, auth):
    """Un-flagging the only heavy-duty truck must un-qualify the crash — the
    stored verdict tracks its inputs in both directions."""
    insp = auth(INSPECTOR_KS)
    cid = _new_crash(client, insp, state_code="KS", num_fatalities=1)

    veh = client.post(f"{API}/crashes/{cid}/incident-vehicles", headers=insp,
                      json={"vehicle_number": 1, "is_cmv": True, "vehicle_class": "8"}).json()
    assert client.get(f"{API}/crashes/{cid}/scope", headers=insp).json()["scope"] == "IN_SCOPE"

    client.patch(f"{API}/crashes/{cid}/incident-vehicles/{veh['id']}", headers=insp,
                 json={"vehicle_number": 1, "is_cmv": False, "vehicle_class": "3"})
    assert client.get(f"{API}/crashes/{cid}/scope", headers=insp).json()["scope"] == "OUT_OF_SCOPE"


def test_manual_override_is_not_clobbered_by_auto_refresh(client, auth):
    """A deliberate PUT /scope decision survives later vehicle edits."""
    insp = auth(INSPECTOR_KS)
    analyst = auth(ANALYST_KS)
    cid = _new_crash(client, insp, state_code="KS", num_fatalities=1)

    override = client.put(f"{API}/crashes/{cid}/scope", headers=analyst,
                          json={"is_qualifying": False, "scope": "OUT_OF_SCOPE",
                                "classification_reason": "Analyst review: duplicate report"})
    assert override.status_code == 200, override.text
    assert override.json()["is_manual_override"] is True

    # A vehicle that would otherwise derive IN_SCOPE must not overwrite it.
    client.post(f"{API}/crashes/{cid}/incident-vehicles", headers=insp,
                json={"vehicle_number": 1, "is_cmv": True, "vehicle_class": "8"})
    held = client.get(f"{API}/crashes/{cid}/scope", headers=insp).json()
    assert held["scope"] == "OUT_OF_SCOPE"
    assert held["classification_reason"] == "Analyst review: duplicate report"

    # An explicit reclassify is a deliberate request to re-derive, so it wins and
    # returns the record to automatic upkeep.
    forced = client.post(f"{API}/crashes/{cid}/scope/reclassify", headers=analyst).json()
    assert forced["scope"] == "IN_SCOPE"
    assert forced["is_manual_override"] is False


def test_inspector_may_rerun_classification(client, auth):
    """The role that files the IIF can correct the classification its own
    submission produced: reclassify accepts initial_incident:write."""
    insp = auth(INSPECTOR_KS)
    cid = _new_crash(client, insp, state_code="KS", num_fatalities=1)
    client.post(f"{API}/crashes/{cid}/incident-vehicles", headers=insp,
                json={"vehicle_number": 1, "is_cmv": True, "vehicle_class": "8"})

    resp = client.post(f"{API}/crashes/{cid}/scope/reclassify", headers=insp)
    assert resp.status_code == 200, resp.text
    assert resp.json()["scope"] == "IN_SCOPE"


def test_inspector_cannot_manually_override_scope(client, auth):
    """Recomputing a derived value is not the same privilege as overriding it:
    the Inspector holds initial_incident:write but not crash:update."""
    insp = auth(INSPECTOR_KS)
    cid = _new_crash(client, insp, state_code="KS", num_fatalities=1)

    resp = client.put(f"{API}/crashes/{cid}/scope", headers=insp,
                      json={"is_qualifying": True, "scope": "IN_SCOPE"})
    assert resp.status_code == 403, resp.text


def test_correcting_fatality_count_re_derives_scope(client, auth):
    """PATCH /crashes must not leave the verdict stale against its own inputs."""
    insp = auth(INSPECTOR_KS)
    analyst = auth(ANALYST_KS)
    cid = _new_crash(client, insp, state_code="KS", num_fatalities=0)
    client.post(f"{API}/crashes/{cid}/incident-vehicles", headers=insp,
                json={"vehicle_number": 1, "is_cmv": True, "vehicle_class": "8"})

    # No fatality yet -> not a qualifying Phase 1 crash.
    assert client.get(f"{API}/crashes/{cid}/scope", headers=insp).json()["scope"] == "OUT_OF_SCOPE"

    resp = client.patch(f"{API}/crashes/{cid}", headers=analyst, json={"num_fatalities": 1})
    assert resp.status_code == 200, resp.text
    assert client.get(f"{API}/crashes/{cid}/scope", headers=insp).json()["scope"] == "IN_SCOPE"


# --------------------------------------------------------------------------- DL1: no silent non-routing
def test_unclassifiable_submit_is_announced_not_silent(client, auth, db):
    """A crash submitted with facts still missing matches neither routing branch.

    That silence is the shape the BTS-routing defect hid in: the form reaches
    ROUTED and nobody is told. The scope must stay UNDETERMINED (nothing is
    assumed), BTS must NOT be routed, and the CCFP Project Team must be told the
    crash could not be classified.
    """
    insp = auth(INSPECTOR_KS)
    # No incident vehicles recorded -> the Phase 1 rule cannot be evaluated.
    cid = _new_crash(client, insp, state_code="KS", num_fatalities=1)
    client.put(f"{API}/crashes/{cid}/initial-incident", headers=insp,
               json={"event_summary": "Fatal crash; vehicles not yet identified"})

    submit = client.post(f"{API}/crashes/{cid}/initial-incident/submit", headers=insp)
    assert submit.status_code == 200, submit.text
    body = submit.json()
    assert body["routed_to_bts"] is False
    assert body["routed_out_of_scope"] is False
    assert body["routed_unclassified"] is True, body

    assert client.get(f"{API}/crashes/{cid}/scope", headers=insp).json()["scope"] == "UNDETERMINED"
    # Nothing is invented for BTS: an unclassified crash is not an in-scope one.
    assert _notif_rows(db, cid, "IN_SCOPE_ROUTING") == []
    # ...but it is no longer silent.
    flagged = _notif_rows(db, cid, "SCOPE_UNDETERMINED")
    assert len(flagged) >= 1
    ident = client.get(f"{API}/crashes/{cid}", headers=insp).json()["ccfp_identifier"]
    assert ident in (flagged[0].message or "")


def test_unclassified_crash_reaches_bts_once_the_vehicle_is_recorded(client, auth, db):
    """The recovery path: supplying the missing fact routes the crash to BTS."""
    insp = auth(INSPECTOR_KS)
    cid = _new_crash(client, insp, state_code="KS", num_fatalities=1)
    client.put(f"{API}/crashes/{cid}/initial-incident", headers=insp,
               json={"event_summary": "Fatal crash; vehicles not yet identified"})
    client.post(f"{API}/crashes/{cid}/initial-incident/submit", headers=insp)
    assert _notif_rows(db, cid, "IN_SCOPE_ROUTING") == []

    # Recording the heavy-duty truck re-derives scope; the crash becomes IN_SCOPE
    # after submit, which is the NOTI-7 transition that routes it to BTS.
    resp = client.post(f"{API}/crashes/{cid}/incident-vehicles", headers=insp,
                       json={"vehicle_number": 1, "is_cmv": True, "vehicle_class": "8"})
    assert resp.status_code == 201, resp.text

    assert client.get(f"{API}/crashes/{cid}/scope", headers=insp).json()["scope"] == "IN_SCOPE"
    assert len(_notif_rows(db, cid, "IN_SCOPE_ROUTING")) == 1
