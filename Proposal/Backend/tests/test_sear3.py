"""SEAR-3 — configuration-driven searchable entity/column set.

Verifies that the cross-entity search resolves *which* entities/columns are
searchable from per-study ``study_parameters`` config against a code-owned
whitelist, while authorization (State scope, PII clearance) is preserved
regardless of config.

Each test runs inside the shared rolled-back transaction (conftest), so the
``study_parameters`` rows inserted here never reach the real database.
"""
from __future__ import annotations

from sqlalchemy import select

from app.models import Crash, StudyParameter
from tests.conftest import ANALYST_KS, PUBLIC

API = "/api/v1"
SEARCH_PARAM_KEY = "searchable_entities"


def _phase1_study_id(db) -> str:
    return str(db.scalar(select(Crash.study_id).where(Crash.ccfp_identifier == "CCFP-2026-KS-000101")))


def _set_config(db, study_id, value: dict) -> None:
    """Insert/replace the searchable_entities config for a study, then flush so
    the request (sharing this session) sees it."""
    existing = db.scalar(
        select(StudyParameter).where(
            StudyParameter.study_id == study_id,
            StudyParameter.param_key == SEARCH_PARAM_KEY,
        )
    )
    if existing is not None:
        existing.param_value = value
    else:
        db.add(StudyParameter(study_id=study_id, param_key=SEARCH_PARAM_KEY, param_value=value))
    db.flush()


# --------------------------------------------------------------------------- parity (default / no config)
def test_search_default_config_still_returns_crash(client, auth):
    """(a) With no config, a crash-id query still returns a crash hit (parity
    with the original hardcoded behaviour)."""
    res = client.get(f"{API}/search?q=CCFP-2026-KS", headers=auth(ANALYST_KS)).json()
    assert any(h["type"] == "crash" for h in res["hits"])


# --------------------------------------------------------------------------- config restricts the set
def test_config_limited_to_reports_drops_crashes(client, auth, db):
    """(b) Limiting searchable_entities to ['reports'] removes crash hits while
    a report query still works."""
    study_id = _phase1_study_id(db)
    _set_config(db, study_id, {"entities": ["reports"]})

    headers = auth(ANALYST_KS)
    crash_res = client.get(f"{API}/search?q=CCFP-2026-KS", headers=headers).json()
    assert not any(h["type"] == "crash" for h in crash_res["hits"]), crash_res

    report_res = client.get(f"{API}/search?q=CCFP", headers=headers).json()
    assert any(h["type"] == "report" for h in report_res["hits"]), report_res


# --------------------------------------------------------------------------- unknown keys ignored
def test_unknown_entity_key_in_config_is_ignored(client, auth, db):
    """(c) An unknown entity key in config is silently dropped: no error, no
    extra hits, and the valid entities still resolve."""
    study_id = _phase1_study_id(db)
    _set_config(db, study_id, {"entities": ["crashes", "totally_made_up_entity"]})

    res = client.get(f"{API}/search?q=CCFP-2026-KS", headers=auth(ANALYST_KS))
    assert res.status_code == 200, res.text
    body = res.json()
    assert any(h["type"] == "crash" for h in body["hits"])
    # The bogus entity produces no hit type of its own.
    assert all(h["type"] in {"crash", "person", "carrier", "report", "document"} for h in body["hits"])


def test_unknown_column_code_is_ignored(client, auth, db):
    """A column-restricted config naming an unknown column for an entity drops
    only that column; a query against an *enabled* column still matches, and a
    query that would only match the dropped/whitelisted-out column does not."""
    study_id = _phase1_study_id(db)
    # Enable crashes but only via 'ccfp_identifier' (drop city/local_report_number);
    # also list a bogus column that must be ignored.
    _set_config(db, study_id, {"entities": {"crashes": ["ccfp_identifier", "evil_column"]}})

    headers = auth(ANALYST_KS)
    by_id = client.get(f"{API}/search?q=CCFP-2026-KS", headers=headers).json()
    assert any(h["type"] == "crash" for h in by_id["hits"]), by_id

    # 'Topeka' is a city of a KS crash; with city disabled it must NOT match a crash.
    by_city = client.get(f"{API}/search?q=Topeka", headers=headers).json()
    assert not any(h["type"] == "crash" for h in by_city["hits"]), by_city


# --------------------------------------------------------------------------- types filter still honored
def test_types_filter_intersects_config(client, auth):
    """The optional ?types filter still intersects the configured/enabled set."""
    res = client.get(f"{API}/search?q=CCFP-2026-KS&types=reports", headers=auth(ANALYST_KS)).json()
    assert not any(h["type"] == "crash" for h in res["hits"]), res


# --------------------------------------------------------------------------- authorization is NOT bypassed by config
def test_state_scope_preserved_even_when_crashes_enabled(client, auth, db):
    """Config selects *what* is searched, never *who may see it*: a KS analyst
    still cannot see a TX crash even with crashes explicitly enabled."""
    study_id = _phase1_study_id(db)
    _set_config(db, study_id, {"entities": ["crashes", "persons", "carriers", "reports", "documents"]})

    res = client.get(f"{API}/search?q=CCFP-2026-TX", headers=auth(ANALYST_KS)).json()
    assert not any(h["type"] == "crash" for h in res["hits"]), res


def test_unauthenticated_search_is_401(client):
    """Negative/authorization: search requires auth regardless of config."""
    assert client.get(f"{API}/search?q=test").status_code == 401


def test_public_user_forbidden_from_search(client, auth):
    """A Public user lacks crash:read/report:read and is rejected (403), so
    config never grants search access on its own."""
    assert client.get(f"{API}/search?q=test", headers=auth(PUBLIC)).status_code == 403
