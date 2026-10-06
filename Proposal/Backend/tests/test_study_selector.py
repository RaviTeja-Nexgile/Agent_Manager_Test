"""Study selector contract — human-readable study names + correct default study.

The New-crash study selector must never show raw UUID fragments and must
default to the correct study. That rests on three backend guarantees:

1. ``GET /studies`` is auth-only (crash-creating roles such as the MCSAP CMV
   Inspector hold no ``study:read``) and returns name/code/status/phase for
   every visible study, ordered by phase then code, so the first ACTIVE row is
   the correct default (the current phase).
2. A study-restricted principal (AUTH-2) sees only its assigned studies.
3. ``POST /crashes`` refuses studies outside the caller's study scope (403)
   and studies that are not ACTIVE (400) — the selector's ACTIVE-only options
   are enforced server-side, not just in the UI.

All rows are created inside the rolled-back ``db`` transaction.
"""
from __future__ import annotations

import uuid

from sqlalchemy import select

from app.core.security import create_access_token
from app.models import Role, Study, User, UserRoleAssignment
from tests.conftest import ADMIN, FEDERAL, INSPECTOR_KS, PROJECT, PUBLIC

API = "/api/v1"


def _bearer(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user)}"}


def _as(db, email: str) -> dict[str, str]:
    """Auth headers for a seeded user, minted directly rather than through
    ``POST /auth/login``. Login writes ``users.last_login_at``, and this suite
    signs in as the same seeded accounts many times; on the shared development
    database that write serializes against other clients doing the same, which
    stalls the run for reasons unrelated to what these tests assert. Token
    minting exercises the identical authorization path (the login endpoint is
    covered by tests/test_api.py)."""
    user = db.scalar(select(User).where(User.email == email))
    assert user is not None, email
    return _bearer(user)


def _study(db, code: str) -> Study:
    study = db.scalar(select(Study).where(Study.code == code))
    assert study is not None, code
    return study


def _scoped_user(db, role_code: str, study_id) -> User:
    """A user holding `role_code` confined to one study (STUDY-scoped, AUTH-2)."""
    user = User(email=f"selector.{uuid.uuid4().hex}@ccfp.gov", full_name="Selector Test", status="ACTIVE")
    db.add(user)
    db.flush()
    role = db.scalar(select(Role).where(Role.code == role_code))
    db.add(UserRoleAssignment(user_id=user.id, role_id=role.id, scope_type="STUDY", study_id=study_id))
    db.flush()
    db.expire(user, ["assignments"])
    return user


# --------------------------------------------------------------------- catalog
def test_inspector_gets_readable_study_catalog(client, db):
    """The MCSAP CMV Inspector (no study:read) can resolve real study names —
    the selector never needs to fall back to UUID fragments."""
    rows = client.get(f"{API}/studies", headers=_as(db, INSPECTOR_KS))
    assert rows.status_code == 200, rows.text
    studies = rows.json()
    assert studies, "seeded studies expected"
    for s in studies:
        assert s["name"].strip(), s
        assert s["code"].strip(), s
        assert s["status"] in {"PLANNING", "ACTIVE", "CLOSED", "PUBLISHED"}
        assert isinstance(s["phase_number"], int)
    codes = {s["code"] for s in studies}
    assert "PHASE1-HDT" in codes


def test_catalog_order_makes_first_active_the_default(client, db):
    """Ordered by phase then code ⇒ the first ACTIVE study is the current phase
    (Phase 1 HDTS), NOT the closed phase-0 pilot the old selector defaulted to."""
    studies = client.get(f"{API}/studies", headers=_as(db, INSPECTOR_KS)).json()
    ordering = [(s["phase_number"], s["code"]) for s in studies]
    assert ordering == sorted(ordering)
    first_active = next(s for s in studies if s["status"] == "ACTIVE")
    assert first_active["code"] == "PHASE1-HDT"
    # The seeded CLOSED pilot precedes Phase 1 in the list — the status filter
    # is what keeps it out of the selector's options.
    assert studies[0]["code"] == "PILOT-2025"
    assert studies[0]["status"] == "CLOSED"


def test_catalog_status_filter(client, db):
    h = _as(db, INSPECTOR_KS)
    active = client.get(f"{API}/studies?status=ACTIVE", headers=h).json()
    assert active and all(s["status"] == "ACTIVE" for s in active)
    assert "PHASE1-HDT" in {s["code"] for s in active}
    planning = client.get(f"{API}/studies?status=PLANNING", headers=h).json()
    assert all(s["status"] == "PLANNING" for s in planning)
    assert client.get(f"{API}/studies?status=BOGUS", headers=h).status_code == 422


