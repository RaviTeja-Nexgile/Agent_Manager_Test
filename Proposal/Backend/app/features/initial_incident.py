"""Initial Incident Form + incident vehicles/persons (documentation §12.4, §8.2, §19.1)."""
from __future__ import annotations

import datetime as dt
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends
from pydantic import BaseModel, computed_field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.common import ORMModel
from app.core.audit import record_audit
from app.core.database import get_db
from app.core.errors import BadRequest, Conflict, NotFound
from app.core.notifications import create_notification, users_with_role
from app.core.permissions import require
from app.core.security import CurrentUser
from app.enums import (
    CrashLifecyclePhase,
    FormStatus,
    InjuryStatus,
    NonMotoristKind,
    NotificationType,
    PersonType,
    PhoneType,
)
from app.features.crashes import _assert_not_locked, load_crash, refresh_scope
from app.integrations import safespect
from app.models import (
    IncidentPerson,
    IncidentVehicle,
    InitialIncidentForm,
)
from app.workers import evaluate_quality

router = APIRouter(prefix="/crashes/{crash_id}", tags=["initial-incident"])

# Tri-state DOT-number validation outcomes (documentation §8.2, l.245).
# A non-CMV crash has no U.S. DOT numbers to check, so its validation outcome is
# NOT_APPLICABLE — distinct from FAILED (numbers were checked and rejected).
# No schema/enum change is used: NOT_APPLICABLE is recorded in-column via the
# free-text `dot_validation_source` sentinel below, and the boolean
# `dot_number_validated` stays False for both N/A and FAILED. The tri-state value
# is derived for API responses by `_dot_validation_status`.
DOT_VALIDATED = "VALIDATED"
DOT_FAILED = "FAILED"
DOT_NOT_APPLICABLE = "NOT_APPLICABLE"
# In-column sentinel written to `dot_validation_source` when there is no CMV to
# validate; lets readers distinguish N/A from a genuine SafeSpect failure without
# a new column.
DOT_SOURCE_NOT_APPLICABLE = "N/A — no CMV"


def _dot_validation_status(validated: bool, source: str | None) -> str:
    """Derive the tri-state DOT outcome from the persisted boolean + source.

    NOT_APPLICABLE is encoded by the `DOT_SOURCE_NOT_APPLICABLE` source sentinel;
    otherwise the boolean distinguishes VALIDATED from FAILED.
    """
    if source == DOT_SOURCE_NOT_APPLICABLE:
        return DOT_NOT_APPLICABLE
    return DOT_VALIDATED if validated else DOT_FAILED


def _find_by_client_uuid(db: Session, model, crash_id: uuid.UUID, client_uuid: uuid.UUID | None):
    """Return the row this crash already holds for `client_uuid`, if any.

    The offline client mints one UUID per record it
    creates on the device and replays that same key on every sync attempt. When
    a key is already present the create endpoints return the existing row rather
    than inserting a second one, which makes the POST idempotent under retry.

    A NULL key means "online caller, no idempotency requested" and always
    returns None, so existing online behaviour is untouched. The key is scoped to
    the crash — matching the partial unique index in migration 0020 — so devices
    working different crashes can never collide.
    """
    if client_uuid is None:
        return None
    return db.scalar(
        select(model).where(model.crash_id == crash_id, model.client_uuid == client_uuid)
    )


def _assert_not_routed(db: Session, crash_id: uuid.UUID) -> None:
    """Block edits/deletes of IIF child records once the parent IIF is ROUTED
    (locked). Mirrors the lock check in save_iif so child deletes are consistent
    with the form-level lock (INIT-7). Unlocking the crash reopens edits."""
    iif = db.scalar(select(InitialIncidentForm).where(InitialIncidentForm.crash_id == crash_id))
    if iif is not None and iif.status == FormStatus.ROUTED.value:
        raise Conflict("Form already routed; unlock the crash to edit")


