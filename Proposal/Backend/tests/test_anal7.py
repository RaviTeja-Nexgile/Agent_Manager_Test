"""Tests for composable dashboard panel definitions and the single-dashboard
render endpoint (ANAL-7, documentation §8.9).

All requests run through the shared ``client`` fixture, which is bound to a single
rolled-back transaction (see conftest.py), so the live database is never mutated.

Role/permission notes (from seeds/0002_rbac_orgs_users.sql, verified against the seed):
  * PROJECT (dana.whitfield, CCFP_PROJECT_TEAM) holds ``analytics:dashboard`` +
    ``report:create`` + ``report:read`` — the dashboard author and positive caller.
  * PUBLIC (public.demo, PUBLIC_USER) holds only ``public:read`` — it lacks BOTH
    ``analytics:dashboard`` and ``report:read``, so it is gated out (403) by the
    ``require("analytics:dashboard", "report:read")`` dependency the new endpoint
    reuses from ``list_dashboards`` (analytics.py), before ``_visible_filter`` is
    ever reached.
  * ANALYST_KS (elliot.fontaine, STATE_CMV_ANALYST) holds ``report:read`` but is a
    non-owner with no share — used to prove ``_visible_filter`` still hides a
    PRIVATE dashboard (404) even after the permission gate passes.

The panel schema is validated on render: a DASHBOARD report can be created with any
JSON ``definition`` (POST /reports does not parse panels), but the render endpoint
re-validates it and rejects a non-whitelisted ``viz`` or ``query_name`` with 400.
"""
from __future__ import annotations

from tests.conftest import ANALYST_KS, PROJECT, PUBLIC

API = "/api/v1"


VALID_DEFINITION = {
    "layout": "grid",
    "panels": [
        {
            "id": "p1",
            "title": "Crashes by State",
            "viz": "bars",
            "query": {"query_name": "crash_counts_by_state"},
            "labelKey": "state_code",
            "valueKey": "count",
        },
        {
            "id": "p2",
            "title": "By lifecycle phase",
            "viz": "donut",
            "query": {"query_name": "crash_counts_by_phase"},
            "labelKey": "lifecycle_phase",
            "valueKey": "count",
        },
    ],
}


