"""ELD extraction end-to-end (BRD Jan-2026 Appendix E, documentation §8.7).

Appendix E asks for two things: that the MCSAP CMV Inspector and CCFP Project
Team analysts can upload ELD output files in CSV format to the associated crash
record, and that the system can extract the data in them so it can be analyzed.
The defect these tests close is that extraction was partial and silent — the
parser understood only a simplified flat CSV, so a REAL ELD/eRODS output file
(the sectioned layout of 49 CFR 395 Appendix A to Subpart B) either produced
rows of NULLs or a bare FAILED with no stored reason.

Coverage:

  * realistic     — a full sectioned output file: header segment, User/CMV
                    lists, event list, annotations, certifications, malfunction
                    and diagnostic events, login/logout, engine power activity,
                    unidentified-driver records, end-of-file check value;
  * completeness  — driver/carrier/VIN/time-zone extracted, duty status derived
                    from the event type/code pair, inactive records excluded
                    from the HOS totals, annotations attached, CCFP code linked;
  * never silent  — empty / binary / oversize / non-tabular uploads refused at
                    the request with an actionable message; unmappable, no-row,
                    unreadable-object and truncated files end in a terminal
                    status carrying error_code, error_message, issue rows and a
                    notification;
  * edge cases    — encodings (UTF-8 BOM, UTF-16, CP1252), duplicate sequence
                    numbers, ragged rows, malformed quoting, bad timestamps and
                    numbers, coordinate sentinels, out-of-range values, blank
                    rows, a partial/truncated file, and a large file;
  * limits        — the event cap and the time budget are reported as ERRORs;
  * authorization — every role holding `eld:upload` (MCSAP Inspector, State CMV
                    Analyst, CCFP Project Team, System Administrator) can upload
                    and re-run extraction; roles without it get 403, and State
                    scope is still enforced;
  * regression    — the flat-CSV path, the RECO-5 provider mapping and the
                    RECO-2 DQ_ELD_LINKED check behave exactly as before.

All tests run inside the rolled-back ``db`` fixture from conftest.py; fixture
rows are committed first (commit() is a SAVEPOINT release in test mode) so the
worker's own commit/rollback nests inside the test transaction and the live
development database is never mutated.
"""
from __future__ import annotations

import datetime as dt
import io
import uuid

import pytest
from sqlalchemy import func, select

from app import workers
from app.core import storage
from app.core.security import create_access_token
from app.models import (
    Crash,
    Document,
    EldDutyCodeMapping,
    EldEvent,
    EldFieldMapping,
    EldFile,
    EldParseIssue,
    Notification,
    Study,
    User,
)
from app.workers import eld_format
from app.workers.eld_format import EldErrorCode
from tests.conftest import (
    ANALYST_KS,
    ANALYST_TX,
    INSPECTOR_KS,
    PROJECT,
    PUBLIC,
    SYSADMIN,
)

API = "/api/v1"


# =========================================================================== fixtures
def _headers(db, email: str) -> dict[str, str]:
    """Bearer header for a seeded user, minted without the login round-trip.

    The token is exactly what ``POST /auth/login`` returns — same
    ``create_access_token``, same claims — so every authorization path under test
    behaves identically. What it skips is the login endpoint's
    ``UPDATE users SET last_login_at``, which takes a row lock held until the
    test's transaction rolls back. On a SHARED development database that lock is
    the single busiest contention point: with several clients running suites at
    once, each login-based test waits on every other client's. Minting here keeps
    these ELD tests independent of that. ``test_upload_through_the_real_login_flow``
    still covers the genuine login round-trip for the ELD upload route.
    """
    user = db.scalar(select(User).where(User.email == email))
    assert user is not None, f"seeded user {email} must exist"
    return {"Authorization": f"Bearer {create_access_token(user)}"}


def _study(db) -> Study:
    study = db.scalar(select(Study).where(Study.code == "PHASE1-HDT"))
    assert study is not None, "PHASE1-HDT study must be seeded"
    return study


def _make_crash(db, state_code: str = "KS") -> Crash:
    crash = Crash(
        ccfp_identifier=f"CCFP-TEST-{uuid.uuid4().hex[:12]}",
        study_id=_study(db).id,
        state_code=state_code,
        num_fatalities=1,
    )
    db.add(crash)
    db.flush()
    return crash


def _make_eld_file(
    db, crash: Crash, content: bytes, *, provider: str | None = None,
    file_name: str = "eld.csv", attach_document: bool = True,
) -> EldFile:
    """Create an EldFile backed by a stored object, mirroring the upload path."""
    document_id = None
    if attach_document:
        uri, size = storage.put_object(content, key_prefix="test-eld", file_name=file_name)
        doc = Document(
            crash_id=crash.id, doc_type="ELD_CSV", file_name=file_name,
            mime_type="text/csv", storage_uri=uri, size_bytes=size,
        )
        db.add(doc)
        db.flush()
        document_id = doc.id
    ef = EldFile(
        crash_id=crash.id, file_name=file_name, document_id=document_id,
        provider=provider, upload_status="UPLOADED",
    )
    db.add(ef)
    db.flush()
    return ef


def _events(db, eld_file_id: uuid.UUID) -> list[EldEvent]:
    return list(
        db.scalars(
            select(EldEvent)
            .where(EldEvent.eld_file_id == eld_file_id)
            .order_by(EldEvent.line_number, EldEvent.event_sequence)
        )
    )


def _issues(db, eld_file_id: uuid.UUID) -> list[EldParseIssue]:
    return list(db.scalars(select(EldParseIssue).where(EldParseIssue.eld_file_id == eld_file_id)))


def _issue_codes(db, eld_file_id: uuid.UUID) -> set[str]:
    return {i.code for i in _issues(db, eld_file_id)}


def _parse(db, ef: EldFile) -> dict:
    db.commit()
    return workers.parse_eld_file(ef.id, db=db)


