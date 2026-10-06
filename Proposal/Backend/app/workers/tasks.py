"""ELD parsing, quality-control evaluation, and completeness evaluation."""
from __future__ import annotations

import dataclasses
import datetime as dt
import re
import uuid
from typing import Any, Callable

from sqlalchemy import func, insert, literal, or_, select, update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import SessionLocal
from app.core import storage
from app.core.notifications import create_notification, users_with_role
from app.enums import (
    CompletenessStatus,
    DutyStatus,
    EldIssueSeverity,
    EldUploadStatus,
    NotificationType,
    QcResultStatus,
)
from app.integrations import cdlis
from app.common import selected_values
from app.models import (
    AttributeRequirement,
    CompletenessRule,
    ContributingFactorSelection,
    Crash,
    CrashAttributeValue,
    CrashCompletenessStatus,
    DataAttribute,
    DataQualityResult,
    DataQualityRule,
    Document,
    EldDutyCodeMapping,
    EldEvent,
    EldFieldMapping,
    EldFile,
    EldParseIssue,
    IncidentPerson,
    IncidentVehicle,
    InitialIncidentForm,
    Notification,
    PostCrashInspection,
    StudyParameter,
)
from app.workers import eld_format
from app.workers.eld_format import EldErrorCode, EldParseError

# NOTI-5: the IIF is expected within 24-48 h of a crash (documentation §12.4).
# A record aged past this window with no submitted IIF is flagged. Kept as a
# named default (config-driven, not an inline Phase-1 literal): a per-study
# `iif_window_hours` parameter overrides it when present (see
# scan_crashes_missing_iif), and a caller may pass window_hours explicitly.
DEFAULT_IIF_WINDOW_HOURS = 48

_DOT_RE = re.compile(r"^[0-9]{1,8}$")

# RECO-2: a CCFP code carried in an ELD output-file comment. Matches the crash
# `ccfp_identifier` shape generated in crashes.py (`CCFP-<year>-<STATE>-<seq>`,
# e.g. `CCFP-2026-KS-000001`) without hardcoding a single state/year: a literal
# `CCFP-` prefix followed by one or more hyphen-separated alphanumeric segments.
# Anchored to a word boundary so it lifts the token out of surrounding prose
# (e.g. `Output File Comment: CCFP-2026-KS-000001`). The test crashes use a
# `CCFP-TEST-<hex>` identifier, which this same pattern matches. Defined once in
# `eld_format` and re-exported here for existing call sites.
_CCFP_CODE_RE = eld_format.CCFP_CODE_RE
# RECO-5: the duty-code translation and the per-field header aliases below are the
# DEFENSIVE FALLBACK only. The normal path is data-driven: `_resolve_eld_mappings`
# loads active `eld_field_mappings` / `eld_duty_code_mappings` rows for the file's
# (study_id, provider) — falling back to the seeded global (NULL) defaults — so a
# new provider/model whose CSV uses different headers or duty codes is configured
# as DATA without a code change (§3.4 configurability, §8.7). These constants are
# used only when NO mapping rows exist at all, which keeps the parser working even
# against an un-seeded database and reproduces today's behaviour byte-for-byte.
#
# Keys are already in `_norm` form (lowercase, non-alnum runs collapsed to `_`),
# matching how seed rows store `source_header` and how `_resolve_eld_mappings`
# normalizes them, so the data path and the fallback path agree exactly.
_DUTY_MAP = {
    "off_duty": "OFF_DUTY", "off": "OFF_DUTY",
    "sleeper": "SLEEPER_BERTH", "sleeper_berth": "SLEEPER_BERTH", "sb": "SLEEPER_BERTH",
    "driving": "DRIVING", "d": "DRIVING",
    "on_duty": "ON_DUTY_NOT_DRIVING", "on_duty_not_driving": "ON_DUTY_NOT_DRIVING", "on": "ON_DUTY_NOT_DRIVING",
}

# canonical_field -> ordered header aliases (first present wins), mirroring the
# inline `r.get(a) or r.get(b) or ...` chains the parser used before RECO-5.
_DEFAULT_FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "event_sequence": ("sequence", "event_sequence"),
    "event_timestamp": ("timestamp", "event_timestamp"),
    "duty": ("duty", "duty_status"),
    "event_type": ("event_type", "type"),
    "location": ("location",),
    "latitude": ("latitude", "lat", "gps_lat"),
    "longitude": ("longitude", "lon", "lng", "long", "gps_lng", "gps_lon"),
    "miles_driven": ("miles_driven", "miles"),
    "engine_hours": ("engine_hours",),
    "ignition_status": ("ignition_status", "ignition"),
}


# ---------------------------------------------------------------------------
# ELD parsing (documentation §8.7, BRD Jan-2026 Appendix E)
# ---------------------------------------------------------------------------
# The decoding/format/extraction logic lives in `app.workers.eld_format` as pure
# functions so it is testable without a session and can back BOTH this
# background task and the synchronous pre-upload validation endpoint. This module
# keeps the DB-facing half: resolving the configured mapping, persisting events
# and issues, and moving the file's status.
#
# The names below are re-exported (not re-implemented) because existing tests and
# call sites import them from here.
_norm = eld_format.norm
_extract_ccfp_code = eld_format.extract_ccfp_code

# RECO-2: the normalized column names that can carry the CCFP output-file comment
# (per the spec's two shapes — a dedicated comment/code column on a data row).
_CCFP_COMMENT_COLUMNS = eld_format.CCFP_COMMENT_COLUMNS


# RECO-5: the canonical fields the parser knows how to populate. Mapping rows
# naming any other canonical_field are ignored (a misconfiguration cannot inject
# new columns); this set bounds what `_resolve_eld_mappings` returns.
_ELD_CANONICAL_FIELDS: frozenset[str] = frozenset(_DEFAULT_FIELD_ALIASES)

# Valid canonical duty values a duty-code mapping may resolve to. A row whose
# canonical_duty is not a real DutyStatus is dropped rather than stored, so a bad
# config row degrades to "unmapped" (-> None) instead of corrupting an event.
_VALID_DUTIES: frozenset[str] = frozenset(d.value for d in DutyStatus)


