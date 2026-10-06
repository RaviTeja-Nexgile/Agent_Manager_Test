"""PCR-2: State feedback loop — per-State PCR coverage is correctable via write/reconcile.

§8.5 — States review the attributes flagged as "not yet collected", report what
they actually collect, and CCFP reconciles the per-State coverage records. This
issue adds write/reconcile endpoints:

  * ``POST  /studies/{id}/pcr-coverage``                     — upsert a reported row
  * ``PATCH /studies/{id}/pcr-coverage/{state}/{section}``   — update reported counts

Both are guarded by ``study:configure`` (held by CCFP_PROJECT_ADMIN / SYSTEM_ADMIN,
NOT by State analysts), enforce State scope, write an ``audit_logs`` row, and create
a ``notifications`` row so the project team sees the State-reported update. The
generated ``completion_pct`` column recomputes on write.

The read endpoint (``GET``) still *derives* live counts from collected data (PCR-6)
and must NOT regress — these writes target the stored ``state_pcr_coverage`` catalog
row that records what a State *reports*, independent of the derived view.

Every test runs inside the rolled-back transaction provided by the ``db``/``client``
fixtures, so any rows added here are discarded on teardown.
"""
from __future__ import annotations

import uuid

from sqlalchemy import select

from app.models import AuditLog, Notification, StatePcrCoverage
from tests.conftest import ADMIN, ANALYST_KS, ANALYST_TX, FEDERAL

API = "/api/v1"


def _study_id(client, headers) -> str:
    return next(
        s for s in client.get(f"{API}/studies", headers=headers).json() if s["code"] == "PHASE1-HDT"
    )["id"]


