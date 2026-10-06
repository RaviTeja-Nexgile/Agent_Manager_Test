"""PCI epic (Wave C) tests — structured post-crash investigation sections
(PCI-1), repeating child arrays (PCI-4), optional conditional sections (PCI-5),
per-study field-definition validation on submit (PCI-3), and ELD summary fields
(PCI-7). All run inside a rolled-back transaction (see conftest)."""
from __future__ import annotations

import io

from tests.conftest import ANALYST_KS, PUBLIC

API = "/api/v1"


def _study_id(client, headers) -> str:
    return next(
        s for s in client.get(f"{API}/studies", headers=headers).json() if s["code"] == "PHASE1-HDT"
    )["id"]


def _new_ks_crash(client, headers, study_id) -> str:
    """Create a fresh KS crash (rolled back at test end) so tests never depend on
    a seed identifier that drifts as seeds grow."""
    return client.post(
        f"{API}/crashes", headers=headers,
        json={"study_id": study_id, "state_code": "KS", "city": "Topeka", "crash_date": "2026-05-01", "num_fatalities": 1},
    ).json()["id"]


# --------------------------------------------------------------------------- PCI-1/4/5 create + round-trip
def test_investigation_structured_sections_roundtrip(client, auth):
    analyst = auth(ANALYST_KS)
    study_id = _study_id(client, analyst)
    cid = _new_ks_crash(client, analyst, study_id)

    body = {
        "case_number": "PCI-CASE-1",
        "carrier_power_unit": {
            "carrier_name_displayed": "ACME Trucking",
            "vin": "1XPWD40X1ED215307",
            "make": "Peterbilt",
            "model": "579",
            "year": 2021,
            "gvwr": 80000,
            "fire": False,
        },
        "driver_load": {
            "driver_name": "Jane Driver",
            "driver_present": True,
            "license_number": "K1234567",
            "license_state": "KS",
            "cargo_loaded": "Steel coils",
            "load_securement": True,
        },
        "seating_positions": [
            {"position": "DRIVER", "seat_belt_equipped": True, "seat_belt_used": True},
            {"position": "PASSENGER_1", "seat_belt_equipped": True, "seat_belt_used": False},
        ],
        "axles": [
            {"axle_index": 1, "abs": True},
            {"axle_index": 2, "abs": True},
            {"axle_index": 3, "abs": False},
        ],
        "trailers": [
            {"trailer_index": 1, "vin": "TRL-VIN-1", "trailer_type": "VAN", "gvwr": 34000},
        ],
        "has_hazmat": True,
        "hazmat": [
            {"unit_scope": "TRUCK", "hazmat_present": True, "hazmat_type": "Class 3", "spill": False},
        ],
    }
    resp = client.post(f"{API}/crashes/{cid}/post-crash-investigations", headers=analyst, json=body)
    assert resp.status_code == 201, resp.text
    created = resp.json()

    # Single-valued sections echo back structurally.
    assert created["carrier_power_unit"]["carrier_name_displayed"] == "ACME Trucking"
    assert created["carrier_power_unit"]["vin"] == "1XPWD40X1ED215307"
    assert float(created["carrier_power_unit"]["gvwr"]) == 80000.0
    assert created["driver_load"]["driver_name"] == "Jane Driver"
    assert created["driver_load"]["load_securement"] is True
    # Sections not supplied are null, not fabricated.
    assert created["medical_certificate"] is None
    assert created["brake_system"] is None

    # Repeating arrays echo with their index/position values.
    assert {p["position"] for p in created["seating_positions"]} == {"DRIVER", "PASSENGER_1"}
    assert sorted(a["axle_index"] for a in created["axles"]) == [1, 2, 3]
    assert len(created["trailers"]) == 1 and created["trailers"][0]["trailer_index"] == 1

    # Optional conditional section persisted because has_hazmat is true.
    assert created["has_hazmat"] is True
    assert len(created["hazmat"]) == 1
    assert created["hazmat"][0]["hazmat_type"] == "Class 3"

    # GET round-trips the same structured data.
    rec_id = created["id"]
    got = client.get(f"{API}/crashes/{cid}/post-crash-investigations/{rec_id}", headers=analyst).json()
    assert got["carrier_power_unit"]["make"] == "Peterbilt"
    assert sorted(a["axle_index"] for a in got["axles"]) == [1, 2, 3]
    assert len(got["seating_positions"]) == 2
    assert len(got["hazmat"]) == 1


def test_investigation_hazmat_flag_off_not_persisted(client, auth):
    """PCI-5: a stray hazmat row with has_hazmat=false must NOT be persisted."""
    analyst = auth(ANALYST_KS)
    study_id = _study_id(client, analyst)
    cid = _new_ks_crash(client, analyst, study_id)

    body = {
        "case_number": "PCI-CASE-NOHAZ",
        "has_hazmat": False,
        "hazmat": [{"unit_scope": "TRUCK", "hazmat_present": True, "hazmat_type": "Class 8"}],
        "has_additional_towed_units": False,
        "additional_towed_units": [{"towed_index": 1, "unit_type": "DOLLY"}],
    }
    resp = client.post(f"{API}/crashes/{cid}/post-crash-investigations", headers=analyst, json=body)
    assert resp.status_code == 201, resp.text
    created = resp.json()
    assert created["has_hazmat"] is False
    assert created["hazmat"] == []
    assert created["additional_towed_units"] == []

    # Confirm persistence (not just the create echo).
    got = client.get(f"{API}/crashes/{cid}/post-crash-investigations/{created['id']}", headers=analyst).json()
    assert got["hazmat"] == []
    assert got["additional_towed_units"] == []


