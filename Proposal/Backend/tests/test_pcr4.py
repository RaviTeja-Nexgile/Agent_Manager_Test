"""PCR-4 (§8.5): structured PCR ingestion path.

Verifies that the two ingestion paths (MCMIS round-trip vs. direct State
connection) are modelled as a structured enum captured on each police-crash-report
record — covering the happy path, the default, the invalid-enum (422) negative,
and the authorization-denied (403) negative. All run inside a rolled-back
transaction (see conftest)."""
from __future__ import annotations

from tests.conftest import ANALYST_KS, FEDERAL

API = "/api/v1"

# STATE_USER (KS-scoped): holds crash:read but NOT source_data:ingest, so it can
# see the crash yet is denied the PCR ingest — the sharp authorization case.
STATE_USER_KS = "tomasz.bialek@ccfp.gov"


def _study_id(client, headers) -> str:
    return next(
        s for s in client.get(f"{API}/studies", headers=headers).json() if s["code"] == "PHASE1-HDT"
    )["id"]


def _new_ks_crash(client, headers) -> str:
    """Create a fresh KS crash (rolled back after the test) and return its id."""
    resp = client.post(
        f"{API}/crashes",
        headers=headers,
        json={"study_id": _study_id(client, headers), "state_code": "KS"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def test_add_pcr_direct_state_path_echoed(client, auth):
    """A PCR created with ingestion_path=DIRECT_STATE returns 201 and echoes it."""
    analyst = auth(ANALYST_KS)
    cid = _new_ks_crash(client, analyst)

    resp = client.post(
        f"{API}/crashes/{cid}/police-crash-reports",
        headers=analyst,
        json={"ingestion_path": "DIRECT_STATE", "pcr_number": "KS-TEST-1"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["ingestion_path"] == "DIRECT_STATE"
    assert body["pcr_number"] == "KS-TEST-1"
    # The structured path is independent of the free-text repository name.
    assert "source_repository" in body

    # And it persists: the read-back (GET) reflects the stored path.
    got = client.get(f"{API}/crashes/{cid}/police-crash-reports/{body['id']}", headers=analyst)
    assert got.status_code == 200, got.text
    assert got.json()["ingestion_path"] == "DIRECT_STATE"


def test_add_pcr_defaults_to_mcmis_roundtrip(client, auth):
    """Omitting ingestion_path defaults to the MCMIS round-trip path."""
    analyst = auth(ANALYST_KS)
    cid = _new_ks_crash(client, analyst)

    resp = client.post(
        f"{API}/crashes/{cid}/police-crash-reports",
        headers=analyst,
        json={"pcr_number": "KS-TEST-2"},
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["ingestion_path"] == "MCMIS_ROUNDTRIP"


def test_add_pcr_mcmis_roundtrip_explicit(client, auth):
    """Explicitly passing MCMIS_ROUNDTRIP is accepted and echoed."""
    analyst = auth(ANALYST_KS)
    cid = _new_ks_crash(client, analyst)

    resp = client.post(
        f"{API}/crashes/{cid}/police-crash-reports",
        headers=analyst,
        json={"ingestion_path": "MCMIS_ROUNDTRIP", "pcr_number": "KS-TEST-3"},
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["ingestion_path"] == "MCMIS_ROUNDTRIP"


def test_add_pcr_invalid_path_is_422(client, auth):
    """An unknown ingestion_path value fails Pydantic validation (422)."""
    analyst = auth(ANALYST_KS)
    cid = _new_ks_crash(client, analyst)

    resp = client.post(
        f"{API}/crashes/{cid}/police-crash-reports",
        headers=analyst,
        json={"ingestion_path": "FAX", "pcr_number": "KS-TEST-4"},
    )
    assert resp.status_code == 422, resp.text


def test_add_pcr_requires_ingest_permission(client, auth):
    """Authorization: a user lacking source_data:ingest cannot add a PCR (403).

    STATE_USER can read the crash (crash:read) but is denied the ingest, and the
    FEDERAL user — lacking the permission entirely — is likewise denied. The
    existing authorization is preserved, never weakened."""
    analyst = auth(ANALYST_KS)
    cid = _new_ks_crash(client, analyst)

    payload = {"ingestion_path": "DIRECT_STATE", "pcr_number": "KS-NO-AUTH"}

    denied = client.post(
        f"{API}/crashes/{cid}/police-crash-reports",
        headers=auth(STATE_USER_KS),
        json=payload,
    )
    assert denied.status_code == 403, denied.text

    denied_fed = client.post(
        f"{API}/crashes/{cid}/police-crash-reports",
        headers=auth(FEDERAL),
        json=payload,
    )
    assert denied_fed.status_code == 403, denied_fed.text

    # The denials created nothing: the analyst still sees zero PCRs.
    listing = client.get(f"{API}/crashes/{cid}/police-crash-reports", headers=analyst)
    assert listing.status_code == 200, listing.text
    assert listing.json() == []