# --------------------------------------------------------------------------- PATCH reconcile
def test_patch_pcr_coverage_recomputes_completion(client, auth, db):
    """As ADMIN (has study:configure), PATCH the stored KS/CRASH row's
    required_collected to 140 -> 200 and the generated completion_pct recomputes
    against the seeded total_required (202): round(140*100/202, 2) == 69.31."""
    h = auth(ADMIN)
    study_id = _study_id(client, h)

    resp = client.patch(
        f"{API}/studies/{study_id}/pcr-coverage/KS/CRASH",
        headers=h,
        json={"required_collected": 140},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["state_code"] == "KS"
    assert body["pcr_section_code"] == "CRASH"
    assert body["required_collected"] == 140
    assert body["total_required"] == 202  # seeded catalog total is preserved
    assert float(body["completion_pct"]) == 69.31

    # The stored catalog row actually changed (and the generated column with it).
    row = db.scalar(
        select(StatePcrCoverage).where(
            StatePcrCoverage.study_id == uuid.UUID(study_id),
            StatePcrCoverage.state_code == "KS",
            StatePcrCoverage.pcr_section_code == "CRASH",
        )
    )
    assert row is not None
    assert row.required_collected == 140
    assert float(row.completion_pct) == 69.31


def test_patch_pcr_coverage_writes_audit_and_notification(client, auth, db):
    """The reconcile action writes audit_logs (UPDATE / state_pcr_coverage) and a
    notifications row to the CCFP project team (§8.5)."""
    h = auth(ADMIN)
    study_id = _study_id(client, h)

    resp = client.patch(
        f"{API}/studies/{study_id}/pcr-coverage/KS/CRASH",
        headers=h,
        json={"required_collected": 150},
    )
    assert resp.status_code == 200, resp.text

    row = db.scalar(
        select(StatePcrCoverage).where(
            StatePcrCoverage.study_id == uuid.UUID(study_id),
            StatePcrCoverage.state_code == "KS",
            StatePcrCoverage.pcr_section_code == "CRASH",
        )
    )
    assert row is not None
    audits = db.scalars(
        select(AuditLog).where(
            AuditLog.entity_type == "state_pcr_coverage",
            AuditLog.entity_id == row.id,
            AuditLog.action == "UPDATE",
        )
    ).all()
    assert len(audits) == 1

    notes = db.scalars(
        select(Notification).where(Notification.notification_type == "PCR_COVERAGE_RECONCILED")
    ).all()
    assert notes, "expected a reconcile notification for the project team"
    assert any("KS" in (n.message or "") for n in notes)


# --------------------------------------------------------------------------- authorization (negative)
def test_patch_pcr_coverage_denied_without_configure(client, auth):
    """A State analyst lacks study:configure and is rejected with 403 (the write
    must not be open to report-only / collection roles)."""
    h = auth(ANALYST_KS)
    study_id = _study_id(client, auth(ADMIN))
    resp = client.patch(
        f"{API}/studies/{study_id}/pcr-coverage/KS/CRASH",
        headers=h,
        json={"required_collected": 140},
    )
    assert resp.status_code == 403


def test_upsert_pcr_coverage_denied_without_configure(client, auth):
    """POST upsert is likewise gated on study:configure (Federal report-only -> 403)."""
    h = auth(FEDERAL)
    study_id = _study_id(client, auth(ADMIN))
    resp = client.post(
        f"{API}/studies/{study_id}/pcr-coverage",
        headers=h,
        json={"state_code": "KS", "pcr_section_code": "CRASH", "required_collected": 1, "total_required": 2},
    )
    assert resp.status_code == 403


# --------------------------------------------------------------------------- POST upsert
def test_upsert_pcr_coverage_creates_and_updates(client, auth, db):
    """POST upserts a (state, section) catalog row: creates it when absent, then
    updates the same row on a second call (no duplicate)."""
    h = auth(ADMIN)
    study_id = _study_id(client, h)

    # ROADWAY is a seeded KS section; overwrite its reported counts.
    created = client.post(
        f"{API}/studies/{study_id}/pcr-coverage",
        headers=h,
        json={
            "state_code": "KS",
            "pcr_section_code": "ROADWAY",
            "required_collected": 8,
            "total_required": 16,
            "optional_collected": 0,
            "total_optional": 0,
        },
    )
    assert created.status_code == 201, created.text
    assert created.json()["required_collected"] == 8
    assert float(created.json()["completion_pct"]) == round(8 * 100 / 16, 2)  # 50.0

    # A second upsert updates the same row rather than inserting a duplicate.
    updated = client.post(
        f"{API}/studies/{study_id}/pcr-coverage",
        headers=h,
        json={
            "state_code": "KS",
            "pcr_section_code": "ROADWAY",
            "required_collected": 12,
            "total_required": 16,
            "optional_collected": 0,
            "total_optional": 0,
        },
    )
    assert updated.status_code == 201, updated.text
    assert updated.json()["required_collected"] == 12

    rows = db.scalars(
        select(StatePcrCoverage).where(
            StatePcrCoverage.study_id == uuid.UUID(study_id),
            StatePcrCoverage.state_code == "KS",
            StatePcrCoverage.pcr_section_code == "ROADWAY",
        )
    ).all()
    assert len(rows) == 1
    assert rows[0].required_collected == 12

    audits = db.scalars(
        select(AuditLog).where(
            AuditLog.entity_type == "state_pcr_coverage",
            AuditLog.action == "UPSERT",
            AuditLog.entity_id == rows[0].id,
        )
    ).all()
    assert len(audits) == 2  # one per upsert call


def test_patch_unknown_row_is_404(client, auth):
    """PATCH on a (state, section) with no stored catalog row is a 404."""
    h = auth(ADMIN)
    study_id = _study_id(client, h)
    resp = client.patch(
        f"{API}/studies/{study_id}/pcr-coverage/KS/DOES_NOT_EXIST",
        headers=h,
        json={"required_collected": 1},
    )
    assert resp.status_code == 404


# --------------------------------------------------------------------------- no GET regression (PCR-6)
def test_patch_does_not_regress_derived_get(client, auth, db):
    """Writing the stored catalog counts must NOT change the DERIVED GET response:
    GET still computes counts from collected data (PCR-6), independent of the
    reported row that PATCH mutates."""
    h = auth(ANALYST_KS)
    study_id = _study_id(client, h)

    def _crash_row():
        cov = client.get(f"{API}/studies/{study_id}/pcr-coverage?state=KS", headers=h).json()
        return next(c for c in cov if c["pcr_section_code"] == "CRASH")

    before = _crash_row()

    # Reconcile the stored row to an arbitrary value as an admin.
    admin = auth(ADMIN)
    client.patch(
        f"{API}/studies/{study_id}/pcr-coverage/KS/CRASH",
        headers=admin,
        json={"required_collected": 999, "total_required": 999},
    )

    after = _crash_row()
    # The derived GET is unchanged by the stored-row edit.
    assert after["required_collected"] == before["required_collected"]
    assert after["total_required"] == before["total_required"]
    assert float(after["completion_pct"]) == float(before["completion_pct"])
    # And the derived total is NOT the inflated stored 999 (proves derivation, not read-through).
    assert after["total_required"] != 999
