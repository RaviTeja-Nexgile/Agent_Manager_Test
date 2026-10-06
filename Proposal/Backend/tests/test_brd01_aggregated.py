"""CCFP Aggregated Data tests (BRD January 2026).

Covers the Appendix D external-system catalog, the crash -> external-system
linkage owned by the CCFP Database Administrator, and the rewritten
``GET /crashes/{id}/aggregated`` document. All run inside the shared rolled-back
transaction (see conftest)."""
from __future__ import annotations

from tests.conftest import ANALYST_KS, ANALYST_TX, DB_ADMIN, INSPECTOR_KS, SCIENTIST, SYSADMIN

API = "/api/v1"


def _study_id(client, headers) -> str:
    return next(s for s in client.get(f"{API}/studies", headers=headers).json() if s["code"] == "PHASE1-HDT")["id"]


def _make_crash(client, auth) -> str:
    insp = auth(INSPECTOR_KS)
    resp = client.post(
        f"{API}/crashes", headers=insp,
        json={"study_id": _study_id(client, insp), "state_code": "KS",
              "city": "Topeka", "crash_date": "2026-05-04", "num_fatalities": 1},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _link(client, headers, crash_id, **overrides):
    body = {"source_system": "DACH", "external_ref": "DACH-QUERY-0001"}
    body.update(overrides)
    return client.post(f"{API}/crashes/{crash_id}/external-links", headers=headers, json=body)


# --------------------------------------------------------------- catalog
def test_external_systems_catalog_matches_appendix_d(client, auth):
    """All 17 Appendix D sources are seeded: 11 FMCSA-owned + 6 other-entity."""
    resp = client.get(f"{API}/external-systems", headers=auth(ANALYST_KS))
    assert resp.status_code == 200, resp.text
    rows = resp.json()
    codes = {r["code"] for r in rows}

    # The three sources the January 2026 BRD ADDED to Appendix D.
    assert {"MCMIS", "NRCME", "SAFESPECT_INSPECTIONS"} <= codes
    # The eight FMCSA-owned sources that were already there.
    assert {"ACE", "DATAQS", "DIR", "DACH", "DSMS", "ELD_ERODS", "SMS", "TPR"} <= codes
    # The six owned by other entities.
    assert {"BTS_SECURE_DB", "CDLIS", "HPMS_MIRE", "GOOGLE_MAPS", "NHTSA_RECALLS", "NOAA_HRRR"} <= codes

    assert sum(1 for r in rows if r["is_fmcsa_owned"]) == 11
    assert sum(1 for r in rows if not r["is_fmcsa_owned"]) == 6
    # The BRD's own "Relevant Data for CCFP" text is retained for traceability.
    mcmis = next(r for r in rows if r["code"] == "MCMIS")
    assert "Motus" in mcmis["relevant_data"]


# --------------------------------------------------------------- aggregated document
def test_aggregated_returns_the_full_document(client, auth):
    """The endpoint returns attributes + source records + external links, not just counts."""
    crash_id = _make_crash(client, auth)
    resp = client.get(f"{API}/crashes/{crash_id}/aggregated", headers=auth(DB_ADMIN))
    assert resp.status_code == 200, resp.text
    doc = resp.json()

    assert doc["crash_id"] == crash_id
    assert doc["ccfp_identifier"]
    for key in ("attributes", "source_records", "external_links"):
        assert isinstance(doc[key], list), key
    summary = doc["summary"]
    assert summary["source_record_count"] == len(doc["source_records"])
    assert summary["external_link_count"] == len(doc["external_links"])


def test_aggregated_keeps_the_pre_existing_counts(client, auth):
    """Backward compatibility: the four scalars this endpoint used to return are
    still present at the top level and now mirrored under `summary`."""
    crash_id = _make_crash(client, auth)
    doc = client.get(f"{API}/crashes/{crash_id}/aggregated", headers=auth(DB_ADMIN)).json()

    for key in ("current_attribute_count", "required_attribute_count", "required_present", "required_missing"):
        assert isinstance(doc[key], int), key
        assert doc[key] == doc["summary"][key], key
    assert doc["required_present"] + doc["required_missing"] == doc["required_attribute_count"]


def test_aggregated_redacts_sensitive_attribute_values(client, auth):
    """Assembling the document must not become a disclosure path: redaction is
    the same as GET /crashes/{id}/attributes. CX1 (Crash description) is
    SENSITIVE; the DBA is in the PII access group, the Data Scientist is not."""
    crash_id = _make_crash(client, auth)
    dba = auth(DB_ADMIN)
    set_resp = client.post(
        f"{API}/crashes/{crash_id}/attributes", headers=dba,
        json={"attribute_code": "CX1", "value_text": "Narrative with identifying detail."},
    )
    assert set_resp.status_code in (200, 201), set_resp.text

    def cx1(headers):
        doc = client.get(f"{API}/crashes/{crash_id}/aggregated", headers=headers).json()
        return next(a for a in doc["attributes"] if a["code"] == "CX1")

    allowed = cx1(dba)
    assert allowed["redacted"] is False
    assert allowed["value_text"] == "Narrative with identifying detail."

    withheld = cx1(auth(SCIENTIST))
    assert withheld["redacted"] is True
    assert withheld["value_text"] is None


def test_aggregated_respects_state_scope(client, auth):
    """A KS-scoped analyst cannot assemble the aggregated document for a TX crash."""
    tx = client.get(f"{API}/crashes", headers=auth(ANALYST_TX)).json()["items"]
    assert tx, "expected seeded TX crashes"
    resp = client.get(f"{API}/crashes/{tx[0]['id']}/aggregated", headers=auth(ANALYST_KS))
    assert resp.status_code == 403, resp.text


# --------------------------------------------------------------- linking
def test_dba_links_external_system_and_document_includes_it(client, auth):
    crash_id = _make_crash(client, auth)
    dba = auth(DB_ADMIN)

    created = _link(
        client, dba, crash_id,
        matched_on={"dot_number": "1234567", "crash_date": "2026-05-04"},
        confidence=92.5,
        notes="Matched on carrier DOT number and crash date.",
    )
    assert created.status_code == 201, created.text
    link = created.json()
    assert link["source_system"] == "DACH"
    assert link["source_system_name"] == "Drug and Alcohol Clearinghouse (DACH)"
    assert link["link_method"] == "MANUAL"
    assert link["is_current"] is True
    assert link["linked_by_name"]
    assert link["matched_on"]["dot_number"] == "1234567"

    doc = client.get(f"{API}/crashes/{crash_id}/aggregated", headers=dba).json()
    assert doc["summary"]["external_link_count"] == 1
    assert doc["external_links"][0]["external_ref"] == "DACH-QUERY-0001"


def test_link_method_is_configurable(client, auth):
    crash_id = _make_crash(client, auth)
    resp = _link(client, auth(DB_ADMIN), crash_id, source_system="MCMIS",
                 external_ref="MCMIS-778812", link_method="AUTO")
    assert resp.status_code == 201, resp.text
    assert resp.json()["link_method"] == "AUTO"


def test_source_system_code_is_normalised(client, auth):
    crash_id = _make_crash(client, auth)
    resp = _link(client, auth(DB_ADMIN), crash_id, source_system="  tpr  ", external_ref="TPR-55")
    assert resp.status_code == 201, resp.text
    assert resp.json()["source_system"] == "TPR"


def test_unknown_external_system_is_400(client, auth):
    crash_id = _make_crash(client, auth)
    resp = _link(client, auth(DB_ADMIN), crash_id, source_system="NOT_A_SYSTEM")
    assert resp.status_code == 400, resp.text


def test_blank_external_ref_is_400(client, auth):
    crash_id = _make_crash(client, auth)
    resp = _link(client, auth(DB_ADMIN), crash_id, external_ref="   ")
    assert resp.status_code == 400, resp.text


def test_out_of_range_confidence_is_400(client, auth):
    crash_id = _make_crash(client, auth)
    resp = _link(client, auth(DB_ADMIN), crash_id, confidence=140)
    assert resp.status_code == 400, resp.text


def test_duplicate_current_link_is_409(client, auth):
    crash_id = _make_crash(client, auth)
    dba = auth(DB_ADMIN)
    assert _link(client, dba, crash_id).status_code == 201
    assert _link(client, dba, crash_id).status_code == 409


def test_analyst_without_aggregated_link_is_403(client, auth):
    """The State CMV Analyst can READ aggregated data but the BRD assigns the
    linkage itself to the CCFP Database Administrator."""
    crash_id = _make_crash(client, auth)
    resp = _link(client, auth(ANALYST_KS), crash_id)
    assert resp.status_code == 403, resp.text


# --------------------------------------------------------------- unlinking
def test_unlink_is_append_only_and_permits_relink(client, auth):
    crash_id = _make_crash(client, auth)
    dba = auth(DB_ADMIN)
    link_id = _link(client, dba, crash_id).json()["id"]
    base = f"{API}/crashes/{crash_id}/external-links"

    removed = client.request("DELETE", f"{base}/{link_id}", headers=dba)
    assert removed.status_code == 204, removed.text

    # Current view is empty; the row itself is retained, not deleted.
    assert client.get(base, headers=dba).json() == []
    history = client.get(base, headers=dba, params={"include_historical": True}).json()
    assert len(history) == 1
    assert history[0]["id"] == link_id
    assert history[0]["is_current"] is False

    # The same reference can be linked again — uq_cel_current is partial.
    relinked = _link(client, dba, crash_id)
    assert relinked.status_code == 201, relinked.text
    assert relinked.json()["id"] != link_id


def test_double_unlink_is_400(client, auth):
    crash_id = _make_crash(client, auth)
    dba = auth(DB_ADMIN)
    link_id = _link(client, dba, crash_id).json()["id"]
    base = f"{API}/crashes/{crash_id}/external-links/{link_id}"
    assert client.request("DELETE", base, headers=dba).status_code == 204
    assert client.request("DELETE", base, headers=dba).status_code == 400


def test_unlink_of_another_crashes_link_is_404(client, auth):
    dba = auth(DB_ADMIN)
    crash_a = _make_crash(client, auth)
    crash_b = _make_crash(client, auth)
    link_id = _link(client, dba, crash_a).json()["id"]
    resp = client.request("DELETE", f"{API}/crashes/{crash_b}/external-links/{link_id}", headers=dba)
    assert resp.status_code == 404, resp.text


def test_analyst_without_aggregated_link_cannot_unlink(client, auth):
    crash_id = _make_crash(client, auth)
    link_id = _link(client, auth(DB_ADMIN), crash_id).json()["id"]
    resp = client.request(
        "DELETE", f"{API}/crashes/{crash_id}/external-links/{link_id}", headers=auth(ANALYST_KS)
    )
    assert resp.status_code == 403, resp.text


# --------------------------------------------------------------- audit
def test_link_and_unlink_are_audited(client, auth):
    """Linking changes state, so both directions must land in the immutable log."""
    crash_id = _make_crash(client, auth)
    dba = auth(DB_ADMIN)
    link_id = _link(client, dba, crash_id).json()["id"]
    client.request("DELETE", f"{API}/crashes/{crash_id}/external-links/{link_id}", headers=dba)

    logs = client.get(
        f"{API}/audit-logs", headers=auth(SYSADMIN),
        params={"crash_id": crash_id, "entity_type": "crash_external_link"},
    )
    assert logs.status_code == 200, logs.text
    actions = {row["action"] for row in logs.json()["items"]}
    assert {"LINK_EXTERNAL", "UNLINK_EXTERNAL"} <= actions
