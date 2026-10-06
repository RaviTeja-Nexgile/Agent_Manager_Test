"""Crash records: CRUD, lifecycle, scope, aggregated attributes, QC, completeness
(documentation §12.3, §5, §8.8)."""
from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.common import ORMModel, selected_values
from app.core.audit import record_audit
from app.core.database import get_db
from app.core.errors import BadRequest, Conflict, Forbidden, NotFound
from app.core.notifications import create_notification, users_with_role
from app.core.pagination import Page, PageParams, paginate
from app.core.permissions import (
    assert_crash_access,
    assert_study_access,
    require,
    scope_crash_query,
    scope_study_query,
)
from app.core.security import CurrentUser
from app.enums import CompletenessStatus, CrashLifecyclePhase, CrashScope, FormStatus, StudyStatus
from app.models import (
    AuditLog,
    Crash,
    CrashAttributeValue,
    CrashCompletenessStatus,
    CrashScopeClassification,
    DataAttribute,
    DataQualityResult,
    DataQualityRule,
    IncidentVehicle,
    InitialIncidentForm,
    RefRepeatUnit,
    SourceRecord,
    Study,
    StudyParameter,
    StudyState,
    User,
)
from app.workers import (
    evaluate_completeness,
    evaluate_quality,
    scan_crashes_missing_iif,
)

# Lifecycle ordering: declaration order in CrashLifecyclePhase IS the lifecycle
# order (documentation §5). Build the index map from the enum so a future phase
# inserted in the enum stays in sync here without a second source of truth.
PHASE_ORDER: dict[str, int] = {p.value: i for i, p in enumerate(CrashLifecyclePhase)}

router = APIRouter(prefix="/crashes", tags=["crashes"])


# --------------------------------------------------------------------------- schemas
class CrashIn(BaseModel):
    study_id: uuid.UUID
    local_report_number: str | None = None
    crash_date: dt.date | None = None
    crash_time: dt.time | None = None
    city: str | None = None
    county: str | None = None
    state_code: str | None = None
    street_highway: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    num_vehicles: int | None = None
    num_persons: int | None = None
    num_fatalities: int | None = None


class CrashUpdate(BaseModel):
    local_report_number: str | None = None
    crash_date: dt.date | None = None
    crash_time: dt.time | None = None
    city: str | None = None
    county: str | None = None
    state_code: str | None = None
    street_highway: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    num_vehicles: int | None = None
    num_persons: int | None = None
    num_fatalities: int | None = None
    lifecycle_phase: CrashLifecyclePhase | None = None


class CrashOut(ORMModel):
    id: uuid.UUID
    ccfp_identifier: str
    study_id: uuid.UUID
    local_report_number: str | None
    crash_date: dt.date | None
    crash_time: dt.time | None
    city: str | None
    county: str | None
    state_code: str | None
    street_highway: str | None
    latitude: float | None
    longitude: float | None
    num_vehicles: int | None
    num_persons: int | None
    num_fatalities: int | None
    lifecycle_phase: str
    created_by: uuid.UUID | None
    created_at: dt.datetime


class ScopeIn(BaseModel):
    is_qualifying: bool = False
    scope: CrashScope = CrashScope.UNDETERMINED
    is_supplemental: bool = False
    classification_reason: str | None = None


class AdvancePhaseIn(BaseModel):
    target_phase: CrashLifecyclePhase


class ScopeOut(ORMModel):
    id: uuid.UUID
    crash_id: uuid.UUID
    is_qualifying: bool
    scope: str
    is_supplemental: bool
    classification_reason: str | None
    # True when a human set this value through PUT /scope; automatic
    # re-derivation leaves it alone. Surfaced so the UI can label the
    # classification as manually overridden rather than system-derived.
    is_manual_override: bool = False


class AttributeValueIn(BaseModel):
    attribute_code: str
    value_text: str | None = None
    value_json: Any | None = None
    source_system: str | None = None
    confidence: float | None = None
    # Optional precise lineage pointer (DATA-5, §11.3 line 505): the source_records
    # row this canonical value was derived from. Validated in set_attribute to
    # belong to *this* crash. `source_system` stays as the human-readable label.
    source_record_id: uuid.UUID | None = None
    # Repeat discriminator (GAP-PCR-03): which unit this value belongs to, e.g.
    # TRAILER 2 or VEHICLE 3. Omit both for a crash-level attribute. Which of the
    # two is legal is decided by the attribute's own `repeats_on`, not by the
    # caller — see `_resolve_unit`.
    unit_type: str | None = None
    unit_number: int | None = None


class AttributeValueOut(BaseModel):
    attribute_id: uuid.UUID
    code: str
    name: str
    pcr_section: str | None
    sensitivity: str
    value_text: str | None
    value_json: Any | None
    source_system: str | None
    confidence: float | None
    is_edited: bool
    # Precise source-record lineage pointer (DATA-5, §11.3): null when the value
    # carries only a free-text `source_system` label and no linked source record.
    source_record_id: uuid.UUID | None = None
    redacted: bool = False
    # Repeat metadata (GAP-PCR-03). `unit_type`/`unit_number` locate the value;
    # `repeats_on`/`max_selections`/`applies_to` describe the attribute itself so
    # the UI can group by unit and render cardinality without a second request.
    unit_type: str | None = None
    unit_number: int | None = None
    repeats_on: str | None = None
    max_selections: int | None = None
    applies_to: str | None = None


class AttributeHistoryEntry(BaseModel):
    """One version of a crash attribute value (DATA-6, documentation §8.8).

    Surfaces an already-retained superseded/current row so the UI can render a
    per-attribute timeline ("tracking every update by user and timestamp") and
    diff consecutive values. Sensitivity redaction mirrors ``AttributeValueOut``:
    ``value_text``/``value_json`` are nulled and ``redacted=True`` when the caller
    fails ``can_view_sensitivity`` for the attribute.
    """

    value_id: uuid.UUID
    value_text: str | None
    value_json: Any | None
    source_system: str | None
    confidence: float | None
    is_current: bool
    is_edited: bool
    edited_by: uuid.UUID | None
    edited_by_name: str | None
    edited_at: dt.datetime | None
    created_at: dt.datetime
    # Which repeat unit this version belongs to (GAP-PCR-03). Null for a
    # crash-level attribute. Carried per entry so an unscoped history call
    # (every unit at once) is still readable.
    unit_type: str | None = None
    unit_number: int | None = None
    redacted: bool = False


class AttributeHistoryOut(BaseModel):
    """The full version history for one crash attribute, newest-first."""

    attribute_id: uuid.UUID
    code: str
    name: str
    pcr_section: str | None
    sensitivity: str
    versions: list[AttributeHistoryEntry]
    # The attribute's repeat unit (GAP-PCR-03), so a caller can tell whether the
    # returned versions span several units or are inherently crash-level.
    repeats_on: str | None = None


class QcResultOut(BaseModel):
    rule_code: str
    rule_name: str
    severity: str
    status: str
    message: str | None
    evaluated_at: dt.datetime


class CompletenessOut(ORMModel):
    status: str
    is_locked: bool
    missing_summary: Any | None
    changed_at: dt.datetime