# --------------------------------------------------------------------------- PCI-3 field definitions + submit validation
def test_pci_field_definitions_endpoint(client, auth):
    analyst = auth(ANALYST_KS)
    study_id = _study_id(client, analyst)
    resp = client.get(f"{API}/studies/{study_id}/pci-field-definitions", headers=analyst)
    assert resp.status_code == 200, resp.text
    defs = resp.json()
    assert len(defs) > 0
    # Seed marks these required (schema summary): assert at least one required def
    # exists and carries the expected shape.
    required = [d for d in defs if d["is_required"]]
    assert required
    sample = required[0]
    assert {"section_code", "field_code", "is_required", "is_optional"} <= set(sample.keys())
    # is_optional is NOT(is_required) per seed.
    assert all(d["is_optional"] == (not d["is_required"]) for d in defs)


def test_submit_blocks_when_required_field_empty(client, auth):
    """PCI-3: submit must 400 while a required field is empty, then succeed once filled."""
    analyst = auth(ANALYST_KS)
    study_id = _study_id(client, analyst)
    cid = _new_ks_crash(client, analyst, study_id)

    # Create with required fields deliberately missing (no carrier_power_unit /
    # driver_load / hours_of_service / brake_system).
    created = client.post(
        f"{API}/crashes/{cid}/post-crash-investigations", headers=analyst,
        json={"case_number": "PCI-SUBMIT-1"},
    ).json()
    rec_id = created["id"]

    blocked = client.post(
        f"{API}/crashes/{cid}/post-crash-investigations/{rec_id}/submit", headers=analyst
    )
    assert blocked.status_code == 400, blocked.text

    # Fill every seeded-required field (CARRIER_POWER_UNIT.carrier_name_displayed,
    # CARRIER_POWER_UNIT.vin, DRIVER_LOAD.driver_name, HOURS_OF_SERVICE.driving_hours,
    # BRAKE_SYSTEM.brake_type).
    filled = client.patch(
        f"{API}/crashes/{cid}/post-crash-investigations/{rec_id}", headers=analyst,
        json={
            "case_number": "PCI-SUBMIT-1",
            "carrier_power_unit": {"carrier_name_displayed": "ACME", "vin": "1XPVIN0000000001"},
            "driver_load": {"driver_name": "Jane Driver"},
            "hours_of_service": {"driving_hours": 9.5},
            "brake_system": {"brake_type": "AIR"},
        },
    )
    assert filled.status_code == 200, filled.text

    ok = client.post(
        f"{API}/crashes/{cid}/post-crash-investigations/{rec_id}/submit", headers=analyst
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["status"] == "SUBMITTED"


# --------------------------------------------------------------------------- PCI-7 ELD summary PATCH
def test_eld_summary_patch_roundtrip(client, auth):
    analyst = auth(ANALYST_KS)
    study_id = _study_id(client, analyst)
    cid = _new_ks_crash(client, analyst, study_id)

    # Upload a minimal ELD CSV so a file record exists to PATCH.
    files = {"file": ("eld.csv", io.BytesIO(b"timestamp,duty\n2026-05-01T08:00:00Z,DRIVING\n"), "text/csv")}
    up = client.post(f"{API}/crashes/{cid}/eld-files", headers=analyst, files=files)
    assert up.status_code == 201, up.text
    file_id = up.json()["id"]

    patch_body = {
        "eld_downloaded": True,
        "last_entry_at": "2026-05-01T08:30:00Z",
        "last_duty_status": "DRIVING",
        "last_stop_arrived_at": "2026-05-01T07:00:00Z",
        "last_stop_departed_at": "2026-05-01T07:45:00Z",
    }
    patched = client.patch(f"{API}/crashes/{cid}/eld-files/{file_id}", headers=analyst, json=patch_body)
    assert patched.status_code == 200, patched.text
    pj = patched.json()
    assert pj["eld_downloaded"] is True
    assert pj["last_duty_status"] == "DRIVING"

    # GET confirms persistence of the summary fields.
    got = client.get(f"{API}/crashes/{cid}/eld-files/{file_id}", headers=analyst).json()
    assert got["eld_downloaded"] is True
    assert got["last_duty_status"] == "DRIVING"
    assert got["last_entry_at"] is not None
    assert got["last_stop_arrived_at"] is not None
    assert got["last_stop_departed_at"] is not None


# --------------------------------------------------------------------------- negative / authorization
def test_public_user_cannot_post_investigation(client, auth):
    """public.demo lacks source_data:ingest -> 403 on investigation create."""
    analyst = auth(ANALYST_KS)
    study_id = _study_id(client, analyst)
    cid = _new_ks_crash(client, analyst, study_id)
    resp = client.post(
        f"{API}/crashes/{cid}/post-crash-investigations", headers=auth(PUBLIC),
        json={"case_number": "NOPE", "carrier_power_unit": {"carrier_name_displayed": "X"}},
    )
    assert resp.status_code == 403


def test_public_user_cannot_patch_eld_file(client, auth):
    """public.demo lacks eld:upload -> 403 on ELD summary PATCH."""
    analyst = auth(ANALYST_KS)
    study_id = _study_id(client, analyst)
    cid = _new_ks_crash(client, analyst, study_id)
    files = {"file": ("eld.csv", io.BytesIO(b"timestamp,duty\n2026-05-01T08:00:00Z,DRIVING\n"), "text/csv")}
    file_id = client.post(f"{API}/crashes/{cid}/eld-files", headers=analyst, files=files).json()["id"]

    resp = client.patch(
        f"{API}/crashes/{cid}/eld-files/{file_id}", headers=auth(PUBLIC),
        json={"eld_downloaded": True},
    )
    assert resp.status_code == 403