def _resolve_eld_mappings(
    db: Session, study_id: uuid.UUID | None, provider: str | None
) -> tuple[dict[str, list[str]], dict[str, str]]:
    """Build (field-aliases, duty-code-map) for an ELD file (RECO-5, §8.7).

    Loads active ``eld_field_mappings`` / ``eld_duty_code_mappings`` rows whose
    ``study_id`` is the file's study or NULL (global default) and whose
    ``provider`` is the file's provider or NULL (global default), then collapses
    them to:

      * ``field_aliases``: ``canonical_field -> [source_header, ...]`` in
        descending specificity, so a study+provider-specific header is tried
        before a global default. Each ``source_header`` is ``_norm``-ed to match
        the normalized row keys the parser reads.
      * ``duty_map``: normalized ``source_code -> DutyStatus`` value, again with
        the most specific active row winning per code.

    Defensive fallback: when NO field rows / NO duty rows exist at all (e.g. an
    un-seeded database), returns the hardcoded ``_DEFAULT_FIELD_ALIASES`` /
    ``_DUTY_MAP`` so existing CSVs parse identically. The two halves fall back
    independently, so a partial config never silently blanks the other half.
    """

    # Specificity weight: study+provider (3) > provider-only (2) > study-only (1)
    # > global default (0). Within the same canonical field / source code, a more
    # specific active row's header/value is preferred; the explicit ``priority``
    # column breaks ties and lets an admin force an ordering.
    def _specificity(row_study, row_provider) -> int:
        score = 0
        if study_id is not None and row_study == study_id:
            score += 2
        if provider is not None and row_provider == provider:
            score += 1
        return score

    # Scope predicate builder: match rows whose study_id is the file's study OR
    # NULL (global default), AND whose provider is the file's provider OR NULL.
    # NULL on either column means "applies to any value of that key" — the seeded
    # global defaults carry NULL on both. Built with explicit `or_(... IS NULL)`
    # rather than `IN (val, None)` so a NULL key is an unambiguous IS NULL.
    def _scope(model):
        study_pred = (
            or_(model.study_id == study_id, model.study_id.is_(None))
            if study_id is not None
            else model.study_id.is_(None)
        )
        provider_pred = (
            or_(model.provider == provider, model.provider.is_(None))
            if provider is not None
            else model.provider.is_(None)
        )
        return (model.is_active.is_(True), study_pred, provider_pred)

    # --- header -> canonical-field aliases ---------------------------------
    field_rows = list(
        db.scalars(select(EldFieldMapping).where(*_scope(EldFieldMapping)))
    )
    field_aliases: dict[str, list[str]]
    if field_rows:
        # Order each canonical field's headers by (specificity, priority) desc so
        # the winning header is first; keep all so a row missing the top header
        # still resolves via a lower-priority alias (mirrors the old or-chains).
        ordered = sorted(
            field_rows,
            key=lambda r: (_specificity(r.study_id, r.provider), r.priority or 0),
            reverse=True,
        )
        field_aliases = {}
        for row in ordered:
            canonical = row.canonical_field
            if canonical not in _ELD_CANONICAL_FIELDS:
                continue  # ignore unknown canonical fields (cannot inject columns)
            header = _norm(row.source_header)
            if not header:
                continue
            aliases = field_aliases.setdefault(canonical, [])
            if header not in aliases:
                aliases.append(header)
    else:
        # No configuration at all -> reproduce today's behaviour exactly.
        field_aliases = {k: list(v) for k, v in _DEFAULT_FIELD_ALIASES.items()}

    # --- source duty code -> canonical DutyStatus --------------------------
    duty_rows = list(
        db.scalars(select(EldDutyCodeMapping).where(*_scope(EldDutyCodeMapping)))
    )
    duty_map: dict[str, str]
    if duty_rows:
        # Apply least-specific first so the most specific active row overwrites,
        # leaving the winning canonical_duty per normalized source code.
        ordered_duty = sorted(
            duty_rows,
            key=lambda r: (_specificity(r.study_id, r.provider), 0),
        )
        duty_map = {}
        for row in ordered_duty:
            code = _norm(row.source_code)
            canonical = row.canonical_duty
            if not code or canonical not in _VALID_DUTIES:
                continue  # drop blank codes / unknown duty values (-> unmapped)
            duty_map[code] = canonical
        if not duty_map:  # every row was invalid -> fall back rather than blank
            duty_map = dict(_DUTY_MAP)
    else:
        duty_map = dict(_DUTY_MAP)

    return field_aliases, duty_map


#: Public alias. The resolver is also needed outside the worker — the dry-run
#: validation endpoint must apply exactly the same (study, provider) mapping the
#: background parse will, or a file could validate clean and then extract badly.
resolve_eld_mappings = _resolve_eld_mappings


# --- ELD file (re)parse ----------------------------------------------------
# Columns copied straight from the extracted header segment onto `eld_files`.
_HEADER_COLUMNS = (
    "driver_name", "driver_license_number", "driver_license_state", "co_driver_name",
    "carrier_name", "carrier_usdot", "vin", "power_unit_number", "trailer_numbers",
    "time_zone_offset", "eld_registration_id", "eld_identifier", "output_file_comment",
    "file_data_check_value",
)

# Columns written per extracted event. Listed once so the bulk INSERT and the
# row builder cannot drift apart.
_EVENT_COLUMNS = (
    "event_sequence", "event_timestamp", "duty", "event_type", "location",
    "latitude", "longitude", "miles_driven", "engine_hours", "ignition_status",
    "raw", "section", "line_number", "event_type_code", "event_code",
    "record_status", "record_origin", "distance_since_last_coords",
    "malfunction_indicator", "diagnostic_indicator", "annotation",
    "driver_identifier", "cmv_identifier", "data_check_value", "is_duplicate",
)

#: Rows per executemany batch. Keeps a very large file's INSERT off one giant
#: statement without giving up the speed of bulk inserts.
_EVENT_INSERT_BATCH = 1_000


def _clear_extraction(db: Session, ef: EldFile) -> None:
    """Discard everything the previous extraction produced for this file.

    Events, issues, diagnostics, extracted header values, the CCFP code and the
    derived summary all belong to ONE parse. Leaving any of them behind would
    show an analyst a blend of two extractions — the quiet kind of wrong this
    work exists to remove. Called at the start of every (re)parse AND again after
    a rollback on failure, because the rollback would otherwise resurrect the
    prior run's events under a FAILED status.
    """
    db.query(EldEvent).filter(EldEvent.eld_file_id == ef.id).delete(synchronize_session=False)
    db.query(EldParseIssue).filter(EldParseIssue.eld_file_id == ef.id).delete(synchronize_session=False)
    ef.error_code = None
    ef.error_message = None
    ef.event_count = 0
    ef.error_count = 0
    ef.warning_count = 0
    ef.row_count = None
    ef.line_count = None
    ef.file_format = None
    ef.encoding = None
    ef.delimiter = None
    ef.sections = None
    ef.hos_summary = None
    for column in _HEADER_COLUMNS:
        setattr(ef, column, None)
    ef.header_metadata = None
    ef.ccfp_code_in_file = None


def _reset_parse_state(db: Session, ef: EldFile, started: dt.datetime) -> None:
    """Begin a parse run: clear the last one and stamp the bookkeeping."""
    _clear_extraction(db, ef)
    ef.upload_status = EldUploadStatus.PARSING.value
    ef.parse_started_at = started
    ef.parse_attempts = (ef.parse_attempts or 0) + 1


def _store_issues(db: Session, eld_file_id: uuid.UUID, issues: list[eld_format.Issue]) -> None:
    for issue in issues:
        db.add(
            EldParseIssue(
                eld_file_id=eld_file_id,
                severity=issue.severity,
                code=issue.code,
                message=issue.message,
                section=issue.section,
                line_number=issue.line_number,
                column_name=issue.column_name,
                raw_value=issue.raw_value,
                occurrences=issue.occurrences,
                details=issue.details or None,
            )
        )


def _notify_parse_outcome(db: Session, ef: EldFile, status: str, headline: str) -> None:
    """Tell the uploader what happened to a file parsed after the response left.

    The upload endpoint returns 201 immediately, so a failed or partial
    extraction has no request left to report on — without this the uploader would
    have to go back and look. The notification carries the actionable message, so
    the failure reaches a person even if nobody reopens the crash record.
    """
    if ef.uploaded_by is None:
        return
    create_notification(
        db,
        recipient_user_id=ef.uploaded_by,
        notification_type=NotificationType.ELD_PARSE_FAILED,
        title=(
            f"ELD file '{ef.file_name}' could not be processed"
            if status == EldUploadStatus.FAILED.value
            else f"ELD file '{ef.file_name}' extracted with problems"
        ),
        message=headline,
        crash_id=ef.crash_id,
    )