class TimelineEntry(BaseModel):
    action: str
    entity_type: str
    actor_user_id: uuid.UUID | None
    occurred_at: dt.datetime
    after_state: Any | None
    # Lifecycle-phase derivation (CRAS-6): set when an audit row represents a
    # transition into a phase, so the UI can render it as a milestone on the
    # phase rail rather than a generic audit row. Non-transition audits leave
    # phase=None / is_milestone=False.
    phase: str | None = None
    is_milestone: bool = False


class SourceRecordOut(ORMModel):
    id: uuid.UUID
    source_system: str
    source_type: str
    external_id: str | None
    raw_zone_uri: str | None
    provenance_note: str | None
    received_at: dt.datetime


# --------------------------------------------------------------------------- helpers
def load_crash(db: Session, crash_id: uuid.UUID, current: CurrentUser) -> Crash:
    crash = db.get(Crash, crash_id)
    if crash is None:
        raise NotFound("Crash")
    assert_crash_access(crash, current)
    # AUTH-2: enforce study scope on the detail path and every /{crash_id}/...
    # sub-resource at once (they all route through load_crash).
    assert_study_access(crash, current)
    return crash


def _is_crash_locked(db: Session, crash_id: uuid.UUID) -> bool:
    """Return whether the crash's *current* completeness row is locked (DATA-1, §8.8).

    A complete record is locked on completion; edits are rejected until an
    authorized user unlocks it via ``POST /crashes/{id}/unlock`` (§12.3). A crash
    with no completeness row yet is not locked.
    """
    return bool(
        db.scalar(
            select(CrashCompletenessStatus.is_locked).where(
                CrashCompletenessStatus.crash_id == crash_id,
                CrashCompletenessStatus.is_current.is_(True),
            )
        )
    )


def _assert_not_locked(db: Session, crash_id: uuid.UUID) -> None:
    """Reject edits on a locked (complete) crash with 409 (DATA-1, §8.8).

    Distinct from a permission ``Forbidden`` (403): the caller may be authorized
    but the record is frozen until an authorized unlock restores editability.
    """
    if _is_crash_locked(db, crash_id):
        raise Conflict("Crash record is locked; unlock it before editing.")


# Default CCFP identifier scheme (CRAS-7, documentation §3.4, §11.3). The format
# stays study-configurable via the `ccfp_identifier_scheme` study parameter; this
# default reproduces the original Phase-1 shape (CCFP-{year}-{state}-{6-digit seq})
# so existing identifiers and tests are unaffected when no scheme is configured.
_CCFP_SCHEME_PARAM_KEY = "ccfp_identifier_scheme"
_DEFAULT_CCFP_TEMPLATE = "CCFP-{year}-{state}-{seq}"
_DEFAULT_CCFP_SEQ_WIDTH = 6


def _generate_ccfp_identifier(db: Session, crash: CrashIn) -> str:
    """Mint a stable, study-configurable CCFP identifier (CRAS-7, §3.4 / §11.3).

    The scheme is read from `study_parameters` (param_key
    ``ccfp_identifier_scheme``) so the format is not hardcoded to Phase-1
    assumptions — mirroring how scope reads ``qualifying_rule``. The JSONB value
    may carry ``{"template": "...", "seq_width": N}`` with the placeholders
    ``{study_code}``, ``{year}``, ``{state}`` and ``{seq}`` (zero-padded to
    ``seq_width``). When no scheme is configured the default template reproduces
    the original ``CCFP-{year}-{state}-{seq:06d}`` shape.

    Race-safety: the sequence number comes from the database SEQUENCE
    ``ccfp_identifier_seq`` via ``nextval`` — atomic, so two concurrent
    ``create_crash`` calls always receive distinct integers and can never mint
    the same identifier (the old ``COUNT(*)+1`` read was a check-then-act race
    that collided against the ``UNIQUE`` constraint on ``crashes.ccfp_identifier``).
    The ``nextval`` runs inside the caller's transaction, committing with the
    insert. Numbers are global/monotonic across studies and States; the template
    still embeds year+state so identifiers stay human-readable, and the global
    sequence keeps them unique without retry.
    """
    year = (crash.crash_date or dt.date.today()).year
    state = (crash.state_code or "US").upper()

    # Per-study scheme (configurable; falls back to the Phase-1 default).
    template = _DEFAULT_CCFP_TEMPLATE
    seq_width = _DEFAULT_CCFP_SEQ_WIDTH
    study = db.get(Study, crash.study_id)
    scheme_row = db.scalar(
        select(StudyParameter).where(
            StudyParameter.study_id == crash.study_id,
            StudyParameter.param_key == _CCFP_SCHEME_PARAM_KEY,
        )
    )
    scheme = (
        scheme_row.param_value
        if scheme_row and isinstance(scheme_row.param_value, dict)
        else {}
    )
    configured_template = scheme.get("template")
    if isinstance(configured_template, str) and configured_template.strip():
        template = configured_template
    configured_width = scheme.get("seq_width")
    if isinstance(configured_width, int) and configured_width > 0:
        seq_width = configured_width

    # Race-safe monotonic number from the DB sequence (atomic nextval).
    next_num = db.scalar(select(func.nextval("ccfp_identifier_seq")))
    seq = f"{int(next_num):0{seq_width}d}"

    study_code = study.code if study is not None else ""
    try:
        return template.format(
            study_code=study_code, year=year, state=state, seq=seq,
        )
    except (KeyError, IndexError, ValueError):
        # A misconfigured template must never break crash creation — fall back to
        # the safe Phase-1 default so an identifier is always issued.
        return _DEFAULT_CCFP_TEMPLATE.format(
            study_code=study_code, year=year, state=state,
            seq=f"{int(next_num):0{_DEFAULT_CCFP_SEQ_WIDTH}d}",
        )


def _study_params(db: Session, study_id: uuid.UUID) -> dict[str, Any]:
    """All `study_parameters` rows for a study as a {param_key: param_value} dict."""
    return {
        row.param_key: row.param_value
        for row in db.scalars(
            select(StudyParameter).where(StudyParameter.study_id == study_id)
        )
    }


def _as_number(value: Any) -> float | None:
    """Coerce a JSON study-parameter value to a float, or None if it isn't numeric.

    `param_value` is jsonb, so a parameter may arrive as 26001, "26001", or
    {"value": 26001} depending on how it was seeded or edited through the UI.
    """
    if isinstance(value, dict):
        value = value.get("value")
    if isinstance(value, bool) or value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_class_set(value: Any) -> set[str]:
    """Coerce a JSON study-parameter value to a set of vehicle-class strings.

    Accepts ["7","8"], [7,8], "7,8" and {"value": [...]} so a study configured
    through the parameters UI behaves the same as the seeded one.
    """
    if isinstance(value, dict):
        value = value.get("value")
    if value is None:
        return set()
    if isinstance(value, str):
        return {part.strip() for part in value.split(",") if part.strip()}
    if isinstance(value, (list, tuple, set)):
        return {str(v).strip() for v in value if str(v).strip()}
    return {str(value).strip()}