# --------------------------------------------------------------------------- schemas
class IIFIn(BaseModel):
    event_summary: str | None = None
    dot_validation_source: str | None = None
    # INIT-4 / BRD DC1: the Initial Incident Form IS the instrument that captures
    # crash date/time, location, the local report number, and the vehicle/person/
    # fatality counts (documentation §5 Phase 2, §8.2 l.154). Those columns live on
    # `crashes`, but the MCSAP Inspector who owns the form holds only `crash:read`
    # — the role table (§ l.127) grants them update on the FORM and *view* on crash
    # records. Accepting the fields the form collects here lets the form's owner
    # correct them without widening the role to `crash:update`, which would
    # additionally expose lifecycle-phase advancement via PATCH /crashes/{id}.
    local_report_number: str | None = None
    crash_date: dt.date | None = None
    crash_time: dt.time | None = None
    state_code: str | None = None
    city: str | None = None
    county: str | None = None
    street_highway: str | None = None
    num_vehicles: int | None = None
    num_persons: int | None = None
    num_fatalities: int | None = None


# The IIFIn fields above that belong to the crash row rather than the form row.
# Split out before the form setattr loop so they are applied to `crashes` and
# audited as a crash UPDATE, not blindly set on InitialIncidentForm.
_IIF_CRASH_FIELDS = frozenset({
    "local_report_number", "crash_date", "crash_time", "state_code", "city",
    "county", "street_highway", "num_vehicles", "num_persons", "num_fatalities",
})


class IIFOut(ORMModel):
    id: uuid.UUID
    crash_id: uuid.UUID
    status: str
    event_summary: str | None
    dot_number_validated: bool
    dot_validation_source: str | None
    submitted_at: dt.datetime | None
    routed_at: dt.datetime | None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def dot_validation_status(self) -> str:
        """Tri-state outcome (VALIDATED / FAILED / NOT_APPLICABLE) derived
        from the persisted boolean + source sentinel."""
        return _dot_validation_status(self.dot_number_validated, self.dot_validation_source)


class VehicleIn(BaseModel):
    vehicle_number: int
    # offline-sync idempotency key. The offline client mints one UUID
    # per locally-created record and replays it on every attempt, so a retried
    # sync returns the row created by the first attempt instead of a duplicate.
    # Omitted by online callers, whose behaviour is unchanged.
    client_uuid: uuid.UUID | None = None
    is_cmv: bool = False
    # Qualifying-criterion inputs (DL2, §3.1). Without these the classifier could
    # only guess "heavy-duty Class 7/8 truck" from the is_cmv checkbox, so the
    # study's configured vehicle_classes / min_gvwr_lbs were unevaluable. Both
    # optional — an inspector filing within 24-48h may not know the GVWR yet.
    vehicle_class: str | None = None
    gvwr_lbs: float | None = None
    us_dot_number: str | None = None
    make: str | None = None
    num_occupants: int | None = None
    num_injured_occupants: int | None = None
    carrier_name: str | None = None
    carrier_phone: str | None = None
    is_supplemental: bool = False


class VehicleOut(ORMModel):
    id: uuid.UUID
    crash_id: uuid.UUID
    client_uuid: uuid.UUID | None = None
    vehicle_number: int
    is_cmv: bool
    vehicle_class: str | None = None
    gvwr_lbs: float | None = None
    us_dot_number: str | None
    make: str | None
    num_occupants: int | None
    num_injured_occupants: int | None
    carrier_name: str | None
    carrier_phone: str | None
    is_supplemental: bool


