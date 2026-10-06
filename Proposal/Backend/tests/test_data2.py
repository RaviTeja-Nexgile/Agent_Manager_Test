"""DATA-2: definition-driven QC rule evaluation.

The QC evaluator must interpret each rule's stored JSONB ``definition`` instead
of switching only on a fixed list of hardcoded built-in codes. An admin-created
rule whose code is not one of the eight built-ins previously fell through to
``NOT_EVALUATED``; with a recognised definition it now actually runs. Rules
whose definition is null/empty fall back to the legacy code switch, so every
seeded built-in keeps its exact prior PASS/WARNING/FAIL result.

All tests run inside the shared rolled-back transaction (conftest), so creating
a rule and re-running the worker never mutates the dev database.
"""
from __future__ import annotations

import uuid

from app import workers
from app.models import DataQualityRule
from tests.conftest import ADMIN, ANALYST_KS

API = "/api/v1"

# Seeded, fully-populated Kansas crash (num_fatalities == 1, ANALYSIS phase).
KS_CRASH_ID = "c1a51001-0000-0000-0000-000000000001"


def _result_for(qc: dict, code: str) -> dict | None:
    return next((r for r in qc["results"] if r["rule"] == code), None)


def test_admin_can_create_rule_with_definition(client, auth):
    """An admin (holds study:configure) may create a definition-carrying rule."""
    resp = client.post(
        f"{API}/data-quality-rules",
        headers=auth(ADMIN),
        json={
            "code": "DQ_TEST_FATAL2",
            "name": "At least 2 fatalities",
            "rule_type": "CROSS_FIELD",
            "severity": "WARNING",
            "definition": {"min_fatalities": 2},
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["code"] == "DQ_TEST_FATAL2"
    assert body["definition"] == {"min_fatalities": 2}
    assert body["is_active"] is True


def test_configured_rule_evaluates_from_definition(client, auth, db):
    """A configured {"min_fatalities": 2} rule FAILs on a 1-fatality crash
    instead of returning NOT_EVALUATED, and the seeded DQ_DOT_FORMAT rule still
    evaluates exactly as before (regression guard)."""
    # Create the admin-configured rule through the real API (audited path).
    created = client.post(
        f"{API}/data-quality-rules",
        headers=auth(ADMIN),
        json={
            "code": "DQ_TEST_FATAL2",
            "name": "At least 2 fatalities",
            "rule_type": "CROSS_FIELD",
            "severity": "WARNING",
            "definition": {"min_fatalities": 2},
        },
    )
    assert created.status_code == 201, created.text

    qc = workers.evaluate_quality(uuid.UUID(KS_CRASH_ID), db=db)
    assert "error" not in qc, qc

    # The configured rule now runs: 1 fatality < required 2 -> FAIL, not NOT_EVALUATED.
    fatal2 = _result_for(qc, "DQ_TEST_FATAL2")
    assert fatal2 is not None, qc["results"]
    assert fatal2["status"] == "FAIL", fatal2
    assert fatal2["status"] != "NOT_EVALUATED"

    # Regression guard: the seeded DQ_DOT_FORMAT rule (pattern definition) still
    # PASSes for this crash (its only CMV vehicle's U.S. DOT "3192847" is well
    # formed), exactly as the code-based check produced before this change.
    dot = _result_for(qc, "DQ_DOT_FORMAT")
    assert dot is not None
    assert dot["status"] == "PASS", dot
    assert dot["message"] == "U.S. DOT numbers well-formed."

    # And the seeded DQ_FATALITY_COUNT (min_fatalities == 1) still PASSes
    # unchanged for the same 1-fatality crash.
    fatal1 = _result_for(qc, "DQ_FATALITY_COUNT")
    assert fatal1 is not None
    assert fatal1["status"] == "PASS", fatal1


def test_definition_min_fatalities_one_passes(client, auth, db):
    """A configured rule with {"min_fatalities": 1} PASSes the same 1-fatality
    crash, proving the dispatcher reads the threshold from the definition."""
    created = client.post(
        f"{API}/data-quality-rules",
        headers=auth(ADMIN),
        json={
            "code": "DQ_TEST_FATAL1",
            "name": "At least 1 fatality",
            "rule_type": "CROSS_FIELD",
            "severity": "INFO",
            "definition": {"min_fatalities": 1},
        },
    )
    assert created.status_code == 201, created.text

    qc = workers.evaluate_quality(uuid.UUID(KS_CRASH_ID), db=db)
    res = _result_for(qc, "DQ_TEST_FATAL1")
    assert res is not None and res["status"] == "PASS", res


def test_unknown_definition_falls_back_to_not_evaluated(db):
    """A rule with neither a recognised definition key nor a known built-in code
    still falls back to NOT_EVALUATED (no behaviour change for that case)."""
    db.add(
        DataQualityRule(
            code="DQ_TEST_UNKNOWN",
            name="Unknown configured rule",
            rule_type="CUSTOM",
            severity="INFO",
            definition={"unsupported_key": True},
            is_active=True,
        )
    )
    db.flush()

    qc = workers.evaluate_quality(uuid.UUID(KS_CRASH_ID), db=db)
    res = _result_for(qc, "DQ_TEST_UNKNOWN")
    assert res is not None and res["status"] == "NOT_EVALUATED", res


def test_non_admin_cannot_create_rule(client, auth):
    """Authorization: a State analyst lacks admin:system / study:configure, so
    creating a QC rule is forbidden (403)."""
    resp = client.post(
        f"{API}/data-quality-rules",
        headers=auth(ANALYST_KS),
        json={
            "code": "DQ_TEST_FORBIDDEN",
            "name": "Should be rejected",
            "rule_type": "CROSS_FIELD",
            "severity": "WARNING",
            "definition": {"min_fatalities": 2},
        },
    )
    assert resp.status_code == 403, resp.text