def _fmcsa_file(code: str) -> bytes:
    """A realistic 49 CFR 395 Appendix A ELD output file for one driver.

    Kansas crash on 2026-05-01: power-up, off duty, on duty (pre-trip), driving,
    an intermediate log, on duty again, then a duty-status record the driver
    edited out (inactive). Plus every other section a real transfer carries.
    """
    return (
        "ELD File Header Segment:\n"
        "Kowalczyk,Nora,nkowal,KS,K1234567\n"
        "Delacruz,Victor,vdela\n"
        "PU-1187,1FUJGLDR3CLBP8834,TR-4471\n"
        "1234567,Prairie Freight Lines LLC,0,00:00,6\n"
        f"050126,ELD-REG-0042,ACMEELD01,A1B2,Output File Comment: {code}\n"
        "User List:\n"
        "User Order Number,User Last Name,User First Name,Account Type\n"
        "1,Kowalczyk,Nora,D\n"
        "2,Delacruz,Victor,D\n"
        "CMV List:\n"
        "CMV Order Number,CMV Power Unit Number,VIN\n"
        "1,PU-1187,1FUJGLDR3CLBP8834\n"
        "ELD Event List:\n"
        "Event Sequence ID Number,Event Record Status,Event Record Origin,Event Type,"
        "Event Code,Event Date,Event Time,Accumulated Vehicle Miles,Elapsed Engine Hours,"
        "Event Latitude,Event Longitude,Distance Since Last Valid Coordinates,"
        "CMV Order Number,User Order Number,Malfunction Indicator Status,"
        "Data Diagnostic Event Indicator Status,Event Data Check Value\n"
        "1,1,1,6,1,050126,055900,10230,412.5,39.0481N,95.6779W,0,1,1,0,0,80\n"
        "2,1,1,1,1,050126,060000,10230,412.5,39.0481N,95.6779W,0,1,1,0,0,7A\n"
        "3,1,1,1,4,050126,063000,10230,412.6,39.0481N,95.6779W,0,1,1,0,0,7B\n"
        "4,1,1,1,3,050126,070000,10231,412.8,39.0500N,95.6800W,0,1,1,0,0,7C\n"
        "5,1,1,2,1,050126,080000,10285,413.9,38.9700N,95.2350W,0,1,1,0,0,7D\n"
        "6,1,1,1,4,050126,113000,10402,417.4,38.9717N,95.2353W,0,1,1,0,0,7E\n"
        "7,2,2,1,1,050126,120000,10402,417.4,X,X,,1,1,0,0,7F\n"
        "Event Annotations or Comments:\n"
        "Event Sequence ID Number,Annotation\n"
        "5,Intermediate log recorded at highway speed\n"
        "Driver's Certification/Recertification Actions:\n"
        "Event Sequence ID Number,Event Record Status,Event Record Origin,Event Type,"
        "Event Code,Event Date,Event Time\n"
        "20,1,2,4,1,050126,190000\n"
        "Malfunction and Data Diagnostic Events:\n"
        "Event Sequence ID Number,Event Record Status,Event Record Origin,Event Type,"
        "Event Code,Event Date,Event Time,Malfunction Indicator Status\n"
        "30,1,1,7,1,050126,090000,1\n"
        "ELD Login/Logout Report:\n"
        "Event Sequence ID Number,Event Type,Event Code,Event Date,Event Time,User Order Number\n"
        "40,5,1,050126,055000,1\n"
        "CMV Engine Power-Up and Shut Down Activity:\n"
        "Event Sequence ID Number,Event Type,Event Code,Event Date,Event Time,"
        "Accumulated Vehicle Miles,Elapsed Engine Hours\n"
        "50,6,3,050126,193000,10402,417.4\n"
        "Unidentified Driver Records:\n"
        "Event Sequence ID Number,Event Record Status,Event Record Origin,Event Type,"
        "Event Code,Event Date,Event Time\n"
        "1,1,4,1,3,043026,220000\n"
        "End of File:\n"
        "File Data Check Value,9C3F\n"
    ).encode("utf-8")


