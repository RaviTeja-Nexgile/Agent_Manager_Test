"""RECO-5: the ELD CSV parser is driven by PostgreSQL configuration.

Per §3.4 (configurable for future phases/providers/States without code changes)
and §8.7 (ELD providers/models vary), the column-name and duty-status mapping was
moved out of hardcoded Python constants into the ``eld_field_mappings`` /
``eld_duty_code_mappings`` tables. ``parse_eld_file`` resolves the active mapping
for the file's ``(study_id, provider)`` — falling back to the seeded global
(NULL) defaults — and applies it per row. These tests verify:

  * regression  — with the SEEDED default mappings, a standard CSV parses to the
                  same duty/columns as before RECO-5 (no behaviour change);
  * data-driven — a provider-specific mapping row (header ``status`` -> canonical
                  ``duty``, code ``1`` -> ``DRIVING``) makes a non-default CSV
                  uploaded as that provider resolve correctly;
  * fallback    — with NO mapping rows at all, the resolver returns the hardcoded
                  defaults so an un-seeded database still parses identically;
  * negative    — a duty code / header with no mapping resolves to ``None`` (the
                  event still parses, the parser does not crash, and unrelated
                  rows are unaffected);
  * authorization — a user without ``eld:upload`` (public.demo) is 403 on upload.

All tests run inside the rolled-back ``db`` session fixture from conftest.py; setup
rows are committed first (in test mode ``commit()`` is a SAVEPOINT release) so the
worker's own commit/rollback nests inside the test transaction and the real
database is never mutated. Robust to seed drift: every fixture crash/file row is
created in the transaction (only the PHASE1-HDT study + the seeded global default
mappings are assumed present).
"""
from __future__ import annotations

import io
import uuid

from sqlalchemy import func, select

from app import workers
from app.core import storage
from app.models import (
    Crash,
    Document,
    EldDutyCodeMapping,
    EldEvent,
    EldFieldMapping,
    EldFile,
    Study,
)
from app.workers.tasks import _DEFAULT_FIELD_ALIASES, _DUTY_MAP, _resolve_eld_mappings
from tests.conftest import INSPECTOR_KS, PUBLIC

API = "/api/v1"


# --------------------------------------------------------------------------- fixtures
def _study(db) -> Study:
    study = db.scalar(select(Study).where(Study.code == "PHASE1-HDT"))
    assert study is not None, "PHASE1-HDT study must be seeded"
    return study


def _make_crash(db) -> Crash:
    """Create a throwaway in-transaction crash bound to the Phase 1 study."""
    crash = Crash(
        ccfp_identifier=f"CCFP-TEST-{uuid.uuid4().hex[:12]}",
        study_id=_study(db).id,
        state_code="KS",
        num_fatalities=1,
    )
    db.add(crash)
    db.flush()
    return crash


def _make_eld_file(db, crash: Crash, content: bytes, *, provider: str | None = None) -> EldFile:
    """Create an EldFile backed by a stored Document, optionally tagged with a provider."""
    storage_uri, size = storage.put_object(content, key_prefix="test-reco5", file_name="eld.csv")
    doc = Document(
        crash_id=crash.id, doc_type="ELD_CSV", file_name="eld.csv",
        mime_type="text/csv", storage_uri=storage_uri, size_bytes=size,
    )
    db.add(doc)
    db.flush()
    ef = EldFile(
        crash_id=crash.id, file_name="eld.csv", document_id=doc.id,
        provider=provider, upload_status="UPLOADED",
    )
    db.add(ef)
    db.flush()
    return ef


def _events(db, eld_file_id: uuid.UUID) -> list[EldEvent]:
    return list(
        db.scalars(
            select(EldEvent).where(EldEvent.eld_file_id == eld_file_id).order_by(EldEvent.event_sequence)
        )
    )


# --------------------------------------------------------------------------- seeded defaults present
def test_seeded_default_mappings_exist(db):
    """The global default field + duty-code mappings are seeded (the normal path)."""
    n_fields = db.scalar(select(func.count()).select_from(EldFieldMapping)) or 0
    n_duties = db.scalar(select(func.count()).select_from(EldDutyCodeMapping)) or 0
    assert n_fields > 0, "expected seeded eld_field_mappings global defaults"
    assert n_duties > 0, "expected seeded eld_duty_code_mappings global defaults"


