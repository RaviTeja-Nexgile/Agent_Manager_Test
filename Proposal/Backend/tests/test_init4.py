"""INIT-4: IIF general-information & location fields are editable after creation
via the existing ``PATCH /crashes/{id}`` (CrashUpdate). The IIF tab surfaces an
edit card that wires Save to ``crashApi.update`` and gates it on ``crash:update``.

These tests exercise the backend contract the new UI relies on:
  * a user with ``crash:update`` (KS State CMV Analyst) can PATCH the general-info
    / location fields and a subsequent GET reflects them, and
  * a user without ``crash:update`` (MCSAP Inspector — IIF read/write but no
    ``crash:update``) is rejected with 403.

All work runs inside the rolled-back transaction provided by the ``client``/``db``
fixtures, so the live database is never mutated.
"""
from __future__ import annotations

from tests.conftest import ANALYST_KS, INSPECTOR_KS

API = "/api/v1"


def _study_id(client, headers) -> str:
    return next(
        s for s in client.get(f"{API}/studies", headers=headers).json() if s["code"] == "PHASE1-HDT"
    )["id"]


def _new_ks_crash(client, headers, study_id: str) -> str:
    """Create a fresh KS crash (inspector or analyst both hold crash:create)."""
    resp = client.post(
        f"{API}/crashes",
        headers=headers,
        json={"study_id": study_id, "state_code": "KS", "city": "Topeka", "num_fatalities": 1},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def test_analyst_can_patch_general_info_and_location(client, auth):
    """KS analyst (has crash:update) edits IIF general-info/location → GET reflects it."""
    analyst = auth(ANALYST_KS)
    study_id = _study_id(client, analyst)
    cid = _new_ks_crash(client, analyst, study_id)

    patch = client.patch(
        f"{API}/crashes/{cid}",
        headers=analyst,
        json={
            "city": "Lawrence",
            "county": "Douglas",
            "street_highway": "I-70 near MM 202",
            "local_report_number": "KS-2026-0042",
            "num_vehicles": 3,
            "num_persons": 5,
            "num_fatalities": 2,
        },
    )
    assert patch.status_code == 200, patch.text

    got = client.get(f"{API}/crashes/{cid}", headers=analyst).json()
    assert got["city"] == "Lawrence"
    assert got["county"] == "Douglas"
    assert got["street_highway"] == "I-70 near MM 202"
    assert got["local_report_number"] == "KS-2026-0042"
    assert got["num_vehicles"] == 3
    assert got["num_persons"] == 5
    assert got["num_fatalities"] == 2


def test_partial_patch_leaves_other_fields_untouched(client, auth):
    """exclude_unset: omitting fields in the PATCH body must not clear them."""
    analyst = auth(ANALYST_KS)
    study_id = _study_id(client, analyst)
    cid = _new_ks_crash(client, analyst, study_id)

    # Only city changes; the seed-on-create county/num_fatalities must persist.
    patch = client.patch(f"{API}/crashes/{cid}", headers=analyst, json={"city": "Olathe"})
    assert patch.status_code == 200, patch.text

    got = client.get(f"{API}/crashes/{cid}", headers=analyst).json()
    assert got["city"] == "Olathe"
    assert got["num_fatalities"] == 1  # untouched create value
    assert got["state_code"] == "KS"


def test_inspector_without_crash_update_is_forbidden(client, auth):
    """Negative/authorization: MCSAP Inspector lacks crash:update → PATCH is 403.

    The IIF tab gates the edit card on crash:update precisely so this role never
    sees a Save control that the API would reject.
    """
    inspector = auth(INSPECTOR_KS)
    study_id = _study_id(client, inspector)
    # Inspector holds crash:create, so it can create the crash it then cannot edit.
    cid = _new_ks_crash(client, inspector, study_id)

    resp = client.patch(
        f"{API}/crashes/{cid}", headers=inspector, json={"city": "Lawrence", "num_fatalities": 2}
    )
    assert resp.status_code == 403, resp.text

    # And the value is unchanged when read back by an authorized user.
    analyst = auth(ANALYST_KS)
    got = client.get(f"{API}/crashes/{cid}", headers=analyst).json()
    assert got["city"] == "Topeka"
    assert got["num_fatalities"] == 1