# =========================================================================== realistic file
def test_realistic_fmcsa_output_file_extracts_completely(db):
    """The whole sectioned output file is read: header, every section, HOS totals."""
    crash = _make_crash(db)
    ef = _make_eld_file(db, crash, _fmcsa_file(crash.ccfp_identifier))

    result = _parse(db, ef)
    assert result["status"] == "PARSED", result
    assert result["file_format"] == "FMCSA_ELD_OUTPUT"

    db.refresh(ef)
    # --- header segment: the identifiers that tie HOS data to the crash -----
    assert ef.driver_name == "Nora Kowalczyk"
    assert ef.driver_license_number == "K1234567"
    assert ef.driver_license_state == "KS"
    assert ef.co_driver_name == "Victor Delacruz"
    assert ef.carrier_name == "Prairie Freight Lines LLC"
    assert ef.carrier_usdot == "1234567"
    assert ef.vin == "1FUJGLDR3CLBP8834"
    assert ef.power_unit_number == "PU-1187"
    assert ef.trailer_numbers == "TR-4471"
    assert ef.time_zone_offset == "6"
    assert ef.eld_registration_id == "ELD-REG-0042"
    assert ef.eld_identifier == "ACMEELD01"
    assert ef.file_data_check_value == "9C3F"
    # --- the CCFP code in the Output File Comment links the upload ----------
    assert ef.ccfp_code_in_file == crash.ccfp_identifier

    # --- every section accounted for ---------------------------------------
    assert set(ef.sections) == {
        "USER_LIST", "CMV_LIST", "EVENT_LIST", "EVENT_ANNOTATIONS", "CERTIFICATIONS",
        "MALFUNCTIONS", "LOGIN_LOGOUT", "ENGINE_POWER", "UNIDENTIFIED_DRIVER", "END_OF_FILE",
    }
    assert ef.sections["EVENT_LIST"] == 7
    assert ef.sections["UNIDENTIFIED_DRIVER"] == 1

    # 7 event-list rows + certification + malfunction + login + power-up +
    # unidentified-driver record = 12 events, none dropped.
    events = _events(db, ef.id)
    assert len(events) == 12
    assert ef.event_count == 12

    by_section: dict[str, list[EldEvent]] = {}
    for event in events:
        by_section.setdefault(event.section, []).append(event)
    assert {s: len(v) for s, v in by_section.items()} == {
        "EVENT_LIST": 7, "CERTIFICATIONS": 1, "MALFUNCTIONS": 1,
        "LOGIN_LOGOUT": 1, "ENGINE_POWER": 1, "UNIDENTIFIED_DRIVER": 1,
    }

    # --- duty status derived from the event type/code pair ------------------
    duty_changes = [e for e in by_section["EVENT_LIST"] if e.event_type_code == 1]
    assert [e.duty for e in duty_changes] == [
        "OFF_DUTY", "ON_DUTY_NOT_DRIVING", "DRIVING", "ON_DUTY_NOT_DRIVING", "OFF_DUTY",
    ]
    driving = next(e for e in duty_changes if e.duty == "DRIVING")
    assert driving.record_status == "ACTIVE"
    assert driving.record_origin == "AUTOMATIC"
    assert float(driving.latitude) == pytest.approx(39.05)
    assert float(driving.longitude) == pytest.approx(-95.68)  # W hemisphere -> negative
    assert float(driving.miles_driven) == pytest.approx(10231.0)
    assert float(driving.engine_hours) == pytest.approx(412.8)
    assert driving.data_check_value == "7C"

    # The edited-out record is kept for provenance and marked inactive.
    edited = next(e for e in by_section["EVENT_LIST"] if e.event_sequence == 7)
    assert edited.record_status == "INACTIVE_CHANGED"
    assert edited.record_origin == "DRIVER_EDIT"
    assert edited.latitude is None  # 'X' = position not available, not an error

    # Non-duty event types are named, not discarded.
    assert next(e for e in by_section["EVENT_LIST"] if e.event_sequence == 5).event_type == "INTERMEDIATE_LOG"
    assert by_section["MALFUNCTIONS"][0].event_type == "MALFUNCTION_DIAGNOSTIC"
    assert by_section["LOGIN_LOGOUT"][0].event_type == "LOGIN_LOGOUT"
    assert by_section["ENGINE_POWER"][0].ignition_status == "SHUT_DOWN"
    assert by_section["EVENT_LIST"][0].ignition_status == "POWER_UP"
    assert by_section["UNIDENTIFIED_DRIVER"][0].record_origin == "UNIDENTIFIED_DRIVER"

    # Annotations are attached to the event they reference.
    assert next(
        e for e in by_section["EVENT_LIST"] if e.event_sequence == 5
    ).annotation == "Intermediate log recorded at highway speed"

    # --- timestamps normalized to UTC using the header's offset -------------
    # The event reads 07:00 in the driver's home-terminal time and the header
    # declares 6 hours behind UTC, so the instant is 13:00 UTC. Compared as an
    # instant, not a wall clock: TIMESTAMPTZ comes back in the session's zone.
    assert driving.event_timestamp == dt.datetime(2026, 5, 1, 13, 0, tzinfo=dt.timezone.utc)

    # --- hours-of-service roll-up ------------------------------------------
    hos = ef.hos_summary
    assert hos["duty_hours"]["DRIVING"] == pytest.approx(4.5)      # 07:00 -> 11:30
    assert hos["duty_hours"]["ON_DUTY_NOT_DRIVING"] == pytest.approx(0.5)
    assert hos["duty_hours"]["OFF_DUTY"] == pytest.approx(0.5)
    assert hos["total_driving_hours"] == pytest.approx(4.5)
    assert hos["total_on_duty_hours"] == pytest.approx(5.0)
    # The inactive record is counted as inactive, not as a duty period.
    assert hos["inactive_records"] == 1
    assert hos["malfunction_events"] == 1
    assert hos["unidentified_driver_records"] == 1
    assert hos["events_by_type"]["DUTY_STATUS_CHANGE"] == 6

    # --- diagnostics: informational only, nothing blocking ------------------
    assert ef.error_count == 0
    assert ef.upload_status == "PARSED"
    assert ef.error_code is None
    codes = _issue_codes(db, ef.id)
    assert EldErrorCode.COORDINATE_UNAVAILABLE in codes  # the 'X' positions
    assert EldErrorCode.INACTIVE_RECORDS in codes
    assert all(i.severity in ("INFO", "WARNING") for i in _issues(db, ef.id))

    # --- provenance + PCI-7 auto-fill --------------------------------------
    assert ef.encoding == "utf-8"
    assert ef.delimiter == ","
    assert ef.content_sha256 and ef.file_size_bytes > 0
    assert ef.parse_attempts == 1
    assert ef.eld_downloaded is True
    # The last ACTIVE duty status — the driver's edited-out 12:00 OFF_DUTY record
    # must not become the "last duty status" on the crash record.
    assert ef.last_duty_status == "ON_DUTY_NOT_DRIVING"


def test_realistic_file_links_via_dq_eld_linked(db):
    """RECO-2 regression: the parsed CCFP code drives the QC link check."""
    crash = _make_crash(db)
    ef = _make_eld_file(db, crash, _fmcsa_file(crash.ccfp_identifier))
    _parse(db, ef)

    statuses = {
        r["rule"]: r["status"] for r in workers.evaluate_quality(crash.id, db=db)["results"]
    }
    assert statuses["DQ_ELD_LINKED"] == "PASS"


def test_wrong_ccfp_code_in_realistic_file_is_not_linked(db):
    """A file carrying another crash's code is stored verbatim and does NOT link."""
    crash = _make_crash(db)
    ef = _make_eld_file(db, crash, _fmcsa_file("CCFP-2099-ZZ-999999"))
    _parse(db, ef)

    db.refresh(ef)
    assert ef.ccfp_code_in_file == "CCFP-2099-ZZ-999999"
    statuses = {
        r["rule"]: r["status"] for r in workers.evaluate_quality(crash.id, db=db)["results"]
    }
    assert statuses["DQ_ELD_LINKED"] != "PASS"


def test_missing_ccfp_code_is_reported_not_ignored(db):
    """No Output File Comment -> a WARNING naming the fix, not a silent non-link."""
    crash = _make_crash(db)
    content = _fmcsa_file("CCFP-2026-KS-000001").replace(
        b"Output File Comment: CCFP-2026-KS-000001", b""
    )
    ef = _make_eld_file(db, crash, content)
    _parse(db, ef)

    db.refresh(ef)
    assert ef.ccfp_code_in_file is None
    warning = next(i for i in _issues(db, ef.id) if i.code == EldErrorCode.NO_CCFP_CODE)
    assert warning.severity == "WARNING"
    assert "Output File Comment" in warning.message