class PersonIn(BaseModel):
    person_type: PersonType
    # offline-sync idempotency key. Critical here — a person has no
    # natural key, so without this a replayed offline sync silently inserts the
    # person twice, inflating the fatality count that drives qualifying-crash
    # classification (documentation §3.1). Omitted by online callers.
    client_uuid: uuid.UUID | None = None
    related_vehicle_number: int | None = None
    # INIT-1: structured name parts. full_name is DERIVED server-side from the
    # parts when any part is supplied, so existing readers / PII masking are
    # unchanged. A client may still send full_name directly (e.g. witnesses).
    full_name: str | None = None
    name_last: str | None = None
    name_first: str | None = None
    name_middle: str | None = None
    is_minor: bool | None = None
    primary_language: str | None = None
    address: str | None = None
    phone_primary: str | None = None
    phone_secondary: str | None = None
    phone_type: str | None = None
    # INIT-2: per-number phone type (HOME | CELL | WORK). Validated against the
    # PhoneType enum so an unknown value (e.g. "PAGER") is rejected with 422.
    phone_primary_type: PhoneType | None = None
    phone_secondary_type: PhoneType | None = None
    # INIT-3: occupant-vs-pedestrian discriminator; only meaningful when
    # person_type == NON_MOTORIST.
    non_motorist_kind: NonMotoristKind | None = None
    injury: InjuryStatus | None = None
    is_supplemental: bool = False


class PersonOut(BaseModel):
    id: uuid.UUID
    crash_id: uuid.UUID
    client_uuid: uuid.UUID | None = None
    person_type: str
    related_vehicle_number: int | None
    full_name: str | None
    name_last: str | None = None
    name_first: str | None = None
    name_middle: str | None = None
    is_minor: bool | None
    primary_language: str | None
    address: str | None
    phone_primary: str | None
    phone_secondary: str | None
    phone_type: str | None
    phone_primary_type: str | None = None
    phone_secondary_type: str | None = None
    non_motorist_kind: str | None = None
    injury: str | None
    is_supplemental: bool
    pii_redacted: bool = False


class SubmitResult(BaseModel):
    status: str
    dot_number_validated: bool
    dot_validation_status: str
    notified_users: int
    routed_to_bts: bool
    # Surfaces which Notification & Routing branch ran (documentation §5 Phase 2;
    # CRAS-2): an OUT_OF_SCOPE or supplemental (retained, non-qualifying) crash
    # is routed to the CCFP Project Team instead of BTS, so this is the
    # complement of routed_to_bts. Both are False for an UNDETERMINED / unclassified
    # crash — see routed_unclassified.
    routed_out_of_scope: bool = False
    # The third outcome, previously unnamed: the crash could not be classified at
    # all, so neither CIPSEA-style branch applies and the CCFP Project Team is
    # asked to supply the missing fact. Reporting it explicitly means the caller
    # can never mistake "reached nobody" for "routed correctly" — the ambiguity
    # the BTS-routing defect lived in. Exactly one of the three is True.
    routed_unclassified: bool = False


# --------------------------------------------------------------------------- IIF
@router.get("/initial-incident", response_model=IIFOut)
def get_iif(crash_id: uuid.UUID, db: Session = Depends(get_db), current: CurrentUser = Depends(require("initial_incident:read", "crash:read"))):
    load_crash(db, crash_id, current)
    iif = db.scalar(select(InitialIncidentForm).where(InitialIncidentForm.crash_id == crash_id))
    if iif is None:
        raise NotFound("Initial Incident Form")
    return iif


