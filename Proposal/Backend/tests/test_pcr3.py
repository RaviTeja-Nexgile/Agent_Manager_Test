"""PCR-3 (§8.5): per-State, per-attribute three-way collection status.

GET /studies/{study_id}/attribute-coverage?state= returns, per attribute, the
documented colour buckets (REQUIRED_COLLECTED / REQUIRED_NOT_COLLECTED /
OPTIONAL_NOT_COLLECTED). These tests reuse the shared rolled-back-transaction
fixtures (client/auth/db) and seeded users from conftest.py."""
from __future__ import annotations

from tests.conftest import ANALYST_KS, ANALYST_TX, INSPECTOR_KS

API = "/api/v1"

_STATUSES = {"REQUIRED_COLLECTED", "REQUIRED_NOT_COLLECTED", "OPTIONAL_NOT_COLLECTED"}


def _phase1_study_id(client, headers) -> str:
    studies = client.get(f"{API}/studies", headers=headers).json()
    return next(s for s in studies if s["code"] == "PHASE1-HDT")["id"]


def test_attribute_coverage_kansas_shape_and_status(client, auth):
    """As a KS analyst, ?state=KS returns 200 with a valid three-way status per row."""
    headers = auth(ANALYST_KS)
    study_id = _phase1_study_id(client, headers)
    resp = client.get(f"{API}/studies/{study_id}/attribute-coverage?state=KS", headers=headers)
    assert resp.status_code == 200, resp.text
    rows = resp.json()
    assert rows, "expected at least one attribute coverage row for KS"

    for row in rows:
        # Every required key is present.
        for key in ("attribute_id", "code", "name", "pcr_section", "is_required",
                    "is_optional", "is_collected", "status"):
            assert key in row, f"missing key {key!r} in {row!r}"
        # status is one of the three documented buckets and matches the flags.
        assert row["status"] in _STATUSES
        if row["is_required"] and row["is_collected"]:
            assert row["status"] == "REQUIRED_COLLECTED"
        elif row["is_required"] and not row["is_collected"]:
            assert row["status"] == "REQUIRED_NOT_COLLECTED"
        else:
            # Non-required attributes surface only as optional-not-collected.
            assert row["status"] == "OPTIONAL_NOT_COLLECTED"
            assert row["is_optional"] is True


def test_attribute_coverage_kansas_has_all_three_statuses(client, auth):
    """The KS seed exercises all three colour buckets (required-collected,
    required-not-collected, optional-not-collected)."""
    headers = auth(ANALYST_KS)
    study_id = _phase1_study_id(client, headers)
    rows = client.get(f"{API}/studies/{study_id}/attribute-coverage?state=KS", headers=headers).json()
    present = {r["status"] for r in rows}
    assert _STATUSES <= present, f"expected all three statuses, got {present}"

    # Spot-check a couple of seeded facts: a known collected required attr and a
    # known not-collected required attr.
    by_code = {r["code"]: r for r in rows}
    assert by_code["C01"]["status"] == "REQUIRED_COLLECTED"
    assert by_code["V06"]["status"] == "REQUIRED_NOT_COLLECTED"


def test_attribute_coverage_default_state_for_scoped_user(client, auth):
    """A KS-scoped caller with no explicit ?state still only sees KS facts
    (the default scoped State), never another State's coverage."""
    headers = auth(ANALYST_KS)
    study_id = _phase1_study_id(client, headers)
    resp = client.get(f"{API}/studies/{study_id}/attribute-coverage", headers=headers)
    assert resp.status_code == 200, resp.text
    rows = resp.json()
    assert rows
    assert all(r["status"] in _STATUSES for r in rows)


def test_attribute_coverage_tx_analyst_cannot_read_ks(client, auth):
    """Negative / scope: a TX-scoped analyst requesting ?state=KS gets no KS rows."""
    headers = auth(ANALYST_TX)
    study_id = _phase1_study_id(client, headers)
    resp = client.get(f"{API}/studies/{study_id}/attribute-coverage?state=KS", headers=headers)
    assert resp.status_code == 200, resp.text
    assert resp.json() == []


def test_attribute_coverage_requires_auth(client):
    """Unauthenticated access is rejected (auth enforced like every studies route)."""
    # A syntactically-valid but arbitrary UUID; auth is checked before lookup.
    study_id = "00000000-0000-0000-0000-000000000000"
    resp = client.get(f"{API}/studies/{study_id}/attribute-coverage?state=KS")
    assert resp.status_code == 401


def test_attribute_coverage_unknown_study_is_404(client, auth):
    """Unknown study id is a 404 via the shared _get_study guard."""
    headers = auth(ANALYST_KS)
    study_id = "00000000-0000-0000-0000-000000000000"
    resp = client.get(f"{API}/studies/{study_id}/attribute-coverage?state=KS", headers=headers)
    assert resp.status_code == 404


def test_attribute_coverage_inspector_ks_can_read(client, auth):
    """A KS MCSAP inspector (also KS-scoped) can read KS attribute coverage."""
    headers = auth(INSPECTOR_KS)
    study_id = _phase1_study_id(client, headers)
    resp = client.get(f"{API}/studies/{study_id}/attribute-coverage?state=KS", headers=headers)
    assert resp.status_code == 200, resp.text
    assert all(r["status"] in _STATUSES for r in resp.json())
