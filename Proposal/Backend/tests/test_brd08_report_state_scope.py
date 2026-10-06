"""State users may only view their own State's reports.

The January 2026 BRD makes this explicit — "Participating State Users (No PII,
**Only View Own Data**)" in the Visualize access table, and "data shared would be
State-specific" in Manage/Share.

Before this fix ``_visible_filter`` granted *any* caller with a State scope
visibility of *every* report whose visibility is STATE, regardless of which State
it concerned: a Kansas analyst could read a Texas report. ``reports`` carried no
``state_code`` at all, so there was nothing to compare against.

A NULL ``state_code`` means "not State-bound" and stays visible to every State
user, which preserves the behaviour of reports created before this change.

Role notes (seeds/0002_rbac_orgs_users.sql):
  * PROJECT (CCFP_PROJECT_TEAM) — unrestricted by State; holds report:create.
  * ANALYST_KS / ANALYST_TX (STATE_CMV_ANALYST) — State-scoped; report:read only.
  * STATE_USER_KS (STATE_USER, KS) — State-scoped; the only State role that also
    holds report:download, so it exercises the download path.
"""
from __future__ import annotations

from tests.conftest import ANALYST_KS, ANALYST_TX, PROJECT, STATE_USER_KS

API = "/api/v1"


def _create_state_report(client, headers, name, state_code):
    resp = client.post(
        f"{API}/reports", headers=headers,
        json={
            "name": name,
            "report_type": "TABLE",
            "visibility": "STATE",
            "state_code": state_code,
            "definition": {"columns": ["metric"], "rows": [{"metric": 1}]},
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


# --------------------------------------------------------------- cross-State denial
def test_state_report_is_hidden_from_another_state(client, auth):
    """The core leak: a KS-scoped analyst must not see a TX-bound STATE report."""
    report = _create_state_report(client, auth(PROJECT), "BRD08 TX Only Report", "TX")

    resp = client.get(f"{API}/reports/{report['id']}", headers=auth(ANALYST_KS))
    assert resp.status_code == 404, resp.text


def test_state_report_absent_from_another_states_list(client, auth):
    """Same denial on the list endpoint, not just the single GET."""
    report = _create_state_report(client, auth(PROJECT), "BRD08 TX List Report", "TX")

    listed = client.get(f"{API}/reports", headers=auth(ANALYST_KS))
    assert listed.status_code == 200, listed.text
    assert report["id"] not in {r["id"] for r in listed.json()}


def test_cross_state_download_is_denied(client, auth):
    """The download route enforces the same predicate — no CSV exfiltration."""
    report = _create_state_report(client, auth(PROJECT), "BRD08 TX Download", "TX")

    resp = client.get(f"{API}/reports/{report['id']}/download", headers=auth(STATE_USER_KS))
    assert resp.status_code == 404, resp.text


# --------------------------------------------------------------- own-State access preserved
def test_state_report_visible_to_its_own_state(client, auth):
    """A TX analyst still sees the TX report — the fix must not over-restrict."""
    report = _create_state_report(client, auth(PROJECT), "BRD08 TX Own State", "TX")

    resp = client.get(f"{API}/reports/{report['id']}", headers=auth(ANALYST_TX))
    assert resp.status_code == 200, resp.text
    assert resp.json()["state_code"] == "TX"


def test_unbound_state_report_visible_to_every_state(client, auth):
    """NULL state_code = not State-bound; both States still see it (back-compat)."""
    report = _create_state_report(client, auth(PROJECT), "BRD08 Unbound Report", None)

    for who in (ANALYST_KS, ANALYST_TX):
        resp = client.get(f"{API}/reports/{report['id']}", headers=auth(who))
        assert resp.status_code == 200, f"{who}: {resp.text}"


def test_owner_and_unrestricted_reader_unaffected(client, auth):
    """A caller with no State restriction is untouched by the predicate."""
    owner = auth(PROJECT)
    report = _create_state_report(client, owner, "BRD08 Owner Visible", "TX")

    resp = client.get(f"{API}/reports/{report['id']}", headers=owner)
    assert resp.status_code == 200, resp.text


# --------------------------------------------------------------- validation
def test_unknown_state_code_is_rejected(client, auth):
    resp = client.post(
        f"{API}/reports", headers=auth(PROJECT),
        json={"name": "BRD08 Bad State", "report_type": "TABLE",
              "visibility": "STATE", "state_code": "ZZ"},
    )
    assert resp.status_code == 400, resp.text


def test_state_code_survives_update(client, auth):
    """PATCHing an unrelated field must not silently drop the State binding."""
    owner = auth(PROJECT)
    report = _create_state_report(client, owner, "BRD08 Patch Report", "TX")

    patched = client.patch(
        f"{API}/reports/{report['id']}", headers=owner, json={"description": "touched"}
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["state_code"] == "TX"

    # And the KS analyst is still denied afterwards.
    assert client.get(f"{API}/reports/{report['id']}", headers=auth(ANALYST_KS)).status_code == 404


def test_rebinding_state_changes_who_can_see_it(client, auth):
    """Moving the binding TX -> KS flips visibility to the KS analyst."""
    owner = auth(PROJECT)
    report = _create_state_report(client, owner, "BRD08 Rebind Report", "TX")
    assert client.get(f"{API}/reports/{report['id']}", headers=auth(ANALYST_KS)).status_code == 404

    rebound = client.patch(f"{API}/reports/{report['id']}", headers=owner, json={"state_code": "KS"})
    assert rebound.status_code == 200, rebound.text

    assert client.get(f"{API}/reports/{report['id']}", headers=auth(ANALYST_KS)).status_code == 200
    assert client.get(f"{API}/reports/{report['id']}", headers=auth(ANALYST_TX)).status_code == 404