@router.put("/initial-incident", response_model=IIFOut)
def save_iif(crash_id: uuid.UUID, body: IIFIn, db: Session = Depends(get_db), current: CurrentUser = Depends(require("initial_incident:write"))):
    crash = load_crash(db, crash_id, current)
    iif = db.scalar(select(InitialIncidentForm).where(InitialIncidentForm.crash_id == crash_id))
    # Distinguish the first save (form row created) from a subsequent edit so the
    # draft-saved notification fires once, not on every PUT (documentation §5
    # Phase 2; INIT-6). The terminal "submitted-and-routed" notification is a
    # separate, distinct event emitted by submit_iif ("NEW_IIF").
    is_first_save = iif is None
    if iif is None:
        iif = InitialIncidentForm(crash_id=crash_id, created_by=current.id)
        db.add(iif)
    if iif.status in (FormStatus.ROUTED.value,):
        raise Conflict("Form already routed; unlock the crash to edit")
    fields = body.model_dump(exclude_unset=True)
    crash_fields = {k: fields.pop(k) for k in list(fields) if k in _IIF_CRASH_FIELDS}
    for k, v in fields.items():
        setattr(iif, k, v)

    # Apply the general-information/location fields the form carries to the crash
    # row itself (INIT-4). Same guards as PATCH /crashes/{id}: a complete record is
    # locked until an authorized unlock, the change is audited against the crash,
    # and correcting a fact the scope classifier reads re-derives the verdict so it
    # cannot go stale against its own inputs. Lifecycle phase is deliberately NOT
    # accepted here — the form collects crash facts, not workflow state.
    if crash_fields:
        _assert_not_locked(db, crash_id)
        for k, v in crash_fields.items():
            setattr(crash, k, v)
        record_audit(
            db, actor=current, action="UPDATE", entity_type="crash",
            entity_id=crash.id, crash_id=crash_id,
        )

    db.flush()
    if crash_fields.keys() & {"num_fatalities", "state_code"}:
        refresh_scope(db, crash, actor=current)
    record_audit(db, actor=current, action="SAVE", entity_type="initial_incident_form", entity_id=iif.id, crash_id=crash_id)
    if is_first_save:
        # Heads-up that a draft IIF now exists for this crash; a distinct type so
        # it is not confused with the submit-time "NEW_IIF" routing notification.
        for analyst in users_with_role(db, "STATE_CMV_ANALYST", state_code=crash.state_code):
            create_notification(
                db, recipient_user_id=analyst.id, notification_type=NotificationType.IIF_DRAFT_SAVED,
                title="Initial Incident Form draft saved",
                message=f"A draft Initial Incident Form was saved for {crash.ccfp_identifier}.",
                crash_id=crash_id,
            )
    db.commit()
    return iif