# --------------------------------------------------------------------------- regression: default headers/codes
def test_default_mapping_parses_standard_csv_unchanged(db):
    """With seeded defaults, a standard CSV parses to the same duty/columns as before."""
    crash = _make_crash(db)
    csv_bytes = (
        "sequence,timestamp,duty,location,latitude,longitude,miles_driven,ignition_status\n"
        "1,2026-05-01 08:00:00,driving,Topeka KS,39.048191,-95.677956,12.5,ON\n"
        "2,2026-05-01 09:00:00,on_duty,Lawrence KS,,,,OFF\n"
        "3,2026-05-01 10:00:00,sleeper,Salina KS,,,,\n"
    ).encode("utf-8")
    ef = _make_eld_file(db, crash, csv_bytes)
    db.commit()

    result = workers.parse_eld_file(ef.id, db=db)
    assert result["status"] == "PARSED"
    assert result["event_count"] == 3

    events = _events(db, ef.id)
    # Duty codes resolved exactly as the old hardcoded _DUTY_MAP did.
    assert events[0].duty == "DRIVING"
    assert events[1].duty == "ON_DUTY_NOT_DRIVING"
    assert events[2].duty == "SLEEPER_BERTH"
    # Columns resolved via the seeded default header aliases.
    assert events[0].event_type is None
    assert events[0].location == "Topeka KS"
    assert float(events[0].latitude) == 39.048191
    assert float(events[0].longitude) == -95.677956
    assert float(events[0].miles_driven) == 12.5
    assert events[0].ignition_status == "ON"
    # Blank coordinates stay NULL.
    assert events[1].latitude is None and events[1].longitude is None


def test_default_mapping_honours_legacy_header_aliases(db):
    """The seeded defaults reproduce the legacy lat/lng aliases (non-regression)."""
    crash = _make_crash(db)
    csv_bytes = (
        "event_sequence,duty_status,lat,lng,type,miles\n"
        "5,d,40.000000,-100.000000,IGNITION,7.0\n"
    ).encode("utf-8")
    ef = _make_eld_file(db, crash, csv_bytes)
    db.commit()

    result = workers.parse_eld_file(ef.id, db=db)
    assert result["status"] == "PARSED"
    event = db.scalar(select(EldEvent).where(EldEvent.eld_file_id == ef.id))
    assert event.event_sequence == 5            # event_sequence alias
    assert event.duty == "DRIVING"              # duty_status alias + code 'd'
    assert float(event.latitude) == 40.0        # lat alias
    assert float(event.longitude) == -100.0     # lng alias
    assert event.event_type == "IGNITION"       # type alias
    assert float(event.miles_driven) == 7.0     # miles alias


# --------------------------------------------------------------------------- data-driven: provider override
def test_provider_specific_mapping_resolves_non_default_csv(db):
    """A provider mapping (status->duty, code 1->DRIVING) parses a non-default CSV."""
    crash = _make_crash(db)
    provider = f"ACME-{uuid.uuid4().hex[:6]}"

    # Provider-specific config rows (study NULL = applies for any study of this
    # provider). These coexist with the seeded global defaults; the resolver
    # prefers the more specific provider header but keeps defaults available too.
    db.add(EldFieldMapping(
        study_id=None, provider=provider, canonical_field="duty",
        source_header="status", priority=10, is_active=True,
    ))
    db.add(EldFieldMapping(
        study_id=None, provider=provider, canonical_field="event_sequence",
        source_header="seq_no", priority=10, is_active=True,
    ))
    db.add(EldDutyCodeMapping(
        study_id=None, provider=provider, source_code="1",
        canonical_duty="DRIVING", is_active=True,
    ))
    db.add(EldDutyCodeMapping(
        study_id=None, provider=provider, source_code="2",
        canonical_duty="OFF_DUTY", is_active=True,
    ))

    csv_bytes = (
        "seq_no,status,location\n"
        "1,1,Topeka KS\n"
        "2,2,Lawrence KS\n"
    ).encode("utf-8")
    ef = _make_eld_file(db, crash, csv_bytes, provider=provider)
    db.commit()

    result = workers.parse_eld_file(ef.id, db=db)
    assert result["status"] == "PARSED"
    assert result["event_count"] == 2

    events = _events(db, ef.id)
    # Non-default header `seq_no` -> event_sequence; non-default codes `1`/`2`
    # -> the configured DutyStatus values.
    assert events[0].event_sequence == 1
    assert events[0].duty == "DRIVING"
    assert events[0].location == "Topeka KS"
    assert events[1].event_sequence == 2
    assert events[1].duty == "OFF_DUTY"


def test_provider_mapping_does_not_leak_to_other_providers(db):
    """A provider-specific header/code is NOT applied to a different provider's file."""
    crash = _make_crash(db)
    provider_a = f"AAA-{uuid.uuid4().hex[:6]}"
    db.add(EldFieldMapping(
        study_id=None, provider=provider_a, canonical_field="duty",
        source_header="status", priority=10, is_active=True,
    ))
    db.add(EldDutyCodeMapping(
        study_id=None, provider=provider_a, source_code="1",
        canonical_duty="DRIVING", is_active=True,
    ))
    db.commit()

    # Resolve for a DIFFERENT provider: the A-specific rows must be excluded, so
    # `status` is not a duty header and `1` is not a duty code there.
    field_aliases, duty_map = _resolve_eld_mappings(db, _study(db).id, "OTHER-PROVIDER")
    assert "status" not in field_aliases.get("duty", [])
    assert duty_map.get("1") is None
    # The global defaults are still present for the other provider.
    assert "duty" in field_aliases.get("duty", [])
    assert duty_map.get("driving") == "DRIVING"