def _fail_parse(
    db: Session, eld_file_id: uuid.UUID, code: str, message: str,
    issues: list[eld_format.Issue] | None = None,
    *, started: dt.datetime | None = None,
) -> dict:
    """Record a blocking failure against the file and return the result dict.

    Rolls back first so a half-written extraction cannot be committed alongside
    the failure, then re-reads the row (the rollback expired it) and writes the
    status, the actionable message and whatever diagnostics were gathered before
    the failure. A file is NEVER left in PARSING.

    The rollback also undoes the run's opening `_reset_parse_state`, which would
    otherwise (a) resurrect the previous run's events and issues under the new
    FAILED status — a file claiming to have failed while still showing an earlier
    run's data — and (b) lose this attempt's bookkeeping, so a failure would not
    count as an attempt and the duration would be measured from an earlier run's
    start. Both are restored here from ``started``.
    """
    db.rollback()
    ef = db.get(EldFile, eld_file_id)
    if ef is None:
        return {"eld_file_id": str(eld_file_id), "status": EldUploadStatus.FAILED.value,
                "error_code": code, "error": message}
    _clear_extraction(db, ef)
    ef.upload_status = EldUploadStatus.FAILED.value
    ef.event_count = 0
    ef.error_code = code
    ef.error_message = message
    ef.parsed_at = dt.datetime.now(dt.timezone.utc)
    if started is not None:
        ef.parse_started_at = started
        ef.parse_attempts = (ef.parse_attempts or 0) + 1
    if ef.parse_started_at is not None:
        ef.parse_duration_ms = int(
            (ef.parsed_at - ef.parse_started_at).total_seconds() * 1000
        )
    collected = list(issues or [])
    # The blocking failure is itself an issue row, so the file's issue list is a
    # complete account rather than "everything except the reason it failed".
    collected.append(
        eld_format.Issue(
            severity=EldIssueSeverity.ERROR.value, code=code, message=message,
        )
    )
    ef.error_count = sum(
        i.occurrences for i in collected if i.severity == EldIssueSeverity.ERROR.value
    )
    ef.warning_count = sum(
        i.occurrences for i in collected if i.severity == EldIssueSeverity.WARNING.value
    )
    _store_issues(db, ef.id, collected)
    _notify_parse_outcome(db, ef, EldUploadStatus.FAILED.value, message)
    db.commit()
    return {
        "eld_file_id": str(eld_file_id),
        "status": EldUploadStatus.FAILED.value,
        "event_count": 0,
        "error_code": code,
        "error": message,
        "error_count": ef.error_count,
        "warning_count": ef.warning_count,
    }


def parse_eld_file(eld_file_id: uuid.UUID, db: Session | None = None) -> dict:
    """Extract an uploaded ELD/eRODS output file (BRD Appendix E, §8.7).

    Reads the stored object, resolves the study/provider column + duty-code
    mapping, runs the format-aware extraction in ``eld_format`` and persists the
    events, the header-segment metadata, the derived hours-of-service summary and
    every diagnostic the extraction raised.

    The file always ends in a terminal state with a reason attached:

      ``PARSED``              events extracted, no ERROR-severity problem;
      ``PARSED_WITH_ERRORS``  events extracted AND at least one ERROR (truncated
                              at the row cap, a section that could not be read,
                              a time-budget overrun) — deliberately NOT collapsed
                              into PARSED;
      ``FAILED``              nothing could be extracted; ``error_code`` and
                              ``error_message`` say why and what to do.

    Safe to re-run: the previous extraction is cleared first, so a reparse after
    a mapping fix replaces the old result instead of merging with it.
    """
    own = db is None
    db = db or SessionLocal()
    # Captured once, before any DB work: the failure path rolls back, which
    # discards the run's bookkeeping, so this value is what restores it.
    started = dt.datetime.now(dt.timezone.utc)
    try:
        ef = db.get(EldFile, eld_file_id)
        if ef is None:
            # Not a silent no-op: the caller gets an explicit error. There is no
            # row to record it against, so this is the only channel available.
            return {"error": "eld_file not found", "error_code": EldErrorCode.INTERNAL,
                    "eld_file_id": str(eld_file_id), "status": None}

        _reset_parse_state(db, ef, started)
        crash = db.get(Crash, ef.crash_id) if ef.crash_id else None
        study_id = crash.study_id if crash is not None else None
        # RECO-5: the header->canonical and duty-code->DutyStatus maps come from
        # PostgreSQL configuration for this (study, provider), falling back to the
        # seeded global defaults, so a new provider is configured as DATA (§8.7).
        field_aliases, duty_map = _resolve_eld_mappings(db, study_id, ef.provider)
        db.flush()

        # --- read the stored object ---------------------------------------
        try:
            content = b""
            if ef.document_id:
                doc = db.get(Document, ef.document_id)
                if doc is not None:
                    content = storage.read_object(doc.storage_uri)
                else:
                    raise FileNotFoundError("document row missing")
            else:
                raise FileNotFoundError("no document attached")
        except Exception as exc:  # noqa: BLE001 - any storage failure is reportable
            return _fail_parse(
                db, eld_file_id, EldErrorCode.OBJECT_UNREADABLE,
                "The uploaded ELD file could not be read back from storage "
                f"({type(exc).__name__}). Upload the file again; if it keeps failing, "
                "report it to a System Administrator.",
                started=started,
            )

        # --- extract -------------------------------------------------------
        try:
            result = eld_format.extract(
                content, field_aliases=field_aliases, duty_map=duty_map,
                max_events=settings.eld_max_events,
                time_budget_seconds=settings.eld_parse_time_budget_seconds,
            )
        except EldParseError as exc:
            return _fail_parse(db, eld_file_id, exc.code, exc.message, exc.issues, started=started)
        except Exception as exc:  # noqa: BLE001 - an unexpected bug is still reported
            return _fail_parse(
                db, eld_file_id, EldErrorCode.INTERNAL,
                f"The ELD file could not be processed because of an unexpected error "
                f"({type(exc).__name__}: {exc}). The file is stored; report this to a "
                "System Administrator so the extraction can be corrected and re-run.",
                started=started,
            )

        # --- persist -------------------------------------------------------
        if result.events:
            rows = [
                {
                    "eld_file_id": ef.id,
                    "event_sequence": event.event_sequence,
                    "event_timestamp": event.event_timestamp,
                    "duty": event.duty,
                    "event_type": event.event_type,
                    "location": event.location,
                    "latitude": event.latitude,
                    "longitude": event.longitude,
                    "miles_driven": event.miles_driven,
                    "engine_hours": event.engine_hours,
                    "ignition_status": event.ignition_status,
                    "raw": event.raw,
                    "section": event.section,
                    "line_number": event.line_number,
                    "event_type_code": event.event_type_code,
                    "event_code": event.event_code,
                    "record_status": event.record_status,
                    "record_origin": event.record_origin,
                    "distance_since_last_coords": event.distance_since_last_coords,
                    "malfunction_indicator": event.malfunction_indicator,
                    "diagnostic_indicator": event.diagnostic_indicator,
                    "annotation": event.annotation,
                    "driver_identifier": event.driver_identifier,
                    "cmv_identifier": event.cmv_identifier,
                    "data_check_value": event.data_check_value,
                    "is_duplicate": event.is_duplicate,
                }
                for event in result.events
            ]
            for start in range(0, len(rows), _EVENT_INSERT_BATCH):
                db.execute(insert(EldEvent), rows[start:start + _EVENT_INSERT_BATCH])

        _store_issues(db, ef.id, result.issues)

        ef.file_format = result.file_format
        ef.encoding = result.encoding
        ef.delimiter = result.delimiter
        ef.line_count = result.line_count
        ef.row_count = result.row_count
        ef.event_count = len(result.events)
        ef.error_count = result.error_count
        ef.warning_count = result.warning_count
        ef.file_size_bytes = len(content)
        ef.content_sha256 = storage.content_digest(content)
        ef.sections = result.sections or None
        ef.hos_summary = result.hos_summary or None
        for column in _HEADER_COLUMNS:
            setattr(ef, column, result.header.get(column))
        ef.header_metadata = {
            key: value for key, value in result.header.items() if key not in _HEADER_COLUMNS
        } or None
        # RECO-2: the CCFP code is what the FILE carried — None when it carried
        # none. DQ_ELD_LINKED compares this to the crash identifier, so storing
        # None is truthful rather than a fabricated link.
        ef.ccfp_code_in_file = result.ccfp_code
        ef.parsed_at = dt.datetime.now(dt.timezone.utc)
        if ef.parse_started_at is not None:
            ef.parse_duration_ms = int(
                (ef.parsed_at - ef.parse_started_at).total_seconds() * 1000
            )

        # PCI-7: fill the ELD summary fields the post-crash inspection asks for
        # from what the file actually says — but only where a person has not
        # already recorded a value, so extraction never overwrites human entry.
        summary = result.hos_summary or {}
        if ef.last_duty_status is None and summary.get("last_duty_status"):
            ef.last_duty_status = summary["last_duty_status"]
        if ef.last_entry_at is None and summary.get("last_event_at"):
            last_event = eld_format.parse_timestamp(summary["last_event_at"])
            if last_event is not None:
                ef.last_entry_at = last_event
        if ef.eld_downloaded is None:
            ef.eld_downloaded = True  # a readable file IS evidence of a download

        status = (
            EldUploadStatus.PARSED_WITH_ERRORS.value
            if result.has_errors
            else EldUploadStatus.PARSED.value
        )
        ef.upload_status = status
        if result.has_errors:
            blocking = result.first_error()
            ef.error_code = blocking.code if blocking else EldErrorCode.INTERNAL
            ef.error_message = blocking.message if blocking else None
            _notify_parse_outcome(db, ef, status, ef.error_message or "See the file's parse issues.")

        db.commit()
        return {
            "eld_file_id": str(ef.id),
            "status": status,
            "event_count": len(result.events),
            "ccfp_code_in_file": result.ccfp_code,
            "file_format": result.file_format,
            "error_code": ef.error_code,
            "error": ef.error_message,
            "error_count": result.error_count,
            "warning_count": result.warning_count,
            "truncated": result.truncated,
            "sections": result.sections,
            "hos_summary": result.hos_summary,
        }
    except Exception as exc:  # noqa: BLE001 - last resort: never leave PARSING
        # Reaching here means the persistence step itself failed (a database
        # error, a value the schema rejects). The file must not be left mid-parse
        # with no explanation, so the failure is recorded the same way as any other.
        try:
            return _fail_parse(
                db, eld_file_id, EldErrorCode.INTERNAL,
                f"The extracted ELD data could not be stored ({type(exc).__name__}: {exc}). "
                "The uploaded file is intact — retry the extraction from the file's "
                "'Re-run extraction' action, or report this to a System Administrator.",
                started=started,
            )
        except Exception:  # noqa: BLE001 - the DB itself is unusable; surface it
            return {
                "eld_file_id": str(eld_file_id),
                "status": EldUploadStatus.FAILED.value,
                "error_code": EldErrorCode.INTERNAL,
                "error": str(exc),
            }
    finally:
        if own:
            db.close()