@router.post("/initial-incident/submit", response_model=SubmitResult)
def submit_iif(
    crash_id: uuid.UUID, background: BackgroundTasks, db: Session = Depends(get_db),
    current: CurrentUser = Depends(require("initial_incident:submit")),
):
    crash = load_crash(db, crash_id, current)
    iif = db.scalar(select(InitialIncidentForm).where(InitialIncidentForm.crash_id == crash_id))
    if iif is None:
        raise NotFound("Initial Incident Form")

    # Validate U.S. DOT numbers for CMV vehicles via SafeSpect (mock).
    # Tri-state outcome: when there are no CMV vehicles (so no DOT numbers to
    # check), the result is NOT_APPLICABLE — never FAILED. Only a crash whose DOT
    # numbers were actually checked and rejected is FAILED.
    vehicles = list(db.scalars(select(IncidentVehicle).where(IncidentVehicle.crash_id == crash_id, IncidentVehicle.is_cmv.is_(True))))
    dot_numbers = [v.us_dot_number for v in vehicles if v.us_dot_number]
    if not dot_numbers:
        dot_status = DOT_NOT_APPLICABLE
        validated = False
        # Sentinel in the existing free-text column distinguishes N/A from a
        # genuine SafeSpect failure without adding a column (see INIT-10).
        iif.dot_validation_source = DOT_SOURCE_NOT_APPLICABLE
    else:
        validated = all(safespect.validate_dot(n)["valid"] for n in dot_numbers)
        dot_status = DOT_VALIDATED if validated else DOT_FAILED
        iif.dot_validation_source = "SafeSpect"
    iif.dot_number_validated = validated
    iif.status = FormStatus.ROUTED.value
    iif.submitted_by = current.id
    now = dt.datetime.now(dt.timezone.utc)
    iif.submitted_at = now
    iif.routed_at = now
    crash.lifecycle_phase = CrashLifecyclePhase.NOTIFICATION.value

    # Route notifications (documentation §5 Phase 2). The State CMV Data Analyst
    # is notified here, on submit-and-route — NOT on a plain draft save. A draft
    # save emits a distinct, one-time "IIF_DRAFT_SAVED" heads-up (see save_iif);
    # this "NEW_IIF" event signals the form is finalized and routed for review.
    notified = 0
    for analyst in users_with_role(db, "STATE_CMV_ANALYST", state_code=crash.state_code):
        create_notification(
            db, recipient_user_id=analyst.id, notification_type=NotificationType.NEW_IIF,
            title="New Initial Incident Form",
            message=f"IIF submitted for {crash.ccfp_identifier}.", crash_id=crash_id,
        )
        notified += 1

    # Scope-driven Notification & Routing (documentation §5 Phase 2; CRAS-2).
    # Three distinct outcomes on submit:
    #   IN_SCOPE (and not supplemental) -> route to BTS CIPSEA agents for the
    #       confidential interview (IN_SCOPE_ROUTING) — unchanged.
    #   OUT_OF_SCOPE *or* a supplemental record -> route to the CCFP Project Team,
    #       who own retained/non-qualifying records, recording that the crash is
    #       retained but NOT routed for a CIPSEA interview (OUT_OF_SCOPE_ROUTING).
    #       A supplemental record is by definition out-of-scope, so the
    #       is_supplemental flag finally drives a workflow signal here.
    #   UNDETERMINED (facts still genuinely unknown) -> no CIPSEA-style routing.
    #
    # Re-derive scope from the now-complete IIF data (incident vehicles + fatality
    # count) so the system *classifies and routes* on submit, per documentation §5
    # Phase 2. This is the step whose absence let a qualifying crash reach ROUTED
    # while still carrying the provisional UNDETERMINED written at creation —
    # matching neither branch below, so it was routed to nobody. `refresh_scope`
    # preserves a deliberate PUT /scope override and is a no-op when the verdict
    # is unchanged (a vehicle edit will usually have settled it already).
    db.flush()
    scope = refresh_scope(db, crash, actor=current, emit_routing=False)
    is_supplemental = bool(scope and scope.is_supplemental)
    routed_to_bts = bool(scope and scope.scope == "IN_SCOPE" and not is_supplemental)
    routed_out_of_scope = bool(scope and (scope.scope == "OUT_OF_SCOPE" or is_supplemental))
    if routed_to_bts:
        for agent in users_with_role(db, "BTS_CIPSEA_AGENT"):
            create_notification(
                db, recipient_user_id=agent.id, notification_type=NotificationType.IN_SCOPE_ROUTING,
                title="In-scope crash for CIPSEA interview",
                message=f"In-scope crash {crash.ccfp_identifier} routed for confidential interview.",
                crash_id=crash_id, channel="EMAIL",
            )
            notified += 1
    elif routed_out_of_scope:
        kind = "supplemental (retained, non-qualifying)" if is_supplemental else "out-of-scope"
        for member in users_with_role(db, "CCFP_PROJECT_TEAM"):
            create_notification(
                db, recipient_user_id=member.id, notification_type=NotificationType.OUT_OF_SCOPE_ROUTING,
                title="Out-of-scope crash retained",
                message=f"Crash {crash.ccfp_identifier} is {kind}; retained but not routed for CIPSEA interview.",
                crash_id=crash_id, channel="IN_APP",
            )
            notified += 1
    else:
        # UNDETERMINED: the classifier is missing a fact it needs (fatality count
        # or incident vehicles), so neither routing branch above applies. Silence
        # here is what let the original defect hide — a form reaching ROUTED while
        # reaching nobody looks identical to a form routed correctly. The crash is
        # NOT assumed in- or out-of-scope; the CCFP Project Team is told it could
        # not be classified so a human closes the gap. Recording the missing fact
        # re-derives the scope automatically (`refresh_scope`) and, if it lands
        # IN_SCOPE, routes to BTS then (NOTI-7).
        reason = (scope.classification_reason if scope and scope.classification_reason
                  else "required crash facts are not yet recorded")
        for member in users_with_role(db, "CCFP_PROJECT_TEAM"):
            create_notification(
                db, recipient_user_id=member.id, notification_type=NotificationType.SCOPE_UNDETERMINED,
                title="Submitted crash could not be classified",
                message=(f"{crash.ccfp_identifier} was submitted but its scope is undetermined, "
                         f"so it was routed to neither the CIPSEA interview nor retention: {reason}"),
                crash_id=crash_id, channel="IN_APP",
            )
            notified += 1

    record_audit(db, actor=current, action="SUBMIT", entity_type="initial_incident_form", entity_id=iif.id, crash_id=crash_id, after={"status": iif.status, "dot_validated": validated, "dot_validation_status": dot_status})
    db.commit()
    background.add_task(evaluate_quality, crash_id)
    return SubmitResult(status=iif.status, dot_number_validated=validated, dot_validation_status=dot_status, notified_users=notified, routed_to_bts=routed_to_bts, routed_out_of_scope=routed_out_of_scope, routed_unclassified=not (routed_to_bts or routed_out_of_scope))


