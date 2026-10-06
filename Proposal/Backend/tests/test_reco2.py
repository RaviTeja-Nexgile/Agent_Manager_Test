"""RECO-2: parse + validate the CCFP Output-File-Comment code from the ELD CSV.

Per §8.7 an uploaded ELD output file is linked to its crash using the unique CCFP
code carried in the file's output-file comment. These tests verify the parser
extracts that code FROM THE FILE (no longer fabricated from the crash identifier)
and that DQ_ELD_LINKED is a real check:

  * positive  — a CSV whose comment carries the crash's exact CCFP code parses to
                that code and DQ_ELD_LINKED == PASS;
  * negative  — a CSV carrying a different code (or none) parses to that
                wrong/None value and DQ_ELD_LINKED is NOT PASS (the old tautology
                is gone);
  * authorization — a user without `eld:upload` (public.demo) is 403 on upload.

All tests run inside the rolled-back `db` session fixture from conftest.py; setup
rows are committed first (in test mode commit() is a SAVEPOINT release) so the
worker's own commit/rollback nests inside the test transaction and the real
database is never mutated. Robust to seed drift: every fixture row is created in
the transaction (only the PHASE1-HDT study is assumed seeded).
"""
from __future__ import annotations

import io
import uuid

from sqlalchemy import select

from app import workers
from app.core import storage
from app.models import Crash, Document, EldFile, Study
from tests.conftest import INSPECTOR_KS, PUBLIC


API = "/api/v1"


def _make_crash(db) -> Crash:
    study = db.scalar(select(Study).where(Study.code == "PHASE1-HDT"))
    assert study is not None, "PHASE1-HDT study must be seeded"
    crash = Crash(
        ccfp_identifier=f"CCFP-TEST-{uuid.uuid4().hex[:12]}",
        study_id=study.id,
        state_code="KS",
        num_fatalities=1,
    )
    db.add(crash)
    db.flush()
    return crash


def _make_eld_file(db, crash: Crash, content: bytes) -> EldFile:
    storage_uri, size = storage.put_object(content, key_prefix="test-reco2", file_name="eld.csv")
    doc = Document(
        crash_id=crash.id, doc_type="ELD_CSV", file_name="eld.csv",
        mime_type="text/csv", storage_uri=storage_uri, size_bytes=size,
    )
    db.add(doc)
    db.flush()
    ef = EldFile(
        crash_id=crash.id, file_name="eld.csv", document_id=doc.id,
        # Mirror the upload path post-RECO-2: the column starts None; the parser fills it.
        ccfp_code_in_file=None, upload_status="UPLOADED",
    )
    db.add(ef)
    db.flush()
    return ef


def _eld_linked_status(db, crash_id: uuid.UUID) -> str:
    result = workers.evaluate_quality(crash_id, db=db)
    for r in result["results"]:
        if r["rule"] == "DQ_ELD_LINKED":
            return r["status"]
    raise AssertionError("DQ_ELD_LINKED rule not found in QC results")


# --------------------------------------------------------------------------- positive: leading comment line
def test_parse_extracts_code_from_comment_line_and_links(db):
    crash = _make_crash(db)
    code = crash.ccfp_identifier
    csv_bytes = (
        f"# Output File Comment: {code}\n"
        "sequence,timestamp,duty,location\n"
        "1,2026-05-01 08:00:00,driving,Topeka KS\n"
        "2,2026-05-01 09:00:00,on_duty,Lawrence KS\n"
    ).encode("utf-8")
    ef = _make_eld_file(db, crash, csv_bytes)
    db.commit()

    result = workers.parse_eld_file(ef.id, db=db)
    # Existing duty-status/event parsing stays intact (non-regression): the
    # comment line is peeled off so the real header still reaches DictReader.
    assert result["status"] == "PARSED"
    assert result["event_count"] == 2

    db.refresh(ef)
    assert ef.ccfp_code_in_file == code

    # DQ_ELD_LINKED is now a genuine PASS — the parsed code matches the crash.
    assert _eld_linked_status(db, crash.id) == "PASS"


