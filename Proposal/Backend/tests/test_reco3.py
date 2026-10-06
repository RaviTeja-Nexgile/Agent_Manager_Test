"""RECO-3: the reconstruction "upload" endpoint accepts an optional file. When a
file is supplied it is malware-scanned, stored on local disk, persisted as a
`Document`, and linked via `reconstruction_reports.document_id` (§8.6, §12.5).
The metadata-only path (no file) must keep working so existing callers/tests do
not regress.

All tests run inside a rolled-back transaction (see conftest)."""
from __future__ import annotations

from tests.conftest import ANALYST_KS, INSPECTOR_KS, PUBLIC

API = "/api/v1"

# Minimal EICAR test-signature payload — `storage.scan_for_malware` flags this as
# INFECTED (matches the mock AV gate in app/core/storage.py).
EICAR = b"X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"
PDF_BYTES = b"%PDF-1.4 reconstruction narrative\n"


def _study_id(client, headers) -> str:
    return next(s for s in client.get(f"{API}/studies", headers=headers).json() if s["code"] == "PHASE1-HDT")["id"]


def _make_crash(client, auth) -> str:
    """Create a KS crash as the inspector; return its id."""
    insp = auth(INSPECTOR_KS)
    study_id = _study_id(client, insp)
    return client.post(
        f"{API}/crashes", headers=insp, json={"study_id": study_id, "state_code": "KS"},
    ).json()["id"]


def test_add_recon_with_file_stores_document_and_links_it(client, auth):
    """Uploading a file creates the recon row with a non-null document_id, and the
    stored file shows up in the crash's documents."""
    cid = _make_crash(client, auth)
    analyst = auth(ANALYST_KS)

    resp = client.post(
        f"{API}/crashes/{cid}/reconstruction-reports", headers=analyst,
        data={"title": "Recon A", "received_date": "2026-05-02"},
        files={"file": ("recon.pdf", PDF_BYTES, "application/pdf")},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["title"] == "Recon A"
    doc_id = body["document_id"]
    assert doc_id is not None

    # The recon row persists the document_id.
    listed = client.get(f"{API}/crashes/{cid}/reconstruction-reports", headers=analyst).json()
    assert any(r["id"] == body["id"] and r["document_id"] == doc_id for r in listed)

    # The stored file is registered as a crash document.
    docs = client.get(f"{API}/crashes/{cid}/documents", headers=analyst).json()
    assert any(d["id"] == doc_id and d["file_name"] == "recon.pdf" for d in docs)

    # The linked document is fetchable / downloadable via the existing document routes.
    dl = client.get(f"{API}/documents/{doc_id}/download", headers=analyst)
    assert dl.status_code == 200, dl.text
    assert dl.json()["signed_url"]


def test_add_recon_without_file_still_works(client, auth):
    """Metadata-only path: no file -> 201 with a null document_id (no regression)."""
    cid = _make_crash(client, auth)
    analyst = auth(ANALYST_KS)

    resp = client.post(
        f"{API}/crashes/{cid}/reconstruction-reports", headers=analyst,
        data={"title": "Stub recon", "received_date": "2026-05-03"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["title"] == "Stub recon"
    assert body["document_id"] is None


def test_add_recon_infected_file_rejected(client, auth):
    """An EICAR-signature payload fails the malware scan -> 400, no row created."""
    cid = _make_crash(client, auth)
    analyst = auth(ANALYST_KS)

    resp = client.post(
        f"{API}/crashes/{cid}/reconstruction-reports", headers=analyst,
        data={"title": "Bad recon"},
        files={"file": ("evil.pdf", EICAR, "application/pdf")},
    )
    assert resp.status_code == 400, resp.text
    assert "malware" in resp.json()["detail"].lower()

    # Nothing was persisted for this crash.
    listed = client.get(f"{API}/crashes/{cid}/reconstruction-reports", headers=analyst).json()
    assert listed == []


def test_add_recon_forbidden_for_public_user(client, auth):
    """PUBLIC lacks recon:upload -> 403 (authorization case)."""
    cid = _make_crash(client, auth)
    resp = client.post(
        f"{API}/crashes/{cid}/reconstruction-reports", headers=auth(PUBLIC),
        data={"title": "Nope"},
        files={"file": ("recon.pdf", PDF_BYTES, "application/pdf")},
    )
    assert resp.status_code == 403, resp.text


def test_add_recon_upload_writes_audit_log(client, auth):
    """The upload writes an UPLOAD audit (document) plus the CREATE recon audit, so
    the crash timeline reflects the attachment (§ audit requirements)."""
    cid = _make_crash(client, auth)
    analyst = auth(ANALYST_KS)

    resp = client.post(
        f"{API}/crashes/{cid}/reconstruction-reports", headers=analyst,
        data={"title": "Recon audited"},
        files={"file": ("recon.pdf", PDF_BYTES, "application/pdf")},
    )
    assert resp.status_code == 201, resp.text

    timeline = client.get(f"{API}/crashes/{cid}/timeline", headers=analyst).json()
    actions = {e["action"] for e in timeline}
    assert "UPLOAD" in actions
    assert "CREATE" in actions
