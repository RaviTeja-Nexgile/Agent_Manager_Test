"""INIT-8: supplemental IIF records.

The IIF supports supplemental (repeatable, beyond-the-base-form) vehicle,
non-motorist and witness records via an `is_supplemental` flag (documentation
§19.1 l.832-834, §8.2 l.250). The UI now sets and displays the flag; these tests
codify that the API round-trips it for both incident vehicles and persons, and
that the write path stays authorization-gated. All run inside a rolled-back
transaction so the development database is never mutated.
"""
from __future__ import annotations

from tests.conftest import ANALYST_KS, INSPECTOR_KS, PUBLIC

API = "/api/v1"


def _study_id(client, headers) -> str:
    return next(s for s in client.get(f"{API}/studies", headers=headers).json() if s["code"] == "PHASE1-HDT")["id"]


def _make_crash(client, headers) -> str:
    study_id = _study_id(client, headers)
    resp = client.post(
        f"{API}/crashes", headers=headers,
        json={"study_id": study_id, "state_code": "KS", "city": "Topeka", "county": "Shawnee",
              "crash_date": "2026-05-01", "num_fatalities": 1},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def test_supplemental_vehicle_round_trips(client, auth):
    """POSTing a vehicle with is_supplemental:true returns it and GET reflects it."""
    insp = auth(INSPECTOR_KS)
    cid = _make_crash(client, insp)

    created = client.post(
        f"{API}/crashes/{cid}/incident-vehicles", headers=insp,
        json={"vehicle_number": 2, "is_cmv": False, "is_supplemental": True},
    )
    assert created.status_code == 201, created.text
    assert created.json()["is_supplemental"] is True

    listed = client.get(f"{API}/crashes/{cid}/incident-vehicles", headers=insp).json()
    veh = next(v for v in listed if v["vehicle_number"] == 2)
    assert veh["is_supplemental"] is True


def test_vehicle_supplemental_defaults_false(client, auth):
    """Omitting the flag (base-form record) defaults to False — not supplemental."""
    insp = auth(INSPECTOR_KS)
    cid = _make_crash(client, insp)

    created = client.post(
        f"{API}/crashes/{cid}/incident-vehicles", headers=insp,
        json={"vehicle_number": 1, "is_cmv": True},
    )
    assert created.status_code == 201, created.text
    assert created.json()["is_supplemental"] is False


def test_vehicle_supplemental_updatable_via_patch(client, auth):
    """An existing base-form vehicle can be flagged supplemental via PATCH."""
    insp = auth(INSPECTOR_KS)
    cid = _make_crash(client, insp)

    created = client.post(
        f"{API}/crashes/{cid}/incident-vehicles", headers=insp,
        json={"vehicle_number": 3, "is_cmv": False},
    ).json()
    assert created["is_supplemental"] is False

    patched = client.patch(
        f"{API}/crashes/{cid}/incident-vehicles/{created['id']}", headers=insp,
        json={"vehicle_number": 3, "is_cmv": False, "is_supplemental": True},
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["is_supplemental"] is True


def test_supplemental_person_round_trips(client, auth):
    """POSTing a person with is_supplemental:true returns it and GET reflects it."""
    insp = auth(INSPECTOR_KS)
    cid = _make_crash(client, insp)

    created = client.post(
        f"{API}/crashes/{cid}/incident-persons", headers=insp,
        json={"person_type": "WITNESS", "full_name": "Supp Witness", "is_supplemental": True},
    )
    assert created.status_code == 201, created.text
    assert created.json()["is_supplemental"] is True

    listed = client.get(f"{API}/crashes/{cid}/incident-persons", headers=insp).json()
    person = next(p for p in listed if p["person_type"] == "WITNESS")
    assert person["is_supplemental"] is True


def test_person_supplemental_defaults_false(client, auth):
    """Omitting the flag defaults to False for persons too."""
    insp = auth(INSPECTOR_KS)
    cid = _make_crash(client, insp)

    created = client.post(
        f"{API}/crashes/{cid}/incident-persons", headers=insp,
        json={"person_type": "DRIVER", "full_name": "Base Driver"},
    )
    assert created.status_code == 201, created.text
    assert created.json()["is_supplemental"] is False


def test_supplemental_write_requires_permission(client, auth):
    """Negative/authorization case: a user without initial_incident:write cannot
    create supplemental records. PUBLIC lacks the write permission, so the POSTs
    are rejected (403) — the flag never reaches the store via an unauthorized actor."""
    insp = auth(INSPECTOR_KS)
    pub = auth(PUBLIC)
    cid = _make_crash(client, insp)

    veh = client.post(
        f"{API}/crashes/{cid}/incident-vehicles", headers=pub,
        json={"vehicle_number": 9, "is_supplemental": True},
    )
    assert veh.status_code == 403, veh.text

    person = client.post(
        f"{API}/crashes/{cid}/incident-persons", headers=pub,
        json={"person_type": "WITNESS", "is_supplemental": True},
    )
    assert person.status_code == 403, person.text


def test_supplemental_write_audited(client, auth, db):
    """The existing create handler keeps writing audit_logs (DoD) — flagging a
    record supplemental does not bypass the audit trail."""
    import uuid
    from sqlalchemy import select
    from app.models import AuditLog, IncidentVehicle

    insp = auth(INSPECTOR_KS)
    cid = _make_crash(client, insp)

    created = client.post(
        f"{API}/crashes/{cid}/incident-vehicles", headers=insp,
        json={"vehicle_number": 5, "is_supplemental": True},
    ).json()

    audits = db.scalars(
        select(AuditLog).where(
            AuditLog.entity_type == "incident_vehicle",
            AuditLog.entity_id == uuid.UUID(created["id"]),
            AuditLog.action == "CREATE",
        )
    ).all()
    assert len(audits) == 1
    # sanity: the supplemental flag actually persisted on the row.
    veh = db.get(IncidentVehicle, uuid.UUID(created["id"]))
    assert veh is not None and veh.is_supplemental is True
