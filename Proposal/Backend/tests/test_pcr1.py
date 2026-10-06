"""PCR-1 tests: State PCR field -> CCFP attribute mapping (§8.5 / §19.4).

Covers the new pcr_field_mapping CRUD and the strengthened /map gate. All run
inside the shared rolled-back transaction (see conftest)."""
from __future__ import annotations

from tests.conftest import ANALYST_KS, INSPECTOR_KS

API = "/api/v1"


def _study_id(client, headers) -> str:
    return next(s for s in client.get(f"{API}/studies", headers=headers).json() if s["code"] == "PHASE1-HDT")["id"]


def _make_crash_and_pcr(client, auth) -> tuple[str, str]:
    """Create a KS crash + a PCR on it; return (crash_id, pcr_id)."""
    insp = auth(INSPECTOR_KS)
    crash = client.post(
        f"{API}/crashes", headers=insp,
        json={"study_id": _study_id(client, insp), "state_code": "KS",
              "city": "Topeka", "crash_date": "2026-05-01", "num_fatalities": 1},
    ).json()
    cid = crash["id"]
    pcr = client.post(
        f"{API}/crashes/{cid}/police-crash-reports", headers=insp,
        json={"pcr_number": "KS-PCR-TEST-1", "source_repository": "KARS", "state_code": "KS"},
    )
    assert pcr.status_code == 201, pcr.text
    return cid, pcr.json()["id"]


def test_add_list_and_map_field_mapping(client, auth):
    analyst = auth(ANALYST_KS)
    cid, pcr_id = _make_crash_and_pcr(client, auth)
    base = f"{API}/crashes/{cid}/police-crash-reports/{pcr_id}/field-mappings"

    # POST a field mapping -> 201, resolves C01 and echoes mapped fields.
    created = client.post(
        base, headers=analyst,
        json={"state_field_name": "ACCIDENT_KEY", "attribute_code": "C01"},
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["state_field_name"] == "ACCIDENT_KEY"
    assert body["attribute_code"] == "C01"
    assert body["attribute_id"]

    # GET lists exactly the mapping we just created.
    listed = client.get(base, headers=analyst)
    assert listed.status_code == 200, listed.text
    rows = listed.json()
    assert len(rows) == 1
    assert rows[0]["attribute_code"] == "C01"

    # /map now succeeds (>=1 mapping exists) and sets MAPPED.
    mapped = client.post(f"{API}/crashes/{cid}/police-crash-reports/{pcr_id}/map", headers=analyst)
    assert mapped.status_code == 200, mapped.text
    assert mapped.json()["mapping_status"] == "MAPPED"


def test_unknown_attribute_code_is_404(client, auth):
    analyst = auth(ANALYST_KS)
    cid, pcr_id = _make_crash_and_pcr(client, auth)
    resp = client.post(
        f"{API}/crashes/{cid}/police-crash-reports/{pcr_id}/field-mappings",
        headers=analyst,
        json={"state_field_name": "FOO", "attribute_code": "NOT_A_REAL_CODE"},
    )
    assert resp.status_code == 404, resp.text


def test_inspector_lacking_pcr_map_is_403(client, auth):
    # The inspector can ingest/create the PCR but lacks pcr:map, so mapping is denied.
    cid, pcr_id = _make_crash_and_pcr(client, auth)
    resp = client.post(
        f"{API}/crashes/{cid}/police-crash-reports/{pcr_id}/field-mappings",
        headers=auth(INSPECTOR_KS),
        json={"state_field_name": "ACCIDENT_KEY", "attribute_code": "C01"},
    )
    assert resp.status_code == 403, resp.text


def test_map_with_zero_mappings_is_400(client, auth):
    analyst = auth(ANALYST_KS)
    cid, pcr_id = _make_crash_and_pcr(client, auth)
    # No field mappings recorded yet -> /map must refuse to flip to MAPPED.
    resp = client.post(f"{API}/crashes/{cid}/police-crash-reports/{pcr_id}/map", headers=analyst)
    assert resp.status_code == 400, resp.text


def test_delete_field_mapping(client, auth):
    analyst = auth(ANALYST_KS)
    cid, pcr_id = _make_crash_and_pcr(client, auth)
    base = f"{API}/crashes/{cid}/police-crash-reports/{pcr_id}/field-mappings"

    created = client.post(base, headers=analyst, json={"state_field_name": "ACCIDENT_KEY", "attribute_code": "C01"})
    assert created.status_code == 201, created.text
    mapping_id = created.json()["id"]

    deleted = client.request("DELETE", f"{base}/{mapping_id}", headers=analyst)
    assert deleted.status_code in (204, 200), deleted.text

    # The list is empty again after delete.
    rows = client.get(base, headers=analyst).json()
    assert rows == []