# ---------------------------------------------------------------------------
# Quality-control evaluation (documentation §8.8, §5 Phase 5)
# ---------------------------------------------------------------------------
def evaluate_quality(crash_id: uuid.UUID, db: Session | None = None) -> dict:
    own = db is None
    db = db or SessionLocal()
    try:
        crash = db.get(Crash, crash_id)
        if crash is None:
            return {"error": "crash not found"}

        iif = db.scalar(select(InitialIncidentForm).where(InitialIncidentForm.crash_id == crash_id))
        vehicles = list(db.scalars(select(IncidentVehicle).where(IncidentVehicle.crash_id == crash_id)))
        factors = db.scalar(
            select(func.count()).select_from(ContributingFactorSelection)
            .where(ContributingFactorSelection.crash_id == crash_id)
        ) or 0
        present_attr_ids = set(
            db.scalars(
                select(CrashAttributeValue.attribute_id).where(
                    CrashAttributeValue.crash_id == crash_id, CrashAttributeValue.is_current.is_(True)
                )
            )
        )
        required_ids = set(
            db.scalars(
                select(AttributeRequirement.attribute_id).where(
                    AttributeRequirement.study_id == crash.study_id,
                    AttributeRequirement.is_required.is_(True),
                )
            )
        )
        # RECO-2: a genuine link requires an ELD file whose PARSED ccfp_code_in_file
        # equals the crash identifier. Track separately whether *any* ELD file
        # exists so the evaluator can tell "present but unmatched/unparsed" apart
        # from "no ELD file at all".
        # One round-trip answers both questions: how many ELD files exist for the
        # crash, and how many of those carry a matching parsed CCFP code. Two
        # separate queries here cost an extra network round-trip per evaluation
        # for no added information (see the round-trip note on the insert below).
        eld_any, eld_matched = db.execute(
            select(
                func.count(),
                func.count().filter(EldFile.ccfp_code_in_file == crash.ccfp_identifier),
            ).select_from(EldFile).where(EldFile.crash_id == crash_id)
        ).one()
        eld_linked = bool(eld_matched)

        # --- Per-check helpers (DATA-2) ---------------------------------------
        # Each helper carries one rule's logic over the context loaded above so
        # the same body serves both the definition-driven dispatch and the
        # code-keyed fallback, keeping seeded-rule outcomes byte-for-byte stable.
        def _check_iif_exists() -> tuple[str, str]:
            ok = iif is not None and iif.status in ("SUBMITTED", "ROUTED")
            return ("PASS", "Initial Incident Form present.") if ok else ("FAIL", "No submitted Initial Incident Form.")

        def _check_pattern(pattern: str) -> tuple[str, str]:
            # Generalises DQ_DOT_FORMAT: validate CMV U.S. DOT values against the
            # supplied regex. An unparsable pattern is reported, not raised, so a
            # single misconfigured rule cannot abort the whole evaluation run.
            try:
                rx = re.compile(pattern)
            except re.error as exc:
                return ("NOT_EVALUATED", f"Invalid pattern in rule definition: {exc}")
            bad = [v.us_dot_number for v in vehicles if v.is_cmv and v.us_dot_number and not rx.match(v.us_dot_number)]
            return ("FAIL", f"Invalid U.S. DOT format: {bad}") if bad else ("PASS", "U.S. DOT numbers well-formed.")

        def _check_source(source: str) -> tuple[str, str]:
            if source == "SafeSpect":
                ok = bool(iif and iif.dot_number_validated)
                return ("PASS", "U.S. DOT validated via SafeSpect.") if ok else ("FAIL", "U.S. DOT not validated via SafeSpect.")
            if source == "CDLIS":
                # Route each driver through the existing CDLIS adapter (mock
                # until a live client is wired behind integration_cdlis_live) so
                # the rule reflects a real verification verdict rather than mere
                # row existence (documentation §10.1, §13.2, INTE-2). No license
                # column exists in-model, so full_name is the driver identifier
                # and the crash state_code is the jurisdiction.
                drivers = list(
                    db.scalars(
                        select(IncidentPerson).where(
                            IncidentPerson.crash_id == crash_id,
                            IncidentPerson.person_type == "DRIVER",
                        )
                    )
                )
                if not drivers:
                    # Preserve no-driver behaviour so completeness is unchanged.
                    return ("WARNING", "No driver records to validate against CDLIS.")
                results_cdlis = [
                    cdlis.verify_driver(license_number=d.full_name, jurisdiction=crash.state_code)
                    for d in drivers
                ]
                src = results_cdlis[0].get("source", "CDLIS")
                invalid = [r for r in results_cdlis if not r.get("valid")]
                if invalid:
                    return ("WARNING", f"{len(invalid)}/{len(results_cdlis)} driver(s) not validated via {src}.")
                return ("PASS", f"{len(results_cdlis)} driver(s) validated via {src}.")
            return ("NOT_EVALUATED", f"No validator for source '{source}'.")

        def _check_required_attrs() -> tuple[str, str]:
            missing = required_ids - present_attr_ids
            return ("FAIL", f"{len(missing)} required attribute(s) missing.") if missing else ("PASS", "All required attributes present.")

        def _check_min_fatalities(minimum: int) -> tuple[str, str]:
            ok = (crash.num_fatalities or 0) >= minimum
            return ("PASS", f"Fatality count >= {minimum}.") if ok else ("FAIL", f"Qualifying crash must have >= {minimum} fatality.")

        def _check_eld_linked() -> tuple[str, str]:
            # RECO-2: real verification. PASS only when an ELD file's PARSED CCFP
            # code matches the crash identifier. Distinguish "ELD present but its
            # parsed code is missing/does not match" (a genuine warning the analyst
            # must resolve) from "no ELD file uploaded at all".
            if eld_linked:
                return ("PASS", "ELD file linked via CCFP code.")
            if eld_any:
                return ("WARNING", "ELD file present but its CCFP code is missing or does not match the crash identifier.")
            return ("WARNING", "No ELD file linked via CCFP code.")

        def _check_cardinality() -> tuple[str, str]:
            """Every capped multi-select holds no more than its allowed count (GAP-PCR-04).

            ``set_attribute`` already rejects an over-cap write, so this is the
            second line: it catches values that arrived by any other route
            (source ingestion, PCR import) and values that predate a cap being
            tightened. Reports the specific attribute, unit, and counts so the
            analyst can fix it without hunting.
            """
            rows = db.execute(
                select(CrashAttributeValue, DataAttribute)
                .join(DataAttribute, DataAttribute.id == CrashAttributeValue.attribute_id)
                .where(
                    CrashAttributeValue.crash_id == crash_id,
                    CrashAttributeValue.is_current.is_(True),
                    DataAttribute.max_selections.is_not(None),
                )
            ).all()
            over = []
            for cav, da in rows:
                selections = selected_values(cav.value_text, cav.value_json)
                if selections is not None and len(selections) > da.max_selections:
                    where = f" [{cav.unit_type} {cav.unit_number}]" if cav.unit_type else ""
                    over.append(f"{da.code}{where}: {len(selections)}/{da.max_selections}")
            if over:
                return ("FAIL", "Selections exceed the allowed number for: " + "; ".join(sorted(over)))
            if not rows:
                return ("PASS", "No capped multi-select values recorded.")
            return ("PASS", f"All {len(rows)} capped multi-select value(s) within their limits.")

        def _current_attr(code: str) -> str | None:
            """The current crash-level value of one attribute, by code."""
            return db.scalar(
                select(CrashAttributeValue.value_text)
                .join(DataAttribute, DataAttribute.id == CrashAttributeValue.attribute_id)
                .where(
                    CrashAttributeValue.crash_id == crash_id,
                    CrashAttributeValue.is_current.is_(True),
                    DataAttribute.code == code,
                )
            )

        def _check_public_narrative() -> tuple[str, str]:
            """A complete record should carry a public-releasable narrative (GAP-PCR-06).

            The new form separates the Public Narrative from the internal Crash
            Description precisely so the former can be released without
            redaction. If it is missing, the only narrative available is the
            SENSITIVE one — and publishing that would be a disclosure incident.
            So the absence is flagged rather than silently tolerated.

            WARNING, not FAIL: an early-lifecycle crash legitimately has no
            public narrative yet, and this rule must not block a record from
            ever reaching completeness.
            """
            text = _current_attr("C31")
            if text and text.strip():
                return ("PASS", "Public narrative recorded.")
            internal = _current_attr("CX1")
            if internal and internal.strip():
                return (
                    "WARNING",
                    "No public narrative (C31). An internal crash description exists but is "
                    "SENSITIVE and must not be published in its place.",
                )
            return ("WARNING", "No public narrative (C31) recorded for this crash.")

        def _check_pcr_inspection_xref() -> tuple[str, str]:
            """PCR-reported inspection facts must agree with the SafeSpect record (GAP-PCR-07).

            The new form's Crash section repeats inspection identifiers that
            already arrive from SafeSpect, so the same fact now has two sources.
            The gap's instruction is to treat the PCR block as a
            cross-reference, not a second record — which only works if
            disagreement is surfaced. This compares the two and names each
            field that differs.

            Silence is not agreement: when either side is absent there is
            nothing to reconcile, and that is reported as such rather than as a
            pass, so "no inspection ingested yet" cannot masquerade as
            "the sources agree".
            """
            inspection = db.scalar(
                select(PostCrashInspection)
                .where(PostCrashInspection.crash_id == crash_id)
                .order_by(PostCrashInspection.inspection_date.desc().nulls_last())
            )
            pcr_number = _current_attr("C34")
            pcr_officer = _current_attr("C35")
            pcr_type = _current_attr("C36")
            pcr_oos = _current_attr("C37")
            pcr_any = any(v for v in (pcr_number, pcr_officer, pcr_type, pcr_oos))

            if inspection is None and not pcr_any:
                return ("NOT_EVALUATED", "No post-crash inspection reported by either the PCR or SafeSpect.")
            if inspection is None:
                return ("WARNING", "The PCR reports a post-crash inspection but no inspection record has been ingested from SafeSpect.")
            if not pcr_any:
                return ("NOT_EVALUATED", "A SafeSpect inspection exists but the PCR reports no inspection block to reconcile against.")

            def _norm(v) -> str | None:
                if v is None:
                    return None
                s = str(v).strip().lower()
                return {"true": "yes", "false": "no", "y": "yes", "n": "no"}.get(s, s) or None

            mismatches = []
            comparisons = [
                ("report number", pcr_number, inspection.inspection_number),
                ("inspecting officer", pcr_officer, inspection.inspector_name),
                ("inspection type", pcr_type, inspection.inspection_type),
                ("driver out of service", pcr_oos, inspection.driver_oos),
            ]
            for label, pcr_val, safespect_val in comparisons:
                a, b = _norm(pcr_val), _norm(safespect_val)
                # Only a genuine disagreement counts. One side being absent is a
                # gap in collection, not a contradiction between the sources.
                if a is not None and b is not None and a != b:
                    mismatches.append(f"{label} (PCR '{pcr_val}' vs SafeSpect '{safespect_val}')")

            if mismatches:
                return ("FAIL", "PCR and SafeSpect disagree on: " + "; ".join(mismatches))
            return ("PASS", "PCR-reported inspection details agree with the SafeSpect record.")

        def _check_required_count(required_count: int) -> tuple[str, str]:
            # Preserve the seeded DQ_TOP_FACTORS wording ("Three ...") byte-for-
            # byte so its stored data_quality_results row is unchanged; admin
            # rules with other counts get the generic numeric phrasing.
            ok = factors >= required_count
            if ok:
                msg = "Three contributing factors selected." if required_count == 3 else f"{required_count} contributing factors selected."
                return ("PASS", msg)
            return ("WARNING", f"{factors}/{required_count} contributing factors selected.")

        def _check_counts_consistent() -> tuple[str, str]:
            """Internal-consistency (ACCURACY) check on the crash's own numbers.

            The SOO requires "data validations for the completeness *and accuracy*
            of reports". Every other rule here answers "is it present / is it
            well-formed / does it match an external source" — none asks whether
            the record contradicts itself. These contradictions are the ones that
            survive collection and corrupt analysis silently, because each field
            is individually plausible.

            Declared counts are compared against the records actually attached,
            and only a declared value is judged: a NULL count is missing data,
            which DQ_MISSING_REQUIRED_ATTR already owns.
            """
            problems: list[str] = []
            declared_v, declared_p = crash.num_vehicles, crash.num_persons
            declared_f = crash.num_fatalities

            if declared_f is not None and declared_p is not None and declared_f > declared_p:
                problems.append(
                    f"{declared_f} fatalities recorded but only {declared_p} persons involved"
                )
            if declared_v is not None and len(vehicles) > declared_v:
                problems.append(
                    f"{len(vehicles)} vehicle records attached but {declared_v} declared"
                )
            for v in vehicles:
                if v.num_injured_occupants is not None and v.num_occupants is not None \
                        and v.num_injured_occupants > v.num_occupants:
                    problems.append(
                        f"vehicle {v.vehicle_number}: {v.num_injured_occupants} injured "
                        f"of {v.num_occupants} occupants"
                    )
            if problems:
                return ("FAIL", "Crash record contradicts itself: " + "; ".join(problems) + ".")
            return ("PASS", "Declared counts are internally consistent.")

        def _check_date_plausible() -> tuple[str, str]:
            """Range (ACCURACY) check on the crash date.

            A future crash date is impossible, and a date long before the study
            began is a transcription error rather than a real record. Both pass
            every format check, so nothing else in the catalogue catches them.
            """
            if crash.crash_date is None:
                return ("NOT_EVALUATED", "No crash date recorded.")
            today = dt.date.today()
            if crash.crash_date > today:
                return ("FAIL", f"Crash date {crash.crash_date} is in the future.")
            # Ten years is deliberately generous: the point is to catch a
            # mistyped year (e.g. 2016 for 2026), not to police study scope,
            # which the qualifying-crash classifier owns.
            if (today - crash.crash_date).days > 3653:
                return ("WARNING", f"Crash date {crash.crash_date} is more than 10 years old; verify the year.")
            return ("PASS", "Crash date is within a plausible range.")

        # --- Definition-driven dispatch (DATA-2) ------------------------------
        # Interpret only the small, explicit set of definition shapes the seeds
        # use (plus the two named `check` keys). No general DSL. Returns None
        # when the definition carries no recognised key, so the caller falls
        # back to the legacy code-keyed switch.
        def dispatch_definition(definition) -> tuple[str, str] | None:
            if not isinstance(definition, dict) or not definition:
                return None
            if "pattern" in definition:
                return _check_pattern(definition["pattern"])
            if definition.get("scope") == "required_attributes":
                return _check_required_attrs()
            if "source" in definition:
                return _check_source(definition["source"])
            if "min_fatalities" in definition:
                return _check_min_fatalities(int(definition["min_fatalities"]))
            if "required_count" in definition:
                return _check_required_count(int(definition["required_count"]))
            check_key = definition.get("check")
            if check_key == "initial_incident_form_exists":
                return _check_iif_exists()
            if check_key == "eld_ccfp_code":
                return _check_eld_linked()
            if check_key == "cardinality":
                return _check_cardinality()
            if check_key == "counts_consistent":
                return _check_counts_consistent()
            if check_key == "date_plausible":
                return _check_date_plausible()
            if check_key == "public_narrative":
                return _check_public_narrative()
            if check_key == "pcr_inspection_xref":
                return _check_pcr_inspection_xref()
            return None

        def check(code: str) -> tuple[str, str]:
            if code == "DQ_MISSING_IIF":
                return _check_iif_exists()
            if code == "DQ_DOT_FORMAT":
                return _check_pattern(_DOT_RE.pattern)
            if code == "DQ_DOT_SAFESPECT":
                return _check_source("SafeSpect")
            if code == "DQ_MISSING_REQUIRED_ATTR":
                return _check_required_attrs()
            if code == "DQ_FATALITY_COUNT":
                return _check_min_fatalities(1)
            if code == "DQ_CDLIS_CHECK":
                return _check_source("CDLIS")
            if code == "DQ_ELD_LINKED":
                return _check_eld_linked()
            if code == "DQ_TOP_FACTORS":
                return _check_required_count(3)
            if code == "DQ_CARDINALITY":
                return _check_cardinality()
            if code == "DQ_PUBLIC_NARRATIVE":
                return _check_public_narrative()
            if code == "DQ_PCR_INSPECTION_XREF":
                return _check_pcr_inspection_xref()
            return ("NOT_EVALUATED", "No evaluator implemented for this rule.")

        db.query(DataQualityResult).filter(DataQualityResult.crash_id == crash_id).delete()
        rules = list(db.scalars(select(DataQualityRule).where(DataQualityRule.is_active.is_(True))))
        summary = {"PASS": 0, "FAIL": 0, "WARNING": 0, "NOT_EVALUATED": 0}
        results = []
        rows = []
        for rule in rules:
            # Definition-driven first; fall back to the legacy code switch when
            # the definition is null/empty or carries no recognised key, so
            # seeded built-ins keep their exact current PASS/WARNING/FAIL result.
            status, message = dispatch_definition(rule.definition) or check(rule.code)
            summary[status] = summary.get(status, 0) + 1
            rows.append({
                "crash_id": crash_id, "rule_id": rule.id, "attribute_id": rule.attribute_id,
                "status": status, "message": message,
            })
            results.append({"rule": rule.code, "status": status, "message": message})

        # Write every result in ONE multi-row INSERT rather than one INSERT per
        # rule. `id`/`evaluated_at` are server-side defaults, so per-object ORM
        # adds each need their own round-trip; against a remote database that is
        # ~240 ms per rule and made the manual "Run evaluation" trigger take >10 s
        # for a caller that already had nothing to look at. Nothing downstream
        # needs the persisted objects — `results` is built from the rule rows —
        # so a Core insert is both faster and sufficient. All rows share one
        # `evaluated_at` (now()), which is what the UI groups a run by.
        if rows:
            db.execute(insert(DataQualityResult), rows)

        # Notify State CMV Data Analysts on QC failure (documentation §8.11
        # "QC failures"). One summary QC_FAILURE notification per analyst per
        # run lists the failing rule codes so the inbox is actionable; results
        # are re-inserted every run, so a fresh notification matches that
        # per-run semantics. WARNING/NOT_EVALUATED do not notify.
        #
        # De-dup vs NOTI-4: the DQ_MISSING_REQUIRED_ATTR rule gets its own
        # specific, actionable MISSING_DATA notification below (documentation
        # §8.11 "Missing required data"), so it is excluded from the generic
        # QC_FAILURE summary to avoid double-notifying for the same gap.
        # Both notification blocks below address the same audience. Resolving it
        # costs four round-trips (the user rows plus their eagerly-loaded role /
        # permission / access-group collections), so look it up at most once per
        # run and only when there is actually something to send.
        _analysts: list | None = None

        def state_analysts() -> list:
            nonlocal _analysts
            if _analysts is None:
                _analysts = users_with_role(db, "STATE_CMV_ANALYST", state_code=crash.state_code)
            return _analysts

        failed = [
            r["rule"]
            for r in results
            if r["status"] == "FAIL" and r["rule"] != "DQ_MISSING_REQUIRED_ATTR"
        ]
        if failed:
            for analyst in state_analysts():
                create_notification(
                    db,
                    recipient_user_id=analyst.id,
                    notification_type="QC_FAILURE",
                    title="QC checks failed",
                    message=(
                        f"{len(failed)} quality-control rule(s) failed for "
                        f"{crash.ccfp_identifier}: {', '.join(failed)}."
                    ),
                    crash_id=crash_id,
                )

        # Notify the responsible State CMV Data Analyst(s) when required
        # canonical attributes are missing (documentation §8.11 "Missing
        # required data", NOTI-4). The required/present id sets were computed
        # once above (the same sets behind the DQ_MISSING_REQUIRED_ATTR rule),
        # so the missing set is available here. A targeted MISSING_DATA
        # notification carries the count of missing required attributes and is
        # the canonical, actionable signal for this gap (kept distinct from the
        # generic QC_FAILURE summary, which excludes this rule above).
        missing = required_ids - present_attr_ids
        if missing:
            for analyst in state_analysts():
                create_notification(
                    db,
                    recipient_user_id=analyst.id,
                    notification_type="MISSING_DATA",
                    title="Missing required data",
                    message=(
                        f"{len(missing)} required attribute(s) are missing for "
                        f"{crash.ccfp_identifier}."
                    ),
                    crash_id=crash_id,
                )

        # Commit only when this call owns the session. A caller that supplied its
        # own session (the API route) also writes the audit row and the phase
        # advance for the same action, and committing here would split those
        # across two transactions — leaving QC results persisted with no
        # EVALUATE_QC audit trail if a later step failed. Flush so the rows are
        # visible to the rest of the caller's transaction.
        if own:
            db.commit()
        else:
            db.flush()
        return {"crash_id": str(crash_id), "summary": summary, "results": results}
    finally:
        if own:
            db.close()


