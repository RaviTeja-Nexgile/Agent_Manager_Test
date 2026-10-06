"""API tests for statistical analysis over Analysis Environment cohorts.

Complements ``test_statistics.py``, which tests the mathematics with no database.
These exercise the SQL and the authorization, because that is where the two bugs
this feature actually shipped with were hiding:

  * the numeric distribution built ``GROUP BY 1`` over a cast expression while
    ordering by the raw column, which PostgreSQL rejects — invisible until a
    numeric variable was requested, because the categorical branch works;
  * the exposure-varies and control-cohort guards, which are the difference
    between a refused risk model and a confident meaningless one.

All requests run through the shared ``client`` fixture, bound to a single
rolled-back transaction, so the live database is never mutated.
"""
from __future__ import annotations

import pytest

from tests.conftest import ANALYST_KS, FEDERAL, PUBLIC

API = "/api/v1"

# Holds analysis_stats:run + analysis_stats:manage (migration 0028).
DATA_SCIENTIST = "priya.ramanathan@ccfp.gov"
# Holds analysis_stats:run only — may compute, may not define populations.
DB_ADMIN = "victor.delacruz@ccfp.gov"


def _cohorts(client, headers):
    resp = client.get(f"{API}/analysis-cohorts", headers=headers)
    assert resp.status_code == 200, resp.text
    return {c["code"]: c for c in resp.json()}


@pytest.fixture
def cohorts(client, auth):
    found = _cohorts(client, auth(DATA_SCIENTIST))
    if not found:
        pytest.skip("Analysis Environment cohorts are not seeded in this database")
    return found


