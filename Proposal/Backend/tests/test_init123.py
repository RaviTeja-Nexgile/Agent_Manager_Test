"""INIT-1 / INIT-2 / INIT-3: structured incident-person fields.

Closes three Initial Incident Form gaps on `incident_persons`:

* INIT-1 — capture the name as structured parts (`name_last` / `name_first` /
  `name_middle`); the API derives the existing `full_name` from the parts so
  readers and PII masking are unchanged.
* INIT-2 — capture two phone numbers, each with its own HOME/CELL/WORK type
  (`phone_primary_type` / `phone_secondary_type`); the type *labels* are not PII
  (the numbers still are).
* INIT-3 — capture an occupant-vs-pedestrian discriminator (`non_motorist_kind`)
  that is only valid when `person_type == NON_MOTORIST`.

All tests run inside the shared rolled-back transaction (see conftest) so the
development database is never mutated.
"""
from __future__ import annotations

import uuid

from app.enums import NonMotoristKind, PhoneType
from app.features.initial_incident import PersonOut, _person_out
from app.models import IncidentPerson
from tests.conftest import INSPECTOR_KS, PUBLIC

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


# --------------------------------------------------------------------------- INIT-1: name parts
def test_name_parts_round_trip_and_derive_full_name(client, auth):
    """POSTing last/first/middle returns the parts and a derived full_name
    ("first middle last"); GET round-trips all of them."""
    insp = auth(INSPECTOR_KS)
    cid = _make_crash(client, insp)

    created = client.post(
        f"{API}/crashes/{cid}/incident-persons", headers=insp,
        json={"person_type": "DRIVER", "name_last": "Vargas", "name_first": "Lina",
              "name_middle": "M", "injury": "NO_INJURY"},
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["name_last"] == "Vargas"
    assert body["name_first"] == "Lina"
    assert body["name_middle"] == "M"
    # full_name derived from the parts: "first middle last".
    assert body["full_name"] == "Lina M Vargas"

    listed = client.get(f"{API}/crashes/{cid}/incident-persons", headers=insp).json()
    person = next(p for p in listed if p["id"] == body["id"])
    assert (person["name_last"], person["name_first"], person["name_middle"]) == ("Vargas", "Lina", "M")
    assert person["full_name"] == "Lina M Vargas"


def test_full_name_derivation_skips_blank_middle(client, auth):
    """A missing middle name is dropped from the derived full_name (no double
    space) — filter(None, ...) ignores blank parts."""
    insp = auth(INSPECTOR_KS)
    cid = _make_crash(client, insp)

    created = client.post(
        f"{API}/crashes/{cid}/incident-persons", headers=insp,
        json={"person_type": "DRIVER", "name_last": "Okafor", "name_first": "Tunde"},
    ).json()
    assert created["full_name"] == "Tunde Okafor"


def test_direct_full_name_kept_when_no_parts(client, auth):
    """When no structured parts are supplied, a directly-provided full_name is
    preserved (backward compatibility with existing callers)."""
    insp = auth(INSPECTOR_KS)
    cid = _make_crash(client, insp)

    created = client.post(
        f"{API}/crashes/{cid}/incident-persons", headers=insp,
        json={"person_type": "WITNESS", "full_name": "Legacy Name"},
    ).json()
    assert created["full_name"] == "Legacy Name"
    assert created["name_last"] is None and created["name_first"] is None


# --------------------------------------------------------------------------- INIT-2: phones + types
def test_two_phones_with_types_round_trip(client, auth):
    """Both phone numbers and both per-number types round-trip on GET."""
    insp = auth(INSPECTOR_KS)
    cid = _make_crash(client, insp)

    created = client.post(
        f"{API}/crashes/{cid}/incident-persons", headers=insp,
        json={"person_type": "DRIVER", "phone_primary": "555-0100", "phone_primary_type": "CELL",
              "phone_secondary": "555-0200", "phone_secondary_type": "WORK"},
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["phone_primary_type"] == "CELL"
    assert body["phone_secondary_type"] == "WORK"

    listed = client.get(f"{API}/crashes/{cid}/incident-persons", headers=insp).json()
    person = next(p for p in listed if p["id"] == body["id"])
    assert person["phone_primary"] == "555-0100"
    assert person["phone_primary_type"] == "CELL"
    assert person["phone_secondary"] == "555-0200"
    assert person["phone_secondary_type"] == "WORK"


def test_invalid_phone_type_rejected(client, auth):
    """An unknown phone type (not HOME/CELL/WORK) is rejected with 422 by the
    PhoneType-validated schema."""
    insp = auth(INSPECTOR_KS)
    cid = _make_crash(client, insp)

    resp = client.post(
        f"{API}/crashes/{cid}/incident-persons", headers=insp,
        json={"person_type": "DRIVER", "phone_primary": "555-0100", "phone_primary_type": "PAGER"},
    )
    assert resp.status_code == 422, resp.text


# --------------------------------------------------------------------------- INIT-3: non-motorist kind
def test_non_motorist_kind_round_trips(client, auth):
    """A NON_MOTORIST person with non_motorist_kind:"PEDESTRIAN" round-trips."""
    insp = auth(INSPECTOR_KS)
    cid = _make_crash(client, insp)

    created = client.post(
        f"{API}/crashes/{cid}/incident-persons", headers=insp,
        json={"person_type": "NON_MOTORIST", "non_motorist_kind": "PEDESTRIAN"},
    )
    assert created.status_code == 201, created.text
    assert created.json()["non_motorist_kind"] == "PEDESTRIAN"

    listed = client.get(f"{API}/crashes/{cid}/incident-persons", headers=insp).json()
    person = next(p for p in listed if p["id"] == created.json()["id"])
    assert person["non_motorist_kind"] == "PEDESTRIAN"


def test_invalid_non_motorist_kind_rejected(client, auth):
    """An unknown kind (not OCCUPANT/PEDESTRIAN) is rejected with 422."""
    insp = auth(INSPECTOR_KS)
    cid = _make_crash(client, insp)

    resp = client.post(
        f"{API}/crashes/{cid}/incident-persons", headers=insp,
        json={"person_type": "NON_MOTORIST", "non_motorist_kind": "CYCLIST"},
    )
    assert resp.status_code == 422, resp.text


def test_non_motorist_kind_rejected_for_non_non_motorist(client, auth):
    """Cross-field guard: a non-null non_motorist_kind on a DRIVER is a 400
    BadRequest — the discriminator is only valid for NON_MOTORIST."""
    insp = auth(INSPECTOR_KS)
    cid = _make_crash(client, insp)

    resp = client.post(
        f"{API}/crashes/{cid}/incident-persons", headers=insp,
        json={"person_type": "DRIVER", "non_motorist_kind": "PEDESTRIAN"},
    )
    assert resp.status_code == 400, resp.text


# --------------------------------------------------------------------------- PII masking & authorization
def test_person_out_redacts_name_parts_and_numbers_without_pii():
    """Unit-level: when allow_pii is False, the name parts and full_name and the
    phone NUMBERS are redacted to None, but the phone-type LABELS and the
    non_motorist_kind (not PII) are preserved. This exercises the exact redaction
    branch served to any reader who passes the endpoint gate but lacks PII
    sensitivity."""
    p = IncidentPerson(
        id=uuid.uuid4(), crash_id=uuid.uuid4(), person_type="NON_MOTORIST",
        related_vehicle_number=None, full_name="Lina M Vargas",
        name_last="Vargas", name_first="Lina", name_middle="M",
        is_minor=False, primary_language="en", address="1 Main St",
        phone_primary="555-0100", phone_secondary="555-0200", phone_type="CELL",
        phone_primary_type=PhoneType.CELL.value, phone_secondary_type=PhoneType.WORK.value,
        non_motorist_kind=NonMotoristKind.PEDESTRIAN.value, injury="NO_INJURY",
        is_supplemental=False,
    )

    masked = _person_out(p, allow_pii=False)
    assert isinstance(masked, PersonOut)
    assert masked.pii_redacted is True
    # PII redacted.
    assert masked.full_name is None
    assert masked.name_last is None and masked.name_first is None and masked.name_middle is None
    assert masked.address is None
    assert masked.phone_primary is None and masked.phone_secondary is None
    # Non-PII labels preserved.
    assert masked.phone_primary_type == "CELL"
    assert masked.phone_secondary_type == "WORK"
    assert masked.non_motorist_kind == "PEDESTRIAN"

    allowed = _person_out(p, allow_pii=True)
    assert allowed.pii_redacted is False
    assert allowed.full_name == "Lina M Vargas"
    assert allowed.name_last == "Vargas"
    assert allowed.phone_primary == "555-0100"


def test_public_user_cannot_read_incident_persons(client, auth):
    """Negative/authorization case: a Public user lacks crash:read and
    initial_incident:read, so reading the persons list is rejected (403). PII
    never leaves the API for an unauthorized actor — the endpoint gate blocks
    them before any row is serialized."""
    insp = auth(INSPECTOR_KS)
    pub = auth(PUBLIC)
    cid = _make_crash(client, insp)
    client.post(
        f"{API}/crashes/{cid}/incident-persons", headers=insp,
        json={"person_type": "DRIVER", "name_last": "Vargas", "name_first": "Lina"},
    )

    resp = client.get(f"{API}/crashes/{cid}/incident-persons", headers=pub)
    assert resp.status_code == 403, resp.text