# --------------------------------------------------------------------------- defensive fallback
def test_resolver_falls_back_when_no_rows(db):
    """With NO mapping rows at all, the resolver returns the hardcoded defaults."""
    # Empty the mapping tables WITHIN this rolled-back transaction only.
    db.query(EldFieldMapping).delete()
    db.query(EldDutyCodeMapping).delete()
    db.flush()

    field_aliases, duty_map = _resolve_eld_mappings(db, _study(db).id, "any-provider")
    assert field_aliases == {k: list(v) for k, v in _DEFAULT_FIELD_ALIASES.items()}
    assert duty_map == dict(_DUTY_MAP)


def test_parse_still_works_with_no_mapping_rows(db):
    """End-to-end: with the mapping tables empty, a standard CSV still parses."""
    db.query(EldFieldMapping).delete()
    db.query(EldDutyCodeMapping).delete()
    db.flush()

    crash = _make_crash(db)
    csv_bytes = (
        "sequence,duty,location\n"
        "1,driving,Topeka KS\n"
    ).encode("utf-8")
    ef = _make_eld_file(db, crash, csv_bytes)
    db.commit()

    result = workers.parse_eld_file(ef.id, db=db)
    assert result["status"] == "PARSED"
    event = db.scalar(select(EldEvent).where(EldEvent.eld_file_id == ef.id))
    assert event.duty == "DRIVING"
    assert event.location == "Topeka KS"


# --------------------------------------------------------------------------- negative: unmapped code/header
def test_unmapped_duty_code_resolves_to_none(db):
    """A duty code with no mapping resolves to None — no crash, other rows parse."""
    crash = _make_crash(db)
    csv_bytes = (
        "sequence,duty,location\n"
        "1,driving,Topeka KS\n"        # mapped -> DRIVING
        "2,florbnax,Lawrence KS\n"     # unmapped code -> None
    ).encode("utf-8")
    ef = _make_eld_file(db, crash, csv_bytes)
    db.commit()

    result = workers.parse_eld_file(ef.id, db=db)
    assert result["status"] == "PARSED"
    assert result["event_count"] == 2

    events = _events(db, ef.id)
    assert events[0].duty == "DRIVING"
    # Unmapped duty code -> None (not an error); the row still parses.
    assert events[1].duty is None
    assert events[1].location == "Lawrence KS"


def test_unmapped_header_leaves_field_none(db):
    """A canonical field whose mapped header(s) are absent stays None; row parses."""
    crash = _make_crash(db)
    # No latitude/longitude/duty columns at all under any default alias.
    csv_bytes = (
        "sequence,location\n"
        "1,Topeka KS\n"
    ).encode("utf-8")
    ef = _make_eld_file(db, crash, csv_bytes)
    db.commit()

    result = workers.parse_eld_file(ef.id, db=db)
    assert result["status"] == "PARSED"
    event = db.scalar(select(EldEvent).where(EldEvent.eld_file_id == ef.id))
    assert event.event_sequence == 1
    assert event.location == "Topeka KS"
    assert event.duty is None
    assert event.latitude is None and event.longitude is None


def test_inactive_mapping_row_is_ignored(db):
    """An is_active=False provider row does not affect resolution (uses defaults)."""
    crash = _make_crash(db)
    provider = f"INACTIVE-{uuid.uuid4().hex[:6]}"
    db.add(EldFieldMapping(
        study_id=None, provider=provider, canonical_field="duty",
        source_header="status", priority=10, is_active=False,  # inactive!
    ))
    db.commit()

    field_aliases, _ = _resolve_eld_mappings(db, _study(db).id, provider)
    # The inactive `status` header is not picked up; only the active defaults remain.
    assert "status" not in field_aliases.get("duty", [])
    assert "duty" in field_aliases.get("duty", [])


# --------------------------------------------------------------------------- authorization on upload
def test_upload_requires_eld_permission(client, auth, db):
    """The upload endpoint still enforces eld:upload — public.demo gets 403."""
    insp = auth(INSPECTOR_KS)
    study_id = next(
        s for s in client.get(f"{API}/studies", headers=insp).json() if s["code"] == "PHASE1-HDT"
    )["id"]
    crash = client.post(
        f"{API}/crashes", headers=insp,
        json={"study_id": study_id, "state_code": "KS", "crash_date": "2026-05-01", "num_fatalities": 1},
    ).json()
    cid = crash["id"]

    csv_bytes = b"sequence,duty\n1,driving\n"

    # Public user has no eld:upload -> 403 (authorization preserved).
    pub = auth(PUBLIC)
    denied = client.post(
        f"{API}/crashes/{cid}/eld-files", headers=pub,
        files={"file": ("eld.csv", io.BytesIO(csv_bytes), "text/csv")},
    )
    assert denied.status_code == 403, denied.text

    # The inspector (KS, holds eld:upload) succeeds.
    ok = client.post(
        f"{API}/crashes/{cid}/eld-files", headers=insp,
        files={"file": ("eld.csv", io.BytesIO(csv_bytes), "text/csv")},
    )
    assert ok.status_code == 201, ok.text
