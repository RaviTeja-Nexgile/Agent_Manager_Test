"""Tests for report sharing, visibility tiers, download gating, and share/publish
notifications (ANAL-3, ANAL-12, ANAL-4, NOTI-6).

All HTTP requests run through the shared ``client`` fixture and all direct row
reads through the ``db`` fixture; both are bound to the same single, rolled-back
transaction (see conftest.py), so the live database is never mutated. Because the
request session and the ``db`` session share one connection, notifications written
by an endpoint are visible to direct ``db`` queries within the same test.

Role/permission notes (from seeds/0002_rbac_orgs_users.sql):
  * PROJECT (dana.whitfield, CCFP_PROJECT_TEAM) holds report:create + report:share
    + report:download + report:read — the report owner/creator/sharer. (Note
    CCFP_PROJECT_ADMIN holds neither report:create nor report:share, so it cannot
    be used here.)
  * SYSADMIN (sysadmin@ccfp.gov, SYSTEM_ADMIN) holds every permission incl.
    report:publish and admin:system — used for the publish path.
  * ANALYST_KS (elliot.fontaine, STATE_CMV_ANALYST) is State-scoped (KS) and holds
    report:read but NOT report:download — the role-share / STATE-tier visibility
    target (cannot be used as a downloader: the route's report:download guard 403s
    first, before any per-share logic).
  * FEDERAL (omar.haddad, FEDERAL_USER) is unrestricted-by-state and holds
    report:read + report:download — the FEDERAL-tier target and the only
    download-capable non-owner used in the ANAL-4 download-gating tests.
"""
from __future__ import annotations

import uuid

from sqlalchemy import func, select

from app.models import Notification, User
from tests.conftest import ANALYST_KS, FEDERAL, PROJECT

API = "/api/v1"

# SYSTEM_ADMIN — the only seeded role holding report:publish (+ admin:system).
SYSADMIN = "sysadmin@ccfp.gov"


