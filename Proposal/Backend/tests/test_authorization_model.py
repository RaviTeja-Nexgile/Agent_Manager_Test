"""Tests for the January 2026 BRD's rewritten authorization model.

Four changes that describe one model:

  * A new CCFP Super User role (FMCSA Program Office resource) holding CRUD on
    dashboards, visualizations, reports and tables alongside the Project Team.
  * NTSB named as a consumer of shared data for the first time.
  * A formal four-tier audience taxonomy — FMCSA Federal Users / Other Federal
    Users (BTS, NHTSA, NTSB) / Participating State Users / Public Users —
    replacing a single collapsed FEDERAL tier.
  * Outward sharing reassigned from the CCFP Project Team to the CCFP Database
    Administrator, who previously held no report or analytics permission at all.

Role notes (seeds/0002 + 0018):
  * PROJECT (CCFP_PROJECT_TEAM) — FMCSA Federal tier; report:create + report:share.
  * SCIENTIST (CCFP_DATA_SCIENTIST) — FMCSA Federal tier; report:read, not an owner.
  * FEDERAL / NTSB_USER (FEDERAL_USER) — Other Federal tier; report:read.
  * DB_ADMIN (CCFP_DB_ADMIN) — the only business role that may release outward.
"""
from __future__ import annotations

from tests.conftest import (
    ANALYST_KS,
    ANALYST_TX,
    DB_ADMIN,
    FEDERAL,
    FMCSA_ENFORCEMENT,
    FMCSA_HQ,
    NTSB_USER,
    PROJECT,
    SCIENTIST,
    SUPER_USER,
)

API = "/api/v1"