@router.delete("/initial-incident", status_code=204)
def delete_iif(crash_id: uuid.UUID, db: Session = Depends(get_db), current: CurrentUser = Depends(require("initial_incident:delete"))):
    load_crash(db, crash_id, current)
    iif = db.scalar(select(InitialIncidentForm).where(InitialIncidentForm.crash_id == crash_id))
    if iif is None:
        raise NotFound("Initial Incident Form")
    if iif.status == FormStatus.ROUTED.value:
        raise BadRequest("Cannot delete a routed form")
    db.delete(iif)
    record_audit(db, actor=current, action="DELETE", entity_type="initial_incident_form", entity_id=iif.id, crash_id=crash_id)
    db.commit()
    return None


# --------------------------------------------------------------------------- incident vehicles
@router.get("/incident-vehicles", response_model=list[VehicleOut])
def list_vehicles(crash_id: uuid.UUID, db: Session = Depends(get_db), current: CurrentUser = Depends(require("crash:read", "initial_incident:read"))):
    load_crash(db, crash_id, current)
    return list(db.scalars(select(IncidentVehicle).where(IncidentVehicle.crash_id == crash_id).order_by(IncidentVehicle.vehicle_number)))


@router.post("/incident-vehicles", response_model=VehicleOut, status_code=201)
def add_vehicle(crash_id: uuid.UUID, body: VehicleIn, db: Session = Depends(get_db), current: CurrentUser = Depends(require("initial_incident:write"))):
    crash = load_crash(db, crash_id, current)
    # idempotent replay. Checked BEFORE the vehicle_number guard so a
    # retried offline sync returns its own earlier row instead of colliding with
    # it and raising 409 against itself.
    existing = _find_by_client_uuid(db, IncidentVehicle, crash_id, body.client_uuid)
    if existing is not None:
        return existing
    if db.scalar(select(IncidentVehicle).where(IncidentVehicle.crash_id == crash_id, IncidentVehicle.vehicle_number == body.vehicle_number)):
        raise Conflict("vehicle_number already exists for this crash")
    veh = IncidentVehicle(crash_id=crash_id, **body.model_dump())
    db.add(veh)
    try:
        db.flush()
    except IntegrityError:
        # Concurrent replay of the same key won the race; return its row.
        db.rollback()
        raced = _find_by_client_uuid(db, IncidentVehicle, crash_id, body.client_uuid)
        if raced is not None:
            return raced
        raise
    record_audit(db, actor=current, action="CREATE", entity_type="incident_vehicle", entity_id=veh.id, crash_id=crash_id)
    # The vehicle is a classifier input: re-derive scope now rather than leaving
    # the crash stranded at the provisional UNDETERMINED written at creation.
    refresh_scope(db, crash, actor=current)
    db.commit()
    return veh