def _vehicle_is_heavy_duty(
    vehicle: IncidentVehicle, classes: set[str], min_gvwr: float | None
) -> tuple[bool, bool]:
    """Decide whether one incident vehicle meets the study's heavy-duty criterion.

    Returns ``(is_heavy_duty, used_proxy)``. Evidence is taken in descending order
    of authority (documentation §3.1):

      1. ``vehicle_class`` against the study's configured `vehicle_classes`
         (Phase 1: 7 and 8) — the criterion the BRD actually defines.
      2. ``gvwr_lbs`` against the configured `min_gvwr_lbs` (Phase 1: 26,001).
      3. the ``is_cmv`` checkbox, as a documented fallback when neither is
         recorded. ``used_proxy`` is True in that case so the caller can say so in
         the classification reason instead of implying the class was verified.

    A vehicle whose class IS recorded and is outside the configured set does NOT
    qualify, even when is_cmv is ticked — a Class 3 box truck is a commercial
    motor vehicle but not a Phase 1 heavy-duty truck.
    """
    recorded_class = (vehicle.vehicle_class or "").strip()
    if recorded_class and classes:
        return recorded_class in classes, False
    gvwr = None if vehicle.gvwr_lbs is None else float(vehicle.gvwr_lbs)
    if gvwr is not None and min_gvwr is not None:
        return gvwr >= min_gvwr, False
    return bool(vehicle.is_cmv), True


def classify_scope(db: Session, crash: Crash) -> tuple[bool, CrashScope, str]:
    """Derive (is_qualifying, scope, reason) from the study's configured criteria.

    Reads the qualifying rule from `study_parameters` (`qualifying_rule`, plus the
    `vehicle_classes` / `min_gvwr_lbs` criterion parameters) and participating-State
    membership from `study_states` — nothing is hardcoded (documentation §3.1, §5).
    Phase 1 rule: fatalities >= min_fatalities AND, when `requires_heavy_duty_truck`,
    at least one incident vehicle meeting the configured class/GVWR criterion.
    Side-effect free: takes the ORM crash and returns a tuple.

    Scope resolution:
      * UNDETERMINED — required facts not yet known (num_fatalities is null, or the
        rule needs a heavy-duty truck but no vehicles are recorded yet).
      * OUT_OF_SCOPE — not qualifying, or the crash State is not a participating
        State for the study.
      * IN_SCOPE — qualifying AND the State participates.
    """
    params = _study_params(db, crash.study_id)
    raw_rule = params.get("qualifying_rule")
    rule = raw_rule if isinstance(raw_rule, dict) else {}
    min_fatalities = int(rule.get("min_fatalities", 1))
    requires_truck = bool(rule.get("requires_heavy_duty_truck", True))
    # The criterion parameters may live either inside qualifying_rule or as their
    # own study_parameters rows (how Phase 1 is seeded); the rule wins when both
    # are present, so a study can override the defaults without editing seeds.
    classes = _as_class_set(rule.get("vehicle_classes", params.get("vehicle_classes")))
    min_gvwr = _as_number(rule.get("min_gvwr_lbs", params.get("min_gvwr_lbs")))

    vehicles = list(
        db.scalars(select(IncidentVehicle).where(IncidentVehicle.crash_id == crash.id))
    )

    # Facts not yet known -> cannot decide qualification.
    if crash.num_fatalities is None or (requires_truck and not vehicles):
        missing = []
        if crash.num_fatalities is None:
            missing.append("fatality count")
        if requires_truck and not vehicles:
            missing.append("incident vehicles")
        return False, CrashScope.UNDETERMINED, (
            f"Undetermined: {' and '.join(missing)} not yet recorded."
        )

    verdicts = [_vehicle_is_heavy_duty(v, classes, min_gvwr) for v in vehicles]
    heavy_duty = [v for v, (ok, _) in zip(vehicles, verdicts) if ok]
    # True only when the qualifying decision actually rested on the is_cmv proxy,
    # i.e. at least one vehicle counted as heavy-duty without a recorded class or
    # GVWR. Surfaced in the reason so a reviewer can tell a verified Class 7/8
    # determination from an unverified one.
    used_proxy = any(proxy for (ok, proxy) in verdicts if ok)

    meets_fatalities = (crash.num_fatalities or 0) >= min_fatalities
    meets_truck = (not requires_truck) or bool(heavy_duty)
    is_qualifying = meets_fatalities and meets_truck

    criterion = []
    if classes:
        criterion.append("class " + "/".join(sorted(classes)))
    if min_gvwr is not None:
        criterion.append(f"GVWR >= {min_gvwr:,.0f} lbs")
    criterion_text = " or ".join(criterion) if criterion else "commercial motor vehicle"
    proxy_note = (
        " (heavy-duty inferred from the commercial-motor-vehicle flag; no vehicle "
        "class or GVWR recorded)"
        if used_proxy and meets_truck
        else ""
    )

    participating = db.scalar(
        select(StudyState).where(
            StudyState.study_id == crash.study_id,
            StudyState.state_code == crash.state_code,
            StudyState.is_participating.is_(True),
        )
    ) is not None

    if not is_qualifying:
        unmet = []
        if not meets_fatalities:
            unmet.append(f"fatalities {crash.num_fatalities or 0} < {min_fatalities}")
        if not meets_truck:
            unmet.append(f"no qualifying heavy-duty truck ({criterion_text}) among "
                         f"{len(vehicles)} recorded vehicle(s)")
        return False, CrashScope.OUT_OF_SCOPE, (
            "Out of scope: does not meet qualifying criteria (" + "; ".join(unmet) + ")."
        )
    if not participating:
        return True, CrashScope.OUT_OF_SCOPE, (
            f"Out of scope: qualifying crash but {crash.state_code} is not a "
            f"participating State for this study{proxy_note}."
        )
    return True, CrashScope.IN_SCOPE, (
        f"In scope: qualifying crash ({crash.num_fatalities} fatality(ies), "
        f"{len(heavy_duty)} qualifying heavy-duty truck(s): {criterion_text}) in "
        f"participating State {crash.state_code}{proxy_note}."
    )


def advance_phase(
    db: Session, crash: Crash, target: CrashLifecyclePhase, *, actor: CurrentUser
) -> bool:
    """Move a crash forward to `target` (documentation §5). Forward-only.

    Idempotent: a no-op (already at or past `target`) returns False and writes no
    audit row. On a real forward move it sets `lifecycle_phase`, records an
    ADVANCE_PHASE audit, and returns True. The caller commits within its own
    transaction. Raises BadRequest if the current value is unknown.
    """
    current_phase = crash.lifecycle_phase
    if current_phase not in PHASE_ORDER:
        raise BadRequest(f"Crash is in an unknown lifecycle phase: {current_phase}")
    if PHASE_ORDER[target.value] <= PHASE_ORDER[current_phase]:
        return False
    old = current_phase
    crash.lifecycle_phase = target.value
    record_audit(
        db, actor=actor, action="ADVANCE_PHASE", entity_type="crash",
        entity_id=crash.id, crash_id=crash.id, after={"from": old, "to": target.value},
    )
    return True


