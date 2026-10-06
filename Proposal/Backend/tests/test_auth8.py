"""AUTH-8 — role/access groupings served from the API (not hardcoded in the UI).

The groupings endpoint exposes the backend's single source of truth for the
role-grouping map and the PII permission codes, so the frontend can stop
hardcoding them.
"""
from __future__ import annotations

from app.core.security import _CIPSEA_PERMISSION, _PII_PERMISSIONS, ROLE_GROUPS
from tests.conftest import ADMIN, ANALYST_KS

API = "/api/v1"


def test_groupings_pii_codes_match_backend_source(client, auth):
    """Positive: authed GET returns 200; pii_permission_codes == _PII_PERMISSIONS.

    Comparing against the imported backend constant makes drift impossible.
    """
    resp = client.get(f"{API}/auth/groupings", headers=auth(ADMIN))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert set(body["pii_permission_codes"]) == _PII_PERMISSIONS
    assert body["cipsea_permission_code"] == _CIPSEA_PERMISSION


def test_groupings_role_map_contains_expected_codes(client, auth):
    """The role-grouping map carries the expected role codes per group."""
    body = client.get(f"{API}/auth/groupings", headers=auth(ANALYST_KS)).json()
    groups = body["role_groups"]
    # Matches the backend ROLE_GROUPS source of truth exactly.
    assert {k: set(v) for k, v in groups.items()} == {k: set(v) for k, v in ROLE_GROUPS.items()}
    assert "STATE_CMV_ANALYST" in groups["STATE"]
    assert "SYSTEM_ADMIN" in groups["ADMIN"]
    assert "BTS_CIPSEA_AGENT" in groups["CIPSEA"]
    assert "PUBLIC_USER" in groups["PUBLIC"]


def test_groupings_requires_auth(client):
    """Negative: unauthenticated GET is rejected (401), like the other metadata routes."""
    assert client.get(f"{API}/auth/groupings").status_code == 401