def test_event_list_only_export_uses_the_standard_parser(db):
    """An export of just the ELD Event List (no section titles) still resolves.

    The numeric Event Type / Event Code pair must be read structurally: a code of
    3 means "driving" only because the type is 1.
    """
    crash = _make_crash(db)
    content = (
        f"# Output File Comment: {crash.ccfp_identifier}\n"
        "Event Sequence ID Number,Event Record Status,Event Record Origin,Event Type,"
        "Event Code,Event Date,Event Time,Accumulated Vehicle Miles,Elapsed Engine Hours\n"
        "1,1,1,1,3,050126,070000,10231,412.8\n"
        "2,1,1,3,1,050126,090000,10260,414.0\n"   # personal conveyance -> off duty
        "3,1,1,1,1,050126,100000,10260,414.2\n"
    ).encode("utf-8")
    ef = _make_eld_file(db, crash, content)
    result = _parse(db, ef)

    assert result["status"] == "PARSED"
    assert result["file_format"] == "FMCSA_ELD_OUTPUT"
    events = _events(db, ef.id)
    assert [e.duty for e in events] == ["DRIVING", "OFF_DUTY", "OFF_DUTY"]
    assert [e.event_type for e in events] == [
        "DUTY_STATUS_CHANGE", "PERSONAL_USE_YARD_MOVE", "DUTY_STATUS_CHANGE",
    ]
    db.refresh(ef)
    assert ef.ccfp_code_in_file == crash.ccfp_identifier
    assert ef.hos_summary["personal_conveyance_events"] == 1


# =========================================================================== blocking failures
@pytest.mark.parametrize(
    "content, expected_code, expected_text",
    [
        (b"alpha,beta,gamma\n1,2,3\n", EldErrorCode.NO_MAPPABLE_COLUMNS, "matched a known ELD field"),
        (b"sequence,duty,location\n", EldErrorCode.NO_DATA_ROWS, "no data rows"),
    ],
)
def test_unusable_file_fails_with_an_actionable_reason(db, content, expected_code, expected_text):
    """A file that cannot yield events ends FAILED with a stored, readable reason.

    This is the core of the defect: these shapes used to end PARSED — one with a
    run of empty events, the other with a clean zero — telling nobody anything.
    """
    crash = _make_crash(db)
    ef = _make_eld_file(db, crash, content)
    result = _parse(db, ef)

    assert result["status"] == "FAILED"
    assert result["error_code"] == expected_code
    db.refresh(ef)
    assert ef.upload_status == "FAILED"
    assert ef.error_code == expected_code
    assert expected_text in ef.error_message
    assert ef.event_count == 0
    assert _events(db, ef.id) == []
    # The blocking reason is also an issue row, so the file's issue list is a
    # complete account rather than everything-except-the-reason.
    blocking = [i for i in _issues(db, ef.id) if i.severity == "ERROR"]
    assert [i.code for i in blocking] == [expected_code]


def test_missing_stored_object_fails_visibly(db):
    """A file whose object cannot be read is FAILED, never PARSED with 0 events."""
    crash = _make_crash(db)
    ef = _make_eld_file(db, crash, b"", attach_document=False)
    result = _parse(db, ef)

    assert result["status"] == "FAILED"
    assert result["error_code"] == EldErrorCode.OBJECT_UNREADABLE
    db.refresh(ef)
    assert ef.upload_status == "FAILED"
    assert "could not be read back from storage" in ef.error_message


def test_failed_reparse_does_not_leave_the_previous_run_behind(db):
    """A re-parse that fails must not show the earlier run's events under FAILED.

    The failure path rolls back, which would otherwise resurrect the events and
    issues the run had just cleared — a file reporting FAILED while still listing
    a previous extraction's data is precisely the misleading state this work
    removes.
    """
    crash = _make_crash(db)
    ef = _make_eld_file(db, crash, _fmcsa_file(crash.ccfp_identifier))
    assert _parse(db, ef)["status"] == "PARSED"
    assert len(_events(db, ef.id)) == 12

    # Break the link to the stored object, then re-run extraction.
    ef.document_id = None
    db.commit()
    result = workers.parse_eld_file(ef.id, db=db)

    assert result["status"] == "FAILED"
    assert result["error_code"] == EldErrorCode.OBJECT_UNREADABLE
    db.refresh(ef)
    assert ef.upload_status == "FAILED"
    assert ef.event_count == 0
    assert _events(db, ef.id) == []                     # no stale events
    assert ef.driver_name is None                       # no stale header values
    assert ef.ccfp_code_in_file is None                 # no stale CCFP link
    assert ef.hos_summary is None
    assert ef.parse_attempts == 2
    # The only issues left describe THIS run.
    assert _issue_codes(db, ef.id) == {EldErrorCode.OBJECT_UNREADABLE}


def test_parse_failure_notifies_the_uploader(db):
    """A background failure reaches a person — the upload request is long gone."""
    crash = _make_crash(db)
    uploader = db.scalar(select(User).where(User.email == INSPECTOR_KS))
    assert uploader is not None, "the seeded MCSAP inspector must exist"

    ef = _make_eld_file(db, crash, b"alpha,beta\n1,2\n")
    ef.uploaded_by = uploader.id
    db.flush()

    _parse(db, ef)

    notes = list(
        db.scalars(
            select(Notification).where(
                Notification.crash_id == crash.id,
                Notification.notification_type == "ELD_PARSE_FAILED",
            )
        )
    )
    assert len(notes) == 1
    assert notes[0].recipient_user_id == uploader.id
    assert "could not be processed" in notes[0].title
    # The notification carries the actionable message, not just "it failed".
    assert "matched a known ELD field" in notes[0].message


# =========================================================================== upload-time rejection
def _upload(client, headers, crash_id, name, content, mime="text/csv"):
    return client.post(
        f"{API}/crashes/{crash_id}/eld-files", headers=headers,
        files={"file": (name, io.BytesIO(content), mime)},
    )


def _after_background_parse(db) -> None:
    """Drop cached ORM state so a later request sees the background task's writes.

    Test-harness artifact, not production behaviour: `conftest.client` yields the
    SAME session to every request (production gives each request a fresh one),
    while the background task runs in its own session. Without this the request
    session would answer from its identity map with the pre-parse row.
    """
    db.expire_all()


def _new_crash_via_api(client, headers) -> dict:
    study_id = next(
        s for s in client.get(f"{API}/studies", headers=headers).json() if s["code"] == "PHASE1-HDT"
    )["id"]
    return client.post(
        f"{API}/crashes", headers=headers,
        json={"study_id": study_id, "state_code": "KS", "crash_date": "2026-05-01",
              "num_fatalities": 1},
    ).json()


