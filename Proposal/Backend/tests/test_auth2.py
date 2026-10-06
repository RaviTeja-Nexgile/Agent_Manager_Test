"""AUTH-2 — authorization enforced by STUDY / study phase.

Mirrors the State-scope pattern: a user with NO study restriction sees all
studies; only an explicitly STUDY-scoped assignment confines visibility to its
study set. All rows are created inside the rolled-back ``db`` transaction.
"""
from __future__ import annotations

import uuid

from sqlalchemy import select

from app.core.security import create_access_token
from app.models import Crash, Role, Study, User, UserRoleAssignment
from tests.conftest import ADMIN, ANALYST_KS

API = "/api/v1"


def _bearer(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user)}"}


def _study(db, code: str) -> Study:
    study = db.scalar(select(Study).where(Study.code == code))
    assert study is not None, code
    return study


def _mk_crash(db, study_id, state_code: str) -> Crash:
    crash = Crash(
        ccfp_identifier=f"CCFP-TEST-{uuid.uuid4().hex[:12]}",
        study_id=study_id,
        state_code=state_code,
        num_fatalities=1,
    )
    db.add(crash)
    db.flush()
    return crash


def _study_scoped_user(db, study_id) -> User:
    user = User(email=f"study.{uuid.uuid4().hex}@ccfp.gov", full_name="Study Scoped", status="ACTIVE")
    db.add(user)
    db.flush()
    # CCFP_PROJECT_TEAM carries crash:read so the user reaches /crashes (not a 403).
    role = db.scalar(select(Role).where(Role.code == "CCFP_PROJECT_TEAM"))
    db.add(
        UserRoleAssignment(
            user_id=user.id, role_id=role.id, scope_type="STUDY", study_id=study_id
        )
    )
    db.flush()
    db.expire(user, ["assignments"])
    return user


def test_study_scoped_user_sees_only_their_study(client, db):
    """Positive + negative: a STUDY-scoped user sees their study's crash, not others'."""
    s1 = _study(db, "PHASE1-HDT")
    s3 = _study(db, "PHASE3-BUS")
    c1 = _mk_crash(db, s1.id, "KS")
    c3 = _mk_crash(db, s3.id, "KS")

    user = _study_scoped_user(db, s1.id)
    resp = client.get(f"{API}/crashes", headers=_bearer(user))
    assert resp.status_code == 200, resp.text
    ids = {i["id"] for i in resp.json()["items"]}
    assert str(c1.id) in ids        # positive: in-scope study crash visible
    assert str(c3.id) not in ids    # negative: other-study crash excluded
    # Every returned crash must belong to the authorized study.
    assert all(i["study_id"] == str(s1.id) for i in resp.json()["items"])


def test_study_scoped_detail_access_denied_cross_study(client, db):
    """A study-scoped user gets 403 on a crash detail outside their study."""
    s1 = _study(db, "PHASE1-HDT")
    s3 = _study(db, "PHASE3-BUS")
    c1 = _mk_crash(db, s1.id, "KS")
    c3 = _mk_crash(db, s3.id, "KS")

    user = _study_scoped_user(db, s1.id)
    headers = _bearer(user)
    assert client.get(f"{API}/crashes/{c1.id}", headers=headers).status_code == 200
    assert client.get(f"{API}/crashes/{c3.id}", headers=headers).status_code == 403
    # The study filter on the list endpoint also narrows the explicit study_id param.
    empty = client.get(f"{API}/crashes?study_id={s3.id}", headers=headers).json()
    assert empty["items"] == []


def test_unrestricted_user_sees_all_studies(client, auth, db):
    """REGRESSION: a GLOBAL user (not study_restricted) sees crashes across studies.

    Also confirms State scope is unchanged for a State-scoped analyst.
    """
    s1 = _study(db, "PHASE1-HDT")
    s3 = _study(db, "PHASE3-BUS")
    c1 = _mk_crash(db, s1.id, "KS")
    c3 = _mk_crash(db, s3.id, "KS")

    # dana.whitfield (CCFP_PROJECT_TEAM, GLOBAL) holds crash:read and is unrestricted.
    project = auth("dana.whitfield@ccfp.gov")
    me = client.get(f"{API}/auth/me", headers=project).json()
    assert me["study_restricted"] is False

    items = client.get(f"{API}/crashes?limit=500", headers=project).json()["items"]
    ids = {i["id"] for i in items}
    assert str(c1.id) in ids and str(c3.id) in ids  # both studies visible

    # State scope still holds: a KS analyst sees only KS crashes (no AUTH regression).
    ks = client.get(f"{API}/crashes", headers=auth(ANALYST_KS)).json()
    assert ks["items"]
    assert all(i["state_code"] == "KS" for i in ks["items"])