@router.patch("/incident-vehicles/{vehicle_id}", response_model=VehicleOut)
def update_vehicle(crash_id: uuid.UUID, vehicle_id: uuid.UUID, body: VehicleIn, db: Session = Depends(get_db), current: CurrentUser = Depends(require("initial_incident:write"))):
    crash = load_crash(db, crash_id, current)
    veh = db.get(IncidentVehicle, vehicle_id)
    if veh is None or veh.crash_id != crash_id:
        raise NotFound("Incident vehicle")
    # client_uuid is a creation-time idempotency key, not editable state: a PATCH
    # that omits it must not blank the key set at create time.
    for k, v in body.model_dump(exclude={"client_uuid"}).items():
        setattr(veh, k, v)
    record_audit(db, actor=current, action="UPDATE", entity_type="incident_vehicle", entity_id=veh.id, crash_id=crash_id)
    # Correcting the CMV flag, class, or GVWR changes the qualifying verdict.
    db.flush()
    refresh_scope(db, crash, actor=current)
    db.commit()
    return veh


@router.delete("/incident-vehicles/{vehicle_id}", status_code=204)
def delete_vehicle(crash_id: uuid.UUID, vehicle_id: uuid.UUID, db: Session = Depends(get_db), current: CurrentUser = Depends(require("initial_incident:write"))):
    crash = load_crash(db, crash_id, current)
    _assert_not_routed(db, crash_id)
    veh = db.get(IncidentVehicle, vehicle_id)
    if veh is None or veh.crash_id != crash_id:
        raise NotFound("Incident vehicle")
    db.delete(veh)
    record_audit(db, actor=current, action="DELETE", entity_type="incident_vehicle", entity_id=vehicle_id, crash_id=crash_id)
    # Removing the only heavy-duty truck un-qualifies the crash; the stored
    # verdict must follow its inputs down as well as up.
    db.flush()
    refresh_scope(db, crash, actor=current)
    db.commit()
    return None


# --------------------------------------------------------------------------- incident persons (PII)
def _person_data(body: PersonIn, exclude: set[str] | None = None) -> dict:
    """Normalize a PersonIn body into a column-ready dict.

    `exclude` drops fields the caller must not write — used by the PATCH path to
    protect the creation-time `client_uuid` idempotency key from being blanked by
    an update body that omits it.

    - Serializes the enum fields to their bare string value (.value), matching
      how person_type / injury are persisted.
    - Derives full_name from the structured name parts when any part is supplied
      (INIT-1), so list/read consumers and PII masking are unchanged. When no
      part is supplied, the directly-provided full_name (if any) is kept.
    - Enforces the INIT-3 cross-field rule: a non_motorist_kind may only be set
      when person_type == NON_MOTORIST.
    """
    if body.non_motorist_kind is not None and body.person_type != PersonType.NON_MOTORIST:
        raise BadRequest("non_motorist_kind is only valid when person_type is NON_MOTORIST")
    data = body.model_dump(exclude=exclude or set())
    data["person_type"] = body.person_type.value
    data["injury"] = body.injury.value if body.injury else None
    data["phone_primary_type"] = body.phone_primary_type.value if body.phone_primary_type else None
    data["phone_secondary_type"] = body.phone_secondary_type.value if body.phone_secondary_type else None
    data["non_motorist_kind"] = body.non_motorist_kind.value if body.non_motorist_kind else None
    parts = [body.name_first, body.name_middle, body.name_last]
    if any(parts):
        data["full_name"] = " ".join(filter(None, parts))
    return data


def _person_out(p: IncidentPerson, allow_pii: bool) -> PersonOut:
    return PersonOut(
        id=p.id, crash_id=p.crash_id, person_type=p.person_type,
        # Echoed so the offline client can reconcile its local record with the
        # server row after sync. Not PII — an opaque device key.
        client_uuid=p.client_uuid,
        related_vehicle_number=p.related_vehicle_number,
        # Name parts are PII — redact them together with the derived full_name
        # when the caller lacks PII sensitivity (INIT-1).
        full_name=p.full_name if allow_pii else None,
        name_last=p.name_last if allow_pii else None,
        name_first=p.name_first if allow_pii else None,
        name_middle=p.name_middle if allow_pii else None,
        is_minor=p.is_minor, primary_language=p.primary_language,
        address=p.address if allow_pii else None,
        phone_primary=p.phone_primary if allow_pii else None,
        phone_secondary=p.phone_secondary if allow_pii else None,
        # Phone type LABELS are not PII (mirror phone_type); only the numbers are.
        phone_type=p.phone_type,
        phone_primary_type=p.phone_primary_type,
        phone_secondary_type=p.phone_secondary_type,
        non_motorist_kind=p.non_motorist_kind,
        injury=p.injury, is_supplemental=p.is_supplemental,
        pii_redacted=not allow_pii,
    )


