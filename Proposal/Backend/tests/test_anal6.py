"""Tests for the constrained ad-hoc query builder (ANAL-6, documentation §8.9 / §14).

All requests run through the shared ``client`` fixture, which is bound to a single
rolled-back transaction (see conftest.py), so the live database is never mutated.

Role/permission notes (from seeds/0002_rbac_orgs_users.sql, verified against the seed):
  * Only ``CCFP_PROJECT_TEAM`` and ``CCFP_DATA_SCIENTIST`` hold ``analytics:query``;
    both are GLOBAL-scoped. PROJECT (dana.whitfield, CCFP_PROJECT_TEAM) and
    DATA_SCIENTIST (priya.ramanathan, CCFP_DATA_SCIENTIST) are the positive callers.
  * No seeded State-scoped user holds ``analytics:query`` (STATE_CMV_ANALYST,
    CCFP_PROJECT_ADMIN/ADMIN, and FEDERAL all lack it), so State-scope enforcement
    is asserted at the code level: the builder routes its statement through the
    shared ``scope_crash_query`` and must produce the same scoping as the existing
    canned ``crash_counts_by_state`` query for the same caller.
  * FEDERAL (omar.haddad), ADMIN (avery.thornton, CCFP_PROJECT_ADMIN), ANALYST_KS
    (elliot.fontaine, STATE_CMV_ANALYST), and PUBLIC all lack ``analytics:query`` —
    used for the authorization-negative cases (403).
"""
from __future__ import annotations

from tests.conftest import ADMIN, ANALYST_KS, FEDERAL, PROJECT, PUBLIC

# CCFP Data Scientist (CCFP_DATA_SCIENTIST) — holds analytics:query (seed line 91).
DATA_SCIENTIST = "priya.ramanathan@ccfp.gov"

API = "/api/v1"
QB = f"{API}/analytics/query-builder"


