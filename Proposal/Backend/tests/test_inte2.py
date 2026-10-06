"""INTE-2 — wire DQ_CDLIS_CHECK to the existing mock CDLIS adapter.

The data-quality rule must route each DRIVER incident-person through the
already-present `cdlis.verify_driver` adapter (mock until a live client is
configured behind `integration_cdlis_live`) instead of merely asserting that a
driver row exists. All tests run inside a rolled-back transaction so the live
development database is never mutated."""
from __future__ import annotations

import uuid

from app import workers
from tests.conftest import ANALYST_KS, INSPECTOR_KS

API = "/api/v1"


def _study_id(client, headers) -> str:
    return next(
        s for s in client.get(f"{API}/studies", headers=headers).json()
        if s["code"] == "PHASE1-HDT"
    )["id"]


def _create_ks_crash(client, insp_headers) -> str:
    study_id = _study_id(client, insp_headers)
    return client.post(
        f"{API}/crashes",
        headers=insp_headers,
        json={
            "study_id": study_id, "state_code": "KS", "city": "Topeka",
            "county": "Shawnee", "crash_date": "2026-05-01", "num_fatalities": 1,
        },
    ).json()["id"]


def _cdlis_result(qc: dict) -> dict:
    return next(r for r in qc["results"] if r["rule"] == "DQ_CDLIS_CHECK")


# --------------------------------------------------------------------------- positive
def test_cdlis_check_passes_via_mock_adapter(client, auth, db):
    """A crash with a named DRIVER routes through the CDLIS adapter and PASSes,
    with a message referencing the mock CDLIS source."""
    insp = auth(INSPECTOR_KS)
    cid = _create_ks_crash(client, insp)

    # Add a DRIVER incident-person — full_name is the only available driver
    # identifier (no license column exists in-model).
    resp = client.post(
        f"{API}/crashes/{cid}/incident-persons",
        headers=insp,
        json={"person_type": "DRIVER", "full_name": "Wendell Pruitt", "injury": "NO_INJURY"},
    )
    assert resp.status_code == 201, resp.text

    qc = workers.evaluate_quality(uuid.UUID(cid), db=db)
    cdlis = _cdlis_result(qc)
    assert cdlis["status"] == "PASS"
    # Proves the adapter was actually exercised (mock returns "CDLIS (mock)").
    assert "CDLIS" in cdlis["message"]
    assert "CDLIS (mock)" in cdlis["message"]
    assert "1 driver" in cdlis["message"]


def test_cdlis_check_aggregates_multiple_drivers(client, auth, db):
    """Multiple named DRIVERs all validate via the mock adapter -> PASS, count
    reflected in the message."""
    insp = auth(INSPECTOR_KS)
    cid = _create_ks_crash(client, insp)
    for name in ("Wendell Pruitt", "Carla Devereaux"):
        client.post(
            f"{API}/crashes/{cid}/incident-persons",
            headers=insp,
            json={"person_type": "DRIVER", "full_name": name, "injury": "NO_INJURY"},
        )

    qc = workers.evaluate_quality(uuid.UUID(cid), db=db)
    cdlis = _cdlis_result(qc)
    assert cdlis["status"] == "PASS"
    assert "2 driver(s) validated via CDLIS (mock)." == cdlis["message"]


# --------------------------------------------------------------------------- negative (no drivers)
def test_cdlis_check_no_drivers_is_warning(client, auth, db):
    """A crash with no DRIVER rows still yields the unchanged WARNING message,
    so completeness behaviour is preserved (the rule is WARNING severity and
    does not count toward critical failures)."""
    insp = auth(INSPECTOR_KS)
    cid = _create_ks_crash(client, insp)

    qc = workers.evaluate_quality(uuid.UUID(cid), db=db)
    cdlis = _cdlis_result(qc)
    assert cdlis["status"] == "WARNING"
    assert cdlis["message"] == "No driver records to validate against CDLIS."


# --------------------------------------------------------------------------- authorization
def test_run_quality_requires_qc_permission(client, auth):
    """The QC evaluate route requires data_mgmt:qc. The MCSAP CMV Inspector
    holds source_data:ingest but NOT data_mgmt:qc, so triggering QC is 403 —
    confirming the CDLIS rule runs only inside the gated, audited QC flow."""
    insp = auth(INSPECTOR_KS)
    cid = _create_ks_crash(client, insp)
    resp = client.post(f"{API}/crashes/{cid}/quality/evaluate", headers=insp)
    assert resp.status_code == 403


def test_run_quality_allowed_for_analyst_runs_cdlis_rule(client, auth):
    """The KS State CMV Analyst holds data_mgmt:qc and can run QC end-to-end;
    the persisted DQ_CDLIS_CHECK result is then readable via GET .../quality and
    references CDLIS."""
    insp = auth(INSPECTOR_KS)
    analyst = auth(ANALYST_KS)
    cid = _create_ks_crash(client, insp)
    client.post(
        f"{API}/crashes/{cid}/incident-persons",
        headers=insp,
        json={"person_type": "DRIVER", "full_name": "Wendell Pruitt", "injury": "NO_INJURY"},
    )

    run = client.post(f"{API}/crashes/{cid}/quality/evaluate", headers=analyst)
    assert run.status_code == 200, run.text

    rows = client.get(f"{API}/crashes/{cid}/quality", headers=analyst).json()
    cdlis = next(r for r in rows if r["rule_code"] == "DQ_CDLIS_CHECK")
    assert cdlis["status"] == "PASS"
    assert "CDLIS" in cdlis["message"]
