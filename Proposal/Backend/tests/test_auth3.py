"""AUTH-3 — access groups as first-class data, driving data-sensitivity reach.

PII / CIPSEA visibility is now derived from access-group membership
(``access_groups`` on ``CurrentUser``) seeded so that EVERY seeded role keeps
its *exact* current ``can_view_sensitivity(...)`` answers — this is a structural
change, not a policy change. These tests pin that parity and verify the groups
surface on ``/auth/me`` so the frontend can read PII visibility from one source.

All tests run inside a rolled-back transaction (see conftest), so the live
development database is never mutated.
"""
from __future__ import annotations

from sqlalchemy import select

from app.core.security import _resolve
from app.enums import DataSensitivity
from app.models import User
from tests.conftest import (
    ADMIN,
    ANALYST_KS,
    FEDERAL,
    INSPECTOR_KS,
    PROJECT,
    PUBLIC,
)

API = "/api/v1"

# BTS / FMCSA CIPSEA agents hold bts:read today -> CIPSEA group (and NOPII for
# operational data; they hold no PII permission code, matching today's reach).
BTS_AGENT = "helena.brandt@ccfp.gov"
FMCSA_AGENT = "marcus.ellingsworth@ccfp.gov"
# The true System Administrator (holds every permission -> PII). NOTE: conftest's
# ADMIN constant is avery.thornton = CCFP Project *Administrator*, a report-only
# role that holds NO PII permission code today and is therefore NOPII (not PII) —
# both before and after AUTH-3. So ADMIN is asserted as a NON-PII account below.
SYSADMIN = "sysadmin@ccfp.gov"


def _resolve_by_email(db, email: str):
    """Resolve a seeded user to a CurrentUser exactly as get_current_user does."""
    user = db.scalar(select(User).where(User.email == email))
    assert user is not None, email
    return _resolve(user)


# --------------------------------------------------------------------------- groups exist
def test_access_groups_resolved_onto_current_user(db):
    """Each seeded principal carries a non-empty access_groups set."""
    for email in (PROJECT, ANALYST_KS, INSPECTOR_KS, FEDERAL, PUBLIC, BTS_AGENT):
        cu = _resolve_by_email(db, email)
        assert cu.access_groups, f"{email} resolved no access groups"


def test_pii_group_membership_matches_seed(db):
    """PII-capable seeded roles are in the PII group; report-only ones are not."""
    # PII group (hold one of the five PII permission codes today).
    for email in (PROJECT, ANALYST_KS, INSPECTOR_KS, SYSADMIN):
        assert "PII" in _resolve_by_email(db, email).access_groups, email
    # Not in the PII group (no PII permission code today). ADMIN here is the CCFP
    # Project Administrator (avery.thornton) — report-only, NOPII, not PII.
    for email in (FEDERAL, PUBLIC, BTS_AGENT, FMCSA_AGENT, ADMIN):
        assert "PII" not in _resolve_by_email(db, email).access_groups, email


def test_cipsea_group_membership_matches_seed(db):
    """Only roles holding bts:read are in the CIPSEA group."""
    for email in (BTS_AGENT, FMCSA_AGENT):
        assert "CIPSEA" in _resolve_by_email(db, email).access_groups, email
    for email in (PROJECT, ANALYST_KS, FEDERAL, PUBLIC):
        assert "CIPSEA" not in _resolve_by_email(db, email).access_groups, email


def test_public_user_only_public_group(db):
    """The public user belongs to PUBLIC and to neither PII nor CIPSEA."""
    groups = _resolve_by_email(db, PUBLIC).access_groups
    assert "PUBLIC" in groups
    assert "PII" not in groups
    assert "CIPSEA" not in groups


# --------------------------------------------------------------------------- behaviour parity
def test_can_view_sensitivity_parity_pii(db):
    """PII/SENSITIVE visibility is unchanged from today, now group-derived.

    PII-capable -> True for PROJECT/ANALYST/INSPECTOR/ADMIN; the report-only
    Federal user (negative case) -> False, exactly as before AUTH-3.
    """
    for email in (PROJECT, ANALYST_KS, INSPECTOR_KS, SYSADMIN):
        cu = _resolve_by_email(db, email)
        assert cu.can_view_sensitivity(DataSensitivity.PII.value) is True, email
        assert cu.can_view_sensitivity(DataSensitivity.SENSITIVE.value) is True, email
    # Negative / authorization case: Federal user is report-only -> no PII.
    fed = _resolve_by_email(db, FEDERAL)
    assert fed.can_view_sensitivity(DataSensitivity.PII.value) is False
    assert fed.can_view_sensitivity(DataSensitivity.SENSITIVE.value) is False
    # Public user also withheld PII.
    assert _resolve_by_email(db, PUBLIC).can_view_sensitivity(DataSensitivity.PII.value) is False
    # CCFP Project Administrator (conftest ADMIN) is report-only -> no PII either.
    assert _resolve_by_email(db, ADMIN).can_view_sensitivity(DataSensitivity.PII.value) is False


def test_can_view_sensitivity_parity_cipsea(db):
    """CIPSEA visibility tracks the CIPSEA group; non-agents are withheld."""
    assert _resolve_by_email(db, BTS_AGENT).can_view_sensitivity(DataSensitivity.CIPSEA.value) is True
    assert _resolve_by_email(db, FMCSA_AGENT).can_view_sensitivity(DataSensitivity.CIPSEA.value) is True
    # A PII-capable but non-CIPSEA role must NOT see CIPSEA data.
    assert _resolve_by_email(db, PROJECT).can_view_sensitivity(DataSensitivity.CIPSEA.value) is False
    assert _resolve_by_email(db, FEDERAL).can_view_sensitivity(DataSensitivity.CIPSEA.value) is False


def test_public_internal_visible_to_everyone(db):
    """PUBLIC/INTERNAL stay visible to every authenticated principal, incl. public."""
    for email in (PROJECT, FEDERAL, PUBLIC, BTS_AGENT):
        cu = _resolve_by_email(db, email)
        assert cu.can_view_sensitivity(DataSensitivity.PUBLIC.value) is True, email
        assert cu.can_view_sensitivity(DataSensitivity.INTERNAL.value) is True, email


# --------------------------------------------------------------------------- /auth/me exposure
def test_me_exposes_access_groups_for_pii_role(client, auth):
    """A PII-capable role's /auth/me includes access_groups containing PII."""
    me = client.get(f"{API}/auth/me", headers=auth(PROJECT)).json()
    assert "access_groups" in me
    assert "PII" in me["access_groups"]
    # Sorted list of strings, no duplicates.
    assert me["access_groups"] == sorted(set(me["access_groups"]))


def test_me_omits_pii_for_federal_user(client, auth):
    """Negative case: Federal user's /auth/me has access_groups WITHOUT PII."""
    me = client.get(f"{API}/auth/me", headers=auth(FEDERAL)).json()
    assert "access_groups" in me
    assert "PII" not in me["access_groups"]
    # Federal user is in the NOPII group (operational ceiling = INTERNAL).
    assert "NOPII" in me["access_groups"]


def test_me_exposes_cipsea_for_agent(client, auth):
    """A CIPSEA agent's /auth/me advertises the CIPSEA group but not PII."""
    me = client.get(f"{API}/auth/me", headers=auth(BTS_AGENT)).json()
    assert "CIPSEA" in me["access_groups"]
    assert "PII" not in me["access_groups"]