@pytest.mark.parametrize(
    "name, content, expected_text",
    [
        ("empty.csv", b"", "empty"),
        ("report.pdf", b"%PDF-1.7\n1 0 obj\n<<>>\nendobj\n", "PDF document"),
        ("book.xlsx", b"PK\x03\x04\x14\x00\x08\x00" + b"\x00" * 64, "ZIP archive or Office document"),
        ("photo.jpg", b"\xff\xd8\xff\xe0\x00\x10JFIF" + b"\x00" * 32, "JPEG image"),
        ("notes.txt", b"Driver said he was tired. No CSV columns here.\n", "no delimited columns"),
    ],
)
def test_upload_refuses_a_file_that_cannot_be_an_eld_csv(client, db, name, content, expected_text):
    """Structural impossibility is refused in the request, with the reason.

    The uploader learns immediately what is wrong and how to fix it, instead of
    receiving 201 for a file that quietly fails minutes later in the background.
    """
    headers = _headers(db, INSPECTOR_KS)
    crash = _new_crash_via_api(client, headers)

    resp = _upload(client, headers, crash["id"], name, content)
    assert resp.status_code == 400, resp.text
    assert expected_text in resp.json()["detail"]

    # Nothing was stored for a refused upload.
    assert client.get(f"{API}/crashes/{crash['id']}/eld-files", headers=headers).json() == []


def test_upload_refuses_an_oversize_file(client, db, monkeypatch):
    """Past the size limit the read stops and the request is refused."""
    from app.core.config import settings

    monkeypatch.setattr(settings, "eld_max_upload_mb", 1)
    headers = _headers(db, INSPECTOR_KS)
    crash = _new_crash_via_api(client, headers)

    payload = b"sequence,duty\n" + b"1,driving\n" * 200_000  # ~2 MB
    resp = _upload(client, headers, crash["id"], "big.csv", payload)
    assert resp.status_code == 400, resp.text
    assert "larger than the 1 MB limit" in resp.json()["detail"]


def test_upload_refuses_an_infected_file(client, db):
    """The malware gate still runs before anything is stored (regression)."""
    headers = _headers(db, INSPECTOR_KS)
    crash = _new_crash_via_api(client, headers)
    eicar = b"X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"
    resp = _upload(client, headers, crash["id"], "eld.csv", eicar)
    assert resp.status_code == 400
    assert "malware" in resp.json()["detail"].lower()


# =========================================================================== encodings
@pytest.mark.parametrize(
    "encoding, expected",
    [("utf-8-sig", "utf-8-sig"), ("utf-16", "utf-16-le"), ("cp1252", "cp1252")],
)
def test_alternate_encodings_are_decoded_and_recorded(db, encoding, expected):
    """A UTF-16 or CP1252 export decodes correctly and says so.

    Blind UTF-8 decoding with errors="replace" used to turn these into
    replacement characters and report a successful parse of nonsense.
    """
    crash = _make_crash(db)
    text = (
        f"# Output File Comment: {crash.ccfp_identifier}\n"
        "sequence,timestamp,duty,location\n"
        "1,2026-05-01 08:00:00,driving,San José KS\n"
    )
    ef = _make_eld_file(db, crash, text.encode(encoding))
    result = _parse(db, ef)

    assert result["status"] == "PARSED", result
    db.refresh(ef)
    assert ef.encoding == expected
    assert ef.ccfp_code_in_file == crash.ccfp_identifier
    events = _events(db, ef.id)
    assert len(events) == 1
    assert events[0].location == "San José KS"
    assert events[0].duty == "DRIVING"
    if expected != "utf-8-sig":
        assert EldErrorCode.ENCODING_FALLBACK in _issue_codes(db, ef.id)


def test_semicolon_delimited_export_is_detected(db):
    """A European-style semicolon export parses; the delimiter is recorded."""
    crash = _make_crash(db)
    content = (
        "sequence;timestamp;duty;location\n"
        "1;2026-05-01 08:00:00;driving;Topeka KS\n"
    ).encode("utf-8")
    ef = _make_eld_file(db, crash, content)
    assert _parse(db, ef)["status"] == "PARSED"
    db.refresh(ef)
    assert ef.delimiter == ";"
    assert _events(db, ef.id)[0].duty == "DRIVING"


# =========================================================================== dirty data
def test_row_level_problems_are_reported_and_the_rest_still_extracts(db):
    """One bad row no longer costs the whole file, and no bad value is silent."""
    crash = _make_crash(db)
    content = (
        "sequence,timestamp,duty,location,latitude,longitude,miles_driven\n"
        "1,2026-05-01 08:00:00,driving,Topeka KS,39.048191,-95.677956,12.5\n"
        "not-a-number,2026-05-01 09:00:00,off_duty,Lawrence KS,,,\n"   # bad sequence
        "3,the first of May,driving,Salina KS,,,\n"                      # bad timestamp
        "4,2026-05-01 11:00:00,florbnax,Hays KS,,,\n"                    # unmapped duty
        "5,2026-05-01 12:00:00,driving,Colby KS,not-a-lat,-101.0,many\n"  # bad lat + miles
        "\n"                                                              # blank row
        "6,2026-05-01 13:00:00,driving,Goodland KS,,,99999999999\n"       # out of range
    ).encode("utf-8")
    ef = _make_eld_file(db, crash, content)
    result = _parse(db, ef)

    assert result["status"] == "PARSED"
    events = _events(db, ef.id)
    assert len(events) == 6  # the blank row is skipped, every real row survives

    codes = _issue_codes(db, ef.id)
    assert EldErrorCode.BAD_SEQUENCE in codes
    assert EldErrorCode.BAD_TIMESTAMP in codes
    assert EldErrorCode.UNMAPPED_DUTY_CODE in codes
    assert EldErrorCode.BAD_COORDINATE in codes
    assert EldErrorCode.BAD_NUMBER in codes
    assert EldErrorCode.BLANK_ROW in codes

    # The unusable values are NULL — and each one has an issue explaining it.
    assert events[1].event_sequence == 2          # fell back to file position
    assert events[2].event_timestamp is None
    assert events[3].duty is None
    assert events[4].latitude is None
    assert events[5].miles_driven is None

    duty_issue = next(i for i in _issues(db, ef.id) if i.code == EldErrorCode.UNMAPPED_DUTY_CODE)
    assert "florbnax" in duty_issue.message
    assert duty_issue.line_number == 5
    assert duty_issue.severity == "WARNING"
    # Warnings alone do not downgrade the status — the data IS usable.
    db.refresh(ef)
    assert ef.upload_status == "PARSED"
    assert ef.warning_count > 0
    assert ef.error_count == 0


