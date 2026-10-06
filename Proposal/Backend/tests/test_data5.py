"""DATA-5: source-record lineage on attribute values (documentation §11.3 line
505 — "Every source value must retain provenance"; §5 Phase 4 links source records
to the crash).

The ``crash_attribute_values.source_record_id`` FK already existed but the write
path never populated it. ``set_attribute`` now accepts an optional
``source_record_id`` on the input schema, validates it references a
``source_records`` row for *this* crash (400 otherwise), persists it, and surfaces
it on ``AttributeValueOut`` (both the set return and the ``get_attributes`` list).

All tests run inside a rolled-back transaction (see conftest) so the live
development database is never mutated.

Coverage:
  * Setting an attribute with a valid same-crash ``source_record_id`` returns 201
    with the id echoed, and ``GET .../attributes`` reports the same id (lineage
    persisted on the current row).
  * Setting an attribute with no ``source_record_id`` leaves lineage null
    (backward-compatible: free-text ``source_system`` still works).
  * Negative: a ``source_record_id`` that belongs to a *different* crash is
    rejected with 400 BadRequest (cross-crash references must not be persisted).
  * Negative/authorization: a Public user lacks ``data_mgmt:edit`` -> 403, so the
    lineage write path is gated exactly like every other attribute write.
"""
from __future__ import annotations

from tests.conftest import ANALYST_KS, INSPECTOR_KS, PUBLIC

API = "/api/v1"


def _phase1_study_id(client, auth) -> str:
    insp = auth(INSPECTOR_KS)
    return next(
        s for s in client.get(f"{API}/studies", headers=insp).json() if s["code"] == "PHASE1-HDT"
    )["id"]


def _fresh_ks_crash(client, auth, study_id: str) -> str:
    """Create a fresh (unlocked) IN_SCOPE KS crash and return its id.

    A new crash has no completeness row, so _is_crash_locked() is False and
    attribute writes are accepted (unlike the seeded locked CCFP-2026-KS-000101).
    """
    insp = auth(INSPECTOR_KS)
    analyst = auth(ANALYST_KS)
    crash = client.post(
        f"{API}/crashes", headers=insp,
        json={"study_id": study_id, "state_code": "KS", "city": "Topeka", "county": "Shawnee",
              "crash_date": "2026-05-04", "num_fatalities": 1},
    )
    assert crash.status_code == 201, crash.text
    cid = crash.json()["id"]
    client.put(f"{API}/crashes/{cid}/scope", headers=analyst, json={"is_qualifying": True, "scope": "IN_SCOPE"})
    return cid


def _source_record_id(client, auth, crash_id: str) -> str:
    """Create a source record on the crash (via a PCR, which calls _link_source)
    and return its id from GET /crashes/{id}/sources.

    The analyst holds source_data:ingest (-> add_pcr) and data_mgmt:read_raw
    (-> get_sources), so one role drives the whole setup.
    """
    analyst = auth(ANALYST_KS)
    pcr = client.post(
        f"{API}/crashes/{crash_id}/police-crash-reports", headers=analyst,
        json={"source_repository": "MCMIS", "pcr_number": "PCR-DATA5-1"},
    )
    assert pcr.status_code == 201, pcr.text
    sources = client.get(f"{API}/crashes/{crash_id}/sources", headers=analyst)
    assert sources.status_code == 200, sources.text
    recs = sources.json()
    assert recs, "expected at least one source record after adding a PCR"
    return recs[0]["id"]


# --------------------------------------------------------------------------- positive
def test_set_attribute_persists_valid_source_record_lineage(client, auth):
    """A same-crash source_record_id is echoed on the 201 and persisted so the
    aggregated-attributes list reports the same precise lineage pointer."""
    analyst = auth(ANALYST_KS)
    study_id = _phase1_study_id(client, auth)
    cid = _fresh_ks_crash(client, auth, study_id)
    src_id = _source_record_id(client, auth, cid)

    resp = client.post(
        f"{API}/crashes/{cid}/attributes", headers=analyst,
        json={"attribute_code": "C04", "value_text": "Salina", "source_record_id": src_id},
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["source_record_id"] == src_id

    listed = client.get(f"{API}/crashes/{cid}/attributes", headers=analyst)
    assert listed.status_code == 200, listed.text
    c04 = next(a for a in listed.json() if a["code"] == "C04")
    assert c04["source_record_id"] == src_id
    assert c04["value_text"] == "Salina"


def test_set_attribute_without_source_record_leaves_lineage_null(client, auth):
    """Backward-compatible: omitting source_record_id keeps it null while the
    free-text source_system label still round-trips."""
    analyst = auth(ANALYST_KS)
    study_id = _phase1_study_id(client, auth)
    cid = _fresh_ks_crash(client, auth, study_id)

    resp = client.post(
        f"{API}/crashes/{cid}/attributes", headers=analyst,
        json={"attribute_code": "C04", "value_text": "Wichita", "source_system": "Manual"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["source_record_id"] is None
    assert body["source_system"] == "Manual"


# --------------------------------------------------------------------------- negative
def test_set_attribute_rejects_cross_crash_source_record(client, auth):
    """A source_record_id belonging to a *different* crash is a client error:
    cross-crash lineage must never be persisted (400 BadRequest)."""
    analyst = auth(ANALYST_KS)
    study_id = _phase1_study_id(client, auth)
    target = _fresh_ks_crash(client, auth, study_id)
    other = _fresh_ks_crash(client, auth, study_id)
    foreign_src_id = _source_record_id(client, auth, other)

    resp = client.post(
        f"{API}/crashes/{target}/attributes", headers=analyst,
        json={"attribute_code": "C04", "value_text": "Salina", "source_record_id": foreign_src_id},
    )
    assert resp.status_code == 400, resp.text


def test_set_attribute_requires_edit_permission(client, auth):
    """Authorization: a Public user lacks data_mgmt:edit, so the attribute write
    (and thus the lineage write path) is forbidden (403)."""
    public = auth(PUBLIC)
    study_id = _phase1_study_id(client, auth)
    cid = _fresh_ks_crash(client, auth, study_id)

    resp = client.post(
        f"{API}/crashes/{cid}/attributes", headers=public,
        json={"attribute_code": "C04", "value_text": "Salina"},
    )
    assert resp.status_code == 403, resp.text
