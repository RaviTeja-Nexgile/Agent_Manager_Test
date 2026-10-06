"""STUD-5: per-study publication settings (§8.1 / §5 Phase 7).

Each study carries configurable publication settings — a de-identification
policy, a public-sharing scope, a publication toggle, and free-text notes. They
are surfaced through the existing study read/update API:

  * ``GET   /studies/{id}``   exposes the four publication fields (never null for
    the three defaulted columns).
  * ``PATCH /studies/{id}``   lets a holder of ``study:update`` OR ``study:configure``
    edit them; the change is audited via the existing ``record_audit``.

CCFP_PROJECT_ADMIN (``ADMIN``) holds both ``study:update`` and ``study:configure``;
STATE_CMV_ANALYST (``ANALYST_KS``) holds neither, so its PATCH is a 403.

Every test runs inside the rolled-back transaction provided by the ``db`` /
``client`` fixtures, so any rows mutated here are discarded on teardown — this
keeps the suite robust to seed drift (it asserts invariants, not snapshots).
"""
from __future__ import annotations

import uuid

from sqlalchemy import select

from app.models import AuditLog
from tests.conftest import ADMIN, ANALYST_KS, FEDERAL, PUBLIC

API = "/api/v1"

PUBLICATION_FIELDS = (
    "deidentification_policy",
    "public_scope",
    "publication_enabled",
    "publication_notes",
)


def _study(client, headers) -> dict:
    return next(
        s for s in client.get(f"{API}/studies", headers=headers).json() if s["code"] == "PHASE1-HDT"
    )


# --------------------------------------------------------------------------- read
def test_get_study_exposes_publication_fields_with_defaults(client, auth):
    """GET /studies/{id} carries the publication fields; the three defaulted
    (NOT NULL) columns are present and never null."""
    h = auth(ADMIN)
    study = _study(client, h)
    body = client.get(f"{API}/studies/{study['id']}", headers=h).json()
    for field in PUBLICATION_FIELDS:
        assert field in body
    # NOT NULL DEFAULT columns are never null.
    assert body["deidentification_policy"] is not None
    assert body["public_scope"] is not None
    assert isinstance(body["publication_enabled"], bool)
    # Defaults match the applied schema (STANDARD / AGGREGATE_ONLY / false).
    assert body["deidentification_policy"] in {"STANDARD", "STRICT", "NONE"}
    assert body["public_scope"] in {"NONE", "AGGREGATE_ONLY", "DEIDENTIFIED_RECORDS"}


def test_list_studies_exposes_publication_fields(client, auth):
    """The list endpoint (same StudyOut) also surfaces the publication fields."""
    studies = client.get(f"{API}/studies", headers=auth(ADMIN)).json()
    assert studies
    for s in studies:
        for field in PUBLICATION_FIELDS:
            assert field in s


# --------------------------------------------------------------------------- update
def test_admin_can_patch_publication_settings(client, auth):
    """PATCH as ADMIN sets public_scope / publication_enabled / de-id policy /
    notes; a follow-up GET reflects the change."""
    h = auth(ADMIN)
    study = _study(client, h)
    resp = client.patch(
        f"{API}/studies/{study['id']}",
        headers=h,
        json={
            "deidentification_policy": "STRICT",
            "public_scope": "NONE",
            "publication_enabled": True,
            "publication_notes": "Hold publication pending DSA review.",
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["deidentification_policy"] == "STRICT"
    assert body["public_scope"] == "NONE"
    assert body["publication_enabled"] is True
    assert body["publication_notes"] == "Hold publication pending DSA review."

    # The change persists and is visible on a fresh GET.
    fetched = client.get(f"{API}/studies/{study['id']}", headers=h).json()
    assert fetched["deidentification_policy"] == "STRICT"
    assert fetched["public_scope"] == "NONE"
    assert fetched["publication_enabled"] is True
    assert fetched["publication_notes"] == "Hold publication pending DSA review."


def test_patch_publication_is_partial(client, auth):
    """exclude_unset semantics: PATCHing only one publication field leaves the
    others (and non-publication fields) untouched."""
    h = auth(ADMIN)
    study = _study(client, h)
    original = client.get(f"{API}/studies/{study['id']}", headers=h).json()

    resp = client.patch(
        f"{API}/studies/{study['id']}",
        headers=h,
        json={"publication_enabled": True},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["publication_enabled"] is True
    # Unsent publication fields keep their prior values.
    assert body["deidentification_policy"] == original["deidentification_policy"]
    assert body["public_scope"] == original["public_scope"]
    # Non-publication fields are unaffected.
    assert body["name"] == original["name"]
    assert body["status"] == original["status"]


def test_patch_publication_rejects_invalid_enum_value(client, auth):
    """An out-of-vocabulary public_scope / policy value is a 422 (Pydantic enum)."""
    h = auth(ADMIN)
    study = _study(client, h)
    resp = client.patch(
        f"{API}/studies/{study['id']}",
        headers=h,
        json={"public_scope": "EVERYTHING"},
    )
    assert resp.status_code == 422, resp.text


def test_patch_publication_writes_audit(client, auth, db):
    """The publication PATCH is audited via the existing record_audit
    (UPDATE / study / <id>)."""
    h = auth(ADMIN)
    study = _study(client, h)
    resp = client.patch(
        f"{API}/studies/{study['id']}",
        headers=h,
        json={"public_scope": "DEIDENTIFIED_RECORDS"},
    )
    assert resp.status_code == 200, resp.text
    audits = db.scalars(
        select(AuditLog).where(
            AuditLog.entity_type == "study",
            AuditLog.entity_id == uuid.UUID(study["id"]),
            AuditLog.action == "UPDATE",
        )
    ).all()
    assert audits, "expected an UPDATE audit_logs row for the study publication change"


# --------------------------------------------------------------------------- authorization
def test_analyst_cannot_patch_publication(client, auth):
    """STATE_CMV_ANALYST holds neither study:update nor study:configure -> 403."""
    admin_h = auth(ADMIN)
    study = _study(client, admin_h)
    resp = client.patch(
        f"{API}/studies/{study['id']}",
        headers=auth(ANALYST_KS),
        json={"public_scope": "NONE", "publication_enabled": True},
    )
    assert resp.status_code == 403, resp.text


def test_federal_cannot_patch_publication(client, auth):
    """A Federal user (read-only on studies, no study:update/configure) -> 403."""
    admin_h = auth(ADMIN)
    study = _study(client, admin_h)
    resp = client.patch(
        f"{API}/studies/{study['id']}",
        headers=auth(FEDERAL),
        json={"deidentification_policy": "STRICT"},
    )
    assert resp.status_code == 403, resp.text


def test_public_user_cannot_patch_publication(client, auth):
    """A Public user (only public:read) cannot edit publication settings -> 403."""
    admin_h = auth(ADMIN)
    study = _study(client, admin_h)
    resp = client.patch(
        f"{API}/studies/{study['id']}",
        headers=auth(PUBLIC),
        json={"publication_enabled": True},
    )
    assert resp.status_code == 403, resp.text