# ---------------------------------------------------------------------------
# Missing-IIF cross-crash detector (documentation §8.11, §12.4) — NOTI-5
# ---------------------------------------------------------------------------
def _resolve_iif_window_hours(
    db: Session, window_hours: int | None, study_id: uuid.UUID | None
) -> int:
    """Resolve the missing-IIF window (NOTI-5). Precedence: an explicit
    ``window_hours`` argument > a per-study ``iif_window_hours`` parameter (when a
    ``study_id`` is given) > the module default. Never an inline Phase-1 literal,
    so future phases retune the SLA via the study parameter without a code change.
    """
    if window_hours is not None:
        return int(window_hours)
    if study_id is not None:
        param = db.scalar(
            select(StudyParameter).where(
                StudyParameter.study_id == study_id,
                StudyParameter.param_key == "iif_window_hours",
            )
        )
        if param is not None:
            try:
                value = param.param_value
                # Accept a bare number or a {"hours": N} / {"value": N} wrapper.
                if isinstance(value, dict):
                    value = value.get("hours", value.get("value"))
                if value is not None:
                    return int(value)
            except (TypeError, ValueError):
                pass
    return DEFAULT_IIF_WINDOW_HOURS


def scan_crashes_missing_iif(
    db: Session | None = None,
    window_hours: int | None = None,
    study_id: uuid.UUID | None = None,
) -> dict:
    """Flag crashes aged past the IIF window with no submitted IIF (NOTI-5, §8.11).

    In-process, on-demand detector (no scheduler/cron): selects crashes whose
    ``created_at`` is older than ``now - window_hours`` and that have NO
    InitialIncidentForm in status SUBMITTED/ROUTED, and emits a ``MISSING_IIF``
    notification to the State CMV Data Analyst(s) in each crash's State. Returns
    ``{"flagged": N}``.

    Idempotent within and across runs: a crash already carrying an *unread*
    ``MISSING_IIF`` notification for the SAME analyst is skipped, so re-running
    does not spam duplicates. (Once an analyst reads/clears it, a later scan can
    re-flag a still-stale crash — the actionable signal is not lost.) The caller
    commits via this function's own ``db.commit()`` when it owns the session.
    """
    own = db is None
    db = db or SessionLocal()
    try:
        resolved_window = _resolve_iif_window_hours(db, window_hours, study_id)
        cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=resolved_window)

        # Crashes that DO have a submitted/routed IIF are excluded.
        submitted_iif = select(InitialIncidentForm.crash_id).where(
            InitialIncidentForm.status.in_(("SUBMITTED", "ROUTED"))
        )
        stale_stmt = select(Crash).where(
            Crash.created_at < cutoff,
            Crash.id.notin_(submitted_iif),
        )
        if study_id is not None:
            stale_stmt = stale_stmt.where(Crash.study_id == study_id)
        stale = list(db.scalars(stale_stmt))

        flagged = 0
        for crash in stale:
            analysts = users_with_role(db, "STATE_CMV_ANALYST", state_code=crash.state_code)
            notified_any = False
            for analyst in analysts:
                # Idempotency: skip if this analyst already has an unread
                # MISSING_IIF notification for this crash (no duplicate spam).
                existing = db.scalar(
                    select(func.count())
                    .select_from(Notification)
                    .where(
                        Notification.recipient_user_id == analyst.id,
                        Notification.crash_id == crash.id,
                        Notification.notification_type == NotificationType.MISSING_IIF.value,
                        Notification.read_at.is_(None),
                    )
                ) or 0
                if existing:
                    continue
                create_notification(
                    db,
                    recipient_user_id=analyst.id,
                    notification_type=NotificationType.MISSING_IIF,
                    title="Crash missing Initial Incident Form",
                    message=(
                        f"{crash.ccfp_identifier} has no submitted Initial Incident "
                        f"Form after {resolved_window}h."
                    ),
                    crash_id=crash.id,
                )
                notified_any = True
            if notified_any:
                flagged += 1
        db.commit()
        return {"flagged": flagged, "window_hours": resolved_window}
    finally:
        if own:
            db.close()