# --------------------------------------------------------------------------- positive: dedicated column
def test_parse_extracts_code_from_comment_column(db):
    crash = _make_crash(db)
    code = crash.ccfp_identifier
    csv_bytes = (
        "sequence,duty,output_file_comment\n"
        f"1,driving,{code}\n"
    ).encode("utf-8")
    ef = _make_eld_file(db, crash, csv_bytes)
    db.commit()

    result = workers.parse_eld_file(ef.id, db=db)
    assert result["status"] == "PARSED"
    # The header naming a comment column is NOT mistaken for a comment line, so
    # the data row still parses as an event (non-regression with the column shape).
    assert result["event_count"] == 1
    db.refresh(ef)
    assert ef.ccfp_code_in_file == code
    assert _eld_linked_status(db, crash.id) == "PASS"


# --------------------------------------------------------------------------- negative: wrong code
def test_mismatched_code_is_not_linked(db):
    crash = _make_crash(db)
    wrong = "CCFP-2099-ZZ-999999"
    assert wrong != crash.ccfp_identifier
    csv_bytes = (
        f"# Output File Comment: {wrong}\n"
        "sequence,duty,location\n"
        "1,driving,Topeka KS\n"
    ).encode("utf-8")
    ef = _make_eld_file(db, crash, csv_bytes)
    db.commit()

    workers.parse_eld_file(ef.id, db=db)
    db.refresh(ef)
    # The parser stores the wrong code verbatim (no silent "link").
    assert ef.ccfp_code_in_file == wrong
    # The old tautology is gone: a present-but-unmatched file is NOT a PASS.
    assert _eld_linked_status(db, crash.id) != "PASS"


# --------------------------------------------------------------------------- negative: no code
def test_no_code_degrades_gracefully(db):
    crash = _make_crash(db)
    # No comment line, no comment column -> nothing to parse. Must not crash.
    csv_bytes = (
        "sequence,duty,location\n"
        "1,driving,Topeka KS\n"
    ).encode("utf-8")
    ef = _make_eld_file(db, crash, csv_bytes)
    db.commit()

    result = workers.parse_eld_file(ef.id, db=db)
    assert result["status"] == "PARSED"
    db.refresh(ef)
    assert ef.ccfp_code_in_file is None
    assert _eld_linked_status(db, crash.id) != "PASS"


# --------------------------------------------------------------------------- authorization on the upload endpoint
def test_upload_requires_eld_permission(client, auth, db):
    insp = auth(INSPECTOR_KS)
    study_id = next(
        s for s in client.get(f"{API}/studies", headers=insp).json() if s["code"] == "PHASE1-HDT"
    )["id"]
    crash = client.post(
        f"{API}/crashes", headers=insp,
        json={"study_id": study_id, "state_code": "KS", "crash_date": "2026-05-01", "num_fatalities": 1},
    ).json()
    cid = crash["id"]

    csv_bytes = (
        f"# Output File Comment: {crash['ccfp_identifier']}\n"
        "sequence,duty\n1,driving\n"
    ).encode("utf-8")

    # Public user has no eld:upload -> 403.
    pub = auth(PUBLIC)
    denied = client.post(
        f"{API}/crashes/{cid}/eld-files", headers=pub,
        files={"file": ("eld.csv", io.BytesIO(csv_bytes), "text/csv")},
    )
    assert denied.status_code == 403, denied.text

    # The inspector (KS, holds eld:upload) succeeds and the file is stored with
    # ccfp_code_in_file=None at upload (the parser fills it in the background).
    ok = client.post(
        f"{API}/crashes/{cid}/eld-files", headers=insp,
        files={"file": ("eld.csv", io.BytesIO(csv_bytes), "text/csv")},
    )
    assert ok.status_code == 201, ok.text
    assert ok.json()["ccfp_code_in_file"] is None
