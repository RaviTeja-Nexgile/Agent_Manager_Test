"""Tests for AUTH-6: login attempts are audited (success and failure).

Both the request session and the test's ``db`` session are bound to the same
rolled-back connection (see ``conftest.py``), so audit rows written inside the
login handler are visible to a direct ``AuditLog`` query here. The submitted
password must never appear in ``after_state``.
"""
from __future__ import annotations

from sqlalchemy import select

from app.models import AuditLog
from tests.conftest import ANALYST_KS, DEV_PASSWORD

API = "/api/v1"


def _audit_rows(db, action: str) -> list[AuditLog]:
    db.expire_all()
    return list(db.scalars(select(AuditLog).where(AuditLog.action == action)))


def test_successful_login_writes_login_audit(client, db):
    resp = client.post(
        f"{API}/auth/login", json={"email": ANALYST_KS, "password": DEV_PASSWORD}
    )
    assert resp.status_code == 200, resp.text

    rows = _audit_rows(db, "LOGIN")
    assert any(
        r.entity_type == "user" and (r.after_state or {}).get("email") == ANALYST_KS
        for r in rows
    ), "expected a LOGIN audit row referencing the authenticated user"


def test_wrong_password_writes_login_failed_audit(client, db):
    resp = client.post(
        f"{API}/auth/login", json={"email": ANALYST_KS, "password": "not-the-password"}
    )
    assert resp.status_code == 401

    rows = _audit_rows(db, "LOGIN_FAILED")
    matching = [r for r in rows if (r.after_state or {}).get("email") == ANALYST_KS]
    assert matching, "expected a LOGIN_FAILED audit row for the attempted email"
    for r in matching:
        assert r.entity_type == "user"
        # The actor is unauthenticated on failure.
        assert r.actor_user_id is None
        # The password (or any hash of it) must never be persisted.
        after = r.after_state or {}
        assert "password" not in after
        assert "not-the-password" not in str(after)


def test_unknown_email_writes_login_failed_audit_without_password(client, db):
    resp = client.post(
        f"{API}/auth/login",
        json={"email": "nobody@ccfp.gov", "password": "whatever-secret"},
    )
    assert resp.status_code == 401

    rows = _audit_rows(db, "LOGIN_FAILED")
    matching = [r for r in rows if (r.after_state or {}).get("email") == "nobody@ccfp.gov"]
    assert matching, "expected a LOGIN_FAILED audit row for the unknown email"
    for r in matching:
        # No user resolved, so no entity_id / actor.
        assert r.entity_id is None
        assert r.actor_user_id is None
        assert "whatever-secret" not in str(r.after_state or {})
