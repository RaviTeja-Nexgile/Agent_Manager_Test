"""STUD-4: data-driven completeness checks via a token registry.

Completeness rules resolve each token in their ``definition.requires`` against a
code-owned token registry (workers/tasks.py) with parameterised thresholds read
from the rule ``definition`` — so an admin can require, say, 1 contributing
factor instead of the default 3 without editing Python. Tokens are validated at
write time so a typo can no longer make a crash permanently incomplete, and an
unknown token at evaluation time surfaces distinctly instead of silently
blocking completeness.

All tests run inside the rolled-back ``db``/``client`` fixtures from conftest, so
the live development database is never mutated (commit() is a SAVEPOINT release).
Setup rows are committed first, mirroring tests/test_worker_notifications.py.
"""
from __future__ import annotations

import uuid

from sqlalchemy import select

from app import workers
from app.models import CompletenessRule, ContributingFactorSelection, Crash, Study
from tests.conftest import ADMIN, ANALYST_KS, INSPECTOR_KS

API = "/api/v1"


# --------------------------------------------------------------------------- helpers
def _phase1_study(db) -> Study:
    study = db.scalar(select(Study).where(Study.code == "PHASE1-HDT"))
    assert study is not None, "PHASE1-HDT study must be seeded"
    return study


def _make_crash(db, *, study_id: uuid.UUID, state_code: str = "KS") -> Crash:
    crash = Crash(
        ccfp_identifier=f"CCFP-STUD4-{uuid.uuid4().hex[:12]}",
        study_id=study_id,
        state_code=state_code,
        num_fatalities=1,
    )
    db.add(crash)
    db.flush()
    return crash


def _add_factor(db, crash_id: uuid.UUID, rank: int, value: str) -> None:
    db.add(
        ContributingFactorSelection(
            crash_id=crash_id, factor_value=value, rank=rank,
        )
    )


def _phase1_study_id(client, auth) -> str:
    studies = client.get(f"{API}/studies", headers=auth(ADMIN)).json()
    return next(s for s in studies if s["code"] == "PHASE1-HDT")["id"]


# --------------------------------------------------------------------------- regression
def test_seeded_rules_evaluate_unchanged(db):
    """The five seeded single-token rules keep their identical outcome.

    A bare crash satisfies none of the factor/inspection/IIF/attribute checks, so
    every seeded token is reported unmet exactly as before — proving the registry
    default thresholds (3 factors, 1 inspection) reproduce the old literals.
    """
    study = _phase1_study(db)
    crash = _make_crash(db, study_id=study.id)
    db.commit()

    result = workers.evaluate_completeness(crash.id, db=db)
    assert result["status"] == "INCOMPLETE"

    # The seeded vocabulary the checks dict still exposes (token -> bool view).
    assert set(result["checks"]) == {
        "initial_incident_submitted",
        "required_attributes_present",
        "post_crash_inspection_exists",
        "three_contributing_factors",
        "no_critical_qc_failures",
    }
    # Bare crash: no IIF, no inspection, no factors -> these tokens are unmet.
    unmet = {m["unmet"] for m in result["missing"]}
    assert "three_contributing_factors" in unmet
    assert "post_crash_inspection_exists" in unmet
    assert "initial_incident_submitted" in unmet
    # No unknown-token markers from seeded rules.
    assert all(not m.get("unknown_token") for m in result["missing"])


# --------------------------------------------------------------------------- parameterised threshold
def test_parameterised_threshold_lowers_factor_requirement(db):
    """A rule with min_contributing_factors=1 is met at 1 factor; default-3 is not."""
    study = _phase1_study(db)
    crash = _make_crash(db, study_id=study.id)
    _add_factor(db, crash.id, rank=1, value="Following too closely")

    # A second, parameterised rule on the same study requiring only ONE factor.
    relaxed = CompletenessRule(
        study_id=study.id,
        name=f"One factor only {uuid.uuid4().hex[:6]}",
        description="Parameterised threshold (STUD-4)",
        definition={"requires": ["three_contributing_factors"], "params": {"min_contributing_factors": 1}},
        is_active=True,
    )
    db.add(relaxed)
    db.commit()

    result = workers.evaluate_completeness(crash.id, db=db)
    unmet_by_rule = {(m["rule"], m["unmet"]) for m in result["missing"]}

    # The relaxed rule (min 1) is satisfied by the single factor -> not in missing.
    assert (relaxed.name, "three_contributing_factors") not in unmet_by_rule
    # The seeded default-3 rule is still unmet at 1 factor (regression guard).
    seeded = db.scalar(
        select(CompletenessRule).where(
            CompletenessRule.study_id == study.id,
            CompletenessRule.name == "Contributing factors selected",
        )
    )
    assert seeded is not None, "seeded default-3 rule must exist"
    assert (seeded.name, "three_contributing_factors") in unmet_by_rule