def test_catalog_requires_auth_but_no_special_permission(client, db):
    assert client.get(f"{API}/studies").status_code in (401, 403)  # anonymous
    # Internal roles read the catalog without study:read (it backs selectors
    # app-wide) — but a public-only account works with published data products
    # only (documentation §4) and is refused the internal catalog.
    assert client.get(f"{API}/studies", headers=_as(db, FEDERAL)).status_code == 200
    assert client.get(f"{API}/studies", headers=_as(db, PUBLIC)).status_code == 403


def test_duplicate_study_names_stay_distinguishable(client, db):
    """Two studies may share a display name; unique codes keep labels unique."""
    for code in ("DUP-A", "DUP-B"):
        db.add(Study(
            code=code, name="Duplicate Name Study", phase_number=90 + (code == "DUP-B"),
            vehicle_type="Test", crash_severity="Fatal", status="ACTIVE",
        ))
    db.flush()
    studies = client.get(f"{API}/studies", headers=_as(db, INSPECTOR_KS)).json()
    dupes = [s for s in studies if s["name"] == "Duplicate Name Study"]
    assert len(dupes) == 2
    assert len({s["code"] for s in dupes}) == 2


# ----------------------------------------------------------------- AUTH-2 scope
def test_study_restricted_principal_sees_only_its_studies(client, db):
    s1 = _study(db, "PHASE1-HDT")
    user = _scoped_user(db, "CCFP_PROJECT_TEAM", s1.id)
    visible = client.get(f"{API}/studies", headers=_bearer(user)).json()
    assert [s["id"] for s in visible] == [str(s1.id)]
    # Regression: an unrestricted user still sees the whole catalog.
    all_codes = {s["code"] for s in client.get(f"{API}/studies", headers=_as(db, PROJECT)).json()}
    assert {"PILOT-2025", "PHASE1-HDT", "PHASE2-MDT"} <= all_codes


def test_restricted_to_inactive_study_yields_no_active_options(client, db):
    """A principal confined to a PLANNING study has zero ACTIVE options — the
    selector's empty state, enforced server-side."""
    s3 = _study(db, "PHASE3-BUS")  # PLANNING
    user = _scoped_user(db, "STATE_CMV_ANALYST", s3.id)
    active = client.get(f"{API}/studies?status=ACTIVE", headers=_bearer(user)).json()
    assert active == []


