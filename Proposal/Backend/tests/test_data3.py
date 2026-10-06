"""DATA-3: raw/aggregated source-data views are now consumed by the UI
(documentation §8.8 lines 310-311 — authorized users can "view raw data from all
source systems" and "view aggregated crash data"; §12.3 exposes both surfaces).

The backend endpoints already exist:
  * ``GET /api/v1/crashes/{crash_id}/raw-data``  (requires ``data_mgmt:read_raw``)
    returns per-system counts plus a ``source_records`` lineage list.
  * ``GET /api/v1/crashes/{crash_id}/aggregated`` (requires
    ``data_mgmt:read_aggregated`` + ``crash:read``) returns canonical-attribute
    coverage (``required_present`` / ``required_missing`` / counts).

A new "Raw / Aggregated" sub-tab on the crash Source-Data tab calls both. This
test guarantees the contract the UI depends on stays green and that State scope
is enforced on both endpoints.

All tests run inside a rolled-back transaction (see conftest) so the live
development database is never mutated.

Coverage:
  * Positive (raw): a KS-scoped analyst reads the seeded KS crash's raw-data and
    gets 200 with ``counts.source_records == 3`` and a 3-item ``source_records``
    list carrying lineage fields (source_system / source_type / external_id / uri).
  * Positive (aggregated): the same crash's aggregated view returns 200 with all
    four numeric coverage fields, including ``required_missing``.
  * Negative/authorization (scope): the KS analyst reading a TX crash's raw-data
    is 403 (outside authorized State scope) — same scope isolation as crash reads.
  * Negative/authorization (permission): a Public user holds neither
    ``data_mgmt:read_raw`` nor ``data_mgmt:read_aggregated`` -> 403 on both
    endpoints, so the gating the UI relies on is enforced server-side.
"""
from __future__ import annotations

from tests.conftest import ANALYST_KS, PUBLIC

API = "/api/v1"

# Seeded synthetic crashes (Backend/database/seeds/0004_demo_crashes.sql):
#   KS, in-scope, 3 source_records (lines 86-90)
KS_CRASH = "c1a51001-0000-0000-0000-000000000001"
#   TX, in-scope — used for the out-of-State-scope negative case
TX_CRASH = "c2b72002-0000-0000-0000-000000000002"


# --------------------------------------------------------------------------- positive
def test_raw_data_returns_seeded_source_records(client, auth):
    """A KS-scoped analyst can read the KS crash's raw source data: the counts
    block reports exactly the 3 seeded source records and the lineage list carries
    one row per source system with its provenance fields populated."""
    analyst = auth(ANALYST_KS)
    resp = client.get(f"{API}/crashes/{KS_CRASH}/raw-data", headers=analyst)
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["crash_id"] == KS_CRASH
    assert body["counts"]["source_records"] == 3

    records = body["source_records"]
    assert isinstance(records, list)
    assert len(records) == 3
    # Each lineage row carries the provenance fields the UI table renders.
    for rec in records:
        assert set(rec) == {"source_system", "source_type", "external_id", "uri"}
    # The seeded systems (SafeSpect / MCMIS / eRODS) are all represented.
    assert {r["source_system"] for r in records} == {"SafeSpect", "MCMIS", "eRODS"}


def test_aggregated_returns_coverage_summary(client, auth):
    """The aggregated view returns the four numeric coverage fields the stat
    tiles render, including ``required_missing``, with non-negative counts."""
    analyst = auth(ANALYST_KS)
    resp = client.get(f"{API}/crashes/{KS_CRASH}/aggregated", headers=analyst)
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["crash_id"] == KS_CRASH
    for field in (
        "current_attribute_count",
        "required_attribute_count",
        "required_present",
        "required_missing",
    ):
        assert field in body, f"missing {field}"
        assert isinstance(body[field], int)
        assert body[field] >= 0
    # present + missing partitions the required set.
    assert body["required_present"] + body["required_missing"] == body["required_attribute_count"]


# --------------------------------------------------------------------------- negative
def test_raw_data_blocked_outside_state_scope(client, auth):
    """Scope isolation: a KS-scoped analyst reading a TX crash's raw-data is
    forbidden (403) — load_crash enforces the same State scope as every crash
    read, so the new UI surface cannot leak cross-State raw data."""
    analyst = auth(ANALYST_KS)
    resp = client.get(f"{API}/crashes/{TX_CRASH}/raw-data", headers=analyst)
    assert resp.status_code == 403, resp.text


def test_raw_and_aggregated_require_permission(client, auth):
    """Authorization: a Public user holds neither data_mgmt:read_raw nor
    data_mgmt:read_aggregated, so both endpoints reject with 403 — matching the
    UI's permission gating (``hasPermission`` on each block)."""
    public = auth(PUBLIC)
    assert client.get(f"{API}/crashes/{KS_CRASH}/raw-data", headers=public).status_code == 403
    assert client.get(f"{API}/crashes/{KS_CRASH}/aggregated", headers=public).status_code == 403
