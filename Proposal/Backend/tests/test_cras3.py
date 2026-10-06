"""CRAS-3 regression tests: the crash Overview "Edit" form depends on the
existing ``PATCH /crashes/{id}`` route to correct general-info / location metadata.

These prove the endpoint the UI calls behaves as the spec requires:
- a user with ``crash:update`` can edit a crash in their State and the change
  is persisted (visible on a subsequent GET);
- a user without ``crash:update`` (FEDERAL) is rejected with 403;
- a State-scoped user editing a crash outside their State is blocked by
  ``assert_crash_access`` (404/403), so the UI cannot defeat server-side scope.

All run inside a rolled-back transaction (see conftest)."""
from __future__ import annotations

from tests.conftest import (
    ANALYST_KS,
    ANALYST_TX,
    FEDERAL,
    INSPECTOR_KS,
)

API = "/api/v1"


def _study_id(client, headers) -> str:
    return next(
        s for s in client.get(f"{API}/studies", headers=headers).json()
        if s["code"] == "PHASE1-HDT"
    )["id"]


def _new_ks_crash(client, headers) -> str:
    study_id = _study_id(client, headers)
    resp = client.post(
        f"{API}/crashes", headers=headers,
        json={"study_id": study_id, "state_code": "KS", "city": "Topeka",
              "county": "Shawnee", "crash_date": "2026-05-01", "num_fatalities": 1},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def test_update_crash_metadata_persists(client, auth):
    """crash:update holder edits metadata; GET reflects the change (the UI flow).

    ANALYST_KS holds crash:update and is KS-scoped; INSPECTOR_KS (crash:create
    only) seeds the crash. (MCSAP inspectors lack crash:update in the seeded RBAC.)
    """
    insp = auth(INSPECTOR_KS)
    analyst = auth(ANALYST_KS)
    cid = _new_ks_crash(client, insp)

    patch = client.patch(
        f"{API}/crashes/{cid}", headers=analyst,
        json={"city": "Lawrence", "num_fatalities": 2},
    )
    assert patch.status_code == 200, patch.text
    assert patch.json()["city"] == "Lawrence"
    assert patch.json()["num_fatalities"] == 2

    # Re-fetch to prove the change is persisted, not just echoed.
    got = client.get(f"{API}/crashes/{cid}", headers=analyst).json()
    assert got["city"] == "Lawrence"
    assert got["num_fatalities"] == 2
    # Untouched fields are preserved (partial PATCH).
    assert got["county"] == "Shawnee"
    assert got["state_code"] == "KS"


def test_update_crash_coordinates_and_partial_fields(client, auth):
    """Numeric coordinate fields round-trip; omitted fields stay unchanged."""
    insp = auth(INSPECTOR_KS)
    analyst = auth(ANALYST_KS)
    cid = _new_ks_crash(client, insp)

    patch = client.patch(
        f"{API}/crashes/{cid}", headers=analyst,
        json={"latitude": 38.9717, "longitude": -95.2353,
              "local_report_number": "KS-2026-0042"},
    )
    assert patch.status_code == 200, patch.text
    body = patch.json()
    assert body["latitude"] == 38.9717
    assert body["longitude"] == -95.2353
    assert body["local_report_number"] == "KS-2026-0042"
    # City untouched by this PATCH.
    assert body["city"] == "Topeka"


def test_update_crash_denied_without_permission(client, auth):
    """FEDERAL lacks crash:update -> 403 (negative / authorization case)."""
    insp = auth(INSPECTOR_KS)
    cid = _new_ks_crash(client, insp)

    resp = client.patch(
        f"{API}/crashes/{cid}", headers=auth(FEDERAL),
        json={"city": "Lawrence"},
    )
    assert resp.status_code == 403, resp.text
    # The crash must be unchanged.
    got = client.get(f"{API}/crashes/{cid}", headers=auth(ANALYST_KS)).json()
    assert got["city"] == "Topeka"


def test_update_crash_outside_state_scope_blocked(client, auth):
    """A TX-scoped analyst PATCHing a KS crash is blocked by assert_crash_access."""
    insp = auth(INSPECTOR_KS)
    cid = _new_ks_crash(client, insp)

    resp = client.patch(
        f"{API}/crashes/{cid}", headers=auth(ANALYST_TX),
        json={"city": "Lawrence"},
    )
    assert resp.status_code in (403, 404), resp.text
    # The crash must be unchanged.
    got = client.get(f"{API}/crashes/{cid}", headers=auth(ANALYST_KS)).json()
    assert got["city"] == "Topeka"