# ---------------------------------------------------------------------------
# Completeness token registry (documentation §3.4 Configurability, §5 Phase 5)
# ---------------------------------------------------------------------------
# Completeness checks are *data-driven*: a study's CompletenessRule carries a
# `definition` JSON of the shape
#     {"requires": ["<token>", ...], "params": {"<param>": <int>, ...}}
# and the evaluator resolves each token against this code-owned registry rather
# than a hardcoded switch. Each registry entry is a small evaluator callable
# `(facts, params) -> bool` plus the parameter names (with defaults) it reads,
# so thresholds (e.g. how many contributing factors are required) live in the
# rule definition and differ per study/per rule without a code change. This
# mirrors the definition-driven QC dispatch above (DATA-2) and keeps the five
# seeded single-token rules byte-for-byte identical, because a rule with no
# `params` resolves each token at its documented default.
@dataclasses.dataclass
class CompletenessFacts:
    """Gathered crash facts a completeness token may inspect."""

    iif: Any
    inspections: int
    factors: int
    required_ids: set
    present_attr_ids: set
    critical_failures: int


# Parameter name -> default, per token. Defaults reproduce the prior literals
# (`>= 3` factors, `> 0` inspections) so seeded rules are unchanged.
COMPLETENESS_TOKEN_PARAMS: dict[str, dict[str, int]] = {
    "initial_incident_submitted": {},
    "required_attributes_present": {},
    "post_crash_inspection_exists": {"min_post_crash_inspections": 1},
    "three_contributing_factors": {"min_contributing_factors": 3},
    "no_critical_qc_failures": {},
}