# --------------------------------------------------------------------------- distributions
@pytest.mark.parametrize("variable", ["num_fatalities", "num_vehicles", "num_persons"])
def test_numeric_distribution_returns_a_histogram(client, auth, cohorts, variable):
    """Regression: the numeric branch 500'd on a GROUP BY / ORDER BY mismatch.

    The categorical branch was exercised and worked, so nothing surfaced this
    until a numeric variable was actually requested.
    """
    cohort = cohorts["ALL_CRASHES"]
    resp = client.get(
        f"{API}/analysis-cohorts/{cohort['id']}/distribution",
        headers=auth(DATA_SCIENTIST),
        params={"variable": variable, "bins": 6},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["kind"] == "NUMERIC"
    # Every member is accounted for: width_bucket puts the maximum in bin n+1,
    # and folding that back into the top bin is what makes these reconcile.
    assert sum(b["count"] for b in body["histogram"]) == body["n"]
    if body["entries"]:
        assert body["entries"][-1]["cumulative_percent"] == pytest.approx(100.0, abs=1e-6)
        # Ordered numerically, not lexically — "10" must not sort before "2".
        values = [float(e["category"]) for e in body["entries"]]
        assert values == sorted(values)


def test_categorical_distribution_is_a_frequency_table(client, auth, cohorts):
    resp = client.get(
        f"{API}/analysis-cohorts/{cohorts['ALL_CRASHES']['id']}/distribution",
        headers=auth(DATA_SCIENTIST),
        params={"variable": "state_code"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["kind"] == "CATEGORICAL"
    assert sum(e["frequency"] for e in body["entries"]) == body["n"]


def test_unknown_variable_is_400(client, auth, cohorts):
    resp = client.get(
        f"{API}/analysis-cohorts/{cohorts['ALL_CRASHES']['id']}/distribution",
        headers=auth(DATA_SCIENTIST),
        params={"variable": "wage_rate"},
    )
    assert resp.status_code == 400, resp.text


# --------------------------------------------------------------------------- descriptive
def test_describe_reports_provenance_and_caveats(client, auth, cohorts):
    """A statistic without its cohort version is unreproducible, so the version
    stamp is part of the contract, not decoration."""
    resp = client.get(
        f"{API}/analysis-cohorts/{cohorts['FATAL_INSCOPE']['id']}/describe",
        headers=auth(DATA_SCIENTIST),
        params={"variable": "num_fatalities"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    for key in ("version_no", "materialized_at", "cohort_code", "caveats"):
        assert key in body, key
    assert body["n"] >= 1
    assert body["mean"] is not None and body["median"] is not None


def test_describe_rejects_a_categorical_variable(client, auth, cohorts):
    resp = client.get(
        f"{API}/analysis-cohorts/{cohorts['FATAL_INSCOPE']['id']}/describe",
        headers=auth(DATA_SCIENTIST),
        params={"variable": "state_code"},
    )
    assert resp.status_code == 400, resp.text


# --------------------------------------------------------------------------- risk modelling
def test_risk_model_requires_a_control_cohort(client, auth, cohorts):
    """The BRD makes risk modelling conditional on "the availability of control".

    Passing a GENERAL population as the control must be refused: the resulting
    odds ratio would look authoritative and mean nothing.
    """
    resp = client.post(
        f"{API}/analysis-statistics/risk-model",
        headers=auth(DATA_SCIENTIST),
        json={
            "case_cohort_id": cohorts["FATAL_INSCOPE"]["id"],
            "control_cohort_id": cohorts["KS_FATAL"]["id"],
            "exposure_factor": "Fatigue",
        },
    )
    assert resp.status_code == 400, resp.text
    assert "CONTROL" in resp.text


def test_risk_model_refuses_to_compare_a_cohort_with_itself(client, auth, cohorts):
    case_id = cohorts["FATAL_INSCOPE"]["id"]
    resp = client.post(
        f"{API}/analysis-statistics/risk-model",
        headers=auth(DATA_SCIENTIST),
        json={
            "case_cohort_id": case_id,
            "control_cohort_id": case_id,
            "exposure_factor": "Fatigue",
        },
    )
    assert resp.status_code == 400, resp.text


def test_risk_model_against_a_control_reports_an_estimate(client, auth, cohorts):
    resp = client.post(
        f"{API}/analysis-statistics/risk-model",
        headers=auth(DATA_SCIENTIST),
        json={
            "case_cohort_id": cohorts["FATAL_INSCOPE"]["id"],
            "control_cohort_id": cohorts["OUTOFSCOPE_CONTROL"]["id"],
            "exposure_factor": "Fatigue",
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["case_cohort"]["code"] == "FATAL_INSCOPE"
    assert body["control_cohort"]["code"] == "OUTOFSCOPE_CONTROL"
    if body.get("exposure_varies"):
        assert body["odds_ratio"] > 0
        assert body["odds_ratio_ci_lower"] <= body["odds_ratio"] <= body["odds_ratio_ci_upper"]
        # Small cells must not be reported through the chi-square approximation.
        if body["min_expected_cell"] < 5:
            assert body["test_used"] == "FISHER_EXACT"
    # The unadjusted-estimate warning is unconditional; it is never safe to omit.
    assert any("confounder" in c for c in body["caveats"])


def test_absent_exposure_reports_no_estimate_rather_than_one(client, auth, cohorts):
    """An exposure on no crash yields a defined-but-meaningless OR of ~1. Saying
    so beats reporting it."""
    resp = client.post(
        f"{API}/analysis-statistics/risk-model",
        headers=auth(DATA_SCIENTIST),
        json={
            "case_cohort_id": cohorts["FATAL_INSCOPE"]["id"],
            "control_cohort_id": cohorts["OUTOFSCOPE_CONTROL"]["id"],
            "exposure_factor": "no such contributing factor",
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["exposure_varies"] is False
    assert "odds_ratio" not in body


# --------------------------------------------------------------------------- comparison
def test_compare_requires_exactly_one_of_variable_or_factor(client, auth, cohorts):
    payload = {
        "cohort_a_id": cohorts["KS_FATAL"]["id"],
        "cohort_b_id": cohorts["TX_FATAL"]["id"],
    }
    h = auth(DATA_SCIENTIST)
    assert client.post(f"{API}/analysis-statistics/compare", headers=h, json=payload).status_code == 400
    both = {**payload, "variable": "num_fatalities", "factor": "Fatigue"}
    assert client.post(f"{API}/analysis-statistics/compare", headers=h, json=both).status_code == 400


def test_compare_two_states_runs_welch(client, auth, cohorts):
    resp = client.post(
        f"{API}/analysis-statistics/compare",
        headers=auth(DATA_SCIENTIST),
        json={
            "cohort_a_id": cohorts["KS_FATAL"]["id"],
            "cohort_b_id": cohorts["TX_FATAL"]["id"],
            "variable": "num_fatalities",
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    if body.get("test_used"):
        assert body["test_used"] == "WELCH_T"
        assert 0.0 <= body["p_value"] <= 1.0


# --------------------------------------------------------------------------- authorization
@pytest.mark.parametrize("email", [ANALYST_KS, FEDERAL, PUBLIC])
def test_statistical_tooling_is_ccfp_internal(client, auth, email):
    """The BRD's Analyze table lists only the CCFP Project Team — unlike the
    Visualize table, it grants no read to State, Federal or public users. They
    receive analysis outputs through the Analysis Environment shares instead."""
    assert client.get(f"{API}/analysis-cohorts", headers=auth(email)).status_code == 403


def test_running_a_method_does_not_confer_defining_a_population(client, auth, cohorts):
    """analysis_stats:run and :manage are split because a cohort definition
    silently changes every result computed from it afterwards."""
    h = auth(DB_ADMIN)
    assert client.get(f"{API}/analysis-cohorts", headers=h).status_code == 200
    created = client.post(
        f"{API}/analysis-cohorts",
        headers=h,
        json={
            "environment_id": cohorts["ALL_CRASHES"]["environment_id"],
            "code": "ZZ_SHOULD_NOT_EXIST",
            "name": "denied",
            "definition": {"filters": []},
        },
    )
    assert created.status_code == 403, created.text