# ------------------------------------------------------------- crash creation
def test_create_crash_in_active_study(client, db):
    s1 = _study(db, "PHASE1-HDT")
    resp = client.post(
        f"{API}/crashes", headers=_as(db, INSPECTOR_KS),
        json={"study_id": str(s1.id), "state_code": "KS"},
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["study_id"] == str(s1.id)


def test_create_crash_rejects_inactive_studies(client, db):
    h = _as(db, INSPECTOR_KS)
    for code in ("PILOT-2025", "PHASE2-MDT"):  # CLOSED / PLANNING, no crash date
        s = _study(db, code)
        resp = client.post(f"{API}/crashes", headers=h, json={"study_id": str(s.id), "state_code": "KS"})
        assert resp.status_code == 400, (code, resp.text)
        assert "active study" in resp.json()["detail"]


def test_closed_study_accepts_late_report_within_its_window(client, db):
    """Boundary: closing a study must not block the 24-48h Initial Incident
    window for a crash that occurred while the study was running (§5 Phase 1).
    A CLOSED study accepts a crash dated on/before its end_date — and nothing
    after it. A PLANNING study rejects crashes regardless of date."""
    h = _as(db, INSPECTOR_KS)
    pilot = _study(db, "PILOT-2025")  # CLOSED, ran 2025-01-01 → 2025-06-30
    assert pilot.status == "CLOSED" and pilot.end_date is not None
    in_window = client.post(
        f"{API}/crashes", headers=h,
        json={"study_id": str(pilot.id), "state_code": "KS", "crash_date": str(pilot.end_date)},
    )
    assert in_window.status_code == 201, in_window.text
    after = client.post(
        f"{API}/crashes", headers=h,
        json={"study_id": str(pilot.id), "state_code": "KS", "crash_date": "2025-07-15"},
    )
    assert after.status_code == 400
    planning = _study(db, "PHASE2-MDT")
    dated = client.post(
        f"{API}/crashes", headers=h,
        json={"study_id": str(planning.id), "state_code": "KS", "crash_date": "2025-06-01"},
    )
    assert dated.status_code == 400


def test_create_crash_rejects_unknown_or_malformed_study(client, db):
    h = _as(db, INSPECTOR_KS)
    unknown = client.post(
        f"{API}/crashes", headers=h,
        json={"study_id": "00000000-0000-0000-0000-000000000000", "state_code": "KS"},
    )
    assert unknown.status_code == 400
    assert "Unknown study_id" in unknown.json()["detail"]
    assert client.post(
        f"{API}/crashes", headers=h, json={"study_id": "not-a-uuid", "state_code": "KS"}
    ).status_code == 422


def test_create_crash_outside_study_scope_forbidden(client, db):
    """A study-restricted analyst may create only within their study — and the
    scope check (403) fires before existence/status checks (400), so the
    endpoint is not an existence oracle for hidden study UUIDs."""
    s1 = _study(db, "PHASE1-HDT")
    s3 = _study(db, "PHASE3-BUS")
    user = _scoped_user(db, "STATE_CMV_ANALYST", s1.id)
    headers = _bearer(user)
    ok = client.post(f"{API}/crashes", headers=headers, json={"study_id": str(s1.id), "state_code": "KS"})
    assert ok.status_code == 201, ok.text
    denied = client.post(f"{API}/crashes", headers=headers, json={"study_id": str(s3.id), "state_code": "KS"})
    assert denied.status_code == 403
    assert "study scope" in denied.json()["detail"]
    # A nonexistent study answers identically to an out-of-scope one (no oracle).
    ghost = client.post(
        f"{API}/crashes", headers=headers,
        json={"study_id": "00000000-0000-0000-0000-000000000000", "state_code": "KS"},
    )
    assert ghost.status_code == 403
    assert ghost.json()["detail"] == denied.json()["detail"]


def test_study_detail_endpoints_respect_study_restriction(client, db):
    """AUTH-2 consistency: the narrowed catalog is enforced on detail routes,
    not just the list — a study-restricted principal gets 403 on another
    study's detail/config sub-resources."""
    s1 = _study(db, "PHASE1-HDT")
    s2 = _study(db, "PHASE2-MDT")
    user = _scoped_user(db, "CCFP_PROJECT_TEAM", s1.id)
    headers = _bearer(user)
    assert client.get(f"{API}/studies/{s1.id}", headers=headers).status_code == 200
    assert client.get(f"{API}/studies/{s2.id}", headers=headers).status_code == 403
    assert client.get(f"{API}/studies/{s2.id}/attributes", headers=headers).status_code == 403
    assert client.get(f"{API}/studies/{s2.id}/parameters", headers=headers).status_code == 403


# ------------------------------------------------- STUDY-scoped role assignment
def test_study_scoped_assignment_requires_a_real_study(client, db):
    admin = _as(db, ADMIN)
    target = db.scalar(select(User).where(User.email == INSPECTOR_KS))
    base = {"role_code": "CCFP_PROJECT_TEAM", "scope_type": "STUDY"}
    missing = client.post(f"{API}/users/{target.id}/roles", headers=admin, json=base)
    assert missing.status_code == 400
    assert "study_id is required" in missing.json()["detail"]
    dangling = client.post(
        f"{API}/users/{target.id}/roles", headers=admin,
        json={**base, "study_id": "00000000-0000-0000-0000-000000000000"},
    )
    assert dangling.status_code == 400
    s1 = _study(db, "PHASE1-HDT")
    ok = client.post(
        f"{API}/users/{target.id}/roles", headers=admin, json={**base, "study_id": str(s1.id)}
    )
    assert ok.status_code == 201, ok.text
    assert ok.json()["study_id"] == str(s1.id)


def test_scoped_assignments_require_their_target(client, db):
    """A STATE/ORGANIZATION assignment without its target would silently
    resolve to an UNRESTRICTED principal — the API now rejects it."""
    admin = _as(db, ADMIN)
    target = db.scalar(select(User).where(User.email == INSPECTOR_KS))
    no_state = client.post(
        f"{API}/users/{target.id}/roles", headers=admin,
        json={"role_code": "STATE_USER", "scope_type": "STATE"},
    )
    assert no_state.status_code == 400
    assert "state_code is required" in no_state.json()["detail"]
    bad_state = client.post(
        f"{API}/users/{target.id}/roles", headers=admin,
        json={"role_code": "STATE_USER", "scope_type": "STATE", "state_code": "ZZ"},
    )
    assert bad_state.status_code == 400
    no_org = client.post(
        f"{API}/users/{target.id}/roles", headers=admin,
        json={"role_code": "FEDERAL_USER", "scope_type": "ORGANIZATION"},
    )
    assert no_org.status_code == 400
    assert "organization_id is required" in no_org.json()["detail"]
    # A valid STATE assignment still works (regression).
    ok = client.post(
        f"{API}/users/{target.id}/roles", headers=admin,
        json={"role_code": "STATE_USER", "scope_type": "STATE", "state_code": "KS"},
    )
    assert ok.status_code == 201, ok.text
