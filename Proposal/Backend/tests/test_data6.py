"""DATA-6: per-attribute version history (documentation §8.8 — "tracking every
update by user and timestamp"). Attribute edits are already append-only
(``set_attribute`` flips the prior row to ``is_current=False`` and inserts a new
current row), so the full version history exists; this surfaces it through a
read-only ``GET /crashes/{id}/attributes/{code}/history`` endpoint.

All tests run inside a rolled-back transaction (see conftest) so the live
development database is never mutated.

Coverage:
  * Two consecutive edits to the same attribute on an UNLOCKED KS crash produce a
    history with >=2 versions, newest-first, exactly one ``is_current``, with
    ``edited_by`` populated.
  * The history honors the same sensitivity redaction as ``get_attributes``: a
    CCFP Data Scientist (holds ``data_mgmt:read_aggregated`` but none of the
    PII/SENSITIVE-granting permissions) sees ``redacted=True`` and a nulled value
    for a SENSITIVE attribute.
  * Negative/authorization: a Public user lacks ``data_mgmt:read_aggregated`` ->
    403, mirroring ``get_attributes``.
  * An unknown attribute code -> 404.
"""
from __future__ import annotations

from tests.conftest import ANALYST_KS, INSPECTOR_KS, PUBLIC

API = "/api/v1"

# CCFP Data Scientist: GLOBAL-scoped, holds crash:read + data_mgmt:read_aggregated
# (so it passes the endpoint permission gate) but NONE of the PII/SENSITIVE-
# granting permissions (seeds/0002_rbac_orgs_users.sql), so it must be redacted on
# a SENSITIVE attribute exactly as get_attributes redacts it.
DATA_SCIENTIST = "priya.ramanathan@ccfp.gov"


def _fresh_ks_crash(client, auth) -> str:
    """Create a fresh (unlocked) IN_SCOPE KS crash and return its id.

    A new crash has no completeness row, so _is_crash_locked() is False and
    attribute writes are accepted (unlike the seeded locked CCFP-2026-KS-000101).
    """
    insp = auth(INSPECTOR_KS)
    analyst = auth(ANALYST_KS)
    study_id = next(
        s for s in client.get(f"{API}/studies", headers=insp).json() if s["code"] == "PHASE1-HDT"
    )["id"]
    crash = client.post(
        f"{API}/crashes", headers=insp,
        json={"study_id": study_id, "state_code": "KS", "city": "Topeka", "county": "Shawnee",
              "crash_date": "2026-05-04", "num_fatalities": 1},
    )
    assert crash.status_code == 201, crash.text
    cid = crash.json()["id"]
    client.put(f"{API}/crashes/{cid}/scope", headers=analyst, json={"is_qualifying": True, "scope": "IN_SCOPE"})
    return cid


# --------------------------------------------------------------------------- history
def test_history_returns_all_versions_newest_first(client, auth):
    """Two edits of the same code yield >=2 versions, newest-first, one current,
    each carrying who/when, so consecutive values can be diffed in the UI."""
    analyst = auth(ANALYST_KS)
    cid = _fresh_ks_crash(client, auth)

    first = client.post(f"{API}/crashes/{cid}/attributes", headers=analyst,
                        json={"attribute_code": "C04", "value_text": "Salina"})
    assert first.status_code == 201, first.text
    second = client.post(f"{API}/crashes/{cid}/attributes", headers=analyst,
                         json={"attribute_code": "C04", "value_text": "Topeka"})
    assert second.status_code == 201, second.text

    resp = client.get(f"{API}/crashes/{cid}/attributes/C04/history", headers=analyst)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["code"] == "C04"
    versions = body["versions"]
    assert len(versions) >= 2

    # Newest-first: the most recent edit ("Topeka") is first and is the current row.
    assert versions[0]["value_text"] == "Topeka"
    assert versions[0]["is_current"] is True
    assert versions[1]["value_text"] == "Salina"
    assert versions[1]["is_current"] is False

    # Exactly one current row across the whole history.
    assert sum(1 for v in versions if v["is_current"]) == 1
    # Who/when recorded on every edited version.
    assert all(v["edited_by"] for v in versions)
    assert all(v["edited_at"] for v in versions)
    # The editor name is resolved for display ("by <name>").
    assert versions[0]["edited_by_name"]


def test_history_redacts_sensitive_for_unprivileged_reader(client, auth):
    """A reader who passes the endpoint gate but fails can_view_sensitivity sees
    redacted history for a SENSITIVE attribute, mirroring get_attributes."""
    analyst = auth(ANALYST_KS)
    scientist = auth(DATA_SCIENTIST)
    cid = _fresh_ks_crash(client, auth)

    # C25 'Alcohol involvement' is SENSITIVE (seeds/0003_study_attributes_rules.sql).
    set_resp = client.post(f"{API}/crashes/{cid}/attributes", headers=analyst,
                           json={"attribute_code": "C25", "value_text": "Yes"})
    assert set_resp.status_code == 201, set_resp.text

    resp = client.get(f"{API}/crashes/{cid}/attributes/C25/history", headers=scientist)
    assert resp.status_code == 200, resp.text
    versions = resp.json()["versions"]
    assert len(versions) >= 1
    assert all(v["redacted"] is True for v in versions)
    assert all(v["value_text"] is None for v in versions)

    # Sanity: a privileged reader (the analyst holds data_mgmt:edit -> PII perm)
    # sees the unredacted value, so the redaction above is the gate's doing.
    analyst_view = client.get(f"{API}/crashes/{cid}/attributes/C25/history", headers=analyst)
    assert analyst_view.status_code == 200, analyst_view.text
    av = analyst_view.json()["versions"]
    assert av[0]["redacted"] is False
    assert av[0]["value_text"] == "Yes"


def test_history_requires_read_aggregated_permission(client, auth):
    """Negative/authorization: a Public user lacks data_mgmt:read_aggregated, so
    history is forbidden (403) exactly as get_attributes is."""
    analyst = auth(ANALYST_KS)
    public = auth(PUBLIC)
    cid = _fresh_ks_crash(client, auth)
    client.post(f"{API}/crashes/{cid}/attributes", headers=analyst,
                json={"attribute_code": "C04", "value_text": "Salina"})

    resp = client.get(f"{API}/crashes/{cid}/attributes/C04/history", headers=public)
    assert resp.status_code == 403, resp.text


def test_history_unknown_attribute_code_404(client, auth):
    """An unresolvable attribute code returns 404 (mirrors set_attribute's lookup)."""
    analyst = auth(ANALYST_KS)
    cid = _fresh_ks_crash(client, auth)
    resp = client.get(f"{API}/crashes/{cid}/attributes/ZZZ999/history", headers=analyst)
    assert resp.status_code == 404, resp.text