# --------------------------------------------------------------------------- CRUD
@router.get("", response_model=Page[CrashOut])
def list_crashes(
    params: PageParams = Depends(),
    study_id: uuid.UUID | None = None,
    state_code: str | None = None,
    scope: CrashScope | None = None,
    lifecycle_phase: CrashLifecyclePhase | None = None,
    date_from: dt.date | None = None,
    date_to: dt.date | None = None,
    q: str | None = None,
    db: Session = Depends(get_db),
    current: CurrentUser = Depends(require("crash:read")),
):
    stmt = select(Crash).order_by(Crash.crash_date.desc().nullslast(), Crash.ccfp_identifier)
    stmt = scope_study_query(scope_crash_query(stmt, current), current)
    if study_id:
        stmt = stmt.where(Crash.study_id == study_id)
    if state_code:
        stmt = stmt.where(Crash.state_code == state_code)
    if lifecycle_phase:
        stmt = stmt.where(Crash.lifecycle_phase == lifecycle_phase.value)
    if date_from:
        stmt = stmt.where(Crash.crash_date >= date_from)
    if date_to:
        stmt = stmt.where(Crash.crash_date <= date_to)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(Crash.ccfp_identifier.ilike(like) | Crash.local_report_number.ilike(like))
    if scope:
        stmt = stmt.join(CrashScopeClassification, CrashScopeClassification.crash_id == Crash.id).where(
            CrashScopeClassification.scope == scope.value
        )
    rows, total = paginate(db, stmt, params)
    return Page(items=rows, total=total, limit=params.limit, offset=params.offset)


def _assert_study_accepts_new_crashes(study: Study, body: CrashIn) -> None:
    """New crashes attach to an ACTIVE study, with one boundary exception that
    keeps the 24-48h Initial Incident window intact when a study is closed
    during its reporting tail: a CLOSED study still accepts a crash whose
    crash_date falls on/before the study's end_date (the crash occurred while
    the study was running; late reports stay auditable). PLANNING and
    PUBLISHED studies never accept new crashes.
    """
    if study.status == StudyStatus.ACTIVE.value:
        return
    if (
        study.status == StudyStatus.CLOSED.value
        and study.end_date is not None
        and body.crash_date is not None
        and body.crash_date <= study.end_date
    ):
        return
    raise BadRequest(
        f"Study {study.code} is {study.status} — crashes can only be created in an "
        "active study, or a closed study when the crash date falls within its window"
    )


@router.post("", response_model=CrashOut, status_code=201)
def create_crash(
    body: CrashIn, request: Request, db: Session = Depends(get_db),
    current: CurrentUser = Depends(require("crash:create")),
):
    # Study-scope check FIRST: a study-restricted principal (AUTH-2) gets the
    # same 403 for an out-of-scope study and a nonexistent one, so the endpoint
    # is not an existence oracle for studies hidden from their GET /studies.
    if not current.can_access_study(body.study_id):
        raise Forbidden("Cannot create a crash outside your authorized study scope")
    study = db.get(Study, body.study_id)
    if study is None:
        raise BadRequest("Unknown study_id")
    _assert_study_accepts_new_crashes(study, body)
    if not current.can_access_state(body.state_code):
        raise Forbidden("Cannot create a crash outside your authorized State scope")
    crash = Crash(
        ccfp_identifier=_generate_ccfp_identifier(db, body),
        created_by=current.id,
        lifecycle_phase=CrashLifecyclePhase.INITIAL_INCIDENT.value,
        **body.model_dump(),
    )
    db.add(crash)
    db.flush()
    record_audit(
        db, actor=current, action="CREATE", entity_type="crash", entity_id=crash.id,
        crash_id=crash.id, after={"ccfp_identifier": crash.ccfp_identifier},
        ip_address=request.client.host if request.client else None,
    )
    # Auto-classify from the study's configured criteria rather than leaving the
    # row blank (CRAS-1). At create time no vehicles exist yet, so a fresh crash
    # usually resolves UNDETERMINED — or OUT_OF_SCOPE when the State plainly does
    # not participate. This is a provisional verdict, NOT a decision: every
    # endpoint that later records a vehicle, a fatality count, or the submitted
    # IIF re-runs `refresh_scope`, so the crash no longer strands at UNDETERMINED.
    # No routing at creation: nothing has been reported yet, and the scope-driven
    # notifications belong to the submit / transition paths (§5 Phase 2).
    refresh_scope(db, crash, actor=current, emit_routing=False)
    db.commit()
    return crash


# --------------------------------------------------------------------------- missing-IIF scan (NOTI-5)
class ScanMissingIifOut(BaseModel):
    flagged: int
    window_hours: int


# Declared BEFORE the `/{crash_id}` routes so the static path is matched as a
# literal and never captured by the `{crash_id}` path parameter (NOTI-5).
@router.post("/scan-missing-iif", response_model=ScanMissingIifOut)
def scan_missing_iif(
    study_id: uuid.UUID | None = None,
    window_hours: int | None = None,
    db: Session = Depends(get_db),
    current: CurrentUser = Depends(require("admin:system", "study:configure")),
):
    """Admin/project-team on-demand scan for crashes missing an Initial Incident
    Form (NOTI-5, §8.11). Permission-gated (project/admin), in-process — no
    scheduler. Invokes the reusable worker, which emits ``MISSING_IIF``
    notifications to the responsible State CMV Data Analyst(s) and is idempotent
    (re-running does not duplicate notifications for the same crash). The window
    is config-driven: an optional per-study ``iif_window_hours`` parameter, else
    the module default; an explicit ``window_hours`` query param overrides both.
    """
    result = scan_crashes_missing_iif(db=db, window_hours=window_hours, study_id=study_id)
    record_audit(
        db, actor=current, action="SCAN_MISSING_IIF", entity_type="crash",
        entity_id=None, after=result,
    )
    db.commit()
    return result


@router.get("/{crash_id}", response_model=CrashOut)
def get_crash(crash_id: uuid.UUID, db: Session = Depends(get_db), current: CurrentUser = Depends(require("crash:read"))):
    return load_crash(db, crash_id, current)


@router.patch("/{crash_id}", response_model=CrashOut)
def update_crash(crash_id: uuid.UUID, body: CrashUpdate, db: Session = Depends(get_db), current: CurrentUser = Depends(require("crash:update"))):
    crash = load_crash(db, crash_id, current)
    # A complete record is locked: reject metadata edits until an authorized
    # unlock restores editability (DATA-1, §8.8).
    _assert_not_locked(db, crash_id)
    fields = body.model_dump(exclude_unset=True)
    # Route any lifecycle_phase change through the forward-only guard rather than
    # blindly setattr-ing, so the manual PATCH path cannot regress the phase or
    # jump out of order (CRAS-4). A non-advancing target is rejected.
    target_phase = fields.pop("lifecycle_phase", None)
    if target_phase is not None:
        if not advance_phase(db, crash, CrashLifecyclePhase(target_phase), actor=current):
            raise BadRequest(
                f"Cannot move lifecycle phase to {target_phase}: only forward transitions are allowed"
            )
    for k, v in fields.items():
        setattr(crash, k, v.value if hasattr(v, "value") else v)
    record_audit(db, actor=current, action="UPDATE", entity_type="crash", entity_id=crash.id, crash_id=crash.id)
    # Correcting a fact the classifier reads must re-derive the scope, otherwise
    # the stored verdict silently goes stale against its own inputs.
    if fields.keys() & {"num_fatalities", "state_code", "study_id"}:
        db.flush()
        refresh_scope(db, crash, actor=current)
    db.commit()
    return crash


# --------------------------------------------------------------------------- scope
@router.get("/{crash_id}/scope", response_model=ScopeOut)
def get_scope(crash_id: uuid.UUID, db: Session = Depends(get_db), current: CurrentUser = Depends(require("crash:read"))):
    load_crash(db, crash_id, current)
    sc = db.scalar(select(CrashScopeClassification).where(CrashScopeClassification.crash_id == crash_id))
    if sc is None:
        raise NotFound("Scope classification")
    return sc