def _create_report(client, headers, *, name, visibility="PRIVATE", is_deidentified=False):
    resp = client.post(
        f"{API}/reports",
        headers=headers,
        json={
            "name": name,
            "report_type": "TABLE",
            "visibility": visibility,
            "is_deidentified": is_deidentified,
            "definition": {"columns": ["a", "b"], "rows": [{"a": 1, "b": 2}]},
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _list_ids(client, headers) -> set[str]:
    resp = client.get(f"{API}/reports", headers=headers)
    assert resp.status_code == 200, resp.text
    return {r["id"] for r in resp.json()}


def _user_id(db, email: str) -> uuid.UUID:
    uid = db.scalar(select(User.id).where(User.email == email))
    assert uid is not None, f"seeded user {email} must exist"
    return uid


def _report_notes(db, report_name: str, note_type: str) -> list[Notification]:
    return list(
        db.scalars(
            select(Notification).where(
                Notification.notification_type == note_type,
                Notification.message.like(f"%{report_name}%"),
            )
        )
    )


# --------------------------------------------------------------------------- ANAL-3


def test_role_share_grants_visibility_to_role_holder(client, auth):
    """A report shared with a role becomes visible to every holder of that role."""
    name = f"Role-share probe {uuid.uuid4().hex[:8]}"
    report = _create_report(client, auth(PROJECT), name=name)

    resp = client.post(
        f"{API}/reports/{report['id']}/share",
        headers=auth(PROJECT),
        json={"shared_with_role_code": "STATE_CMV_ANALYST", "can_download": False},
    )
    assert resp.status_code == 201, resp.text

    # The State analyst (holds STATE_CMV_ANALYST) now sees the report.
    assert report["id"] in _list_ids(client, auth(ANALYST_KS))


def test_role_share_not_visible_to_non_role_holder(client, auth):
    """Negative: a user who does NOT hold the shared-with role cannot see it."""
    name = f"Role-share negative {uuid.uuid4().hex[:8]}"
    report = _create_report(client, auth(PROJECT), name=name)
    resp = client.post(
        f"{API}/reports/{report['id']}/share",
        headers=auth(PROJECT),
        json={"shared_with_role_code": "STATE_CMV_ANALYST", "can_download": False},
    )
    assert resp.status_code == 201, resp.text

    # FEDERAL_USER does not hold STATE_CMV_ANALYST -> report absent from their list.
    assert report["id"] not in _list_ids(client, auth(FEDERAL))


# --------------------------------------------------------------------------- ANAL-12


def test_federal_report_visible_to_federal_not_state(client, auth):
    """A FEDERAL-visibility report is visible to a federal-role caller but not a
    State-scoped one."""
    report = _create_report(
        client, auth(PROJECT), name=f"Fed tier {uuid.uuid4().hex[:8]}", visibility="FEDERAL"
    )
    assert report["id"] in _list_ids(client, auth(FEDERAL))
    assert report["id"] not in _list_ids(client, auth(ANALYST_KS))


def test_state_report_visible_to_state_not_federal(client, auth):
    """A STATE-visibility report is visible to a State-scoped caller but not a
    purely-federal one."""
    report = _create_report(
        client, auth(PROJECT), name=f"State tier {uuid.uuid4().hex[:8]}", visibility="STATE"
    )
    assert report["id"] in _list_ids(client, auth(ANALYST_KS))
    # FEDERAL_USER is unrestricted-by-state (allowed_states is None) and holds no
    # State assignment -> the STATE tier does not match for them.
    assert report["id"] not in _list_ids(client, auth(FEDERAL))


# --------------------------------------------------------------------------- ANAL-4


def test_owner_can_always_download(client, auth):
    """The owner can download their own (PRIVATE, unshared) report."""
    owner = auth(PROJECT)
    report = _create_report(client, owner, name=f"Owner DL {uuid.uuid4().hex[:8]}")
    resp = client.get(f"{API}/reports/{report['id']}/download", headers=owner)
    assert resp.status_code == 200, resp.text


def test_share_without_download_blocks_download(client, auth):
    """A role-shared report with can_download=False is visible but NOT downloadable
    (403), even though the recipient holds report:download."""
    report = _create_report(client, auth(PROJECT), name=f"DL off {uuid.uuid4().hex[:8]}")
    resp = client.post(
        f"{API}/reports/{report['id']}/share",
        headers=auth(PROJECT),
        json={"shared_with_role_code": "FEDERAL_USER", "can_download": False},
    )
    assert resp.status_code == 201, resp.text

    federal = auth(FEDERAL)
    # Visible via the role share...
    assert report["id"] in _list_ids(client, federal)
    # ...but download is forbidden by the per-share flag (FEDERAL_USER holds report:download).
    dl = client.get(f"{API}/reports/{report['id']}/download", headers=federal)
    assert dl.status_code == 403, dl.text


def test_share_with_download_allows_download(client, auth):
    """A share with can_download=True permits the download (200)."""
    report = _create_report(client, auth(PROJECT), name=f"DL on {uuid.uuid4().hex[:8]}")
    resp = client.post(
        f"{API}/reports/{report['id']}/share",
        headers=auth(PROJECT),
        json={"shared_with_role_code": "FEDERAL_USER", "can_download": True},
    )
    assert resp.status_code == 201, resp.text

    dl = client.get(f"{API}/reports/{report['id']}/download", headers=auth(FEDERAL))
    assert dl.status_code == 200, dl.text
    assert dl.headers["content-type"].startswith("text/csv"), dl.headers


def test_unshared_report_not_downloadable_by_other(client, auth):
    """Negative: a download-capable user with no share/visibility gets 404 on
    download (no existence disclosure), not the file."""
    report = _create_report(client, auth(PROJECT), name=f"DL hidden {uuid.uuid4().hex[:8]}")
    dl = client.get(f"{API}/reports/{report['id']}/download", headers=auth(FEDERAL))
    assert dl.status_code == 404, dl.text


# --------------------------------------------------------------------------- NOTI-6


def test_user_share_emits_report_shared_notification(client, auth, db):
    """Sharing directly with a user emits a REPORT_SHARED notification for them."""
    name = f"Notify user-share {uuid.uuid4().hex[:8]}"
    report = _create_report(client, auth(PROJECT), name=name)
    target_id = _user_id(db, FEDERAL)

    resp = client.post(
        f"{API}/reports/{report['id']}/share",
        headers=auth(PROJECT),
        json={"shared_with_user_id": str(target_id)},
    )
    assert resp.status_code == 201, resp.text

    notes = _report_notes(db, name, "REPORT_SHARED")
    assert any(n.recipient_user_id == target_id for n in notes)


def test_role_share_emits_report_shared_to_role_holders(client, auth, db):
    """Sharing with a role notifies the active holders of that role; an unrelated
    user (not in the role) is NOT notified (negative case)."""
    name = f"Notify role-share {uuid.uuid4().hex[:8]}"
    report = _create_report(client, auth(PROJECT), name=name)

    resp = client.post(
        f"{API}/reports/{report['id']}/share",
        headers=auth(PROJECT),
        json={"shared_with_role_code": "STATE_CMV_ANALYST", "can_download": False},
    )
    assert resp.status_code == 201, resp.text

    notes = _report_notes(db, name, "REPORT_SHARED")
    recipients = {n.recipient_user_id for n in notes}
    assert _user_id(db, ANALYST_KS) in recipients
    # Negative: the FEDERAL user does not hold STATE_CMV_ANALYST -> not notified.
    assert _user_id(db, FEDERAL) not in recipients


def test_publish_emits_report_published_notification(client, auth, db):
    """Publishing a de-identified report emits REPORT_PUBLISHED to the owner and
    the Federal audience."""
    name = f"Notify publish {uuid.uuid4().hex[:8]}"
    owner = auth(SYSADMIN)  # SYSTEM_ADMIN holds report:publish
    report = _create_report(client, owner, name=name, is_deidentified=True)

    resp = client.post(f"{API}/reports/{report['id']}/publish", headers=owner)
    assert resp.status_code == 200, resp.text

    notes = _report_notes(db, name, "REPORT_PUBLISHED")
    recipients = {n.recipient_user_id for n in notes}
    # Owner (the SYSTEM_ADMIN who created it) is notified.
    assert _user_id(db, SYSADMIN) in recipients
    # Federal audience is notified.
    assert _user_id(db, FEDERAL) in recipients


def test_share_forbidden_for_user_without_permission(client, auth, db):
    """Negative/authorization: a user lacking report:share gets 403 and no
    REPORT_SHARED notification is written."""
    name = f"No-share perm {uuid.uuid4().hex[:8]}"
    report = _create_report(client, auth(PROJECT), name=name)

    before = db.scalar(
        select(func.count())
        .select_from(Notification)
        .where(Notification.notification_type == "REPORT_SHARED")
    )
    resp = client.post(
        f"{API}/reports/{report['id']}/share",
        headers=auth(ANALYST_KS),  # STATE_CMV_ANALYST lacks report:share
        json={"shared_with_user_id": str(_user_id(db, FEDERAL))},
    )
    assert resp.status_code == 403, resp.text
    after = db.scalar(
        select(func.count())
        .select_from(Notification)
        .where(Notification.notification_type == "REPORT_SHARED")
    )
    assert after == before