def test_duplicate_sequence_numbers_are_kept_and_flagged(db):
    """Duplicates no longer abort the file on a unique-key violation.

    The ELD rule lets the sequence counter wrap and the unidentified-driver
    section restart its own numbering, so a real file legitimately repeats them.
    """
    crash = _make_crash(db)
    content = (
        "sequence,timestamp,duty\n"
        "1,2026-05-01 08:00:00,driving\n"
        "1,2026-05-01 09:00:00,off_duty\n"
        "1,2026-05-01 10:00:00,sleeper\n"
    ).encode("utf-8")
    ef = _make_eld_file(db, crash, content)
    result = _parse(db, ef)

    assert result["status"] == "PARSED"
    events = _events(db, ef.id)
    assert len(events) == 3                       # nothing dropped
    assert [e.is_duplicate for e in events] == [False, True, True]
    issue = next(i for i in _issues(db, ef.id) if i.code == EldErrorCode.DUPLICATE_SEQUENCE)
    assert issue.occurrences == 2


def test_ragged_and_malformed_rows_are_reported(db):
    """Extra/missing cells are read as far as they go and reported by line."""
    crash = _make_crash(db)
    content = (
        "sequence,timestamp,duty,location\n"
        "1,2026-05-01 08:00:00,driving,Topeka KS,UNEXPECTED\n"
        "2,2026-05-01 09:00:00\n"
    ).encode("utf-8")
    ef = _make_eld_file(db, crash, content)
    assert _parse(db, ef)["status"] == "PARSED"

    events = _events(db, ef.id)
    assert len(events) == 2
    assert events[0].location == "Topeka KS"
    assert events[1].location is None
    ragged = next(i for i in _issues(db, ef.id) if i.code == EldErrorCode.RAGGED_ROW)
    assert ragged.occurrences == 2


def test_truncated_partial_file_still_extracts_what_it_has(db):
    """A transfer cut off mid-section yields its complete rows, plus diagnostics."""
    crash = _make_crash(db)
    full = _fmcsa_file(crash.ccfp_identifier)
    partial = full[: full.index(b"5,1,1,2,1,050126,080000")]  # cut mid-event-list
    ef = _make_eld_file(db, crash, partial)
    result = _parse(db, ef)

    assert result["status"] in ("PARSED", "PARSED_WITH_ERRORS")
    events = _events(db, ef.id)
    assert len(events) == 4                       # the four complete event rows
    assert [e.duty for e in events if e.event_type_code == 1] == [
        "OFF_DUTY", "ON_DUTY_NOT_DRIVING", "DRIVING",
    ]
    db.refresh(ef)
    assert ef.ccfp_code_in_file == crash.ccfp_identifier
    # The sections that never arrived are simply absent — not silently invented.
    assert "UNIDENTIFIED_DRIVER" not in (ef.sections or {})


def test_unbalanced_quote_is_reported(db):
    """Broken CSV quoting does not end as a clean parse."""
    crash = _make_crash(db)
    content = b'sequence,timestamp,duty\n1,2026-05-01 08:00:00,"driving\n2,2026-05-01 09:00:00,off\n'
    ef = _make_eld_file(db, crash, content)
    result = _parse(db, ef)

    # Either the CSV reader reports the malformed line, or the runaway quoted
    # field swallows the rest and the duty code becomes unmappable — both are
    # recorded. What must never happen is a clean parse with no diagnostic.
    codes = _issue_codes(db, ef.id)
    assert codes & {EldErrorCode.CSV_MALFORMED, EldErrorCode.UNMAPPED_DUTY_CODE}
    assert result["warning_count"] + result["error_count"] > 0


# =========================================================================== limits
def test_large_file_extracts_every_event(db):
    """A realistically large export (5,000 events) extracts completely."""
    crash = _make_crash(db)
    rows = "".join(
        f"{i},2026-05-01 {i % 24:02d}:{i % 60:02d}:00,driving,Mile {i}\n"
        for i in range(1, 5001)
    )
    content = (
        f"# Output File Comment: {crash.ccfp_identifier}\n"
        "sequence,timestamp,duty,location\n" + rows
    ).encode("utf-8")
    ef = _make_eld_file(db, crash, content)
    result = _parse(db, ef)

    assert result["status"] == "PARSED"
    assert result["event_count"] == 5000
    db.refresh(ef)
    assert ef.event_count == 5000
    assert db.scalar(
        select(func.count()).select_from(EldEvent).where(EldEvent.eld_file_id == ef.id)
    ) == 5000


def test_event_cap_is_reported_never_a_silent_truncation(db, monkeypatch):
    """Past the event cap the file is PARSED_WITH_ERRORS and says what was dropped."""
    from app.core.config import settings

    monkeypatch.setattr(settings, "eld_max_events", 10)
    crash = _make_crash(db)
    rows = "".join(f"{i},2026-05-01 08:00:00,driving\n" for i in range(1, 26))
    ef = _make_eld_file(db, crash, ("sequence,timestamp,duty\n" + rows).encode("utf-8"))
    result = _parse(db, ef)

    assert result["status"] == "PARSED_WITH_ERRORS"
    assert result["truncated"] is True
    assert result["event_count"] == 10
    db.refresh(ef)
    assert ef.upload_status == "PARSED_WITH_ERRORS"
    assert ef.error_code == EldErrorCode.TRUNCATED
    assert "NOT stored" in ef.error_message
    assert ef.error_count >= 1


def test_time_budget_is_reported_never_a_silent_truncation(db, monkeypatch):
    """An extraction that outruns its time budget says so rather than half-finishing quietly."""
    from app.core.config import settings

    monkeypatch.setattr(settings, "eld_parse_time_budget_seconds", -1.0)  # already expired
    crash = _make_crash(db)
    rows = "".join(f"{i},2026-05-01 08:00:00,driving\n" for i in range(1, 6))
    ef = _make_eld_file(db, crash, ("sequence,timestamp,duty\n" + rows).encode("utf-8"))
    result = _parse(db, ef)

    assert result["status"] == "FAILED"
    db.refresh(ef)
    # Nothing could be extracted inside the budget, so the file is FAILED with
    # the budget named — not PARSED with zero events.
    assert ef.error_code in (
        EldErrorCode.TIME_BUDGET_EXCEEDED, EldErrorCode.NO_EVENTS_EXTRACTED,
    )
    assert EldErrorCode.TIME_BUDGET_EXCEEDED in _issue_codes(db, ef.id)


