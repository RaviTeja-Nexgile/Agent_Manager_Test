"""DATA-7: per-group contributing-factor value catalog.

Covers the new ``GET /contributing-factor-values`` lookup and the catalog
validation added to ``PUT /crashes/{id}/contributing-factors``. All requests run
inside the shared rolled-back transaction (see ``conftest.py``)."""
from __future__ import annotations

from tests.conftest import ANALYST_KS, INSPECTOR_KS, PUBLIC

API = "/api/v1"


def _study_id(client, headers) -> str:
    return next(s for s in client.get(f"{API}/studies", headers=headers).json() if s["code"] == "PHASE1-HDT")["id"]


def _ks_crash_id(client, insp) -> str:
    study_id = _study_id(client, insp)
    return client.post(
        f"{API}/crashes", headers=insp,
        json={"study_id": study_id, "state_code": "KS"},
    ).json()["id"]


# --------------------------------------------------------------------------- catalog lookup
def test_factor_values_filtered_by_group(client, auth):
    """An analyst can read a group's value catalog; it is non-empty and scoped."""
    analyst = auth(ANALYST_KS)
    resp = client.get(f"{API}/contributing-factor-values", headers=analyst, params={"group_code": "DRIVER_ACTIONS"})
    assert resp.status_code == 200, resp.text
    values = resp.json()
    assert values, "DRIVER_ACTIONS catalog should be seeded and non-empty"
    # Every returned value must belong to a single group and expose the catalog shape.
    group_ids = {v["factor_group_id"] for v in values}
    assert len(group_ids) == 1
    for v in values:
        assert set(v) >= {"id", "factor_group_id", "code", "label"}
    labels = {v["label"] for v in values}
    assert "Following too closely" in labels  # lifecycle-test value stays in the catalog


def test_factor_values_unfiltered_returns_all(client, auth):
    """Without ?group_code the endpoint returns the full catalog across groups."""
    analyst = auth(ANALYST_KS)
    resp = client.get(f"{API}/contributing-factor-values", headers=analyst)
    assert resp.status_code == 200, resp.text
    values = resp.json()
    assert values
    # Spans more than one group when unfiltered.
    assert len({v["factor_group_id"] for v in values}) > 1


def test_factor_values_unknown_group_is_empty(client, auth):
    analyst = auth(ANALYST_KS)
    resp = client.get(f"{API}/contributing-factor-values", headers=analyst, params={"group_code": "NOPE-NOPE"})
    assert resp.status_code == 200, resp.text
    assert resp.json() == []


# --------------------------------------------------------------------------- authorization
def test_factor_values_requires_auth(client):
    assert client.get(f"{API}/contributing-factor-values").status_code == 401


def test_factor_values_denied_without_crash_read(client, auth):
    """Public user lacks crash:read and must be rejected (403)."""
    assert client.get(f"{API}/contributing-factor-values", headers=auth(PUBLIC)).status_code == 403


# --------------------------------------------------------------------------- catalog validation on save
def test_set_factor_with_catalog_value_succeeds(client, auth):
    insp = auth(INSPECTOR_KS)
    analyst = auth(ANALYST_KS)
    cid = _ks_crash_id(client, insp)
    resp = client.put(
        f"{API}/crashes/{cid}/contributing-factors", headers=analyst,
        json={"factors": [
            {"factor_group_code": "DRIVER_ACTIONS", "factor_value": "Following too closely", "rank": 1},
            {"factor_group_code": "DRIVER_CONDITIONS", "factor_value": "Fatigue", "rank": 2},
            {"factor_group_code": "CC_VEHICLE", "factor_value": "Brakes", "rank": 3},
        ]},
    )
    assert resp.status_code == 200, resp.text
    assert len(resp.json()) == 3


def test_set_factor_with_unknown_catalog_value_rejected(client, auth):
    """A value that is not in the chosen group's catalog is a 400 (negative case)."""
    insp = auth(INSPECTOR_KS)
    analyst = auth(ANALYST_KS)
    cid = _ks_crash_id(client, insp)
    resp = client.put(
        f"{API}/crashes/{cid}/contributing-factors", headers=analyst,
        json={"factors": [{"factor_group_code": "DRIVER_ACTIONS", "factor_value": "totally-made-up", "rank": 1}]},
    )
    assert resp.status_code == 400, resp.text


def test_set_factor_value_validated_against_its_own_group(client, auth):
    """A real catalog label but under the wrong group is still rejected."""
    insp = auth(INSPECTOR_KS)
    analyst = auth(ANALYST_KS)
    cid = _ks_crash_id(client, insp)
    # 'Brakes' belongs to CC_VEHICLE, not DRIVER_ACTIONS.
    resp = client.put(
        f"{API}/crashes/{cid}/contributing-factors", headers=analyst,
        json={"factors": [{"factor_group_code": "DRIVER_ACTIONS", "factor_value": "Brakes", "rank": 1}]},
    )
    assert resp.status_code == 400, resp.text


def test_set_factor_without_group_allows_free_text(client, auth):
    """Back-compat: a NULL-group entry keeps free-text and is not catalog-checked."""
    insp = auth(INSPECTOR_KS)
    analyst = auth(ANALYST_KS)
    cid = _ks_crash_id(client, insp)
    resp = client.put(
        f"{API}/crashes/{cid}/contributing-factors", headers=analyst,
        json={"factors": [{"factor_value": "legacy free text", "rank": 1}]},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body) == 1
    assert body[0]["factor_group_id"] is None
    assert body[0]["factor_value"] == "legacy free text"