def _emit_scope_routing(
    db: Session, crash: Crash, *, prev_scope: str | None, new_scope: str, is_supplemental: bool,
) -> None:
    """Emit scope-routing notifications when a scope value changes (§8.11).

    NOTI-1 — when the crash is OUT_OF_SCOPE (or marked supplemental), notify the
    State CMV Data Analysts in the crash's State.
    NOTI-7 — when the scope transitions *into* IN_SCOPE and the crash already has a
    submitted/routed IIF, re-run BTS routing (mirrors submit_iif). Firing only on
    the transition keeps repeat set_scope calls idempotent. Caller commits.
    """
    became_in_scope = new_scope == CrashScope.IN_SCOPE.value and prev_scope != CrashScope.IN_SCOPE.value
    if became_in_scope:
        iif = db.scalar(select(InitialIncidentForm).where(InitialIncidentForm.crash_id == crash.id))
        if iif is not None and iif.status in (FormStatus.SUBMITTED.value, FormStatus.ROUTED.value):
            for agent in users_with_role(db, "BTS_CIPSEA_AGENT"):
                create_notification(
                    db, recipient_user_id=agent.id, notification_type="IN_SCOPE_ROUTING",
                    title="In-scope crash for CIPSEA interview",
                    message=f"In-scope crash {crash.ccfp_identifier} routed for confidential interview.",
                    crash_id=crash.id, channel="EMAIL",
                )
    elif new_scope == CrashScope.OUT_OF_SCOPE.value or is_supplemental:
        for analyst in users_with_role(db, "STATE_CMV_ANALYST", state_code=crash.state_code):
            create_notification(
                db, recipient_user_id=analyst.id, notification_type="OUT_OF_SCOPE_ROUTING",
                title="Out-of-scope crash routed",
                message=f"{crash.ccfp_identifier} was classified out-of-scope/supplemental and routed for State review.",
                crash_id=crash.id,
            )


def refresh_scope(
    db: Session, crash: Crash, *, actor: CurrentUser, force: bool = False,
    emit_routing: bool = True,
) -> CrashScopeClassification:
    """Re-derive and persist a crash's scope from the study's criteria.

    This is the fix for the classification never re-running after the Initial
    Incident Form is completed (DL2, DL8). ``classify_scope`` used to be invoked
    only at crash creation — the one moment at which no incident vehicle can yet
    exist, so a study requiring a heavy-duty truck resolved UNDETERMINED for every
    crash and stayed there. UNDETERMINED then matched neither routing branch in
    ``submit_iif``, so qualifying crashes were silently never routed to BTS for
    the CIPSEA interview. Every endpoint that writes a fact the classifier reads
    now calls this instead.

    Rules:
      * A manual override (PUT /scope) is never clobbered — those rows are left
        untouched unless ``force`` (the explicit POST /scope/reclassify), which
        also clears the override so the record returns to automatic upkeep.
      * Idempotent: when the derived verdict matches what is already stored,
        nothing is written — no audit row, no notification. That keeps repeated
        vehicle edits from spamming the audit trail and State analysts' inboxes.
      * On a real change it records an AUTO_CLASSIFY_SCOPE audit row and emits the
        scope-routing notifications, so a crash that becomes IN_SCOPE after its
        IIF was already submitted still reaches BTS (NOTI-7). Callers that do
        their own scope-driven routing immediately afterwards (``submit_iif``)
        pass ``emit_routing=False`` so a crash settled at submit time is not
        announced twice.

    The caller commits.
    """
    sc = db.scalar(
        select(CrashScopeClassification).where(CrashScopeClassification.crash_id == crash.id)
    )
    if sc is not None and sc.is_manual_override and not force:
        return sc

    is_qualifying, scope, reason = classify_scope(db, crash)
    if sc is None:
        sc = CrashScopeClassification(crash_id=crash.id)
        db.add(sc)
        prev_scope = None
    else:
        prev_scope = sc.scope

    unchanged = (
        prev_scope == scope.value
        and sc.is_qualifying == is_qualifying
        and sc.classification_reason == reason
        and not (force and sc.is_manual_override)
    )
    if unchanged:
        return sc

    sc.is_qualifying = is_qualifying
    sc.scope = scope.value
    sc.classification_reason = reason
    sc.classified_by = actor.id
    # A forced re-derivation returns the record to automatic upkeep.
    sc.is_manual_override = False
    db.flush()
    record_audit(
        db, actor=actor, action="AUTO_CLASSIFY_SCOPE",
        entity_type="crash_scope_classification", entity_id=crash.id, crash_id=crash.id,
        before={"scope": prev_scope} if prev_scope is not None else None,
        after={"is_qualifying": is_qualifying, "scope": scope.value},
    )
    if emit_routing:
        _emit_scope_routing(
            db, crash, prev_scope=prev_scope, new_scope=scope.value,
            is_supplemental=sc.is_supplemental,
        )
    return sc


@router.put("/{crash_id}/scope", response_model=ScopeOut)
def set_scope(crash_id: uuid.UUID, body: ScopeIn, db: Session = Depends(get_db), current: CurrentUser = Depends(require("crash:update"))):
    crash = load_crash(db, crash_id, current)
    sc = db.scalar(select(CrashScopeClassification).where(CrashScopeClassification.crash_id == crash_id))
    prev_scope = sc.scope if sc is not None else None
    if sc is None:
        sc = CrashScopeClassification(crash_id=crash_id)
        db.add(sc)
    sc.is_qualifying = body.is_qualifying
    sc.scope = body.scope.value
    sc.is_supplemental = body.is_supplemental
    sc.classification_reason = body.classification_reason
    sc.classified_by = current.id
    # A human decided this value: automatic re-derivation must not overwrite it.
    sc.is_manual_override = True
    record_audit(db, actor=current, action="UPDATE", entity_type="crash_scope_classification", entity_id=crash_id, crash_id=crash_id)
    _emit_scope_routing(
        db, crash, prev_scope=prev_scope, new_scope=body.scope.value, is_supplemental=body.is_supplemental,
    )
    db.commit()
    return sc


@router.post("/{crash_id}/scope/reclassify", response_model=ScopeOut)
def reclassify_scope(
    crash_id: uuid.UUID, db: Session = Depends(get_db),
    current: CurrentUser = Depends(require("crash:update", "initial_incident:write")),
):
    """Re-derive scope from the study's criteria (CRAS-1) — the manual recovery
    control, now a backstop rather than the only path (see `refresh_scope`).

    Authorization deliberately accepts `initial_incident:write` alongside
    `crash:update`: the MCSAP CMV Inspector authors the very facts the classifier
    reads but holds no `crash:update`, so previously the role that filed the form
    could not correct the classification its own submission produced. Recomputing
    a derived value from data the caller may already edit is not the same
    privilege as overriding it — the manual PUT /scope override stays restricted
    to `crash:update`.

    Forced: unlike the automatic path this re-derives even a manually overridden
    record and returns it to automatic upkeep, because the caller asked for it.
    """
    crash = load_crash(db, crash_id, current)
    sc = refresh_scope(db, crash, actor=current, force=True)
    db.commit()
    return sc


