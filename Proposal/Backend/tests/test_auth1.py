"""AUTH-1 — authorization enforced by ORGANIZATION scope.

Mirrors the existing State-scope behaviour: a user with NO org restriction is
unrestricted (sees all orgs); only an explicitly ORGANIZATION-scoped assignment
confines visibility to that org's data. All rows are created inside the
rolled-back ``db`` transaction, so the live DB is never mutated.
"""
from __future__ import annotations

import uuid

from sqlalchemy import select

from app.core.security import create_access_token
from app.models import Organization, Report, Role, User, UserRoleAssignment
from tests.conftest import ADMIN

API = "/api/v1"


def _bearer(user: User) -> dict[str, str]:
    """Mint a JWT directly for a freshly-created user (no seeded password)."""
    return {"Authorization": f"Bearer {create_access_token(user)}"}


def _mk_user(db, email: str, org_id) -> User:
    user = User(email=email, full_name=email.split("@")[0], organization_id=org_id, status="ACTIVE")
    db.add(user)
    db.flush()
    return user


def _assign(db, user: User, role_code: str, scope_type: str, *, org_id=None) -> None:
    role = db.scalar(select(Role).where(Role.code == role_code))
    assert role is not None, role_code
    db.add(
        UserRoleAssignment(
            user_id=user.id, role_id=role.id, scope_type=scope_type, organization_id=org_id
        )
    )
    db.flush()
    db.expire(user, ["assignments"])


def test_org_scoped_admin_sees_only_their_org_users(client, db):
    """Positive + negative: an ORGANIZATION-scoped admin only lists their org's users."""
    org_a = Organization(name=f"Org A {uuid.uuid4()}", org_type="STATE_AGENCY")
    org_b = Organization(name=f"Org B {uuid.uuid4()}", org_type="STATE_AGENCY")
    db.add_all([org_a, org_b])
    db.flush()

    # A peer user in each org (so we can prove cross-org exclusion).
    peer_a = _mk_user(db, f"peer.a.{uuid.uuid4().hex}@ccfp.gov", org_a.id)
    peer_b = _mk_user(db, f"peer.b.{uuid.uuid4().hex}@ccfp.gov", org_b.id)

    # The org-scoped admin lives in org A and holds admin:users at ORGANIZATION scope
    # (CCFP_PROJECT_ADMIN carries admin:users, so it reaches the user listing).
    admin = _mk_user(db, f"orgadmin.{uuid.uuid4().hex}@ccfp.gov", org_a.id)
    _assign(db, admin, "CCFP_PROJECT_ADMIN", "ORGANIZATION", org_id=org_a.id)

    resp = client.get(f"{API}/users", headers=_bearer(admin))
    assert resp.status_code == 200, resp.text
    emails = {u["email"] for u in resp.json()["items"]}
    assert peer_a.email in emails            # positive: same-org user is visible
    assert peer_b.email not in emails        # negative: cross-org user is excluded
    assert admin.email in emails             # the admin itself is in org A


def test_org_scoped_report_visibility(client, db):
    """Org-scoped user sees only reports owned by users in their org."""
    org_a = Organization(name=f"Org A {uuid.uuid4()}", org_type="STATE_AGENCY")
    org_b = Organization(name=f"Org B {uuid.uuid4()}", org_type="STATE_AGENCY")
    db.add_all([org_a, org_b])
    db.flush()

    owner_a = _mk_user(db, f"owner.a.{uuid.uuid4().hex}@ccfp.gov", org_a.id)
    owner_b = _mk_user(db, f"owner.b.{uuid.uuid4().hex}@ccfp.gov", org_b.id)
    rep_a = Report(name="Report in A", owner_id=owner_a.id, visibility="ORGANIZATION")
    rep_b = Report(name="Report in B", owner_id=owner_b.id, visibility="ORGANIZATION")
    db.add_all([rep_a, rep_b])
    db.flush()

    # Org-A viewer with report:read at ORGANIZATION scope (CCFP_PROJECT_TEAM carries it).
    viewer = _mk_user(db, f"viewer.{uuid.uuid4().hex}@ccfp.gov", org_a.id)
    _assign(db, viewer, "CCFP_PROJECT_TEAM", "ORGANIZATION", org_id=org_a.id)

    resp = client.get(f"{API}/reports", headers=_bearer(viewer))
    assert resp.status_code == 200, resp.text
    ids = {r["id"] for r in resp.json()}
    assert str(rep_a.id) in ids        # positive: same-org report visible
    assert str(rep_b.id) not in ids    # negative: cross-org report excluded


def test_unrestricted_admin_still_sees_all_users(client, auth, db):
    """REGRESSION: a GLOBAL admin (org_ids is None) is unaffected — sees all orgs.

    Also confirms /auth/me reports org_ids=null for the unrestricted account.
    """
    me = client.get(f"{API}/auth/me", headers=auth(ADMIN)).json()
    assert me["org_ids"] is None  # unrestricted by organization

    users = client.get(f"{API}/users", headers=auth(ADMIN)).json()
    # The seeded users span many orgs; a GLOBAL admin must see well beyond one org.
    org_ids = {u["organization_id"] for u in users["items"]}
    assert users["total"] >= 15
    assert len([o for o in org_ids if o]) >= 3