def _create_dashboard(client, headers, definition, name="Panels probe", visibility="ORGANIZATION"):
    resp = client.post(
        f"{API}/reports",
        headers=headers,
        json={
            "name": name,
            "report_type": "DASHBOARD",
            "visibility": visibility,
            "definition": definition,
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


# --------------------------------------------------------------------------- happy path
def test_get_dashboard_echoes_validated_panels(client, auth):
    """A DASHBOARD report with a valid two-panel definition renders back through
    GET /analytics/dashboards/{id} with the panels echoed and whitelisted."""
    owner = auth(PROJECT)
    report = _create_dashboard(client, owner, VALID_DEFINITION)

    resp = client.get(f"{API}/analytics/dashboards/{report['id']}", headers=owner)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["id"] == report["id"]
    assert body["report_type"] == "DASHBOARD"

    panels = body["definition"]["panels"]
    assert [p["id"] for p in panels] == ["p1", "p2"]
    assert {p["viz"] for p in panels} == {"bars", "donut"}
    assert panels[0]["query"]["query_name"] == "crash_counts_by_state"
    assert panels[1]["query"]["query_name"] == "crash_counts_by_phase"
    assert body["definition"]["layout"] == "grid"


def test_get_dashboard_empty_definition_is_ok(client, auth):
    """An ad-hoc/legacy definition (no panels) renders as an empty panel set
    rather than erroring — keeps seeded dashboards from breaking."""
    owner = auth(PROJECT)
    report = _create_dashboard(client, owner, {"widgets": ["factor_distribution"]})

    resp = client.get(f"{API}/analytics/dashboards/{report['id']}", headers=owner)
    assert resp.status_code == 200, resp.text
    assert resp.json()["definition"]["panels"] == []


# --------------------------------------------------------------------------- validation negatives
def test_get_dashboard_rejects_unknown_viz(client, auth):
    """A panel that requests a non-whitelisted viz (e.g. ``pie``) is a 400 — no
    arbitrary renderer can be referenced."""
    owner = auth(PROJECT)
    bad = {
        "panels": [
            {
                "id": "p1",
                "title": "Bad viz",
                "viz": "pie",
                "query": {"query_name": "crash_counts_by_state"},
            }
        ]
    }
    report = _create_dashboard(client, owner, bad, name="Bad viz dash")
    resp = client.get(f"{API}/analytics/dashboards/{report['id']}", headers=owner)
    assert resp.status_code == 400, resp.text


def test_get_dashboard_rejects_unknown_query_name(client, auth):
    """A panel that binds to a query outside ALLOWED_QUERIES (e.g. ``DROP``) is a
    400 — no free-form query can be referenced."""
    owner = auth(PROJECT)
    bad = {
        "panels": [
            {
                "id": "p1",
                "title": "Injection attempt",
                "viz": "bars",
                "query": {"query_name": "DROP"},
            }
        ]
    }
    report = _create_dashboard(client, owner, bad, name="Bad query dash")
    resp = client.get(f"{API}/analytics/dashboards/{report['id']}", headers=owner)
    assert resp.status_code == 400, resp.text


# --------------------------------------------------------------------------- visibility / scoping
def test_get_dashboard_unknown_id_returns_404(client, auth):
    resp = client.get(
        f"{API}/analytics/dashboards/00000000-0000-0000-0000-000000000000",
        headers=auth(PROJECT),
    )
    assert resp.status_code == 404, resp.text


def test_get_dashboard_non_dashboard_report_returns_404(client, auth):
    """A non-DASHBOARD report id does not resolve through this endpoint (404)."""
    owner = auth(PROJECT)
    resp = client.post(
        f"{API}/reports",
        headers=owner,
        json={
            "name": "A table not a dashboard",
            "report_type": "TABLE",
            "visibility": "PRIVATE",
            "definition": {"columns": ["a"], "rows": [{"a": 1}]},
        },
    )
    assert resp.status_code == 201, resp.text
    report_id = resp.json()["id"]

    got = client.get(f"{API}/analytics/dashboards/{report_id}", headers=owner)
    assert got.status_code == 404, got.text


def test_get_private_dashboard_hidden_from_non_owner_returns_404(client, auth):
    """_visible_filter is layered on top of the permission gate: a report:read
    non-owner with no share gets 404 for a PRIVATE dashboard, not the panels."""
    report = _create_dashboard(
        client, auth(PROJECT), VALID_DEFINITION, name="Private dash", visibility="PRIVATE"
    )
    other = auth(ANALYST_KS)  # holds report:read, passes the gate, but cannot see it
    resp = client.get(f"{API}/analytics/dashboards/{report['id']}", headers=other)
    assert resp.status_code == 404, resp.text


# --------------------------------------------------------------------------- authorization negative
def test_get_dashboard_forbidden_for_public(client, auth):
    """A PUBLIC_USER lacks both analytics:dashboard and report:read, so the
    permission gate (reused from list_dashboards) returns 403 before any report
    lookup — no existence disclosure either way."""
    report = _create_dashboard(client, auth(PROJECT), VALID_DEFINITION)
    resp = client.get(f"{API}/analytics/dashboards/{report['id']}", headers=auth(PUBLIC))
    assert resp.status_code == 403, resp.text


def test_list_dashboards_still_works(client, auth):
    """Regression: the existing list endpoint is unchanged and still 200s for an
    authorized caller."""
    resp = client.get(f"{API}/analytics/dashboards", headers=auth(PROJECT))
    assert resp.status_code == 200, resp.text
    assert isinstance(resp.json(), list)