# =========================================================================== reparse
def test_reparse_recovers_a_file_after_the_mapping_is_configured(db, client):
    """The §3.4 recovery path: configure the provider's columns, re-run extraction."""
    headers = _headers(db, ANALYST_KS)
    crash = _new_crash_via_api(client, headers)
    provider = f"ACME-{uuid.uuid4().hex[:6]}"
    content = b"telemetry_row,telemetry_status,waypoint\n1,driving,Topeka KS\n"

    created = client.post(
        f"{API}/crashes/{crash['id']}/eld-files", headers=headers,
        files={"file": ("acme.csv", io.BytesIO(content), "text/csv")},
        data={"provider": provider},
    )
    assert created.status_code == 201, created.text
    file_id = created.json()["id"]

    # The background task ran inside the TestClient; the file is FAILED with a
    # reason a configurator can act on.
    _after_background_parse(db)
    detail = client.get(f"{API}/crashes/{crash['id']}/eld-files/{file_id}", headers=headers).json()
    assert detail["upload_status"] == "FAILED"
    assert detail["error_code"] == EldErrorCode.NO_MAPPABLE_COLUMNS
    assert "telemetry_row" in detail["error_message"]

    issues = client.get(
        f"{API}/crashes/{crash['id']}/eld-files/{file_id}/issues", headers=headers
    ).json()
    assert issues[0]["severity"] == "ERROR"
    assert issues[0]["code"] == EldErrorCode.NO_MAPPABLE_COLUMNS

    # Configure the provider's column names as DATA, then re-run extraction.
    db.add(EldFieldMapping(study_id=None, provider=provider, canonical_field="event_sequence",
                           source_header="telemetry_row", priority=10, is_active=True))
    db.add(EldFieldMapping(study_id=None, provider=provider, canonical_field="duty",
                           source_header="telemetry_status", priority=10, is_active=True))
    db.add(EldFieldMapping(study_id=None, provider=provider, canonical_field="location",
                           source_header="waypoint", priority=10, is_active=True))
    db.commit()

    reparsed = client.post(
        f"{API}/crashes/{crash['id']}/eld-files/{file_id}/reparse", headers=headers
    )
    assert reparsed.status_code == 200, reparsed.text
    body = reparsed.json()
    assert body["upload_status"] == "PARSED"
    assert body["event_count"] == 1
    assert body["error_code"] is None
    assert body["parse_attempts"] == 2

    events = client.get(f"{API}/crashes/{crash['id']}/eld-events", headers=headers).json()
    assert len(events) == 1
    assert events[0]["duty"] == "DRIVING"
    assert events[0]["location"] == "Topeka KS"

    # The stale ERROR issue is gone — a reparse replaces the previous account.
    after = client.get(
        f"{API}/crashes/{crash['id']}/eld-files/{file_id}/issues", headers=headers
    ).json()
    assert all(i["code"] != EldErrorCode.NO_MAPPABLE_COLUMNS for i in after)


def test_issues_endpoint_filters_by_severity(client, db):
    headers = _headers(db, INSPECTOR_KS)
    crash = _new_crash_via_api(client, headers)
    content = b"sequence,timestamp,duty\n1,not-a-date,florbnax\n"
    created = _upload(client, headers, crash["id"], "eld.csv", content)
    assert created.status_code == 201, created.text
    file_id = created.json()["id"]
    _after_background_parse(db)

    warnings = client.get(
        f"{API}/crashes/{crash['id']}/eld-files/{file_id}/issues?severity=WARNING",
        headers=headers,
    ).json()
    assert warnings and all(i["severity"] == "WARNING" for i in warnings)
    assert {i["code"] for i in warnings} >= {
        EldErrorCode.BAD_TIMESTAMP, EldErrorCode.UNMAPPED_DUTY_CODE,
    }


# =========================================================================== validate (dry run)
def test_validate_endpoint_reports_without_storing(client, db):
    """A dry run answers "would this extract?" before anything is committed."""
    headers = _headers(db, INSPECTOR_KS)
    crash = _new_crash_via_api(client, headers)

    good = client.post(
        f"{API}/crashes/{crash['id']}/eld-files/validate", headers=headers,
        files={"file": ("eld.csv", io.BytesIO(_fmcsa_file(crash["ccfp_identifier"])), "text/csv")},
    )
    assert good.status_code == 200, good.text
    body = good.json()
    assert body["ok"] is True
    assert body["file_format"] == "FMCSA_ELD_OUTPUT"
    assert body["event_count"] == 12
    assert body["ccfp_code_in_file"] == crash["ccfp_identifier"]
    assert body["ccfp_code_matches_crash"] is True
    assert body["header"]["carrier_name"] == "Prairie Freight Lines LLC"
    assert body["hos_summary"]["total_driving_hours"] == pytest.approx(4.5)

    bad = client.post(
        f"{API}/crashes/{crash['id']}/eld-files/validate", headers=headers,
        files={"file": ("nope.csv", io.BytesIO(b"alpha,beta\n1,2\n"), "text/csv")},
    )
    assert bad.status_code == 200
    assert bad.json()["ok"] is False
    assert bad.json()["error_code"] == EldErrorCode.NO_MAPPABLE_COLUMNS

    # Nothing was persisted by either dry run.
    assert client.get(f"{API}/crashes/{crash['id']}/eld-files", headers=headers).json() == []


