"""SEAR-2: PostgreSQL-native full-text + trigram cross-entity search.

These tests exercise ``GET /api/v1/search`` after the ILIKE-only matcher was
replaced with ``to_tsvector``/``websearch_to_tsquery`` full-text, ``pg_trgm``
fuzzy matching, and an ILIKE substring safety-net (so exact identifier queries
such as ``CCFP-2026-KS`` keep working), with broadened searched columns and a
new searchable ``documents.content_text`` column.

Everything runs inside the shared rolled-back transaction (see conftest), so the
live development database is never mutated. Authorization (State scope, PII
clearance, document sensitivity) must be preserved — the negative cases assert
that explicitly.
"""
from __future__ import annotations

import uuid

from app.models import Document
from tests.conftest import (
    ANALYST_KS,
    ANALYST_TX,
    FEDERAL,
    INSPECTOR_KS,
)

API = "/api/v1"

# Seeded fixtures (synthetic — Backend/database/seeds/0004_demo_crashes.sql):
#   crash CCFP-2026-KS-000101 is KS-scoped; it owns the SENSITIVE KS document
#   recon_KS_000101.pdf and the KS driver "Wendell Pruitt". The TX crash owns
#   the TX driver "Darnell Whitaker".
KS_DOC_FILENAME_STEM = "recon"
KS_DOC_FULL = "recon_KS_000101.pdf"
KS_PERSON_NAME = "Wendell Pruitt"
TX_PERSON_NAME = "Darnell Whitaker"
KS_DOCUMENT_ID = uuid.UUID("d0c00001-0000-0000-0000-000000000001")


def _search(client, auth, email, q, types=None):
    params = {"q": q}
    if types is not None:
        params["types"] = types
    resp = client.get(f"{API}/search", headers=auth(email), params=params)
    assert resp.status_code == 200, resp.text
    return resp.json()


# --------------------------------------------------------------------------- parity
def test_exact_identifier_still_matches(client, auth):
    """Regression parity with today: exact CCFP-id substring still returns the crash.

    This is the safety-net case (ILIKE/trigram) — ``websearch_to_tsquery`` alone
    would not reliably tokenize the hyphenated identifier.
    """
    res = _search(client, auth, ANALYST_KS, "CCFP-2026-KS")
    assert any(h["type"] == "crash" for h in res["hits"])


def test_partial_identifier_matches_via_trigram(client, auth):
    # A partial / fuzzy id token still resolves through the trigram fallback.
    res = _search(client, auth, ANALYST_KS, "2026-KS")
    assert any(h["type"] == "crash" for h in res["hits"])


# --------------------------------------------------------------------------- broadened content
def test_document_filename_is_searchable(client, auth):
    # A KS analyst (KS scope, can view the SENSITIVE KS doc) finds it by name token.
    res = _search(client, auth, ANALYST_KS, KS_DOC_FILENAME_STEM)
    docs = [h for h in res["hits"] if h["type"] == "document"]
    assert any(h["label"] == KS_DOC_FULL for h in docs)


def test_document_content_text_is_searchable(client, auth, db):
    """Content search: a word stored only in ``content_text`` finds the document.

    The binary seed docs have NULL content; this writes plain text (as the
    upload/edit path would) and confirms full-text content matching works. The
    write lives in the rolled-back test transaction.
    """
    token = "exemplarnarrativetoken"
    doc = db.get(Document, KS_DOCUMENT_ID)
    assert doc is not None
    doc.content_text = f"Reconstruction narrative mentioning {token} for the rear-end event."
    db.flush()

    res = _search(client, auth, ANALYST_KS, token)
    docs = [h for h in res["hits"] if h["type"] == "document"]
    assert any(str(h["id"]) == str(KS_DOCUMENT_ID) for h in docs), res["hits"]


def test_report_description_is_searchable(client, auth):
    # "dashboard" appears in a seeded report name + description — a column that
    # was NOT searchable before SEAR-2 broadened the report columns.
    res = _search(client, auth, ANALYST_KS, "dashboard")
    assert any(h["type"] == "report" for h in res["hits"])


def test_person_name_searchable_for_pii_cleared_user(client, auth):
    # KS analyst has PII clearance and KS scope -> finds the KS driver by name.
    res = _search(client, auth, ANALYST_KS, KS_PERSON_NAME)
    assert any(h["type"] == "person" and h["label"] == KS_PERSON_NAME for h in res["hits"])


# --------------------------------------------------------------------------- authorization (negative)
def test_state_scope_enforced_for_documents(client, auth):
    """A TX analyst must NOT see the KS document even by exact name (State scope)."""
    res = _search(client, auth, ANALYST_TX, KS_DOC_FULL)
    assert not any(
        h["type"] == "document" and h["label"] == KS_DOC_FULL for h in res["hits"]
    ), res["hits"]


def test_state_scope_enforced_for_crashes(client, auth):
    # KS analyst sees only KS crash hits; never a TX identifier.
    res = _search(client, auth, ANALYST_KS, "CCFP-2026", types="crashes")
    assert res["hits"]
    assert all("-KS-" in h["label"] for h in res["hits"]), res["hits"]


def test_state_scope_enforced_for_persons(client, auth):
    """A KS (PII-cleared) analyst must not surface the TX driver (out of scope)."""
    res = _search(client, auth, ANALYST_KS, TX_PERSON_NAME)
    assert not any(h["type"] == "person" for h in res["hits"]), res["hits"]


def test_pii_clearance_required_for_person_hits(client, auth):
    """A user without PII clearance never receives person hits.

    The Federal User has ``report:read`` (so the search endpoint admits them) but
    no PII permission and no ``crash:read``; the person branch is gated by
    ``can_view_sensitivity('PII')`` and must stay empty regardless of query.
    """
    res = _search(client, auth, FEDERAL, KS_PERSON_NAME)
    assert not any(h["type"] == "person" for h in res["hits"]), res["hits"]


def test_no_crash_read_yields_no_crash_or_document_hits(client, auth):
    # Federal User lacks crash:read -> crashes, carriers, documents are skipped;
    # only report:read-gated entities can return.
    res = _search(client, auth, FEDERAL, KS_DOC_FILENAME_STEM)
    assert not any(h["type"] in {"crash", "carrier", "document"} for h in res["hits"]), res["hits"]


# --------------------------------------------------------------------------- endpoint guards
def test_search_requires_authentication(client):
    assert client.get(f"{API}/search", params={"q": "test"}).status_code == 401


def test_short_query_rejected(client, auth):
    # min_length=2 is preserved on q.
    assert client.get(f"{API}/search", headers=auth(ANALYST_KS), params={"q": "x"}).status_code == 422


def test_carrier_broadened_columns(client, auth):
    """Carrier search now also covers make / us_dot_number (broadened columns).

    The inspector created CMV with make 'Freightliner' in the lifecycle seed; we
    assert the registry exposes these columns so a DOT-number / make query can
    match — without depending on a specific seeded carrier string.
    """
    from app.features.search import SEARCH_REGISTRY

    carrier_cols = set(SEARCH_REGISTRY["carriers"].columns)
    assert {"carrier_name", "make", "us_dot_number"} <= carrier_cols
    crash_cols = set(SEARCH_REGISTRY["crashes"].columns)
    assert {"county", "street_highway"} <= crash_cols
    assert "content_text" in set(SEARCH_REGISTRY["documents"].columns)
    assert "description" in set(SEARCH_REGISTRY["reports"].columns)
