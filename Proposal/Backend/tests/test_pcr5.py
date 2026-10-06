"""PCR-5 — the PCR coverage dashboard table renders the optional-coverage figures
(``optional_collected`` / ``total_optional``) alongside the required columns.

The change is frontend-only (two extra columns in ``StudyCoverageTab.tsx``), so the
backend contract to guard is that the ``GET /studies/{id}/pcr-coverage`` response
already carries those optional fields the new columns bind to — and that the read
stays auth-protected. All requests run inside a rolled-back transaction."""
from __future__ import annotations

from tests.conftest import ANALYST_KS

API = "/api/v1"


def _phase1_study(client, headers) -> dict:
    return next(
        s
        for s in client.get(f"{API}/studies", headers=headers).json()
        if s["code"] == "PHASE1-HDT"
    )


def test_pcr_coverage_exposes_optional_fields(client, auth):
    """Every coverage row carries the optional figures the new dashboard columns
    render — non-negative ints, with ``optional_collected <= total_optional``."""
    h = auth(ANALYST_KS)
    study = _phase1_study(client, h)
    resp = client.get(f"{API}/studies/{study['id']}/pcr-coverage?state=KS", headers=h)
    assert resp.status_code == 200
    rows = resp.json()
    assert rows, "expected at least one KS coverage row to render"
    for c in rows:
        # The two fields the PCR-5 columns bind to must be present on the wire.
        assert "optional_collected" in c and "total_optional" in c
        assert isinstance(c["optional_collected"], int)
        assert isinstance(c["total_optional"], int)
        assert c["optional_collected"] >= 0
        assert c["total_optional"] >= 0
        # A State cannot have collected more optional attributes than exist.
        assert c["optional_collected"] <= c["total_optional"]
        # Required columns (rendered next to the optional ones) stay intact.
        assert "required_collected" in c and "total_required" in c


def test_pcr_coverage_crash_total_optional_matches_requirements(client, auth):
    """The KS ``CRASH`` "Total optional" figure the dashboard renders equals the
    count of study CRASH-section attributes flagged optional in
    ``attribute_requirements`` (the endpoint derives totals from requirements per
    PCR-6; the stored ``state_pcr_coverage`` count is no longer trusted).

    Derived rather than snapshotted so the assertion tracks the seed logic and
    does not drift: ``total_optional`` for a section == (count of that section's
    attributes) − (count flagged required)."""
    h = auth(ANALYST_KS)
    study = _phase1_study(client, h)
    sid = study["id"]

    attrs = client.get(f"{API}/studies/{sid}/attributes", headers=h).json()
    crash_attrs = [a for a in attrs if a.get("pcr_section") == "CRASH"]
    assert crash_attrs, "expected the study to define CRASH-section attributes"
    expected_optional = sum(1 for a in crash_attrs if a.get("is_optional"))

    cov = client.get(f"{API}/studies/{sid}/pcr-coverage?state=KS", headers=h).json()
    crash_section = next(c for c in cov if c["pcr_section_code"] == "CRASH")
    assert crash_section["total_optional"] == expected_optional
    # And the optional figure is meaningfully populated (not a dropped column).
    assert crash_section["total_optional"] > 0


def test_pcr_coverage_requires_auth(client):
    """Negative / authorization case: the coverage read is auth-protected, so a
    request with no bearer token is rejected with 401 (the data the optional
    columns render is never served unauthenticated)."""
    # Any study id is fine — auth is enforced before the study is resolved.
    placeholder = "00000000-0000-0000-0000-000000000000"
    resp = client.get(f"{API}/studies/{placeholder}/pcr-coverage?state=KS")
    assert resp.status_code == 401


def test_pcr_coverage_state_scope_isolation(client, auth):
    """Authorization / scope case: a KS-scoped analyst only ever receives KS
    coverage rows (so the optional columns render only in-scope data), even when
    no explicit ``state`` filter is supplied."""
    h = auth(ANALYST_KS)
    study = _phase1_study(client, h)
    resp = client.get(f"{API}/studies/{study['id']}/pcr-coverage", headers=h)
    assert resp.status_code == 200
    rows = resp.json()
    assert rows, "expected the KS-scoped analyst to see their own coverage rows"
    assert all(c["state_code"] == "KS" for c in rows)