# token -> callable(facts, params) -> bool. Thresholded tokens read their
# parameter from `params`, falling back to the documented default above so a
# rule that omits `params` behaves exactly as the old hardcoded literal did.
COMPLETENESS_TOKENS: dict[str, Callable[[CompletenessFacts, dict], bool]] = {
    "initial_incident_submitted": lambda f, p: f.iif is not None
    and f.iif.status in ("SUBMITTED", "ROUTED"),
    "required_attributes_present": lambda f, p: f.required_ids.issubset(f.present_attr_ids),
    "post_crash_inspection_exists": lambda f, p: f.inspections
    >= int(p.get("min_post_crash_inspections", 1)),
    "three_contributing_factors": lambda f, p: f.factors
    >= int(p.get("min_contributing_factors", 3)),
    "no_critical_qc_failures": lambda f, p: f.critical_failures == 0,
}

# Public token vocabulary — imported by features/studies.py for write-time
# validation and surfaced via the read endpoint that drives the UI builder, so
# the API, the UI, and the evaluator share one source of truth.
COMPLETENESS_TOKEN_NAMES: frozenset[str] = frozenset(COMPLETENESS_TOKENS)


def completeness_token_catalog() -> list[dict]:
    """Token vocabulary + each token's numeric parameter names and defaults.

    Shape per entry: ``{"token": str, "params": [{"name": str, "default": int}]}``.
    Consumed by ``GET /completeness-rule-tokens`` so the rule-builder UI renders a
    backend-driven picker instead of a hardcoded list.
    """
    return [
        {
            "token": token,
            "params": [
                {"name": name, "default": default}
                for name, default in COMPLETENESS_TOKEN_PARAMS[token].items()
            ],
        }
        for token in sorted(COMPLETENESS_TOKENS)
    ]