# --------------------------------------------------------------------------- lifecycle phase
@router.post("/{crash_id}/advance-phase", response_model=CrashOut)
def advance_crash_phase(crash_id: uuid.UUID, body: AdvancePhaseIn, db: Session = Depends(get_db), current: CurrentUser = Depends(require("crash:update"))):
    """Advance a crash forward to the requested lifecycle phase (CRAS-4, §5).

    Forward-only: rejects a backward or no-op target with 400 so the terminal
    PUBLICATION move (and any manual correction) is ordering-checked and audited.
    """
    crash = load_crash(db, crash_id, current)
    if not advance_phase(db, crash, body.target_phase, actor=current):
        raise BadRequest(
            f"Cannot advance to {body.target_phase.value}: the crash is already at or past that phase"
        )
    db.commit()
    return crash


# --------------------------------------------------------------------------- aggregated attributes
def resolve_attribute_unit(db: Session, da: DataAttribute, unit_type: str | None, unit_number: int | None) -> tuple[str | None, int | None]:
    """Validate a repeat discriminator against the attribute's own declaration (GAP-PCR-03).

    The attribute is the authority, not the caller: ``data_attributes.repeats_on``
    decides whether a unit is required, forbidden, and of which type. That keeps
    "Trailer 2 GVWR" from being filed against a crash-level attribute (which
    would silently create a second current row the old uniqueness rule used to
    prevent) and keeps a trailer value from being filed as VEHICLE 2.

    Returns the pair to persist. Raises ``BadRequest`` on any mismatch.
    """
    if da.repeats_on is None:
        # Crash-level attribute: a unit is meaningless and would fragment the
        # value across rows that all claim to be current.
        if unit_type is not None or unit_number is not None:
            raise BadRequest(
                f"Attribute {da.code} is crash-level and does not repeat; omit unit_type/unit_number"
            )
        return None, None

    if unit_type is None or unit_number is None:
        raise BadRequest(
            f"Attribute {da.code} repeats per {da.repeats_on}; unit_type and unit_number are both required"
        )
    if unit_type != da.repeats_on:
        raise BadRequest(
            f"Attribute {da.code} repeats per {da.repeats_on}, not {unit_type}"
        )
    if unit_number < 1:
        raise BadRequest("unit_number is 1-based; it must be 1 or greater")
    # Resolve against the reference table rather than the enum so a unit added by
    # a later-phase seed works without a code change.
    if db.get(RefRepeatUnit, unit_type) is None:
        raise BadRequest(f"Unknown unit_type: {unit_type}")
    return unit_type, unit_number


def assert_within_cap(da: DataAttribute, value_text: str | None, value_json: Any | None) -> None:
    """Reject a write that exceeds the attribute's declared selection cap.

    Enforced at the point of entry, not only in background QC (GAP-PCR-04 item
    4): the analyst sees the error while the form is still open instead of
    discovering it in a QC report after the record is filed.
    """
    if da.max_selections is None:
        return
    selections = selected_values(value_text, value_json)
    if selections is None:
        return
    if len(selections) > da.max_selections:
        raise BadRequest(
            f"Attribute {da.code} allows at most {da.max_selections} selection(s); {len(selections)} supplied"
        )
    # A JSON list with repeats would pass the count check while representing
    # fewer real selections — and duplicates are never meaningful in a
    # check-all-that-apply group.
    hashable = [s for s in selections if isinstance(s, (str, int, float, bool))]
    if len(set(hashable)) != len(hashable):
        raise BadRequest(f"Attribute {da.code} has duplicate selections")


def supersede_current_attribute_value(
    db: Session, *, crash_id: uuid.UUID, attribute_id: uuid.UUID,
    unit_type: str | None, unit_number: int | None,
) -> None:
    """Retire the current value for exactly one (crash, attribute, unit) (GAP-PCR-03).

    Shared by every append-only writer — ``set_attribute`` and reconstruction
    coding — because the unit predicate is easy to omit and omitting it is
    silently destructive: without it, writing Vehicle 2's damage code retires
    Vehicle 1's and Vehicle 3's too, leaving one surviving value that looks
    authoritative. One helper means one place to get it right.

    ``is_(None)`` rather than ``== None`` so the crash-level case emits
    ``IS NULL`` instead of a never-true ``= NULL``.
    """
    filters = [
        CrashAttributeValue.crash_id == crash_id,
        CrashAttributeValue.attribute_id == attribute_id,
        CrashAttributeValue.is_current.is_(True),
    ]
    if unit_type is None:
        filters += [
            CrashAttributeValue.unit_type.is_(None),
            CrashAttributeValue.unit_number.is_(None),
        ]
    else:
        filters += [
            CrashAttributeValue.unit_type == unit_type,
            CrashAttributeValue.unit_number == unit_number,
        ]
    db.query(CrashAttributeValue).filter(*filters).update({"is_current": False})


@router.get("/{crash_id}/attributes", response_model=list[AttributeValueOut])
def get_attributes(crash_id: uuid.UUID, db: Session = Depends(get_db), current: CurrentUser = Depends(require("crash:read", "data_mgmt:read_aggregated"))):
    load_crash(db, crash_id, current)
    rows = db.execute(
        select(CrashAttributeValue, DataAttribute)
        .join(DataAttribute, DataAttribute.id == CrashAttributeValue.attribute_id)
        .where(CrashAttributeValue.crash_id == crash_id, CrashAttributeValue.is_current.is_(True))
        # Group a unit's attributes together and order units 1,2,3 within a type
        # (GAP-PCR-03). Crash-level rows (NULL unit) sort first so the record's
        # own attributes lead, then each repeating unit in position order.
        .order_by(
            CrashAttributeValue.unit_type.nulls_first(),
            CrashAttributeValue.unit_number.nulls_first(),
            DataAttribute.code,
        )
    ).all()
    out = []
    for cav, da in rows:
        allowed = current.can_view_sensitivity(da.sensitivity)
        out.append(
            AttributeValueOut(
                attribute_id=da.id, code=da.code, name=da.name, pcr_section=da.pcr_section,
                sensitivity=da.sensitivity,
                value_text=cav.value_text if allowed else None,
                value_json=cav.value_json if allowed else None,
                source_system=cav.source_system, confidence=float(cav.confidence) if cav.confidence is not None else None,
                source_record_id=cav.source_record_id,
                is_edited=cav.is_edited, redacted=not allowed,
                unit_type=cav.unit_type, unit_number=cav.unit_number,
                repeats_on=da.repeats_on, max_selections=da.max_selections,
                applies_to=da.applies_to,
            )
        )
    return out