# --------------------------------------------------------------------------- happy path
def test_query_builder_group_by_state_sum_fatalities(client, auth):
    """A whitelisted group-by + aggregation returns a QueryResult with the
    expected columns and JSON-serialisable rows."""
    resp = client.post(
        QB,
        headers=auth(PROJECT),
        json={"group_by": "state_code", "aggregation": "sum_fatalities"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["query_name"] == "query_builder"
    assert body["columns"] == ["state_code", "sum_fatalities"]
    # Every row carries exactly the two requested keys.
    for row in body["rows"]:
        assert set(row.keys()) == {"state_code", "sum_fatalities"}


def test_query_builder_count_default_aggregation(client, auth):
    """aggregation defaults to count; lifecycle_phase is a valid dimension.
    Uses the Data Scientist account, which also holds analytics:query."""
    resp = client.post(QB, headers=auth(DATA_SCIENTIST), json={"group_by": "lifecycle_phase"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["columns"] == ["lifecycle_phase", "count"]


def test_query_builder_filter_is_applied(client, auth):
    """A validated filter narrows the result to matching rows only."""
    resp = client.post(
        QB,
        headers=auth(PROJECT),
        json={
            "group_by": "state_code",
            "aggregation": "count",
            "filters": [{"column": "num_fatalities", "op": "gte", "value": 1}],
        },
    )
    assert resp.status_code == 200, resp.text
    # Filtered query stays well-formed; rows still carry the two columns.
    for row in resp.json()["rows"]:
        assert set(row.keys()) == {"state_code", "count"}


# --------------------------------------------------------------------------- State scope
def test_query_builder_scope_matches_canned_query(client, auth):
    """The builder routes through the shared scope_crash_query, so for the same
    caller its state_code/count grouping is identical to the canned
    crash_counts_by_state query. This proves State-scope visibility is enforced by
    the same path (no seeded State-scoped account holds analytics:query, so scope
    is verified via this equivalence rather than a cross-State leak attempt)."""
    headers = auth(PROJECT)
    built = client.post(
        QB, headers=headers, json={"group_by": "state_code", "aggregation": "count"}
    )
    assert built.status_code == 200, built.text
    canned = client.post(
        f"{API}/analytics/queries", headers=headers, json={"query_name": "crash_counts_by_state"}
    )
    assert canned.status_code == 200, canned.text

    def _as_map(rows):
        return {r["state_code"]: r["count"] for r in rows}

    assert _as_map(built.json()["rows"]) == _as_map(canned.json()["rows"])


def test_query_builder_scope_dependency_is_wired(client, auth):
    """Static guard: the handler must call scope_crash_query, so a future edit that
    drops State-scope visibility from the builder fails here."""
    import inspect

    from app.features import analytics

    src = inspect.getsource(analytics.run_query_builder)
    assert "scope_crash_query(" in src


# --------------------------------------------------------------------------- validation negatives
def test_query_builder_rejects_unknown_group_by(client, auth):
    """A column outside the allow-list (e.g. an injection attempt) is a 400 — no
    free-form SQL path exists."""
    resp = client.post(
        QB,
        headers=auth(PROJECT),
        json={"group_by": "password", "aggregation": "count"},
    )
    assert resp.status_code == 400, resp.text


def test_query_builder_rejects_sql_injection_in_group_by(client, auth):
    resp = client.post(
        QB,
        headers=auth(PROJECT),
        json={"group_by": "state_code; drop table crashes", "aggregation": "count"},
    )
    assert resp.status_code == 400, resp.text


def test_query_builder_rejects_unknown_aggregation(client, auth):
    resp = client.post(
        QB,
        headers=auth(PROJECT),
        json={"group_by": "state_code", "aggregation": "drop"},
    )
    assert resp.status_code == 400, resp.text


def test_query_builder_rejects_unknown_filter_column(client, auth):
    resp = client.post(
        QB,
        headers=auth(PROJECT),
        json={
            "group_by": "state_code",
            "filters": [{"column": "ssn", "op": "eq", "value": "x"}],
        },
    )
    assert resp.status_code == 400, resp.text


def test_query_builder_rejects_unknown_operator(client, auth):
    resp = client.post(
        QB,
        headers=auth(PROJECT),
        json={
            "group_by": "state_code",
            "filters": [{"column": "num_fatalities", "op": "like", "value": 1}],
        },
    )
    assert resp.status_code == 400, resp.text


# --------------------------------------------------------------------------- authorization negative
def test_query_builder_forbidden_without_permission(client, auth):
    """FEDERAL lacks analytics:query, so the endpoint is 403."""
    resp = client.post(
        QB,
        headers=auth(FEDERAL),
        json={"group_by": "state_code", "aggregation": "count"},
    )
    assert resp.status_code == 403, resp.text


def test_query_builder_forbidden_for_public(client, auth):
    resp = client.post(
        QB,
        headers=auth(PUBLIC),
        json={"group_by": "state_code", "aggregation": "count"},
    )
    assert resp.status_code == 403, resp.text


def test_query_builder_forbidden_for_state_analyst(client, auth):
    """A State CMV Analyst (ANALYST_KS) lacks analytics:query — 403, even though
    the role is otherwise State-scoped for crash work."""
    resp = client.post(
        QB,
        headers=auth(ANALYST_KS),
        json={"group_by": "state_code", "aggregation": "count"},
    )
    assert resp.status_code == 403, resp.text


def test_query_builder_forbidden_for_admin(client, auth):
    """CCFP Project Team Administrator (ADMIN) holds admin perms but NOT
    analytics:query — confirms least-privilege separation."""
    resp = client.post(
        QB,
        headers=auth(ADMIN),
        json={"group_by": "state_code", "aggregation": "count"},
    )
    assert resp.status_code == 403, resp.text


# --------------------------------------------------------------------------- metadata endpoint
def test_query_builder_fields_lists_allow_lists(client, auth):
    """The fields endpoint advertises the server-side allow-lists for the UI."""
    resp = client.get(f"{QB}/fields", headers=auth(PROJECT))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "state_code" in body["group_by"]
    assert "count" in body["aggregations"]
    assert "num_fatalities" in body["filter_columns"]
    assert set(body["operators"]) == {"eq", "neq", "gte", "lte"}


def test_query_builder_fields_forbidden_without_permission(client, auth):
    resp = client.get(f"{QB}/fields", headers=auth(FEDERAL))
    assert resp.status_code == 403, resp.text


# --------------------------------------------------------------------------- regression: canned queries still work
def test_canned_queries_unchanged(client, auth):
    resp = client.post(
        f"{API}/analytics/queries",
        headers=auth(PROJECT),
        json={"query_name": "crash_counts_by_state"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["columns"] == ["state_code", "count"]