def _report(client, headers, name, visibility, **extra):
    body = {"name": name, "report_type": "TABLE", "visibility": visibility,
            "definition": {"columns": ["a"], "rows": [{"a": 1}]}}
    body.update(extra)
    resp = client.post(f"{API}/reports", headers=headers, json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()


def _visible(client, headers, report_id) -> bool:
    return client.get(f"{API}/reports/{report_id}", headers=headers).status_code == 200


# --------------------------------------------------------------- Super User
def test_super_user_can_sign_in_and_holds_expected_reach(client, auth):
    me = client.get(f"{API}/auth/me", headers=auth(SUPER_USER))
    assert me.status_code == 200, me.text
    body = me.json()
    assert "CCFP_SUPER_USER" in body["roles"]
    # "Create and share dashboards, visualizations, reports, and tables" — CRUD.
    for code in ("report:create", "report:read", "report:share", "report:download",
                 "report:publish", "analytics:query", "analytics:dashboard"):
        assert code in body["permissions"], code


def test_super_user_can_create_and_share_a_report(client, auth):
    su = auth(SUPER_USER)
    report = _report(client, su, "Authz Super User Report", "FMCSA_FEDERAL")
    shared = client.post(
        f"{API}/reports/{report['id']}/share", headers=su,
        json={"shared_with_role_code": "CCFP_PROJECT_TEAM", "can_download": True},
    )
    assert shared.status_code == 201, shared.text


# --------------------------------------------------------------- NTSB
def test_ntsb_organization_exists(client, auth):
    orgs = client.get(f"{API}/organizations", headers=auth(PROJECT), params={"limit": 200})
    assert orgs.status_code == 200, orgs.text
    ntsb = [o for o in orgs.json()["items"] if o["org_type"] == "NTSB"]
    assert ntsb, "expected a seeded NTSB organization"
    assert ntsb[0]["name"] == "National Transportation Safety Board"


# --------------------------------------------------- four-tier separation
def test_fmcsa_federal_report_is_hidden_from_other_federal(client, auth):
    """An FMCSA-internal report must not reach BTS/NHTSA/NTSB consumers."""
    report = _report(client, auth(PROJECT), "Authz FMCSA Only", "FMCSA_FEDERAL")
    assert not _visible(client, auth(FEDERAL), report["id"])
    assert not _visible(client, auth(NTSB_USER), report["id"])


def test_fmcsa_federal_report_is_visible_within_the_fmcsa_tier(client, auth):
    report = _report(client, auth(PROJECT), "Authz FMCSA Tier", "FMCSA_FEDERAL")
    for who in (SCIENTIST, SUPER_USER, FMCSA_HQ, FMCSA_ENFORCEMENT):
        assert _visible(client, auth(who), report["id"]), who


def test_other_federal_report_is_hidden_from_the_fmcsa_tier(client, auth):
    """The separation runs both ways — the tiers are addressed independently."""
    report = _report(client, auth(PROJECT), "Authz Other Federal Only", "OTHER_FEDERAL")
    assert not _visible(client, auth(SCIENTIST), report["id"])
    assert not _visible(client, auth(FMCSA_HQ), report["id"])
    # ...but it does reach the Other Federal consumers it addresses.
    assert _visible(client, auth(NTSB_USER), report["id"])


def test_legacy_federal_report_still_reaches_both_tiers(client, auth):
    """FEDERAL predates the split and means the whole federal audience, so no
    report created before this change loses its readers."""
    report = _report(client, auth(PROJECT), "Authz Legacy Federal", "FEDERAL")
    assert _visible(client, auth(SCIENTIST), report["id"])
    assert _visible(client, auth(FEDERAL), report["id"])


# --------------------------------------------------- outward sharing = DBA
def test_dba_may_release_to_outward_audiences(client, auth):
    dba = auth(DB_ADMIN)
    report = _report(client, auth(PROJECT), "Authz DBA Release", "FMCSA_FEDERAL")
    for audience, extra in (
        ("OTHER_FEDERAL", {}),
        ("PUBLIC", {}),
        ("STATE", {"audience_state_code": "KS"}),
    ):
        resp = client.post(
            f"{API}/reports/{report['id']}/share", headers=dba,
            json={"audience": audience, **extra},
        )
        assert resp.status_code == 201, f"{audience}: {resp.text}"


def test_project_team_may_not_release_outward(client, auth):
    """The Project Team keeps report:share for dashboards, but the BRD assigns
    every outward release to the Database Administrator."""
    team = auth(PROJECT)
    report = _report(client, team, "Authz Team Release", "FMCSA_FEDERAL")
    for audience in ("OTHER_FEDERAL", "STATE", "PUBLIC"):
        body = {"audience": audience}
        if audience == "STATE":
            body["audience_state_code"] = "KS"
        resp = client.post(f"{API}/reports/{report['id']}/share", headers=team, json=body)
        assert resp.status_code == 403, f"{audience}: {resp.text}"


def test_project_team_may_still_share_within_fmcsa_federal(client, auth):
    team = auth(PROJECT)
    report = _report(client, team, "Authz Team FMCSA Share", "PRIVATE")
    resp = client.post(
        f"{API}/reports/{report['id']}/share", headers=team,
        json={"audience": "FMCSA_FEDERAL"},
    )
    assert resp.status_code == 201, resp.text


def test_audience_share_grants_visibility_to_that_tier(client, auth):
    """A release has to actually reach its audience, or the share row is inert."""
    report = _report(client, auth(PROJECT), "Authz Audience Grant", "PRIVATE")
    assert not _visible(client, auth(NTSB_USER), report["id"])

    shared = client.post(
        f"{API}/reports/{report['id']}/share", headers=auth(DB_ADMIN),
        json={"audience": "OTHER_FEDERAL"},
    )
    assert shared.status_code == 201, shared.text
    assert _visible(client, auth(NTSB_USER), report["id"])


def test_state_audience_share_respects_state_scope(client, auth):
    """A KS release must not reach a TX analyst — the State rule carries through
    the sharing path, not just the report's own binding."""
    report = _report(client, auth(PROJECT), "Authz KS Release", "PRIVATE")
    shared = client.post(
        f"{API}/reports/{report['id']}/share", headers=auth(DB_ADMIN),
        json={"audience": "STATE", "audience_state_code": "KS"},
    )
    assert shared.status_code == 201, shared.text
    assert _visible(client, auth(ANALYST_KS), report["id"])
    assert not _visible(client, auth(ANALYST_TX), report["id"])


# --------------------------------------------------------------- validation
def test_state_audience_requires_a_state(client, auth):
    report = _report(client, auth(PROJECT), "Authz State No Code", "PRIVATE")
    resp = client.post(
        f"{API}/reports/{report['id']}/share", headers=auth(DB_ADMIN),
        json={"audience": "STATE"},
    )
    assert resp.status_code == 400, resp.text


def test_state_code_rejected_on_a_non_state_audience(client, auth):
    report = _report(client, auth(PROJECT), "Authz Bad State Code", "PRIVATE")
    resp = client.post(
        f"{API}/reports/{report['id']}/share", headers=auth(DB_ADMIN),
        json={"audience": "PUBLIC", "audience_state_code": "KS"},
    )
    assert resp.status_code == 400, resp.text


def test_share_with_no_target_at_all_is_400(client, auth):
    report = _report(client, auth(PROJECT), "Authz No Target", "PRIVATE")
    resp = client.post(f"{API}/reports/{report['id']}/share", headers=auth(PROJECT), json={})
    assert resp.status_code == 400, resp.text