# =========================================================================== authorization
@pytest.mark.parametrize("email", [INSPECTOR_KS, ANALYST_KS, PROJECT, SYSADMIN])
def test_every_role_with_eld_upload_can_upload_and_reparse(client, db, email):
    """Appendix E names the MCSAP CMV Inspector and CCFP Project Team analysts.

    CCFP_PROJECT_TEAM did not hold `eld:upload` before this work, so an analyst
    named in the requirement got a 403. The System Administrator holds every
    permission and is covered here too.
    """
    headers = _headers(db, email)
    crash = _new_crash_via_api(client, _headers(db, INSPECTOR_KS))  # KS crash, created by the inspector

    resp = _upload(client, headers, crash["id"], "eld.csv", _fmcsa_file(crash["ccfp_identifier"]))
    assert resp.status_code == 201, f"{email}: {resp.text}"
    body = resp.json()
    assert body["upload_status"] in ("UPLOADED", "PARSED")

    _after_background_parse(db)
    detail = client.get(
        f"{API}/crashes/{crash['id']}/eld-files/{body['id']}", headers=headers
    ).json()
    assert detail["upload_status"] == "PARSED"
    assert detail["event_count"] == 12
    assert detail["driver_name"] == "Nora Kowalczyk"

    reparse = client.post(
        f"{API}/crashes/{crash['id']}/eld-files/{body['id']}/reparse", headers=headers
    )
    assert reparse.status_code == 200, f"{email}: {reparse.text}"
    assert reparse.json()["event_count"] == 12

    validated = client.post(
        f"{API}/crashes/{crash['id']}/eld-files/validate", headers=headers,
        files={"file": ("eld.csv", io.BytesIO(_fmcsa_file(crash["ccfp_identifier"])), "text/csv")},
    )
    assert validated.status_code == 200, f"{email}: {validated.text}"


def test_upload_through_the_real_login_flow(client, auth, db):
    """One end-to-end pass using the genuine `POST /auth/login` round-trip.

    The other API tests here mint their bearer token directly (see `_headers`) to
    stay off the shared database's busiest row lock. This test keeps the real
    login path covered for the ELD upload route, so the shortcut cannot hide an
    authentication regression.
    """
    headers = auth(INSPECTOR_KS)
    crash = _new_crash_via_api(client, headers)

    resp = _upload(client, headers, crash["id"], "eld.csv", _fmcsa_file(crash["ccfp_identifier"]))
    assert resp.status_code == 201, resp.text
    _after_background_parse(db)

    detail = client.get(
        f"{API}/crashes/{crash['id']}/eld-files/{resp.json()['id']}", headers=headers
    ).json()
    assert detail["upload_status"] == "PARSED"
    assert detail["event_count"] == 12
    assert detail["ccfp_code_in_file"] == crash["ccfp_identifier"]


def test_roles_without_eld_upload_are_refused(client, db):
    """The public user holds no `eld:upload` — upload, validate and reparse are 403."""
    inspector = _headers(db, INSPECTOR_KS)
    crash = _new_crash_via_api(client, inspector)
    created = _upload(client, inspector, crash["id"], "eld.csv", _fmcsa_file(crash["ccfp_identifier"]))
    assert created.status_code == 201
    file_id = created.json()["id"]

    public = _headers(db, PUBLIC)
    assert _upload(client, public, crash["id"], "eld.csv", b"sequence,duty\n1,driving\n").status_code == 403
    assert client.post(
        f"{API}/crashes/{crash['id']}/eld-files/{file_id}/reparse", headers=public
    ).status_code == 403
    assert client.post(
        f"{API}/crashes/{crash['id']}/eld-files/validate", headers=public,
        files={"file": ("eld.csv", io.BytesIO(b"sequence,duty\n1,driving\n"), "text/csv")},
    ).status_code == 403


def test_state_scope_is_still_enforced_on_every_eld_route(client, db):
    """A TX analyst holds `eld:upload` but cannot touch a Kansas crash's ELD data."""
    inspector = _headers(db, INSPECTOR_KS)
    crash = _new_crash_via_api(client, inspector)
    created = _upload(client, inspector, crash["id"], "eld.csv", _fmcsa_file(crash["ccfp_identifier"]))
    assert created.status_code == 201
    file_id = created.json()["id"]

    tx = _headers(db, ANALYST_TX)
    assert _upload(client, tx, crash["id"], "eld.csv", b"sequence,duty\n1,driving\n").status_code == 403
    assert client.get(f"{API}/crashes/{crash['id']}/eld-files", headers=tx).status_code == 403
    assert client.get(
        f"{API}/crashes/{crash['id']}/eld-files/{file_id}/issues", headers=tx
    ).status_code == 403
    assert client.post(
        f"{API}/crashes/{crash['id']}/eld-files/{file_id}/reparse", headers=tx
    ).status_code == 403


# =========================================================================== regression
def test_flat_csv_path_is_unchanged(db):
    """RECO-5 regression: the simplified CSV still maps through configuration."""
    crash = _make_crash(db)
    content = (
        "event_sequence,duty_status,lat,lng,type,miles\n"
        "5,d,40.000000,-100.000000,IGNITION,7.0\n"
    ).encode("utf-8")
    ef = _make_eld_file(db, crash, content)
    assert _parse(db, ef)["status"] == "PARSED"

    event = db.scalar(select(EldEvent).where(EldEvent.eld_file_id == ef.id))
    assert event.event_sequence == 5
    assert event.duty == "DRIVING"
    assert float(event.latitude) == 40.0
    assert float(event.longitude) == -100.0
    assert event.event_type == "IGNITION"
    assert float(event.miles_driven) == 7.0
    db.refresh(ef)
    assert ef.file_format == "FLAT_CSV"


def test_provider_duty_mapping_still_wins_over_the_global_default(db):
    """RECO-5 regression: a provider-specific duty code beats the seeded default."""
    crash = _make_crash(db)
    provider = f"ACME-{uuid.uuid4().hex[:6]}"
    db.add(EldDutyCodeMapping(study_id=None, provider=provider, source_code="driving",
                              canonical_duty="OFF_DUTY", is_active=True))
    ef = _make_eld_file(db, crash, b"sequence,duty\n1,driving\n", provider=provider)
    assert _parse(db, ef)["status"] == "PARSED"
    assert _events(db, ef.id)[0].duty == "OFF_DUTY"


def test_pure_extraction_never_raises_on_arbitrary_bytes(db):
    """Fuzz-ish guard: extraction either yields a result or a typed EldParseError.

    An unhandled exception here would surface as an opaque 500 or a file stuck in
    PARSING — the failure mode this work removes.
    """
    payloads = [
        b"\x00\x01\x02\x03",
        b",,,,,\n,,,,\n",
        b"\n\n\n\n",
        b'"' * 500,
        "sequence,duty\n1,driving\n".encode("utf-32"),
        b"sequence,duty\n" + b"x" * 100_000 + b"\n",
        "中文,数据\n1,2\n".encode("utf-8"),
        b"sequence;duty|timestamp\ta,b\n",
    ]
    for payload in payloads:
        try:
            result = eld_format.extract(payload, field_aliases={}, duty_map={})
        except eld_format.EldParseError as exc:
            assert exc.code and exc.message
        else:
            assert result.file_format