@router.get("/incident-persons", response_model=list[PersonOut])
def list_persons(crash_id: uuid.UUID, db: Session = Depends(get_db), current: CurrentUser = Depends(require("crash:read", "initial_incident:read"))):
    load_crash(db, crash_id, current)
    allow_pii = current.can_view_sensitivity("PII")
    rows = db.scalars(select(IncidentPerson).where(IncidentPerson.crash_id == crash_id).order_by(IncidentPerson.person_type))
    return [_person_out(p, allow_pii) for p in rows]


@router.post("/incident-persons", response_model=PersonOut, status_code=201)
def add_person(crash_id: uuid.UUID, body: PersonIn, db: Session = Depends(get_db), current: CurrentUser = Depends(require("initial_incident:write"))):
    load_crash(db, crash_id, current)
    # Idempotent replay. A person has no natural key, so this check is the only
    # thing standing between a retried offline sync and a duplicate person —
    # which would inflate the fatality count feeding the qualifying-crash rule
    # (documentation §3.1).
    #
    # The replay response is redacted on the same terms as a normal read: a
    # replay is effectively a read of an existing row, so it must not hand back
    # more than `list_persons` would to the same caller.
    allow_pii = current.can_view_sensitivity("PII")
    existing = _find_by_client_uuid(db, IncidentPerson, crash_id, body.client_uuid)
    if existing is not None:
        record_audit(db, actor=current, action="REPLAY", entity_type="incident_person", entity_id=existing.id, crash_id=crash_id)
        db.commit()
        return _person_out(existing, allow_pii)
    data = _person_data(body)
    person = IncidentPerson(crash_id=crash_id, **data)
    db.add(person)
    try:
        db.flush()
    except IntegrityError:
        # Concurrent replay of the same key won the race; return its row.
        db.rollback()
        raced = _find_by_client_uuid(db, IncidentPerson, crash_id, body.client_uuid)
        if raced is not None:
            return _person_out(raced, allow_pii)
        raise
    record_audit(db, actor=current, action="CREATE", entity_type="incident_person", entity_id=person.id, crash_id=crash_id)
    db.commit()
    return _person_out(person, True)


@router.patch("/incident-persons/{person_id}", response_model=PersonOut)
def update_person(crash_id: uuid.UUID, person_id: uuid.UUID, body: PersonIn, db: Session = Depends(get_db), current: CurrentUser = Depends(require("initial_incident:write"))):
    load_crash(db, crash_id, current)
    person = db.get(IncidentPerson, person_id)
    if person is None or person.crash_id != crash_id:
        raise NotFound("Incident person")
    # client_uuid is a creation-time idempotency key, not editable state.
    data = _person_data(body, exclude={"client_uuid"})
    for k, v in data.items():
        setattr(person, k, v)
    record_audit(db, actor=current, action="UPDATE", entity_type="incident_person", entity_id=person.id, crash_id=crash_id)
    db.commit()
    return _person_out(person, True)


@router.delete("/incident-persons/{person_id}", status_code=204)
def delete_person(crash_id: uuid.UUID, person_id: uuid.UUID, db: Session = Depends(get_db), current: CurrentUser = Depends(require("initial_incident:write"))):
    load_crash(db, crash_id, current)
    _assert_not_routed(db, crash_id)
    person = db.get(IncidentPerson, person_id)
    if person is None or person.crash_id != crash_id:
        raise NotFound("Incident person")
    db.delete(person)
    record_audit(db, actor=current, action="DELETE", entity_type="incident_person", entity_id=person_id, crash_id=crash_id)
    db.commit()
    return None
