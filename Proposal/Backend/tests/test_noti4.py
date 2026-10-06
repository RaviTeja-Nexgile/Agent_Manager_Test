"""NOTI-4: MISSING_DATA notification on missing required canonical attributes.

Per documentation §8.11 ("Missing required data"), evaluate_quality must emit a
targeted MISSING_DATA notification to the responsible State CMV Data Analyst(s)
(State-scoped) when a crash is missing one or more required canonical attributes,
in addition to recording the DQ_MISSING_REQUIRED_ATTR DataQualityResult.

All tests run against the rolled-back `db` session fixture from conftest.py.
Setup rows are committed first (in test mode commit() is a SAVEPOINT release), so
the worker's own commit stays inside the test transaction and the real database
is never mutated — mirroring tests/test_worker_notifications.py.
"""
from __future__ import annotations

import uuid

from sqlalchemy import select

from app import workers
from app.models import (
    AttributeRequirement,
    Crash,
    CrashAttributeValue,
    Notification,
    Role,
    Study,
    User,
    UserRoleAssignment,
)
from tests.conftest import ANALYST_KS, PUBLIC

API = "/api/v1"


def _make_crash(db, *, state_code: str = "KS", num_fatalities: int = 1) -> Crash:
    """Create a throwaway in-transaction crash bound to the Phase 1 study."""
    study = db.scalar(select(Study).where(Study.code == "PHASE1-HDT"))
    assert study is not None, "PHASE1-HDT study must be seeded"
    crash = Crash(
        ccfp_identifier=f"CCFP-NOTI4-{uuid.uuid4().hex[:12]}",
        study_id=study.id,
        state_code=state_code,
        num_fatalities=num_fatalities,
    )
    db.add(crash)
    db.flush()
    return crash


def _required_attr_ids(db, study_id: uuid.UUID) -> set[uuid.UUID]:
    return set(
        db.scalars(
            select(AttributeRequirement.attribute_id).where(
                AttributeRequirement.study_id == study_id,
                AttributeRequirement.is_required.is_(True),
            )
        )
    )


def _analyst_ids(db, state_code: str) -> set[uuid.UUID]:
    """Active STATE_CMV_ANALYST user ids in scope for `state_code`.

    Mirrors users_with_role: a STATE-scoped assignment must match the State; a
    non-STATE assignment is in scope for any State.
    """
    rows = db.execute(
        select(User.id, UserRoleAssignment.scope_type, UserRoleAssignment.state_code)
        .join(UserRoleAssignment, UserRoleAssignment.user_id == User.id)
        .join(Role, Role.id == UserRoleAssignment.role_id)
        .where(Role.code == "STATE_CMV_ANALYST", User.status == "ACTIVE")
    ).all()
    return {
        uid
        for (uid, scope_type, sc) in rows
        if scope_type != "STATE" or sc == state_code
    }


def _missing_data_notes(db, crash_id: uuid.UUID) -> list[Notification]:
    return list(
        db.scalars(
            select(Notification).where(
                Notification.crash_id == crash_id,
                Notification.notification_type == "MISSING_DATA",
            )
        )
    )


# --------------------------------------------------------------------------- positive
def test_missing_required_attr_emits_missing_data_notification(db):
    """A bare crash (no canonical attribute values) is missing required
    attributes -> DQ_MISSING_REQUIRED_ATTR FAILs and a MISSING_DATA notification
    is sent to every in-scope KS State CMV Data Analyst."""
    crash = _make_crash(db, state_code="KS")
    required = _required_attr_ids(db, crash.study_id)
    assert required, "PHASE1-HDT must seed at least one required attribute"
    db.commit()

    result = workers.evaluate_quality(crash.id, db=db)

    # (a) the rule result itself FAILs
    missing_rule = next(
        (r for r in result["results"] if r["rule"] == "DQ_MISSING_REQUIRED_ATTR"),
        None,
    )
    assert missing_rule is not None
    assert missing_rule["status"] == "FAIL"

    # (b) a MISSING_DATA notification exists for every in-scope KS analyst
    notes = _missing_data_notes(db, crash.id)
    recipients = {n.recipient_user_id for n in notes}
    expected = _analyst_ids(db, "KS")
    assert expected, "expected at least one KS STATE_CMV_ANALYST seeded"
    assert recipients == expected
    assert len(notes) == len(expected)  # exactly one per analyst per run
    # Message carries the crash identifier and the count of missing attributes.
    assert all(crash.ccfp_identifier in (n.message or "") for n in notes)
    assert all(str(len(required)) in (n.message or "") for n in notes)


def test_missing_data_is_state_scoped(db):
    """A KS crash's MISSING_DATA notification never reaches a different State's
    analysts (authorization/scope isolation)."""
    crash = _make_crash(db, state_code="KS")
    db.commit()

    workers.evaluate_quality(crash.id, db=db)

    recipients = {n.recipient_user_id for n in _missing_data_notes(db, crash.id)}
    tx_only = _analyst_ids(db, "TX") - _analyst_ids(db, "KS")
    assert tx_only, "expected a TX-only analyst seeded for the scope check"
    assert recipients.isdisjoint(tx_only)


# --------------------------------------------------------------------------- negative
def test_all_required_attrs_present_emits_no_missing_data(db):
    """When every required canonical attribute has a current value, the missing
    set is empty -> no MISSING_DATA notification is created."""
    crash = _make_crash(db, state_code="KS")
    required = _required_attr_ids(db, crash.study_id)
    assert required, "PHASE1-HDT must seed at least one required attribute"
    for attr_id in required:
        db.add(
            CrashAttributeValue(
                crash_id=crash.id,
                attribute_id=attr_id,
                value_text="present",
                is_current=True,
            )
        )
    db.commit()

    result = workers.evaluate_quality(crash.id, db=db)

    # The required-attribute rule now PASSes...
    missing_rule = next(
        (r for r in result["results"] if r["rule"] == "DQ_MISSING_REQUIRED_ATTR"),
        None,
    )
    assert missing_rule is not None
    assert missing_rule["status"] == "PASS"
    # ...and no MISSING_DATA notification is emitted.
    assert _missing_data_notes(db, crash.id) == []


# --------------------------------------------------------------------------- authorization
def test_qc_evaluate_forbidden_for_unauthorized_role(db, client, auth):
    """Negative/authorization: a Public User lacks data_mgmt:qc, so the QC
    evaluation endpoint (the only way to reach the MISSING_DATA emission path
    over the API) returns 403 — the missing-data notification can never be
    triggered by an unauthorized role."""
    crash = _make_crash(db, state_code="KS")
    db.commit()

    resp = client.post(
        f"{API}/crashes/{crash.id}/quality/evaluate",
        headers=auth(PUBLIC),
    )
    assert resp.status_code == 403, resp.text

    # No MISSING_DATA notification was created by the rejected request.
    assert _missing_data_notes(db, crash.id) == []