@router.get("/{crash_id}/attributes/{attribute_code}/history", response_model=AttributeHistoryOut)
def get_attribute_history(
    crash_id: uuid.UUID,
    attribute_code: str,
    unit_type: str | None = None,
    unit_number: int | None = None,
    db: Session = Depends(get_db),
    current: CurrentUser = Depends(require("crash:read", "data_mgmt:read_aggregated")),
):
    """Return every version (current + superseded) of one attribute, newest-first (DATA-6, §8.8).

    The edit history already lives in ``crash_attribute_values`` because
    ``set_attribute`` is append-only (it flips the prior row to
    ``is_current=False`` and inserts a new current row). This read mirrors
    ``get_attributes``' join to ``DataAttribute`` but drops the ``is_current``
    filter, scopes to one resolved attribute code, and orders newest-first so the
    UI can render the timeline and diff consecutive values. Sensitivity redaction
    is identical to ``get_attributes``: a caller who fails
    ``can_view_sensitivity`` sees ``redacted=True`` with the value nulled.

    For an attribute that repeats (GAP-PCR-03), pass ``unit_type``/``unit_number``
    to scope the timeline to one unit — otherwise every unit's versions are
    returned interleaved, each entry tagged with the unit it belongs to.
    """
    load_crash(db, crash_id, current)
    da = db.scalar(select(DataAttribute).where(DataAttribute.code == attribute_code))
    if da is None:
        raise NotFound("Attribute")
    filters = [
        CrashAttributeValue.crash_id == crash_id,
        CrashAttributeValue.attribute_id == da.id,
    ]
    # Scoping is optional here (unlike a write), so validate only what was sent:
    # a partial pair is ambiguous and a unit on a crash-level attribute is a
    # caller error worth surfacing rather than silently returning everything.
    if unit_type is not None or unit_number is not None:
        if unit_type is None or unit_number is None:
            raise BadRequest("unit_type and unit_number must be supplied together")
        if da.repeats_on is None:
            raise BadRequest(f"Attribute {da.code} is crash-level and has no units")
        filters += [
            CrashAttributeValue.unit_type == unit_type,
            CrashAttributeValue.unit_number == unit_number,
        ]
    rows = list(
        db.scalars(
            select(CrashAttributeValue)
            .where(*filters)
            # Newest first: prefer the explicit edit timestamp, fall back to the
            # row's created_at so source-ingested (un-edited) rows still order.
            # is_current breaks ties so the live row always sorts ahead of a
            # superseded row written in the same transaction (identical now()).
            .order_by(
                func.coalesce(CrashAttributeValue.edited_at, CrashAttributeValue.created_at).desc(),
                CrashAttributeValue.is_current.desc(),
                CrashAttributeValue.created_at.desc(),
            )
        )
    )
    allowed = current.can_view_sensitivity(da.sensitivity)
    editor_ids = {cav.edited_by for cav in rows if cav.edited_by is not None}
    editor_names: dict[uuid.UUID, str] = {}
    if editor_ids:
        editor_names = {
            u.id: u.full_name
            for u in db.scalars(select(User).where(User.id.in_(editor_ids)))
        }
    versions = [
        AttributeHistoryEntry(
            value_id=cav.id,
            value_text=cav.value_text if allowed else None,
            value_json=cav.value_json if allowed else None,
            source_system=cav.source_system,
            confidence=float(cav.confidence) if cav.confidence is not None else None,
            is_current=cav.is_current,
            is_edited=cav.is_edited,
            edited_by=cav.edited_by,
            edited_by_name=editor_names.get(cav.edited_by) if cav.edited_by else None,
            edited_at=cav.edited_at,
            created_at=cav.created_at,
            redacted=not allowed,
            unit_type=cav.unit_type,
            unit_number=cav.unit_number,
        )
        for cav in rows
    ]
    return AttributeHistoryOut(
        attribute_id=da.id, code=da.code, name=da.name, pcr_section=da.pcr_section,
        sensitivity=da.sensitivity, versions=versions, repeats_on=da.repeats_on,
    )


@router.post("/{crash_id}/attributes", response_model=AttributeValueOut, status_code=201)
def set_attribute(crash_id: uuid.UUID, body: AttributeValueIn, db: Session = Depends(get_db), current: CurrentUser = Depends(require("data_mgmt:edit"))):
    crash = load_crash(db, crash_id, current)
    # A complete record is locked: reject attribute set/override until an
    # authorized unlock restores editability (DATA-1, §8.8).
    _assert_not_locked(db, crash_id)
    da = db.scalar(select(DataAttribute).where(DataAttribute.code == body.attribute_code))
    if da is None:
        raise BadRequest(f"Unknown attribute code: {body.attribute_code}")
    # Source-record lineage (DATA-5, §11.3 line 505): when a precise lineage pointer
    # is supplied it must reference a source_records row for *this* crash; a missing
    # or cross-crash reference is a client error (400), not a silently dropped value.
    if body.source_record_id is not None:
        src = db.scalar(
            select(SourceRecord).where(
                SourceRecord.id == body.source_record_id,
                SourceRecord.crash_id == crash_id,
            )
        )
        if src is None:
            raise BadRequest("source_record_id does not reference a source record for this crash")
    # Repeat discriminator (GAP-PCR-03): resolved against the attribute's own
    # `repeats_on` declaration before any write, then used to retire only THIS
    # unit's prior value.
    unit_type, unit_number = resolve_attribute_unit(db, da, body.unit_type, body.unit_number)
    # Selection cap (GAP-PCR-04), checked before any write so an over-cap
    # submission never lands.
    assert_within_cap(da, body.value_text, body.value_json)
    supersede_current_attribute_value(
        db, crash_id=crash_id, attribute_id=da.id,
        unit_type=unit_type, unit_number=unit_number,
    )
    cav = CrashAttributeValue(
        crash_id=crash_id, attribute_id=da.id, value_text=body.value_text, value_json=body.value_json,
        unit_type=unit_type, unit_number=unit_number,
        source_system=body.source_system, source_record_id=body.source_record_id, confidence=body.confidence,
        is_current=True, is_edited=True, edited_by=current.id, edited_at=dt.datetime.now(dt.timezone.utc),
    )
    db.add(cav)
    db.flush()
    record_audit(
        db, actor=current, action="SET_ATTRIBUTE", entity_type="crash_attribute_value",
        entity_id=cav.id, crash_id=crash_id,
        after={
            "code": da.code, "value": body.value_text,
            "unit_type": unit_type, "unit_number": unit_number,
        },
    )
    db.commit()
    return AttributeValueOut(
        attribute_id=da.id, code=da.code, name=da.name, pcr_section=da.pcr_section, sensitivity=da.sensitivity,
        value_text=cav.value_text, value_json=cav.value_json, source_system=cav.source_system,
        source_record_id=cav.source_record_id, confidence=body.confidence, is_edited=True, redacted=False,
        unit_type=unit_type, unit_number=unit_number,
        repeats_on=da.repeats_on, max_selections=da.max_selections, applies_to=da.applies_to,
    )


# --------------------------------------------------------------------------- quality control
@router.get("/{crash_id}/quality", response_model=list[QcResultOut])
def get_quality(crash_id: uuid.UUID, db: Session = Depends(get_db), current: CurrentUser = Depends(require("crash:read", "data_mgmt:qc"))):
    load_crash(db, crash_id, current)
    rows = db.execute(
        select(DataQualityResult, DataQualityRule)
        .join(DataQualityRule, DataQualityRule.id == DataQualityResult.rule_id)
        .where(DataQualityResult.crash_id == crash_id)
        .order_by(DataQualityRule.code)
    ).all()
    return [
        QcResultOut(rule_code=r.code, rule_name=r.name, severity=r.severity, status=res.status, message=res.message, evaluated_at=res.evaluated_at)
        for res, r in rows
    ]