def test_higher_threshold_can_be_required(db):
    """A rule with min_post_crash_inspections=2 is unmet when only the default would pass."""
    study = _phase1_study(db)
    crash = _make_crash(db, study_id=study.id)
    rule = CompletenessRule(
        study_id=study.id,
        name=f"Two inspections {uuid.uuid4().hex[:6]}",
        definition={"requires": ["post_crash_inspection_exists"], "params": {"min_post_crash_inspections": 2}},
        is_active=True,
    )
    db.add(rule)
    db.commit()

    result = workers.evaluate_completeness(crash.id, db=db)
    unmet_by_rule = {(m["rule"], m["unmet"]) for m in result["missing"]}
    assert (rule.name, "post_crash_inspection_exists") in unmet_by_rule


# --------------------------------------------------------------------------- unknown token surfaces at eval
def test_unknown_token_surfaces_at_evaluation(db):
    """An unknown token (only reachable if it bypassed write validation) is flagged."""
    study = _phase1_study(db)
    crash = _make_crash(db, study_id=study.id)
    rule = CompletenessRule(
        study_id=study.id,
        name=f"Bad token {uuid.uuid4().hex[:6]}",
        definition={"requires": ["definitely_not_a_real_token"]},
        is_active=True,
    )
    db.add(rule)
    db.commit()

    result = workers.evaluate_completeness(crash.id, db=db)
    flagged = [
        m for m in result["missing"]
        if m["unmet"] == "definitely_not_a_real_token" and m.get("unknown_token")
    ]
    assert flagged, "unknown token must surface with an unknown_token marker"


# --------------------------------------------------------------------------- token catalog endpoint
def test_token_catalog_endpoint(client, auth):
    """GET /completeness-rule-tokens lists the vocabulary + numeric thresholds."""
    resp = client.get(f"{API}/completeness-rule-tokens", headers=auth(ADMIN))
    assert resp.status_code == 200, resp.text
    tokens = {t["token"]: t for t in resp.json()["tokens"]}
    assert "three_contributing_factors" in tokens
    params = {p["name"] for p in tokens["three_contributing_factors"]["params"]}
    assert params == {"min_contributing_factors"}
    assert tokens["three_contributing_factors"]["params"][0]["default"] == 3
    # A token without a threshold exposes no params.
    assert tokens["no_critical_qc_failures"]["params"] == []


def test_token_catalog_requires_auth(client):
    assert client.get(f"{API}/completeness-rule-tokens").status_code == 401


# --------------------------------------------------------------------------- write-time validation
def test_create_rule_accepts_known_token_with_params(client, auth):
    study_id = _phase1_study_id(client, auth)
    resp = client.post(
        f"{API}/studies/{study_id}/completeness-rules",
        headers=auth(ADMIN),
        json={
            "name": f"Two factors {uuid.uuid4().hex[:6]}",
            "definition": {"requires": ["three_contributing_factors"], "params": {"min_contributing_factors": 2}},
        },
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["definition"]["params"]["min_contributing_factors"] == 2


def test_create_rule_rejects_unknown_token(client, auth):
    study_id = _phase1_study_id(client, auth)
    resp = client.post(
        f"{API}/studies/{study_id}/completeness-rules",
        headers=auth(ADMIN),
        json={"name": "bad", "definition": {"requires": ["bogus_token"]}},
    )
    assert resp.status_code == 400, resp.text
    assert "bogus_token" in resp.json()["detail"]


def test_create_rule_rejects_negative_threshold(client, auth):
    study_id = _phase1_study_id(client, auth)
    resp = client.post(
        f"{API}/studies/{study_id}/completeness-rules",
        headers=auth(ADMIN),
        json={
            "name": "neg",
            "definition": {"requires": ["three_contributing_factors"], "params": {"min_contributing_factors": -1}},
        },
    )
    assert resp.status_code == 400, resp.text


# --------------------------------------------------------------------------- authorization (negative)
def test_create_rule_forbidden_for_analyst(client, auth):
    """STATE_CMV_ANALYST holds neither admin:completeness nor study:configure -> 403."""
    study_id = _phase1_study_id(client, auth)
    resp = client.post(
        f"{API}/studies/{study_id}/completeness-rules",
        headers=auth(ANALYST_KS),
        json={"name": "x", "definition": {"requires": ["three_contributing_factors"]}},
    )
    assert resp.status_code == 403, resp.text


def test_create_rule_forbidden_for_inspector(client, auth):
    study_id = _phase1_study_id(client, auth)
    resp = client.post(
        f"{API}/studies/{study_id}/completeness-rules",
        headers=auth(INSPECTOR_KS),
        json={"name": "x", "definition": {"requires": ["three_contributing_factors"]}},
    )
    assert resp.status_code == 403, resp.text
