"""Pytest fixtures: each test runs inside a single rolled-back transaction so the
live development database is never mutated.

Isolation covers *every* session the app may open during a request — not just the
request-scoped `get_db` dependency, but also the standalone `SessionLocal()`
sessions that background tasks and workers create. All of them are rebound to one
test connection whose outer transaction is rolled back on teardown; nested
`commit()` calls become SAVEPOINT releases (``join_transaction_mode``) and never
reach the real database."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

import app.core.database as database_mod
import app.workers.tasks as workers_tasks
from app.core.database import engine, get_db
from app.main import app


@pytest.fixture
def _connection():
    """A single connection wrapped in an outer transaction that is always rolled back."""
    connection = engine.connect()
    trans = connection.begin()
    try:
        yield connection
    finally:
        if trans.is_active:
            trans.rollback()
        connection.close()


@pytest.fixture
def db(_connection, monkeypatch):
    # Bind a session factory to the test connection. create_savepoint turns any
    # in-request commit() into a SAVEPOINT release, keeping the outer transaction
    # open so the final rollback discards everything.
    TestSession = sessionmaker(
        bind=_connection,
        join_transaction_mode="create_savepoint",
        autoflush=False,
        expire_on_commit=False,
        future=True,
    )
    # Redirect every standalone-session entry point (workers, background tasks)
    # to the test connection so their commits cannot escape the transaction.
    monkeypatch.setattr(database_mod, "SessionLocal", TestSession)
    monkeypatch.setattr(workers_tasks, "SessionLocal", TestSession)

    session = TestSession()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(db):
    # Every request shares the test session, on the same rolled-back connection.
    def _override():
        yield db

    app.dependency_overrides[get_db] = _override
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


# Shared development password seeded for every demo user (seeds/0005_dev_passwords.sql).
DEV_PASSWORD = "Second@123"


@pytest.fixture
def auth(client):
    def _headers(email: str, password: str = DEV_PASSWORD) -> dict[str, str]:
        resp = client.post("/api/v1/auth/login", json={"email": email, "password": password})
        assert resp.status_code == 200, resp.text
        return {"Authorization": f"Bearer {resp.json()['access_token']}"}

    return _headers


# Convenience seeded-user emails
INSPECTOR_KS = "nora.kowalczyk@ccfp.gov"
ANALYST_KS = "elliot.fontaine@ccfp.gov"
ANALYST_TX = "grant.holloway@ccfp.gov"
FEDERAL = "omar.haddad@ccfp.gov"
PUBLIC = "public.demo@ccfp.gov"
ADMIN = "avery.thornton@ccfp.gov"
PROJECT = "dana.whitfield@ccfp.gov"
DB_ADMIN = "victor.delacruz@ccfp.gov"
SCIENTIST = "priya.ramanathan@ccfp.gov"
SYSADMIN = "sysadmin@ccfp.gov"  # the only seeded role holding audit:read
# STATE_USER role, KS-scoped. Unlike STATE_CMV_ANALYST it holds report:download,
# so it is the principal to use when exercising the download path under scope.
STATE_USER_KS = "tomasz.bialek@ccfp.gov"
# Roles introduced by the Jan-2026 BRD's rewritten authorization model.
SUPER_USER = "imogen.sandoval@ccfp.gov"      # CCFP_SUPER_USER, FMCSA Federal tier
FMCSA_HQ = "desmond.okafor@ccfp.gov"          # FMCSA_HQ, FMCSA Federal tier
FMCSA_ENFORCEMENT = "bernadette.kruse@ccfp.gov"  # FMCSA_ENFORCEMENT, FMCSA Federal tier
NTSB_USER = "soren.vasquez@ccfp.gov"          # FEDERAL_USER in the NTSB org, Other Federal tier
