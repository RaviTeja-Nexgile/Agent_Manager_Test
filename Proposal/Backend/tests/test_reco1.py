"""RECO-1: coding reconstruction findings writes provenance-tagged
CrashAttributeValue rows (source_system="RECONSTRUCTION") so coded findings reach
the aggregated attribute set, QC, completeness, and analysis (§8.6, §11.3).

All tests run inside a rolled-back transaction (see conftest)."""
from __future__ import annotations

from tests.conftest import ANALYST_KS, INSPECTOR_KS, PUBLIC

API = "/api/v1"


def _study_id(client, headers) -> str:
    return next(s for s in client.get(f"{API}/studies", headers=headers).json() if s["code"] == "PHASE1-HDT")["id"]


def _real_attribute_code(client, headers) -> str:
    """Pick a real data-attribute code from the catalog (robust to seed drift)."""
    attrs = client.get(f"{API}/data-attributes", headers=headers).json()
    assert attrs, "expected a seeded data-attribute catalog"
    return attrs[0]["code"]


def _make_crash_with_recon(client, auth):
    """Create a KS crash (inspector) and a reconstruction report (analyst).
    Returns (crash_id, recon_id, analyst_headers)."""
    insp = auth(INSPECTOR_KS)
    analyst = auth(ANALYST_KS)
    study_id = _study_id(client, insp)
    cid = client.post(
        f"{API}/crashes", headers=insp,
        json={"study_id": study_id, "state_code": "KS"},
    ).json()["id"]
    rid = client.post(
        f"{API}/crashes/{cid}/reconstruction-reports", headers=analyst,
        json={"title": "Recon A", "received_date": "2026-05-02"},
    ).json()["id"]
    return cid, rid, analyst


def test_code_recon_creates_attribute_value_with_reconstruction_provenance(client, auth):
    cid, rid, analyst = _make_crash_with_recon(client, auth)
    code = _real_attribute_code(client, analyst)

    resp = client.patch(
        f"{API}/crashes/{cid}/reconstruction-reports/{rid}", headers=analyst,
        json={
            "coding_status": "CODED",
            "coded_attributes": [{"attribute_code": code, "value_text": "Following too closely", "confidence": 0.8}],
        },
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["coding_status"] == "CODED"

    # The coded finding now shows up on the crash's aggregated attributes, tagged
    # to the reconstruction source.
    attrs = client.get(f"{API}/crashes/{cid}/attributes", headers=analyst).json()
    match = next((a for a in attrs if a["code"] == code), None)
    assert match is not None, f"coded attribute {code} not in aggregated set: {attrs}"
    assert match["source_system"] == "RECONSTRUCTION"
    assert match["value_text"] == "Following too closely"
    assert match["is_edited"] is True


def test_code_recon_appends_new_current_value(client, auth):
    """Recoding the same attribute flips the prior value to non-current and the
    aggregated view returns only the latest (append-only history)."""
    cid, rid, analyst = _make_crash_with_recon(client, auth)
    code = _real_attribute_code(client, analyst)

    client.patch(
        f"{API}/crashes/{cid}/reconstruction-reports/{rid}", headers=analyst,
        json={"coding_status": "CODED", "coded_attributes": [{"attribute_code": code, "value_text": "first"}]},
    )
    client.patch(
        f"{API}/crashes/{cid}/reconstruction-reports/{rid}", headers=analyst,
        json={"coding_status": "CODED", "coded_attributes": [{"attribute_code": code, "value_text": "second"}]},
    )
    attrs = [a for a in client.get(f"{API}/crashes/{cid}/attributes", headers=analyst).json() if a["code"] == code]
    assert len(attrs) == 1
    assert attrs[0]["value_text"] == "second"


def test_code_recon_unknown_attribute_code_is_400(client, auth):
    cid, rid, analyst = _make_crash_with_recon(client, auth)
    resp = client.patch(
        f"{API}/crashes/{cid}/reconstruction-reports/{rid}", headers=analyst,
        json={"coding_status": "CODED", "coded_attributes": [{"attribute_code": "NO_SUCH_ATTR_CODE", "value_text": "x"}]},
    )
    assert resp.status_code == 400, resp.text


def test_code_recon_unknown_code_writes_nothing(client, auth):
    """An unknown code fails the whole request before any attribute is written."""
    cid, rid, analyst = _make_crash_with_recon(client, auth)
    good = _real_attribute_code(client, analyst)
    resp = client.patch(
        f"{API}/crashes/{cid}/reconstruction-reports/{rid}", headers=analyst,
        json={
            "coding_status": "CODED",
            "coded_attributes": [
                {"attribute_code": good, "value_text": "ok"},
                {"attribute_code": "NO_SUCH_ATTR_CODE", "value_text": "bad"},
            ],
        },
    )
    assert resp.status_code == 400, resp.text
    attrs = client.get(f"{API}/crashes/{cid}/attributes", headers=analyst).json()
    assert all(a["code"] != good for a in attrs), "no attribute should be written when the request fails"


def test_code_recon_forbidden_for_public_user(client, auth):
    """PUBLIC lacks recon:code -> 403 (authorization case)."""
    cid, rid, analyst = _make_crash_with_recon(client, auth)
    code = _real_attribute_code(client, analyst)
    resp = client.patch(
        f"{API}/crashes/{cid}/reconstruction-reports/{rid}", headers=auth(PUBLIC),
        json={"coding_status": "CODED", "coded_attributes": [{"attribute_code": code, "value_text": "x"}]},
    )
    assert resp.status_code == 403, resp.text
