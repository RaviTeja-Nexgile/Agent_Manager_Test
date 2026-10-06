"""Unit tests for the ELD CSV parser worker (documentation §8.7).

Covers RECO-4 (latitude/longitude populated from the CSV) and RECO-6 (parse
failures / unreadable-or-empty objects set upload_status = FAILED instead of
masquerading as a clean PARSED result). The full BRD Appendix E extraction —
the sectioned ELD output file, diagnostics, limits and authorization — is
covered in ``test_eld_extraction.py``.

All tests run against the rolled-back `db` session fixture from conftest.py.
Setup rows are committed first (in test mode commit() is a SAVEPOINT release),
so the worker's own commit/rollback stays inside the test transaction and the
real database is never mutated.
"""
from __future__ import annotations

import uuid

from sqlalchemy import select

from app import workers
from app.core import storage
from app.models import Crash, Document, EldEvent, EldFile, Study


def _make_crash(db) -> Crash:
    """Create a throwaway in-transaction crash bound to the Phase 1 study."""
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


def _make_eld_file(db, crash: Crash, *, content: bytes | None) -> EldFile:
    """Create an EldFile; when `content` is given, back it with a stored Document."""
    document_id = None
    if content is not None:
        storage_uri, size = storage.put_object(
            content, key_prefix="test-eld", file_name="eld.csv"
        )
        doc = Document(
            crash_id=crash.id,
            doc_type="ELD_CSV",
            file_name="eld.csv",
            mime_type="text/csv",
            storage_uri=storage_uri,
            size_bytes=size,
        )
        db.add(doc)
        db.flush()
        document_id = doc.id
    ef = EldFile(
        crash_id=crash.id,
        file_name="eld.csv",
        document_id=document_id,
        upload_status="UPLOADED",
    )
    db.add(ef)
    db.flush()
    return ef


# --------------------------------------------------------------------------- RECO-4
def test_parse_populates_latitude_longitude(db):
    crash = _make_crash(db)
    csv_bytes = (
        "sequence,timestamp,duty,location,latitude,longitude\n"
        "1,2026-05-01 08:00:00,driving,Topeka KS,39.048191,-95.677956\n"
        "2,2026-05-01 09:00:00,on_duty,Lawrence KS,,\n"
    ).encode("utf-8")
    ef = _make_eld_file(db, crash, content=csv_bytes)
    # Commit setup so the worker's commit/rollback nests beneath it.
    db.commit()

    result = workers.parse_eld_file(ef.id, db=db)
    assert result["status"] == "PARSED"
    assert result["event_count"] == 2

    events = list(
        db.scalars(
            select(EldEvent).where(EldEvent.eld_file_id == ef.id).order_by(EldEvent.event_sequence)
        )
    )
    assert len(events) == 2
    # Row 1 carried coordinates -> populated as floats.
    assert float(events[0].latitude) == 39.048191
    assert float(events[0].longitude) == -95.677956
    # Row 2 had blank coordinates -> left NULL.
    assert events[1].latitude is None
    assert events[1].longitude is None


def test_parse_accepts_lat_lng_header_aliases(db):
    crash = _make_crash(db)
    csv_bytes = (
        "sequence,duty,lat,lng\n"
        "1,driving,40.000000,-100.000000\n"
    ).encode("utf-8")
    ef = _make_eld_file(db, crash, content=csv_bytes)
    db.commit()

    result = workers.parse_eld_file(ef.id, db=db)
    assert result["status"] == "PARSED"
    event = db.scalar(select(EldEvent).where(EldEvent.eld_file_id == ef.id))
    assert float(event.latitude) == 40.0
    assert float(event.longitude) == -100.0


# --------------------------------------------------------------------------- RECO-6
def test_unreadable_object_sets_failed(db):
    """A Document whose backing object does not exist on disk -> FAILED."""
    crash = _make_crash(db)
    doc = Document(
        crash_id=crash.id,
        doc_type="ELD_CSV",
        file_name="missing.csv",
        mime_type="text/csv",
        storage_uri=f"file://test-eld/{uuid.uuid4().hex}_missing.csv",  # never written
        size_bytes=0,
    )
    db.add(doc)
    db.flush()
    ef = EldFile(
        crash_id=crash.id,
        file_name="missing.csv",
        document_id=doc.id,
        upload_status="UPLOADED",
    )
    db.add(ef)
    db.flush()
    db.commit()

    result = workers.parse_eld_file(ef.id, db=db)
    assert result["status"] == "FAILED"

    db.refresh(ef)
    assert ef.upload_status == "FAILED"
    assert ef.event_count == 0
    assert ef.parsed_at is not None


def test_empty_content_sets_failed(db):
    """An ELD file with no extractable bytes -> FAILED, not a clean PARSED/0."""
    crash = _make_crash(db)
    ef = _make_eld_file(db, crash, content=b"")
    db.commit()

    result = workers.parse_eld_file(ef.id, db=db)
    assert result["status"] == "FAILED"

    db.refresh(ef)
    assert ef.upload_status == "FAILED"
    assert ef.event_count == 0


def test_header_only_csv_fails_with_a_reason(db):
    """A readable CSV with a header but zero data rows is FAILED, not a clean PARSED.

    This assertion is the inverse of what it used to be, deliberately. The point
    of an ELD upload is to extract hours-of-service data; a file that yields zero
    events has not done that. Reporting it as `PARSED` with `event_count = 0`
    told the inspector nothing was wrong while nothing had been extracted —
    exactly the silent failure BRD Appendix E work removes. The file is now
    `FAILED` with a code and a message naming the fix.
    """
    crash = _make_crash(db)
    ef = _make_eld_file(db, crash, content=b"sequence,duty,latitude,longitude\n")
    db.commit()

    result = workers.parse_eld_file(ef.id, db=db)
    assert result["status"] == "FAILED"
    assert result["error_code"] == "ELD_NO_DATA_ROWS"
    assert result["event_count"] == 0

    db.refresh(ef)
    assert ef.upload_status == "FAILED"
    assert ef.event_count == 0
    assert ef.error_code == "ELD_NO_DATA_ROWS"
    assert "no data rows" in ef.error_message
    assert db.scalar(select(EldEvent).where(EldEvent.eld_file_id == ef.id)) is None