# ---------------------------------------------------------------------------
# Completeness evaluation (documentation §5 Phase 5, §8.8)
# ---------------------------------------------------------------------------
def evaluate_completeness(
    crash_id: uuid.UUID, db: Session | None = None, changed_by: uuid.UUID | None = None
) -> dict:
    own = db is None
    db = db or SessionLocal()
    try:
        crash = db.get(Crash, crash_id)
        if crash is None:
            return {"error": "crash not found"}

        iif = db.scalar(select(InitialIncidentForm).where(InitialIncidentForm.crash_id == crash_id))

        # The three counts are independent aggregates over unrelated tables, so
        # they answer in ONE round-trip as scalar subqueries of a single SELECT.
        # Issued separately they cost three, and against a remote database a
        # round-trip is ~250-300 ms — the difference between a manual "Evaluate"
        # feeling instant and looking like it never fired (see the connection
        # note on the caller in features/crashes.py).
        inspections, factors, critical_failures = db.execute(
            select(
                select(func.count()).select_from(PostCrashInspection)
                .where(PostCrashInspection.crash_id == crash_id)
                .scalar_subquery(),
                select(func.count()).select_from(ContributingFactorSelection)
                .where(ContributingFactorSelection.crash_id == crash_id)
                .scalar_subquery(),
                select(func.count()).select_from(DataQualityResult)
                .join(DataQualityRule, DataQualityRule.id == DataQualityResult.rule_id)
                .where(
                    DataQualityResult.crash_id == crash_id,
                    DataQualityResult.status == "FAIL",
                    DataQualityRule.severity.in_(("ERROR", "CRITICAL")),
                )
                .scalar_subquery(),
            )
        ).one()

        # Both attribute-id sets are plain id lists, so one UNION ALL carrying a
        # discriminator column fetches them together instead of in two
        # round-trips. The partition below reproduces the two sets exactly.
        attr_rows = db.execute(
            select(literal("present").label("kind"), CrashAttributeValue.attribute_id)
            .where(
                CrashAttributeValue.crash_id == crash_id,
                CrashAttributeValue.is_current.is_(True),
            )
            .union_all(
                select(literal("required"), AttributeRequirement.attribute_id).where(
                    AttributeRequirement.study_id == crash.study_id,
                    AttributeRequirement.is_required.is_(True),
                )
            )
        ).all()
        present_attr_ids = {aid for kind, aid in attr_rows if kind == "present"}
        required_ids = {aid for kind, aid in attr_rows if kind == "required"}

        # Gather the crash facts once; every token evaluator reads from these.
        facts = CompletenessFacts(
            iif=iif,
            inspections=inspections,
            factors=factors,
            required_ids=required_ids,
            present_attr_ids=present_attr_ids,
            critical_failures=critical_failures,
        )
        # `checks` mirrors the prior return shape (token -> bool) so nothing
        # downstream breaks; it now reflects each token resolved at its DEFAULT
        # params (the rule-agnostic view). Per-rule thresholds are applied in
        # the rule loop below using each rule's own `params`.
        checks = {token: fn(facts, {}) for token, fn in COMPLETENESS_TOKENS.items()}

        rules = list(db.scalars(select(CompletenessRule).where(
            CompletenessRule.study_id == crash.study_id, CompletenessRule.is_active.is_(True))))
        missing = []
        for rule in rules:
            definition = rule.definition or {}
            requires = definition.get("requires", [])
            # Accept either `params` or `thresholds`; per-rule so two rules in
            # one study can require different thresholds.
            params = definition.get("params") or definition.get("thresholds") or {}
            for token in requires:
                evaluator = COMPLETENESS_TOKENS.get(token)
                if evaluator is None:
                    # Unknown token must SURFACE, not silently block completeness:
                    # mark it distinctly so a reviewer sees a misconfiguration
                    # rather than a phantom incompleteness. (Write-time
                    # validation in studies.py prevents most of these.)
                    missing.append({"rule": rule.name, "unmet": token, "unknown_token": True})
                elif not evaluator(facts, params):
                    missing.append({"rule": rule.name, "unmet": token})
        status = CompletenessStatus.COMPLETE.value if not missing else CompletenessStatus.INCOMPLETE.value

        # Append-only history: clear the current flag, then insert the new
        # current row. RETURNING hands back the status of the very row being
        # superseded, which is exactly the "prior status" the fire-on-change
        # check needs — so the read and the write share one round-trip instead
        # of taking one each (documentation §8.11 "Completed record status
        # changes"). No current row (first-ever evaluation) returns None, which
        # correctly counts as a transition below.
        prev = db.execute(
            update(CrashCompletenessStatus)
            .where(
                CrashCompletenessStatus.crash_id == crash_id,
                CrashCompletenessStatus.is_current.is_(True),
            )
            .values(is_current=False)
            .returning(CrashCompletenessStatus.status)
            .execution_options(synchronize_session=False)
        ).scalar()
        db.add(
            CrashCompletenessStatus(
                crash_id=crash_id, status=status, is_current=True, is_locked=False,
                missing_summary={"missing": missing}, changed_by=changed_by,
            )
        )

        # Fire-on-change only: notify State CMV Data Analysts (State-scoped) and
        # the CCFP Project Team when the completeness status actually changes.
        if status != prev:
            title = (
                "Record marked complete"
                if status == CompletenessStatus.COMPLETE.value
                else "Record now incomplete"
            )
            message = f"{crash.ccfp_identifier} completeness status changed to {status}."
            recipients = users_with_role(db, "STATE_CMV_ANALYST", state_code=crash.state_code)
            recipients += users_with_role(db, "CCFP_PROJECT_TEAM")
            seen: set[uuid.UUID] = set()
            for recipient in recipients:
                if recipient.id in seen:
                    continue
                seen.add(recipient.id)
                create_notification(
                    db,
                    recipient_user_id=recipient.id,
                    notification_type="COMPLETENESS_CHANGE",
                    title=title,
                    message=message,
                    crash_id=crash_id,
                )

        # Commit only when this call owns the session. A caller that supplied
        # its own session (the API route) also writes the audit row, the lock
        # flag, and the phase advance for the same action, and committing here
        # would split those across two transactions — leaving a status change
        # persisted with no audit trail if a later step failed. Flush so the
        # rows are visible to the rest of the caller's transaction.
        if own:
            db.commit()
        else:
            db.flush()
        return {"crash_id": str(crash_id), "status": status, "checks": checks, "missing": missing}
    finally:
        if own:
            db.close()