@router.post("/{crash_id}/quality/evaluate")
def run_quality(crash_id: uuid.UUID, db: Session = Depends(get_db), current: CurrentUser = Depends(require("data_mgmt:qc"))):
    crash = load_crash(db, crash_id, current)
    # Reuse the request's session/connection. Omitting `db` makes the evaluator
    # open a second pooled connection for a request that already holds one —
    # against a remote database that handshake alone cost seconds, on top of the
    # evaluation itself, and made this synchronous endpoint look like it had
    # done nothing. It also keeps the QC write in the same transaction as the
    # audit row and phase advance below.
    result = evaluate_quality(crash_id, db=db)
    record_audit(db, actor=current, action="EVALUATE_QC", entity_type="crash", entity_id=crash_id, crash_id=crash_id, after=result.get("summary"))
    # QC evaluated -> advance into Quality Control (CRAS-4; forward-only, idempotent).
    advance_phase(db, crash, CrashLifecyclePhase.QUALITY_CONTROL, actor=current)
    db.commit()
    return result


# --------------------------------------------------------------------------- completeness
@router.get("/{crash_id}/completeness", response_model=CompletenessOut)
def get_completeness(crash_id: uuid.UUID, db: Session = Depends(get_db), current: CurrentUser = Depends(require("crash:read", "data_mgmt:complete"))):
    load_crash(db, crash_id, current)
    cs = db.scalar(
        select(CrashCompletenessStatus).where(
            CrashCompletenessStatus.crash_id == crash_id, CrashCompletenessStatus.is_current.is_(True)
        )
    )
    if cs is None:
        raise NotFound("Completeness status")
    return cs


@router.post("/{crash_id}/completeness/evaluate")
def run_completeness(crash_id: uuid.UUID, db: Session = Depends(get_db), current: CurrentUser = Depends(require("data_mgmt:complete"))):
    crash = load_crash(db, crash_id, current)
    # Reuse the request's session/connection. Omitting `db` made the evaluator
    # open a SECOND pooled connection for a request that already holds one —
    # against a remote database that handshake alone cost seconds, on top of the
    # evaluation's own round-trips, so the button appeared to do nothing and
    # users reloaded before the response landed. Sharing the session also keeps
    # the completeness row in the same transaction as the audit row, the lock
    # flag, and the phase advance below, and lets `db.get(Crash, ...)` inside the
    # evaluator hit the identity map that `load_crash` just populated. Mirrors
    # the QC fix in run_quality (Defect 4, commit cc6136c).
    result = evaluate_completeness(crash_id, db=db, changed_by=current.id)
    record_audit(db, actor=current, action="EVALUATE_COMPLETENESS", entity_type="crash", entity_id=crash_id, crash_id=crash_id, after={"status": result.get("status")})
    # Lock the record on completion (DATA-1, §8.8): when the crash evaluates to
    # COMPLETE, flip the current completeness row to is_locked=True so edits are
    # rejected until an authorized user unlocks it (§12.3). Idempotent — only
    # locks/audits on the transition into a locked state. evaluate_completeness
    # appends an unlocked current row, so we read it back and lock it here; if a
    # later re-evaluation drops to INCOMPLETE the new current row is unlocked.
    if result.get("status") == CompletenessStatus.COMPLETE.value:
        cs = db.scalar(
            select(CrashCompletenessStatus).where(
                CrashCompletenessStatus.crash_id == crash_id,
                CrashCompletenessStatus.is_current.is_(True),
            )
        )
        if cs is not None and not cs.is_locked:
            cs.is_locked = True
            cs.changed_by = current.id
            record_audit(db, actor=current, action="LOCK", entity_type="crash", entity_id=crash_id, crash_id=crash_id, after={"status": result.get("status")})
    # Completeness evaluated -> advance into Quality Control (CRAS-4; forward-only, idempotent).
    advance_phase(db, crash, CrashLifecyclePhase.QUALITY_CONTROL, actor=current)
    db.commit()
    return result


@router.post("/{crash_id}/unlock", response_model=CompletenessOut)
def unlock_crash(crash_id: uuid.UUID, db: Session = Depends(get_db), current: CurrentUser = Depends(require("crash:unlock"))):
    load_crash(db, crash_id, current)
    cs = db.scalar(
        select(CrashCompletenessStatus).where(
            CrashCompletenessStatus.crash_id == crash_id, CrashCompletenessStatus.is_current.is_(True)
        )
    )
    if cs is None:
        raise NotFound("Completeness status")
    if not cs.is_locked:
        raise BadRequest("Crash record is not locked")
    cs.is_locked = False
    cs.changed_by = current.id
    record_audit(db, actor=current, action="UNLOCK", entity_type="crash", entity_id=crash_id, crash_id=crash_id)
    db.commit()
    return cs


# --------------------------------------------------------------------------- timeline & sources
def _timeline_phase(a: AuditLog) -> tuple[str | None, bool]:
    """Derive the lifecycle phase an audit row represents (CRAS-6, documentation §5).

    Phase transitions are *already* audited, so the timeline only has to read the
    existing rows — no new persistence. Returns (phase, is_milestone):

      * ``ADVANCE_PHASE`` (added by CRAS-4) carries ``after_state={"from":..,"to":..}``
        → phase is the ``to`` value, milestone.
      * The IIF ``SUBMIT`` (entity_type ``initial_incident_form``) moves the crash
        into NOTIFICATION → phase NOTIFICATION, milestone.
      * The crash ``CREATE`` row marks the start of the lifecycle → phase
        INITIAL_INCIDENT, milestone.
      * Everything else is a routine audit → (None, False).

    Degrades gracefully: when CRAS-4's ADVANCE_PHASE rows are absent only
    CREATE/SUBMIT surface as milestones, and the rail still reflects the crash's
    current ``lifecycle_phase``.
    """
    if a.action == "ADVANCE_PHASE":
        to = a.after_state.get("to") if isinstance(a.after_state, dict) else None
        if to in PHASE_ORDER:
            return to, True
        return None, False
    if a.action == "SUBMIT" and a.entity_type == "initial_incident_form":
        return CrashLifecyclePhase.NOTIFICATION.value, True
    if a.action == "CREATE" and a.entity_type == "crash":
        return CrashLifecyclePhase.INITIAL_INCIDENT.value, True
    return None, False


@router.get("/{crash_id}/timeline", response_model=list[TimelineEntry])
def get_timeline(crash_id: uuid.UUID, db: Session = Depends(get_db), current: CurrentUser = Depends(require("crash:read"))):
    # The crash's present phase comes straight off the already-loaded row, so the
    # rail reflects it even when no ADVANCE_PHASE audit exists yet (no extra query).
    load_crash(db, crash_id, current)
    rows = db.scalars(select(AuditLog).where(AuditLog.crash_id == crash_id).order_by(AuditLog.occurred_at))
    entries: list[TimelineEntry] = []
    for a in rows:
        phase, is_milestone = _timeline_phase(a)
        entries.append(
            TimelineEntry(
                action=a.action, entity_type=a.entity_type, actor_user_id=a.actor_user_id,
                occurred_at=a.occurred_at, after_state=a.after_state,
                phase=phase, is_milestone=is_milestone,
            )
        )
    return entries


@router.get("/{crash_id}/sources", response_model=list[SourceRecordOut])
def get_sources(crash_id: uuid.UUID, db: Session = Depends(get_db), current: CurrentUser = Depends(require("crash:read", "data_mgmt:read_raw"))):
    load_crash(db, crash_id, current)
    return list(db.scalars(select(SourceRecord).where(SourceRecord.crash_id == crash_id).order_by(SourceRecord.received_at)))
