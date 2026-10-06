"""Source-data collection: inspections, investigations, PCR, reconstruction, ELD
(documentation §12.5, §8.3-8.7)."""
from __future__ import annotations

import csv
import io
import re

import datetime as dt
import uuid
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, UploadFile
from pydantic import BaseModel
from sqlalchemy import or_, func, select
from sqlalchemy.orm import Session

from app.common import ORMModel
from app.core import storage
from app.core.audit import record_audit
from app.core.config import settings
from app.core.database import get_db
from app.core.errors import BadRequest, NotFound
from app.core.permissions import require
from app.core.security import CurrentUser
from app.enums import (
    CodingStatus,
    CrashLifecyclePhase,
    DocumentType,
    EldIssueSeverity,
    FormStatus,
    IngestionPath,
    MappingStatus,
)
from app.features.crashes import (
    assert_within_cap,
    advance_phase,
    load_crash,
    resolve_attribute_unit,
    supersede_current_attribute_value,
)
from app.models import (
    PcrColumnMapping,
    Crash,
    CrashAttributeValue,
    DataAttribute,
    Document,
    EldEvent,
    EldFile,
    EldParseIssue,
    PciAdditionalTowedUnit,
    PciAxle,
    PciBrakeSystem,
    PciCarrierPowerUnit,
    PciDriverLoad,
    PciExemptions,
    PciFieldDefinition,
    PciHazmat,
    PciHoursOfService,
    PciMedicalCertificate,
    PciSeatingPosition,
    PciTire,
    PciTrailer,
    PciVehicleCondition,
    PcrFieldMapping,
    PoliceCrashReport,
    PostCrashInspection,
    PostCrashInvestigation,
    ReconstructionReport,
    SourceRecord,
    Study,
)
from app.workers import eld_format, parse_eld_file, resolve_eld_mappings
from app.workers.eld_format import EldParseError

# Crash-scoped source-data endpoints live on this prefixed router. The study-scoped
# PCI field-definitions read (PCI-3) lives on `study_router` (no crash prefix);
# both are merged into the module-exported `router` at the bottom of this file so
# main.py's single-`router` include picks up everything.
crash_router = APIRouter(prefix="/crashes/{crash_id}", tags=["source-data"])
study_router = APIRouter(tags=["source-data"])

# §8.3 — the MCSAP CMV Inspector uploads post-crash inspection data within this
# many days of the inspection. Kept as a single named constant so future study
# phases can change the SLA window without code archaeology (per CLAUDE.md
# configurability mandate). Visibility only — late uploads are still accepted.
INSPECTION_UPLOAD_WINDOW_DAYS = 7


def _link_source(db: Session, crash_id: uuid.UUID, system: str, stype: str, external_id: str | None, note: str) -> None:
    db.add(SourceRecord(crash_id=crash_id, source_system=system, source_type=stype, external_id=external_id, provenance_note=note))


# =========================================================================== inspections
class InspectionIn(BaseModel):
    source_system: str = "SafeSpect"
    inspection_number: str | None = None
    inspection_date: dt.date | None = None
    inspector_name: str | None = None
    # The two facts the new PCR form's inspection block also reports (GAP-PCR-07).
    # None means "not reported by this source", which DQ_PCR_INSPECTION_XREF
    # treats as nothing to reconcile rather than as a disagreement.
    inspection_type: str | None = None
    driver_oos: bool | None = None
    violations_count: int | None = 0
    defects_count: int | None = 0
    details: dict[str, Any] | None = None


class InspectionOut(ORMModel):
    id: uuid.UUID
    crash_id: uuid.UUID
    source_system: str
    inspection_number: str | None
    inspection_date: dt.date | None
    inspector_name: str | None
    inspection_type: str | None = None
    driver_oos: bool | None = None
    violations_count: int | None
    defects_count: int | None
    details: Any | None
    # Derived §8.3 SLA indicator (not stored): elapsed days from inspection to
    # upload, and whether that exceeded the 7-day window. Visibility only.
    days_to_upload: int | None = None
    is_overdue: bool = False


def _inspection_out(rec: PostCrashInspection) -> InspectionOut:
    """Shape an inspection ORM row into its response, deriving the §8.3 7-day
    upload-window SLA. The upload date is `linked_at` (set at ingest) when present,
    else `created_at`, else today for a not-yet-persisted record. `days_to_upload`
    is None when the inspection has no `inspection_date` to measure against."""
    out = InspectionOut.model_validate(rec)
    if rec.inspection_date is not None:
        upload_at = rec.linked_at or rec.created_at
        upload_date = upload_at.date() if upload_at is not None else dt.date.today()
        out.days_to_upload = (upload_date - rec.inspection_date).days
        out.is_overdue = out.days_to_upload > INSPECTION_UPLOAD_WINDOW_DAYS
    return out


@crash_router.get("/post-crash-inspections", response_model=list[InspectionOut])
def list_inspections(crash_id: uuid.UUID, db: Session = Depends(get_db), current: CurrentUser = Depends(require("source_data:read", "crash:read"))):
    load_crash(db, crash_id, current)
    return [_inspection_out(r) for r in db.scalars(select(PostCrashInspection).where(PostCrashInspection.crash_id == crash_id))]


@crash_router.post("/post-crash-inspections", response_model=InspectionOut, status_code=201)
def add_inspection(crash_id: uuid.UUID, body: InspectionIn, db: Session = Depends(get_db), current: CurrentUser = Depends(require("source_data:ingest"))):
    load_crash(db, crash_id, current)
    rec = PostCrashInspection(crash_id=crash_id, **body.model_dump())
    db.add(rec)
    db.flush()
    _link_source(db, crash_id, body.source_system, "INSPECTION", body.inspection_number, "Post-crash inspection ingested")
    record_audit(db, actor=current, action="CREATE", entity_type="post_crash_inspection", entity_id=rec.id, crash_id=crash_id)
    # Source data collected -> advance into Data Collection (CRAS-4; forward-only, idempotent).
    advance_phase(db, load_crash(db, crash_id, current), CrashLifecyclePhase.DATA_COLLECTION, actor=current)
    db.commit()
    return _inspection_out(rec)


@crash_router.get("/post-crash-inspections/{rec_id}", response_model=InspectionOut)
def get_inspection(crash_id: uuid.UUID, rec_id: uuid.UUID, db: Session = Depends(get_db), current: CurrentUser = Depends(require("source_data:read", "crash:read"))):
    load_crash(db, crash_id, current)
    rec = db.get(PostCrashInspection, rec_id)
    if rec is None or rec.crash_id != crash_id:
        raise NotFound("Inspection")
    return _inspection_out(rec)


@crash_router.patch("/post-crash-inspections/{rec_id}", response_model=InspectionOut)
def update_inspection(crash_id: uuid.UUID, rec_id: uuid.UUID, body: InspectionIn, db: Session = Depends(get_db), current: CurrentUser = Depends(require("source_data:ingest"))):
    load_crash(db, crash_id, current)
    rec = db.get(PostCrashInspection, rec_id)
    if rec is None or rec.crash_id != crash_id:
        raise NotFound("Inspection")
    for k, v in body.model_dump().items():
        setattr(rec, k, v)
    record_audit(db, actor=current, action="UPDATE", entity_type="post_crash_inspection", entity_id=rec.id, crash_id=crash_id)
    db.commit()
    return _inspection_out(rec)


# =========================================================================== investigations
# PCI-1/4/5 (§8.4, §19.2). The post-crash investigation is the full field-level
# §19.2 inventory, modeled as typed child tables: single-valued sections
# (one-to-one), repeating structures (one-to-many keyed by index/position), and
# the two optional conditional sections gated by presence flags. Each nested
# model below maps 1:1 to its `pci_*` table; every field is optional because the
# form marks most fields optional and per-field required/optional is configured
# per study (PCI-3). The legacy untyped `sections` JSONB is still accepted for
# back-compat with in-flight data.


# --- PCI-1 single-valued section payloads (one-to-one child tables) ---------
class CarrierPowerUnitIn(BaseModel):
    work_zone: bool | None = None
    work_zone_type: str | None = None
    preclearance_bypass_serial: str | None = None
    fire: bool | None = None
    fire_pre_crash: bool | None = None
    fire_post_crash: bool | None = None
    carrier_name_displayed: str | None = None
    us_dot_displayed: bool | None = None
    nsc_number: str | None = None
    motor_carrier_name: str | None = None
    motor_carrier_address: str | None = None
    motor_carrier_phone: str | None = None
    owner_name: str | None = None
    owner_address: str | None = None
    lease_indicator: bool | None = None
    year: int | None = None
    make: str | None = None
    model: str | None = None
    company_unit_number: str | None = None
    manufacture_date: dt.date | None = None
    vin: str | None = None
    color: str | None = None
    license_plate: str | None = None
    license_plate_state: str | None = None
    registered_gross_weight: float | None = None
    gvwr: float | None = None
    annual_inspection: bool | None = None
    axles_up: int | None = None
    axles_down: int | None = None
    remarks: str | None = None


class DriverLoadIn(BaseModel):
    driver_name: str | None = None
    driver_present: bool | None = None
    driver_address: str | None = None
    license_state: str | None = None
    license_province: str | None = None
    license_number: str | None = None
    license_class: str | None = None
    license_endorsements: str | None = None
    license_restrictions: str | None = None
    license_issue_date: dt.date | None = None
    license_expiration_date: dt.date | None = None
    lenses_required: bool | None = None
    lenses_worn: bool | None = None
    shipper: str | None = None
    bill_of_lading: str | None = None
    manifest_load_weight: float | None = None
    cargo_loaded: str | None = None
    cargo_destination: str | None = None
    load_securement: bool | None = None
    securement_contributed: bool | None = None
    securement_proper_use: bool | None = None
    securement_exceeded_wll: bool | None = None
    securement_type: str | None = None
    remarks: str | None = None


class MedicalCertificateIn(BaseModel):
    examination_date: dt.date | None = None
    expiration_date: dt.date | None = None
    lenses: bool | None = None
    hearing_aid: bool | None = None
    waiver: bool | None = None
    medic_alert: bool | None = None
    cert_state: str | None = None
    cert_province: str | None = None
    remarks: str | None = None


class HoursOfServiceIn(BaseModel):
    on_duty_not_driving_hours: float | None = None
    driving_hours: float | None = None
    total_on_duty_hours: float | None = None
    miles_driven: float | None = None
    kilometers_driven: float | None = None
    record_of_duty_status: bool | None = None
    timecard: bool | None = None
    violations: str | None = None
    onboard_computer_eld: bool | None = None
    eld_present: bool | None = None
    co_driver: bool | None = None
    last_8_days_present: bool | None = None
    approved_eld: bool | None = None
    driver_history: str | None = None
    road_familiarity: str | None = None
    years_experience: float | None = None
    previous_cmv_crashes: int | None = None
    purpose_of_trip: str | None = None
    trip_destination: str | None = None
    driver_condition_remarks: str | None = None


class ExemptionsIn(BaseModel):
    exemption_14_hour: bool | None = None
    exemption_11_hour: bool | None = None
    exemption_split_sleeper: bool | None = None
    exemption_60_70_hour: bool | None = None
    exemption_34_hour_restart: bool | None = None
    exemption_federal: bool | None = None
    exemption_state: bool | None = None
    exemption_oilfield: bool | None = None
    exemption_agricultural: bool | None = None
    exemption_150_air_mile: bool | None = None
    exemption_temporary: bool | None = None
    docket_or_state_number: str | None = None
    emergency_declaration: bool | None = None
    emergency_jurisdiction: str | None = None
    emergency_federal_number: str | None = None
    emergency_state_number: str | None = None
    service_center: str | None = None
    other_description: str | None = None


class VehicleConditionIn(BaseModel):
    compartment_condition: str | None = None
    drivers_view: str | None = None
    wipers: str | None = None
    wiper_switch_position: str | None = None
    heater_defroster: str | None = None
    mirrors: str | None = None
    rearward_camera: bool | None = None
    fender_mirrors: bool | None = None
    odometer: float | None = None
    engine_hours: float | None = None
    engine_manufacturer: str | None = None
    fuel_type: str | None = None
    ecm_serial: str | None = None
    adas: str | None = None
    steering_type: str | None = None
    steering_wheel_diameter: float | None = None
    steering_lash: str | None = None
    steering_checked_running: bool | None = None
    transmission_type: str | None = None
    transmission_model: str | None = None
    transmission_serial: str | None = None
    transmission_gear_position: str | None = None
    transmission_forward_gears: int | None = None
    drive_line_notes: str | None = None
    drive_axle_ratio: str | None = None
    radio: bool | None = None
    cb: bool | None = None
    dash_camera: bool | None = None
    audio_technology: bool | None = None
    headphones: bool | None = None
    bluetooth: bool | None = None
    remarks: str | None = None


class BrakeSystemIn(BaseModel):
    brake_type: str | None = None
    abs_type: str | None = None
    engine_brake_type: str | None = None
    engine_brake_position: str | None = None
    air_leaks: bool | None = None
    application_loss: bool | None = None
    low_air_vacuum_warning: bool | None = None
    low_air_vacuum_warning_psi: float | None = None
    hydraulic_master_cylinder_secure: bool | None = None
    hydraulic_fluid_level: str | None = None
    hydraulic_fluid_seepage: bool | None = None
    hydraulic_line_condition: str | None = None
    electric_controller_mfr: str | None = None
    electric_gain_setting: str | None = None
    electric_breakaway_device: bool | None = None
    electric_battery_wiring: str | None = None
    surge_breakaway_device: bool | None = None
    surge_fluid_leak: bool | None = None
    power_assist: bool | None = None
    parking_brake: bool | None = None
    wheel_end_weight_note: str | None = None
    remarks: str | None = None


# --- PCI-4 repeating structure item payloads (one-to-many child tables) ------
class SeatingPositionIn(BaseModel):
    position: str | None = None  # DRIVER | PASSENGER_1 | PASSENGER_2 | SLEEPER_BERTH
    seat_belt_equipped: bool | None = None
    seat_belt_used: bool | None = None
    seat_belt_condition: str | None = None
    airbag_equipped: bool | None = None
    airbag_deployed: bool | None = None
    remarks: str | None = None


class AxleIn(BaseModel):
    axle_index: int | None = None
    abs: bool | None = None
    slack_adjuster_type: str | None = None
    slack_adjuster_length: float | None = None
    push_rod_stroke_available: float | None = None
    push_rod_stroke_applied: float | None = None
    air_pressure: str | None = None
    chamber_type: str | None = None
    drum_rotor: str | None = None
    brake_friction_code: str | None = None
    rolling_radius: float | None = None
    wheel_end_weight: float | None = None
    total_end_weight: float | None = None
    remarks: str | None = None


class TireIn(BaseModel):
    axle_index: int | None = None
    side: str | None = None  # LEFT | RIGHT
    inner_outer: str | None = None  # INSIDE | OUTSIDE
    size: str | None = None
    make: str | None = None
    model_design: str | None = None
    tin_dot: str | None = None
    rated_psi: float | None = None
    rated_weight: float | None = None
    inspection_psi: float | None = None
    retread_tin_dot: str | None = None
    repair: bool | None = None
    repair_location: str | None = None
    speed_rating: str | None = None
    tread_depth: float | None = None
    wheel_hub_remarks: str | None = None


class TrailerIn(BaseModel):
    trailer_index: int | None = None
    owner_name: str | None = None
    owner_address: str | None = None
    trailer_type: str | None = None
    intermodal_indicator: bool | None = None
    unit_number: str | None = None
    year: int | None = None
    make: str | None = None
    model: str | None = None
    vin: str | None = None
    color: str | None = None
    license_plate: str | None = None
    expiration: dt.date | None = None
    registered_gross_weight: float | None = None
    gvwr: float | None = None
    axle_weight_rating: float | None = None
    annual_inspection: bool | None = None
    axles_up: int | None = None
    axles_down: int | None = None
    converter_dolly: bool | None = None
    converter_dolly_details: str | None = None
    remarks: str | None = None


# --- PCI-5 optional conditional section item payloads ------------------------
class HazmatIn(BaseModel):
    unit_scope: str | None = None  # TRUCK | TRAILER_1 ...
    hazmat_present: bool | None = None
    hazmat_type: str | None = None
    placards: str | None = None
    spill: bool | None = None
    leak: bool | None = None
    remarks: str | None = None


class AdditionalTowedUnitIn(BaseModel):
    towed_index: int | None = None
    owner_name: str | None = None
    owner_address: str | None = None
    unit_type: str | None = None
    unit_number: str | None = None
    vin: str | None = None
    front_clearance: str | None = None
    rear_clearance: str | None = None
    side_marker_left: str | None = None
    side_marker_right: str | None = None
    turn_signals: str | None = None
    stop_lamps: str | None = None
    id_lamps: str | None = None
    tail_lamps: str | None = None
    reflectors: str | None = None
    conspicuity_tape: str | None = None
    distance_from_rear: float | None = None
    rear_protection_from_rear: float | None = None
    rear_protection_from_ground: float | None = None
    rear_protection_from_side: float | None = None
    rear_protection_width: float | None = None
    remarks: str | None = None


# Single-valued sections: (InvestigationIn attr, ORM relationship attr, ORM class).
_PCI_SINGLE_SECTIONS: list[tuple[str, str, type]] = [
    ("carrier_power_unit", "carrier_power_unit", PciCarrierPowerUnit),
    ("driver_load", "driver_load", PciDriverLoad),
    ("medical_certificate", "medical_certificate", PciMedicalCertificate),
    ("hours_of_service", "hours_of_service", PciHoursOfService),
    ("exemptions", "exemptions", PciExemptions),
    ("vehicle_condition", "vehicle_condition", PciVehicleCondition),
    ("brake_system", "brake_system", PciBrakeSystem),
]


class InvestigationIn(BaseModel):
    case_number: str | None = None
    inspection_number: str | None = None
    officer_name: str | None = None
    officer_id: str | None = None
    post_crash_date: dt.date | None = None
    # DEPRECATED legacy untyped blob, accepted for back-compat (PCI-1).
    sections: dict[str, Any] | None = None
    # PCI-1 single-valued sections.
    carrier_power_unit: CarrierPowerUnitIn | None = None
    driver_load: DriverLoadIn | None = None
    medical_certificate: MedicalCertificateIn | None = None
    hours_of_service: HoursOfServiceIn | None = None
    exemptions: ExemptionsIn | None = None
    vehicle_condition: VehicleConditionIn | None = None
    brake_system: BrakeSystemIn | None = None
    # PCI-4 repeating structures (replace-on-write).
    seating_positions: list[SeatingPositionIn] = []
    axles: list[AxleIn] = []
    tires: list[TireIn] = []
    trailers: list[TrailerIn] = []
    # PCI-5 optional conditional sections; rows persisted only when the flag is on.
    has_hazmat: bool = False
    has_additional_towed_units: bool = False
    hazmat: list[HazmatIn] = []
    additional_towed_units: list[AdditionalTowedUnitIn] = []


# Header fields the parent investigation row owns directly (everything else on
# InvestigationIn is a structured child section/array or a presence flag).
_INVESTIGATION_HEADER_FIELDS = (
    "case_number", "inspection_number", "officer_name", "officer_id",
    "post_crash_date", "sections", "has_hazmat", "has_additional_towed_units",
)


# The *Out section/array models reuse their *In field shapes but read from ORM
# attribute objects, so every one carries `from_attributes=True`; without it the
# nested relationship objects on InvestigationOut would fail validation.
class CarrierPowerUnitOut(CarrierPowerUnitIn):
    model_config = {"from_attributes": True}


class DriverLoadOut(DriverLoadIn):
    model_config = {"from_attributes": True}


class MedicalCertificateOut(MedicalCertificateIn):
    model_config = {"from_attributes": True}


class HoursOfServiceOut(HoursOfServiceIn):
    model_config = {"from_attributes": True}


class ExemptionsOut(ExemptionsIn):
    model_config = {"from_attributes": True}


class VehicleConditionOut(VehicleConditionIn):
    model_config = {"from_attributes": True}


class BrakeSystemOut(BrakeSystemIn):
    model_config = {"from_attributes": True}


class SeatingPositionOut(SeatingPositionIn):
    model_config = {"from_attributes": True}


class AxleOut(AxleIn):
    model_config = {"from_attributes": True}


class TireOut(TireIn):
    model_config = {"from_attributes": True}


class TrailerOut(TrailerIn):
    model_config = {"from_attributes": True}


class HazmatOut(HazmatIn):
    model_config = {"from_attributes": True}


class AdditionalTowedUnitOut(AdditionalTowedUnitIn):
    model_config = {"from_attributes": True}


class InvestigationOut(ORMModel):
    id: uuid.UUID
    crash_id: uuid.UUID
    case_number: str | None
    inspection_number: str | None
    officer_name: str | None
    officer_id: str | None
    post_crash_date: dt.date | None
    status: str
    sections: Any | None
    has_hazmat: bool
    has_additional_towed_units: bool
    carrier_power_unit: CarrierPowerUnitOut | None = None
    driver_load: DriverLoadOut | None = None
    medical_certificate: MedicalCertificateOut | None = None
    hours_of_service: HoursOfServiceOut | None = None
    exemptions: ExemptionsOut | None = None
    vehicle_condition: VehicleConditionOut | None = None
    brake_system: BrakeSystemOut | None = None
    seating_positions: list[SeatingPositionOut] = []
    axles: list[AxleOut] = []
    tires: list[TireOut] = []
    trailers: list[TrailerOut] = []
    hazmat: list[HazmatOut] = []
    additional_towed_units: list[AdditionalTowedUnitOut] = []


def _apply_investigation_children(rec: PostCrashInvestigation, body: InvestigationIn) -> None:
    """Upsert single-valued sections and replace-on-write repeating/optional rows
    on `rec`, all via its ORM relationships so they flush in the SAME transaction
    as the parent (cascade="all, delete-orphan" deletes any row dropped here).

    - Single-valued sections: replace the related object outright when the body
      carries one (idempotent upsert); a missing section leaves the existing row
      untouched so a partial PATCH need not resend every section.
    - Repeating structures (PCI-4): replace the whole collection on write.
    - Optional conditional sections (PCI-5): persisted ONLY when the matching
      presence flag is true; when the flag is false the collection is cleared so
      stale rows are never kept when a flag flips off.
    """
    for body_attr, orm_attr, orm_cls in _PCI_SINGLE_SECTIONS:
        payload = getattr(body, body_attr)
        if payload is not None:
            setattr(rec, orm_attr, orm_cls(**payload.model_dump()))

    rec.seating_positions = [PciSeatingPosition(**p.model_dump()) for p in body.seating_positions]
    rec.axles = [PciAxle(**a.model_dump()) for a in body.axles]
    rec.tires = [PciTire(**t.model_dump()) for t in body.tires]
    rec.trailers = [PciTrailer(**t.model_dump()) for t in body.trailers]

    rec.hazmat = (
        [PciHazmat(**h.model_dump()) for h in body.hazmat] if body.has_hazmat else []
    )
    rec.additional_towed_units = (
        [PciAdditionalTowedUnit(**u.model_dump()) for u in body.additional_towed_units]
        if body.has_additional_towed_units
        else []
    )


@crash_router.get("/post-crash-investigations", response_model=list[InvestigationOut])
def list_investigations(crash_id: uuid.UUID, db: Session = Depends(get_db), current: CurrentUser = Depends(require("source_data:read", "crash:read"))):
    load_crash(db, crash_id, current)
    return list(db.scalars(select(PostCrashInvestigation).where(PostCrashInvestigation.crash_id == crash_id)))


@crash_router.post("/post-crash-investigations", response_model=InvestigationOut, status_code=201)
def add_investigation(crash_id: uuid.UUID, body: InvestigationIn, db: Session = Depends(get_db), current: CurrentUser = Depends(require("source_data:ingest"))):
    load_crash(db, crash_id, current)
    rec = PostCrashInvestigation(
        crash_id=crash_id, created_by=current.id,
        **{k: getattr(body, k) for k in _INVESTIGATION_HEADER_FIELDS},
    )
    _apply_investigation_children(rec, body)
    db.add(rec)
    db.flush()
    _link_source(db, crash_id, "PCI", "INVESTIGATION", body.case_number, "Post-crash investigation captured")
    record_audit(db, actor=current, action="CREATE", entity_type="post_crash_investigation", entity_id=rec.id, crash_id=crash_id)
    advance_phase(db, load_crash(db, crash_id, current), CrashLifecyclePhase.DATA_COLLECTION, actor=current)
    db.commit()
    db.refresh(rec)
    return rec


@crash_router.get("/post-crash-investigations/{rec_id}", response_model=InvestigationOut)
def get_investigation(crash_id: uuid.UUID, rec_id: uuid.UUID, db: Session = Depends(get_db), current: CurrentUser = Depends(require("source_data:read", "crash:read"))):
    load_crash(db, crash_id, current)
    rec = db.get(PostCrashInvestigation, rec_id)
    if rec is None or rec.crash_id != crash_id:
        raise NotFound("Investigation")
    return rec


@crash_router.patch("/post-crash-investigations/{rec_id}", response_model=InvestigationOut)
def update_investigation(crash_id: uuid.UUID, rec_id: uuid.UUID, body: InvestigationIn, db: Session = Depends(get_db), current: CurrentUser = Depends(require("source_data:ingest"))):
    load_crash(db, crash_id, current)
    rec = db.get(PostCrashInvestigation, rec_id)
    if rec is None or rec.crash_id != crash_id:
        raise NotFound("Investigation")
    for k in _INVESTIGATION_HEADER_FIELDS:
        setattr(rec, k, getattr(body, k))
    _apply_investigation_children(rec, body)
    record_audit(db, actor=current, action="UPDATE", entity_type="post_crash_investigation", entity_id=rec.id, crash_id=crash_id)
    db.commit()
    db.refresh(rec)
    return rec


def _required_field_definitions(db: Session, study_id: uuid.UUID) -> list[PciFieldDefinition]:
    """The study's required PCI form-field definitions (PCI-3)."""
    return list(
        db.scalars(
            select(PciFieldDefinition).where(
                PciFieldDefinition.study_id == study_id,
                PciFieldDefinition.is_required.is_(True),
            )
        )
    )


# Map a PciFieldDefinition.section_code to the InvestigationOut/ORM attribute that
# holds the structured single-valued section. Only single-valued sections carry
# per-field required flags in the Phase-1 seed (PCI-3 schema note).
_SECTION_CODE_TO_ATTR = {
    "CARRIER_POWER_UNIT": "carrier_power_unit",
    "DRIVER_LOAD": "driver_load",
    "MEDICAL_CERTIFICATE": "medical_certificate",
    "HOURS_OF_SERVICE": "hours_of_service",
    "EXEMPTIONS": "exemptions",
    "VEHICLE_CONDITION": "vehicle_condition",
    "BRAKE_SYSTEM": "brake_system",
}


@crash_router.post("/post-crash-investigations/{rec_id}/submit", response_model=InvestigationOut)
def submit_investigation(crash_id: uuid.UUID, rec_id: uuid.UUID, db: Session = Depends(get_db), current: CurrentUser = Depends(require("source_data:ingest"))):
    """Submit an investigation (PCI-3). Before flipping status to SUBMITTED, every
    `is_required` PCI field definition for the crash's study must be populated in
    the stored structured sections; an empty required field raises 400."""
    crash = load_crash(db, crash_id, current)
    rec = db.get(PostCrashInvestigation, rec_id)
    if rec is None or rec.crash_id != crash_id:
        raise NotFound("Investigation")

    missing: list[str] = []
    for fd in _required_field_definitions(db, crash.study_id):
        attr = _SECTION_CODE_TO_ATTR.get(fd.section_code)
        section = getattr(rec, attr) if attr is not None else None
        value = getattr(section, fd.field_code, None) if section is not None else None
        if value is None or (isinstance(value, str) and value.strip() == ""):
            missing.append(f"{fd.section_code}.{fd.field_code}")
    if missing:
        raise BadRequest("Required PCI fields are empty: " + ", ".join(sorted(missing)))

    rec.status = FormStatus.SUBMITTED.value
    record_audit(db, actor=current, action="SUBMIT", entity_type="post_crash_investigation", entity_id=rec.id, crash_id=crash_id)
    db.commit()
    db.refresh(rec)
    return rec


# =========================================================================== PCI field definitions (PCI-3)
class PciFieldDefinitionOut(ORMModel):
    """One per-study PCI form-field definition (PCI-3, §19.2 l.840).

    Mirrors `AttributeRequirement` but keyed to a PCI form field by
    `section_code` + `field_code` (the latter matches a structured field key from
    PCI-1), carrying the per-field required/optional flag the form renders and
    submit-validation enforces."""
    id: uuid.UUID
    study_id: uuid.UUID
    section_code: str
    field_code: str
    label: str | None
    is_required: bool
    is_optional: bool
    display_order: int | None


@study_router.get("/studies/{study_id}/pci-field-definitions", response_model=list[PciFieldDefinitionOut])
def list_pci_field_definitions(
    study_id: uuid.UUID, db: Session = Depends(get_db),
    current: CurrentUser = Depends(require("pcr:read", "crash:read")),
):
    """Per-study PCI form-field definitions (PCI-3). Gated like the other study
    reads (`pcr:read` or `crash:read`). The form renders required markers from
    these and submit-validation enforces the required ones."""
    if db.get(Study, study_id) is None:
        raise NotFound("Study")
    return list(
        db.scalars(
            select(PciFieldDefinition)
            .where(PciFieldDefinition.study_id == study_id)
            .order_by(PciFieldDefinition.section_code, PciFieldDefinition.display_order, PciFieldDefinition.field_code)
        )
    )


# =========================================================================== police crash reports
class PcrIn(BaseModel):
    state_code: str | None = None
    source_repository: str | None = None
    pcr_number: str | None = None
    report_date: dt.date | None = None
    # PCR-4 (§8.5): structured ingestion path — MCMIS round-trip vs. a direct
    # connection to the State crash repository. Defaults to the MCMIS round-trip,
    # mirroring the historical free-text `source_repository` default.
    ingestion_path: IngestionPath = IngestionPath.MCMIS_ROUNDTRIP


class PcrOut(ORMModel):
    id: uuid.UUID
    crash_id: uuid.UUID
    state_code: str | None
    source_repository: str | None
    pcr_number: str | None
    report_date: dt.date | None
    ingestion_path: str
    mapping_status: str


@crash_router.get("/police-crash-reports", response_model=list[PcrOut])
def list_pcr(crash_id: uuid.UUID, db: Session = Depends(get_db), current: CurrentUser = Depends(require("pcr:read", "crash:read"))):
    load_crash(db, crash_id, current)
    return list(db.scalars(select(PoliceCrashReport).where(PoliceCrashReport.crash_id == crash_id)))


@crash_router.post("/police-crash-reports", response_model=PcrOut, status_code=201)
def add_pcr(crash_id: uuid.UUID, body: PcrIn, db: Session = Depends(get_db), current: CurrentUser = Depends(require("source_data:ingest"))):
    crash = load_crash(db, crash_id, current)
    # Persist the structured §8.5 ingestion path as its bare enum value (the native
    # PG `ingestion_path` column stores the string, not the enum member).
    rec = PoliceCrashReport(
        crash_id=crash_id,
        **{
            **body.model_dump(),
            "state_code": body.state_code or crash.state_code,
            "ingestion_path": body.ingestion_path.value,
        },
    )
    db.add(rec)
    db.flush()
    _link_source(db, crash_id, rec.source_repository or "MCMIS", "PCR", body.pcr_number, "Police crash report linked")
    record_audit(db, actor=current, action="CREATE", entity_type="police_crash_report", entity_id=rec.id, crash_id=crash_id)
    advance_phase(db, crash, CrashLifecyclePhase.DATA_COLLECTION, actor=current)
    db.commit()
    return rec


@crash_router.get("/police-crash-reports/{rec_id}", response_model=PcrOut)
def get_pcr(crash_id: uuid.UUID, rec_id: uuid.UUID, db: Session = Depends(get_db), current: CurrentUser = Depends(require("pcr:read", "crash:read"))):
    load_crash(db, crash_id, current)
    rec = db.get(PoliceCrashReport, rec_id)
    if rec is None or rec.crash_id != crash_id:
        raise NotFound("Police crash report")
    return rec


@crash_router.patch("/police-crash-reports/{rec_id}", response_model=PcrOut)
def update_pcr(crash_id: uuid.UUID, rec_id: uuid.UUID, body: PcrIn, db: Session = Depends(get_db), current: CurrentUser = Depends(require("source_data:ingest"))):
    load_crash(db, crash_id, current)
    rec = db.get(PoliceCrashReport, rec_id)
    if rec is None or rec.crash_id != crash_id:
        raise NotFound("Police crash report")
    for k, v in body.model_dump().items():
        setattr(rec, k, v)
    record_audit(db, actor=current, action="UPDATE", entity_type="police_crash_report", entity_id=rec.id, crash_id=crash_id)
    db.commit()
    return rec


# --- PCR field mappings (PCR-1, §8.5/§19.4) ---------------------------------
# Each row records that a field on the State's EXISTING police crash report
# (named/located by `state_field_name` + `state_field_position`) maps to a CCFP
# `data_attributes` row. The State form is never altered — only the mapping FROM
# its fields TO CCFP attribute codes is captured.
class PcrFieldMappingIn(BaseModel):
    state_field_name: str
    state_field_position: str | None = None
    attribute_code: str
    notes: str | None = None


class PcrFieldMappingOut(ORMModel):
    id: uuid.UUID
    pcr_id: uuid.UUID
    state_field_name: str
    state_field_position: str | None
    attribute_id: uuid.UUID
    # Resolved attribute code/name for display (joined from data_attributes), so the
    # mappings table can show the CCFP attribute without a second round-trip.
    attribute_code: str | None = None
    attribute_name: str | None = None
    notes: str | None
    mapped_by: uuid.UUID | None


def _load_pcr(db: Session, crash_id: uuid.UUID, rec_id: uuid.UUID, current: CurrentUser) -> PoliceCrashReport:
    """Load + scope-check a PCR under a crash (mirrors get_pcr's guard)."""
    load_crash(db, crash_id, current)
    rec = db.get(PoliceCrashReport, rec_id)
    if rec is None or rec.crash_id != crash_id:
        raise NotFound("Police crash report")
    return rec


def _mapping_out(m: PcrFieldMapping, da: DataAttribute | None) -> PcrFieldMappingOut:
    out = PcrFieldMappingOut.model_validate(m)
    if da is not None:
        out.attribute_code = da.code
        out.attribute_name = da.name
    return out


@crash_router.get("/police-crash-reports/{rec_id}/field-mappings", response_model=list[PcrFieldMappingOut])
def list_pcr_field_mappings(crash_id: uuid.UUID, rec_id: uuid.UUID, db: Session = Depends(get_db), current: CurrentUser = Depends(require("pcr:read", "crash:read"))):
    _load_pcr(db, crash_id, rec_id, current)
    rows = db.scalars(
        select(PcrFieldMapping)
        .where(PcrFieldMapping.pcr_id == rec_id)
        .order_by(PcrFieldMapping.created_at)
    )
    out: list[PcrFieldMappingOut] = []
    for m in rows:
        da = db.get(DataAttribute, m.attribute_id)
        out.append(_mapping_out(m, da))
    return out


@crash_router.post("/police-crash-reports/{rec_id}/field-mappings", response_model=PcrFieldMappingOut, status_code=201)
def add_pcr_field_mapping(crash_id: uuid.UUID, rec_id: uuid.UUID, body: PcrFieldMappingIn, db: Session = Depends(get_db), current: CurrentUser = Depends(require("pcr:map"))):
    _load_pcr(db, crash_id, rec_id, current)
    # Resolve the CCFP attribute by code; an unknown code is a 404 (mirrors the
    # rest of the API's "resolve attribute -> NotFound" contract).
    da = db.scalar(select(DataAttribute).where(DataAttribute.code == body.attribute_code))
    if da is None:
        raise NotFound("Data attribute")
    m = PcrFieldMapping(
        pcr_id=rec_id,
        state_field_name=body.state_field_name,
        state_field_position=body.state_field_position,
        attribute_id=da.id,
        notes=body.notes,
        mapped_by=current.id,
    )
    db.add(m)
    db.flush()
    record_audit(db, actor=current, action="CREATE", entity_type="pcr_field_mapping", entity_id=m.id, crash_id=crash_id)
    db.commit()
    return _mapping_out(m, da)


@crash_router.delete("/police-crash-reports/{rec_id}/field-mappings/{mapping_id}", status_code=204)
def delete_pcr_field_mapping(crash_id: uuid.UUID, rec_id: uuid.UUID, mapping_id: uuid.UUID, db: Session = Depends(get_db), current: CurrentUser = Depends(require("pcr:map"))):
    _load_pcr(db, crash_id, rec_id, current)
    m = db.get(PcrFieldMapping, mapping_id)
    if m is None or m.pcr_id != rec_id:
        raise NotFound("PCR field mapping")
    db.delete(m)
    record_audit(db, actor=current, action="DELETE", entity_type="pcr_field_mapping", entity_id=mapping_id, crash_id=crash_id)
    db.commit()


@crash_router.post("/police-crash-reports/{rec_id}/map", response_model=PcrOut)
def map_pcr(crash_id: uuid.UUID, rec_id: uuid.UUID, db: Session = Depends(get_db), current: CurrentUser = Depends(require("pcr:map"))):
    rec = _load_pcr(db, crash_id, rec_id, current)
    # PCR-1: "mapped" must reflect real work — require at least one recorded
    # field mapping before the status can flip to MAPPED.
    mapped_count = db.scalar(
        select(func.count()).select_from(PcrFieldMapping).where(PcrFieldMapping.pcr_id == rec_id)
    )
    if not mapped_count:
        raise BadRequest("Add at least one field mapping before marking the PCR as mapped")
    rec.mapping_status = MappingStatus.MAPPED.value
    rec.mapped_by = current.id
    record_audit(db, actor=current, action="MAP_PCR", entity_type="police_crash_report", entity_id=rec.id, crash_id=crash_id)
    # PCR mapped -> advance into Data Mapping (CRAS-4; forward-only, idempotent).
    advance_phase(db, load_crash(db, crash_id, current), CrashLifecyclePhase.DATA_MAPPING, actor=current)
    db.commit()
    return rec


# =========================================================================== reconstruction
class ReconIn(BaseModel):
    title: str | None = None
    received_date: dt.date | None = None
    document_id: uuid.UUID | None = None


class ReconCodedAttribute(BaseModel):
    """One reconstruction finding coded into a CCFP research attribute (§8.6).
    `attribute_code` resolves a `DataAttribute`; the value carries the coded
    finding. Optional `confidence` mirrors `CrashAttributeValue.confidence`."""
    attribute_code: str
    value_text: str | None = None
    value_json: Any | None = None
    confidence: float | None = None
    # Repeat discriminator (GAP-PCR-03). Reconstruction findings are routinely
    # coded against per-vehicle and per-person attributes (damage, sequence of
    # events, driver actions), all of which repeat under the new PCR form, so
    # the coder must say WHICH unit the finding describes. Validated against the
    # attribute's own `repeats_on`, exactly as set_attribute does.
    unit_type: str | None = None
    unit_number: int | None = None


class ReconCodingIn(BaseModel):
    coding_status: CodingStatus
    # Structured coded findings -> written as provenance-tagged CrashAttributeValue
    # rows (RECONSTRUCTION source) so they reach aggregation/QC/completeness (RECO-1).
    coded_attributes: list[ReconCodedAttribute] = []
    # Legacy free-form narrative summary, retained for the coding-status chip /
    # human notes. No longer the carrier of structured findings.
    coded_findings: dict[str, Any] | None = None


class ReconOut(ORMModel):
    id: uuid.UUID
    crash_id: uuid.UUID
    title: str | None
    received_date: dt.date | None
    document_id: uuid.UUID | None
    coding_status: str
    coded_findings: Any | None


@crash_router.get("/reconstruction-reports", response_model=list[ReconOut])
def list_recon(crash_id: uuid.UUID, db: Session = Depends(get_db), current: CurrentUser = Depends(require("source_data:read", "crash:read"))):
    load_crash(db, crash_id, current)
    return list(db.scalars(select(ReconstructionReport).where(ReconstructionReport.crash_id == crash_id)))


@crash_router.post("/reconstruction-reports", response_model=ReconOut, status_code=201)
def add_recon(
    crash_id: uuid.UUID,
    file: UploadFile | None = File(None),
    title: str | None = Form(None),
    received_date: dt.date | None = Form(None),
    db: Session = Depends(get_db),
    current: CurrentUser = Depends(require("recon:upload")),
):
    """Create a reconstruction report (§8.6). A reconstruction is fundamentally a
    narrative document, so when a file is supplied it is malware-scanned, stored on
    local disk via `storage.put_object`, persisted as a `Document`, and linked via
    `reconstruction_reports.document_id` — mirroring the ELD/document upload path so
    the recon row and its source PDF stay connected. The file is optional: a
    metadata-only reconstruction stub (title/received_date) still works."""
    load_crash(db, crash_id, current)
    rec = ReconstructionReport(crash_id=crash_id, title=title, received_date=received_date)
    if file is not None:
        content = file.file.read()
        scan = storage.scan_for_malware(content)
        if scan == "INFECTED":
            raise BadRequest("Uploaded file failed malware scanning")
        uri, size = storage.put_object(content, key_prefix=f"recon/{crash_id}", file_name=file.filename or "reconstruction.pdf")
        doc = Document(
            crash_id=crash_id, doc_type=DocumentType.PDF.value, file_name=file.filename or "reconstruction.pdf",
            mime_type=file.content_type, storage_uri=uri, size_bytes=size,
            malware_scan=scan, uploaded_by=current.id,
        )
        db.add(doc)
        db.flush()
        rec.document_id = doc.id
    db.add(rec)
    db.flush()
    if file is not None:
        record_audit(db, actor=current, action="UPLOAD", entity_type="document", entity_id=rec.document_id, crash_id=crash_id)
    _link_source(db, crash_id, "RECONSTRUCTION", "RECON", None, "Reconstruction report uploaded")
    record_audit(db, actor=current, action="CREATE", entity_type="reconstruction_report", entity_id=rec.id, crash_id=crash_id)
    advance_phase(db, load_crash(db, crash_id, current), CrashLifecyclePhase.DATA_COLLECTION, actor=current)
    db.commit()
    return rec


@crash_router.get("/reconstruction-reports/{rec_id}", response_model=ReconOut)
def get_recon(crash_id: uuid.UUID, rec_id: uuid.UUID, db: Session = Depends(get_db), current: CurrentUser = Depends(require("source_data:read", "crash:read"))):
    load_crash(db, crash_id, current)
    rec = db.get(ReconstructionReport, rec_id)
    if rec is None or rec.crash_id != crash_id:
        raise NotFound("Reconstruction report")
    return rec


@crash_router.patch("/reconstruction-reports/{rec_id}", response_model=ReconOut)
def code_recon(crash_id: uuid.UUID, rec_id: uuid.UUID, body: ReconCodingIn, db: Session = Depends(get_db), current: CurrentUser = Depends(require("recon:code"))):
    """Manually code reconstruction findings into CCFP research attributes (§8.6).

    Each `coded_attributes` entry resolves a `DataAttribute` by code and writes a
    provenance-tagged `CrashAttributeValue` (`source_system="RECONSTRUCTION"`,
    `source_record_id` -> the reconstruction's `SourceRecord`) using the same
    append-only / `is_current`-flip pattern as `crashes.set_attribute` (§11.3), so
    coded findings flow into aggregation, QC, completeness, and analysis. The whole
    operation (status update + every attribute write + the audit row) commits once.
    """
    load_crash(db, crash_id, current)
    rec = db.get(ReconstructionReport, rec_id)
    if rec is None or rec.crash_id != crash_id:
        raise NotFound("Reconstruction report")

    # Resolve all attribute codes up front so an unknown code fails the whole
    # request (400) before any write — mirrors set_attribute's validation.
    # The unit is resolved up front too (GAP-PCR-03): a finding coded against a
    # repeating attribute without saying which vehicle/person it describes is a
    # client error, and must fail before any write rather than silently landing
    # as a crash-level value that no unit-scoped read will ever return.
    resolved: list[tuple[DataAttribute, ReconCodedAttribute, tuple[str | None, int | None]]] = []
    for coded in body.coded_attributes:
        da = db.scalar(select(DataAttribute).where(DataAttribute.code == coded.attribute_code))
        if da is None:
            raise BadRequest(f"Unknown attribute code: {coded.attribute_code}")
        unit = resolve_attribute_unit(db, da, coded.unit_type, coded.unit_number)
        # Selection cap (GAP-PCR-04): coded findings go through the same
        # validation as a manual write, so reconstruction cannot be a back door
        # around a cap the form states.
        assert_within_cap(da, coded.value_text, coded.value_json)
        resolved.append((da, coded, unit))

    rec.coding_status = body.coding_status.value
    rec.coded_findings = body.coded_findings
    rec.coded_by = current.id

    # Provenance: point each coded value at the reconstruction's source record.
    # Reuse the RECON SourceRecord created at upload (source_data.py add_recon);
    # if absent (e.g. legacy row), create one so provenance is never orphaned.
    src = db.scalar(
        select(SourceRecord)
        .where(SourceRecord.crash_id == crash_id, SourceRecord.source_type == "RECON")
        .order_by(SourceRecord.received_at)
    )
    if src is None and resolved:
        src = SourceRecord(
            crash_id=crash_id, source_system="RECONSTRUCTION", source_type="RECON",
            external_id=None, provenance_note="Reconstruction coded findings",
        )
        db.add(src)
        db.flush()

    now = dt.datetime.now(dt.timezone.utc)
    for da, coded, (unit_type, unit_number) in resolved:
        # Append-only history: retire the prior current value for this attribute
        # AND unit only. The shared helper carries the unit predicate — without
        # it, coding Vehicle 2's damage would retire Vehicle 1's and 3's too.
        supersede_current_attribute_value(
            db, crash_id=crash_id, attribute_id=da.id,
            unit_type=unit_type, unit_number=unit_number,
        )
        db.add(
            CrashAttributeValue(
                crash_id=crash_id, attribute_id=da.id,
                value_text=coded.value_text, value_json=coded.value_json,
                unit_type=unit_type, unit_number=unit_number,
                source_record_id=src.id if src is not None else None,
                source_system="RECONSTRUCTION", confidence=coded.confidence,
                is_current=True, is_edited=True, edited_by=current.id, edited_at=now,
            )
        )

    record_audit(
        db, actor=current, action="CODE_RECON", entity_type="reconstruction_report",
        entity_id=rec.id, crash_id=crash_id,
        after={
            "coding_status": rec.coding_status,
            # Record the unit alongside the code: "V19 on VEHICLE 2" is the
            # auditable fact, not just "V19" (GAP-PCR-03).
            "coded_attributes": [
                da.code if ut is None else f"{da.code}[{ut} {un}]"
                for da, _, (ut, un) in resolved
            ],
        },
    )
    db.commit()
    return rec


# =========================================================================== ELD
# BRD Jan-2026 Appendix E: the MCSAP CMV Inspector and CCFP Project Team analysts
# upload ELD output files (CSV) to the associated crash record, and the system
# extracts their data so it can be analyzed. Everything below is built so that a
# file NEVER ends in an unexplained state: an upload that cannot be an ELD CSV is
# refused synchronously with a specific reason, and a file that is accepted always
# ends PARSED / PARSED_WITH_ERRORS / FAILED with a machine-readable code, a
# human-actionable message, and a per-problem issue list.
class EldFileOut(ORMModel):
    id: uuid.UUID
    crash_id: uuid.UUID
    file_name: str
    document_id: uuid.UUID | None
    ccfp_code_in_file: str | None
    provider: str | None
    model: str | None
    version: str | None
    upload_status: str
    event_count: int | None
    parsed_at: dt.datetime | None
    # PCI-7 (§19.2 l.844): ELD summary / download-status detail.
    eld_downloaded: bool | None = None
    last_entry_at: dt.datetime | None = None
    last_duty_status: str | None = None  # app.enums.DutyStatus value (plain text)
    last_stop_arrived_at: dt.datetime | None = None
    last_stop_departed_at: dt.datetime | None = None
    # --- Parse outcome (BRD Appendix E) ---
    # error_code/error_message are the pair the UI shows next to upload_status so
    # a failure is never an unexplained chip.
    error_code: str | None = None
    error_message: str | None = None
    file_format: str | None = None
    encoding: str | None = None
    delimiter: str | None = None
    file_size_bytes: int | None = None
    line_count: int | None = None
    row_count: int | None = None
    error_count: int = 0
    warning_count: int = 0
    parse_duration_ms: int | None = None
    parse_attempts: int = 0
    # --- Extracted ELD file header segment (49 CFR 395 App. A) ---
    driver_name: str | None = None
    driver_license_number: str | None = None
    driver_license_state: str | None = None
    co_driver_name: str | None = None
    carrier_name: str | None = None
    carrier_usdot: str | None = None
    vin: str | None = None
    power_unit_number: str | None = None
    trailer_numbers: str | None = None
    time_zone_offset: str | None = None
    eld_registration_id: str | None = None
    eld_identifier: str | None = None
    output_file_comment: str | None = None
    file_data_check_value: str | None = None
    sections: dict[str, int] | None = None
    hos_summary: dict[str, Any] | None = None


class EldParseIssueOut(ORMModel):
    """One aggregated parse/validation problem recorded against a file."""

    id: uuid.UUID
    severity: str          # ERROR | WARNING | INFO
    code: str              # stable machine-readable code
    message: str           # human-actionable description
    section: str | None
    line_number: int | None
    column_name: str | None
    raw_value: str | None
    occurrences: int
    details: dict[str, Any] | None


class EldValidationOut(BaseModel):
    """Dry-run result: what WOULD be extracted, without storing anything.

    Lets an inspector check a file before committing it to the crash record —
    the same extraction the background parse runs, reported up-front.
    """

    ok: bool
    file_name: str | None = None
    file_format: str | None = None
    encoding: str | None = None
    delimiter: str | None = None
    file_size_bytes: int = 0
    line_count: int = 0
    row_count: int = 0
    event_count: int = 0
    ccfp_code_in_file: str | None = None
    ccfp_code_matches_crash: bool = False
    error_code: str | None = None
    error_message: str | None = None
    error_count: int = 0
    warning_count: int = 0
    sections: dict[str, int] | None = None
    header: dict[str, Any] | None = None
    hos_summary: dict[str, Any] | None = None
    issues: list[dict[str, Any]] = []


class EldFilePatch(BaseModel):
    """PCI-7: editable ELD summary fields. Only these columns are updatable via
    PATCH; provider/model/version/parse-status are set at upload/parse time.
    `model_dump(exclude_unset=True)` is used so a partial PATCH only touches the
    fields the caller actually sent."""
    eld_downloaded: bool | None = None
    last_entry_at: dt.datetime | None = None
    last_duty_status: str | None = None  # OFF_DUTY|SLEEPER_BERTH|DRIVING|ON_DUTY_NOT_DRIVING
    last_stop_arrived_at: dt.datetime | None = None
    last_stop_departed_at: dt.datetime | None = None


class EldEventOut(ORMModel):
    id: uuid.UUID
    event_sequence: int
    event_timestamp: dt.datetime | None
    duty: str | None
    event_type: str | None
    location: str | None
    miles_driven: float | None
    engine_hours: float | None
    ignition_status: str | None
    # --- ELD-standard event detail (49 CFR 395 App. A) ---
    # record_status/record_origin matter for analysis: an INACTIVE_CHANGED record
    # was edited out by the driver and must not be read as a live duty period.
    section: str | None = None
    line_number: int | None = None
    event_type_code: int | None = None
    event_code: int | None = None
    record_status: str | None = None
    record_origin: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    distance_since_last_coords: float | None = None
    malfunction_indicator: str | None = None
    diagnostic_indicator: str | None = None
    annotation: str | None = None
    driver_identifier: str | None = None
    cmv_identifier: str | None = None
    data_check_value: str | None = None
    is_duplicate: bool = False


def _read_upload(file: UploadFile) -> bytes:
    """Read an upload, refusing anything past the configured ELD size limit.

    Read in bounded chunks rather than `file.read()` so a wrong-file upload of
    arbitrary size cannot be pulled into memory before it is rejected. One byte
    past the limit is enough to know, so the read stops there.
    """
    limit = settings.eld_max_upload_mb * 1024 * 1024
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = file.file.read(1024 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > limit:
            raise BadRequest(
                f"The uploaded file is larger than the {settings.eld_max_upload_mb} MB limit "
                "for an ELD output file. Confirm you selected the ELD output CSV and not a "
                "full data export."
            )
        chunks.append(chunk)
    return b"".join(chunks)


def _validate_eld_payload(content: bytes, file_name: str | None) -> None:
    """Refuse an upload that cannot be an ELD output CSV, with the reason.

    Runs inside the request so the uploader is told immediately and specifically
    ("this is a PDF", "the file is empty", "it has no delimited columns") rather
    than receiving a 201 for a file that quietly fails minutes later in the
    background. Only structural impossibility is refused here — anything that
    depends on the per-study/provider column mapping is decided by the real
    extraction, whose diagnostics are stored on the file and shown in the UI.
    """
    try:
        eld_format.preflight(
            content, file_name, max_bytes=settings.eld_max_upload_mb * 1024 * 1024
        )
    except EldParseError as exc:
        raise BadRequest(exc.message) from exc


@crash_router.post("/eld-files/validate", response_model=EldValidationOut)
def validate_eld(
    crash_id: uuid.UUID,
    file: UploadFile = File(...),
    provider: str | None = Form(None),
    db: Session = Depends(get_db),
    current: CurrentUser = Depends(require("eld:upload")),
):
    """Dry-run an ELD output file: report what would be extracted, store nothing.

    Same decode → format-detect → extract path the background parse uses, with the
    same study/provider column mapping, so the answer here is the answer there.
    Returns 200 with ``ok=false`` and the blocking reason for an unusable file
    rather than a 4xx: this endpoint's job is to *report*, and the caller needs
    the warnings alongside the verdict.
    """
    crash = load_crash(db, crash_id, current)
    content = _read_upload(file)
    scan = storage.scan_for_malware(content)
    if scan == "INFECTED":
        raise BadRequest("Uploaded file failed malware scanning")

    field_aliases, duty_map = resolve_eld_mappings(db, crash.study_id, provider)
    try:
        result = eld_format.extract(
            content, field_aliases=field_aliases, duty_map=duty_map,
            max_events=settings.eld_max_events,
            time_budget_seconds=settings.eld_parse_time_budget_seconds,
        )
    except EldParseError as exc:
        return EldValidationOut(
            ok=False, file_name=file.filename, file_size_bytes=len(content),
            error_code=exc.code, error_message=exc.message,
            error_count=1,
            issues=eld_format.issues_as_dicts(exc.issues)
            + [{"severity": "ERROR", "code": exc.code, "message": exc.message,
                "section": None, "line_number": None, "column_name": None,
                "raw_value": None, "occurrences": 1, "details": {}}],
        )
    return EldValidationOut(
        ok=not result.has_errors,
        file_name=file.filename,
        file_format=result.file_format,
        encoding=result.encoding,
        delimiter=result.delimiter,
        file_size_bytes=len(content),
        line_count=result.line_count,
        row_count=result.row_count,
        event_count=len(result.events),
        ccfp_code_in_file=result.ccfp_code,
        ccfp_code_matches_crash=result.ccfp_code == crash.ccfp_identifier,
        error_code=result.first_error().code if result.has_errors else None,
        error_message=result.first_error().message if result.has_errors else None,
        error_count=result.error_count,
        warning_count=result.warning_count,
        sections=result.sections,
        header={k: v for k, v in result.header.items() if k != "raw_lines"},
        hos_summary=result.hos_summary,
        issues=eld_format.issues_as_dicts(result.issues),
    )


@crash_router.post("/eld-files", response_model=EldFileOut, status_code=201)
def upload_eld(
    crash_id: uuid.UUID,
    background: BackgroundTasks,
    file: UploadFile = File(...),
    provider: str | None = Form(None),
    model: str | None = Form(None),
    version: str | None = Form(None),
    # PCI-7: ELD summary / download-status detail, capturable at upload time
    # (also editable later via PATCH). All optional.
    eld_downloaded: bool | None = Form(None),
    last_entry_at: dt.datetime | None = Form(None),
    last_duty_status: str | None = Form(None),
    last_stop_arrived_at: dt.datetime | None = Form(None),
    last_stop_departed_at: dt.datetime | None = Form(None),
    db: Session = Depends(get_db),
    current: CurrentUser = Depends(require("eld:upload")),
):
    crash = load_crash(db, crash_id, current)
    content = _read_upload(file)
    scan = storage.scan_for_malware(content)
    if scan == "INFECTED":
        raise BadRequest("Uploaded file failed malware scanning")
    # Structural pre-flight BEFORE anything is stored: a PDF, an .xlsx, an empty
    # file or a non-delimited payload is refused here with the reason and the fix,
    # so the uploader is not handed a 201 for a file that can never extract.
    _validate_eld_payload(content, file.filename)
    uri, size = storage.put_object(content, key_prefix=f"eld/{crash_id}", file_name=file.filename or "eld.csv")
    doc = Document(
        crash_id=crash_id, doc_type=DocumentType.ELD_CSV.value, file_name=file.filename or "eld.csv",
        mime_type=file.content_type or "text/csv", storage_uri=uri, size_bytes=size,
        malware_scan=scan, uploaded_by=current.id,
    )
    db.add(doc)
    db.flush()
    # RECO-2: do NOT fabricate the link by copying the crash identifier. The CCFP
    # code is carried inside the uploaded file's output-file comment and is parsed
    # out by parse_eld_file (below), which sets ccfp_code_in_file to the real value
    # (or leaves it None when absent). The source record likewise records no
    # external_id at upload time — the QC link check compares the parsed code.
    ef = EldFile(
        crash_id=crash_id, file_name=file.filename or "eld.csv", document_id=doc.id,
        ccfp_code_in_file=None, provider=provider, model=model, version=version,
        uploaded_by=current.id,
        eld_downloaded=eld_downloaded, last_entry_at=last_entry_at,
        last_duty_status=last_duty_status, last_stop_arrived_at=last_stop_arrived_at,
        last_stop_departed_at=last_stop_departed_at,
    )
    db.add(ef)
    db.flush()
    _link_source(db, crash_id, "eRODS", "ELD", None, "ELD/eRODS file uploaded")
    record_audit(db, actor=current, action="UPLOAD_ELD", entity_type="eld_file", entity_id=ef.id, crash_id=crash_id)
    advance_phase(db, crash, CrashLifecyclePhase.DATA_COLLECTION, actor=current)
    db.commit()
    background.add_task(parse_eld_file, ef.id)
    return ef


@crash_router.patch("/eld-files/{file_id}", response_model=EldFileOut)
def update_eld_file(
    crash_id: uuid.UUID, file_id: uuid.UUID, body: EldFilePatch,
    db: Session = Depends(get_db), current: CurrentUser = Depends(require("eld:upload")),
):
    """Edit an ELD file's PCI-7 summary fields (download status / last entry /
    last duty status / last stop). Mirrors `update_inspection`/`update_pcr`: load
    the crash (scope-checked), ownership-check the record, `setattr` only the
    updatable summary columns, audit, commit. Only the fields the caller sent are
    touched (`exclude_unset`)."""
    load_crash(db, crash_id, current)
    ef = db.get(EldFile, file_id)
    if ef is None or ef.crash_id != crash_id:
        raise NotFound("ELD file")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(ef, k, v)
    record_audit(db, actor=current, action="UPDATE", entity_type="eld_file", entity_id=ef.id, crash_id=crash_id)
    db.commit()
    db.refresh(ef)
    return ef


@crash_router.get("/eld-files", response_model=list[EldFileOut])
def list_eld_files(crash_id: uuid.UUID, db: Session = Depends(get_db), current: CurrentUser = Depends(require("source_data:read", "crash:read"))):
    load_crash(db, crash_id, current)
    return list(db.scalars(select(EldFile).where(EldFile.crash_id == crash_id)))


@crash_router.get("/eld-files/{file_id}", response_model=EldFileOut)
def get_eld_file(crash_id: uuid.UUID, file_id: uuid.UUID, db: Session = Depends(get_db), current: CurrentUser = Depends(require("source_data:read", "crash:read"))):
    load_crash(db, crash_id, current)
    ef = db.get(EldFile, file_id)
    if ef is None or ef.crash_id != crash_id:
        raise NotFound("ELD file")
    return ef


@crash_router.get("/eld-files/{file_id}/issues", response_model=list[EldParseIssueOut])
def list_eld_issues(
    crash_id: uuid.UUID, file_id: uuid.UUID,
    severity: str | None = None,
    db: Session = Depends(get_db),
    current: CurrentUser = Depends(require("source_data:read", "crash:read")),
):
    """Every problem the extraction recorded for this file (BRD Appendix E).

    This is what makes "never fails silently" verifiable rather than a claim: an
    ERROR explains why extraction stopped or was incomplete, a WARNING names a
    value that could not be interpreted and the line it was on, and an INFO
    records an interpretation the parser made (encoding fallback, positional
    header reading, positions the ELD itself could not capture). Ordered
    ERROR → WARNING → INFO, then by line.
    """
    load_crash(db, crash_id, current)
    ef = db.get(EldFile, file_id)
    if ef is None or ef.crash_id != crash_id:
        raise NotFound("ELD file")
    stmt = select(EldParseIssue).where(EldParseIssue.eld_file_id == file_id)
    if severity:
        stmt = stmt.where(EldParseIssue.severity == severity.upper())
    rows = list(db.scalars(stmt))
    rank = {
        EldIssueSeverity.ERROR.value: 0,
        EldIssueSeverity.WARNING.value: 1,
        EldIssueSeverity.INFO.value: 2,
    }
    rows.sort(key=lambda r: (rank.get(r.severity, 3), r.line_number or 0, r.code))
    return rows


@crash_router.post("/eld-files/{file_id}/reparse", response_model=EldFileOut)
def reparse_eld_file(
    crash_id: uuid.UUID, file_id: uuid.UUID,
    db: Session = Depends(get_db),
    current: CurrentUser = Depends(require("eld:upload")),
):
    """Re-run extraction on a file already stored (BRD Appendix E, §3.4).

    The recovery path for a file that FAILED or extracted partially because of a
    mapping gap: an administrator adds the provider's column names or duty codes
    under ELD field mappings, then re-runs this. Run synchronously so the caller
    sees the new outcome in the response rather than having to poll — the parse
    is bounded by the same event cap and time budget as the background run.
    """
    load_crash(db, crash_id, current)
    ef = db.get(EldFile, file_id)
    if ef is None or ef.crash_id != crash_id:
        raise NotFound("ELD file")
    record_audit(
        db, actor=current, action="REPARSE_ELD", entity_type="eld_file",
        entity_id=ef.id, crash_id=crash_id,
    )
    db.commit()
    parse_eld_file(ef.id, db=db)
    db.expire_all()
    refreshed = db.get(EldFile, file_id)
    if refreshed is None:
        raise NotFound("ELD file")
    return refreshed


@crash_router.get("/eld-events", response_model=list[EldEventOut])
def list_eld_events(crash_id: uuid.UUID, db: Session = Depends(get_db), current: CurrentUser = Depends(require("source_data:read", "crash:read"))):
    load_crash(db, crash_id, current)
    stmt = (
        select(EldEvent)
        .join(EldFile, EldFile.id == EldEvent.eld_file_id)
        .where(EldFile.crash_id == crash_id)
        .order_by(EldEvent.event_sequence)
    )
    return list(db.scalars(stmt))


# ===========================================================================
# Module-exported router: main.py includes this single `router` under /api/v1.
# It merges the crash-scoped endpoints (/crashes/{crash_id}/...) with the
# study-scoped PCI field-definitions read (/studies/{study_id}/...), so the
# study path is NOT forced under the crashes prefix.
# ===========================================================================
# ===========================================================================
# PCR bulk ingest (GAP-SOO-05) — "import/ingest CCFP-required PCR data elements
# and attributes from States' existing PCRs, with a primary goal of minimizing
# data sharing burden to the States".
#
# The burden-minimising choice is that CCFP adapts to the State's existing
# export rather than publishing a format for 50 States to conform to. So the
# column mapping is configuration (pcr_column_mappings), and this endpoint is
# a generic CSV reader driven by it. Onboarding a State = inserting mapping
# rows, not writing an importer.
# ===========================================================================
def _norm_header(value: str) -> str:
    """Normalise a header for comparison: case- and punctuation-insensitive.

    'Crash Date', 'crash_date' and 'CRASH-DATE' are the same column to a State's
    export author; requiring a separate mapping row for each would be the kind of
    friction this feature exists to remove.
    """
    return re.sub(r"[^a-z0-9]+", "_", (value or "").strip().lower()).strip("_")


def _resolve_pcr_mappings(db: Session, study_id: uuid.UUID | None, state_code: str | None) -> dict[str, DataAttribute]:
    """normalised header -> DataAttribute for one (study, State).

    Specificity: study+state (3) > state-only (2) > study-only (1) > global (0),
    with `priority` breaking ties — the same precedence ELD mappings use, so
    there is one rule to learn rather than two.
    """
    rows = list(
        db.execute(
            select(PcrColumnMapping, DataAttribute)
            .join(DataAttribute, DataAttribute.id == PcrColumnMapping.attribute_id)
            .where(
                PcrColumnMapping.is_active.is_(True),
                or_(PcrColumnMapping.study_id == study_id, PcrColumnMapping.study_id.is_(None)),
                or_(PcrColumnMapping.state_code == state_code, PcrColumnMapping.state_code.is_(None)),
            )
        ).all()
    )

    def specificity(m: PcrColumnMapping) -> tuple[int, int]:
        score = (2 if m.state_code is not None else 0) + (1 if m.study_id is not None else 0)
        return (score, m.priority)

    best: dict[str, tuple[tuple[int, int], DataAttribute]] = {}
    for mapping, attribute in rows:
        key = _norm_header(mapping.source_header)
        rank = specificity(mapping)
        if key not in best or rank > best[key][0]:
            best[key] = (rank, attribute)
    return {k: v[1] for k, v in best.items()}


class PcrColumnMappingIn(BaseModel):
    source_header: str
    attribute_code: str
    study_id: uuid.UUID | None = None
    state_code: str | None = None
    priority: int = 0
    notes: str | None = None


class PcrColumnMappingOut(ORMModel):
    id: uuid.UUID
    study_id: uuid.UUID | None
    state_code: str | None
    source_header: str
    attribute_id: uuid.UUID
    priority: int
    is_active: bool
    notes: str | None


@study_router.get("/pcr-column-mappings", response_model=list[PcrColumnMappingOut])
def list_pcr_column_mappings(
    state_code: str | None = None,
    db: Session = Depends(get_db),
    current: CurrentUser = Depends(require("source_data:read")),
):
    stmt = select(PcrColumnMapping).where(PcrColumnMapping.is_active.is_(True))
    if state_code:
        stmt = stmt.where(PcrColumnMapping.state_code == state_code)
    return list(db.scalars(stmt.order_by(PcrColumnMapping.state_code, PcrColumnMapping.source_header)))


@study_router.post("/pcr-column-mappings", response_model=PcrColumnMappingOut, status_code=201)
def create_pcr_column_mapping(
    body: PcrColumnMappingIn,
    db: Session = Depends(get_db),
    # Configuring how a State's columns land in CCFP attributes is the same act
    # as mapping a filed PCR's fields, so it takes the same permission.
    current: CurrentUser = Depends(require("pcr:map")),
):
    attribute = db.scalar(select(DataAttribute).where(DataAttribute.code == body.attribute_code))
    if attribute is None:
        raise BadRequest(f"Unknown attribute code: {body.attribute_code}")
    row = PcrColumnMapping(
        study_id=body.study_id, state_code=body.state_code, source_header=body.source_header,
        attribute_id=attribute.id, priority=body.priority, notes=body.notes, created_by=current.id,
    )
    db.add(row)
    db.flush()
    record_audit(db, actor=current, action="CREATE", entity_type="pcr_column_mapping", entity_id=row.id)
    db.commit()
    return row


@study_router.post("/pcr-imports")
def import_pcr_bulk(
    file: UploadFile = File(...),
    state_code: str = Form(...),
    study_id: uuid.UUID = Form(...),
    # Default TRUE: a bulk write across many crash records should have to be
    # asked for explicitly. The dry run returns exactly what a commit would do,
    # so an operator can see the effect before causing it.
    dry_run: bool = Form(True),
    db: Session = Depends(get_db),
    current: CurrentUser = Depends(require("source_data:ingest")),
):
    """Ingest a State's own PCR export, mapped by configuration.

    Rows are matched to existing crashes on `local_report_number` — the number
    the State already puts on its report, so no CCFP identifier has to travel
    back to the State. Unmatched rows are reported, never invented as crashes:
    a PCR arriving for a crash CCFP does not know about is a routing question
    for a human, not something to silently create.
    """
    content = file.file.read()
    if len(content) > settings.max_upload_mb * 1024 * 1024:
        raise BadRequest(f"File exceeds the {settings.max_upload_mb} MB maximum")
    try:
        text_body = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise BadRequest("File must be UTF-8 encoded CSV") from None

    reader = csv.DictReader(io.StringIO(text_body))
    if not reader.fieldnames:
        raise BadRequest("CSV has no header row")

    mappings = _resolve_pcr_mappings(db, study_id, state_code)
    if not mappings:
        raise BadRequest(
            f"No PCR column mappings configured for State {state_code}; "
            "configure them via POST /pcr-column-mappings before importing"
        )

    header_to_attr = {}
    unmapped_headers = []
    for header in reader.fieldnames:
        attribute = mappings.get(_norm_header(header))
        if attribute is None:
            unmapped_headers.append(header)
        else:
            header_to_attr[header] = attribute

    # A file whose report-number column is not mapped cannot be matched to any
    # crash, so fail loudly rather than reporting every row as unmatched.
    report_headers = [h for h in reader.fieldnames if _norm_header(h) in
                      ("local_report_number", "report_number", "crash_report_number", "pcr_number")]
    if not report_headers:
        raise BadRequest(
            "CSV must carry a local report number column (e.g. 'Local Report Number') "
            "so rows can be matched to existing crash records"
        )
    report_header = report_headers[0]

    matched = unmatched = values_written = 0
    unmatched_rows: list[str] = []
    for row in reader:
        report_no = (row.get(report_header) or "").strip()
        if not report_no:
            continue
        crash = db.scalar(
            select(Crash).where(
                Crash.local_report_number == report_no,
                Crash.state_code == state_code,
                Crash.study_id == study_id,
            )
        )
        if crash is None:
            unmatched += 1
            if len(unmatched_rows) < 25:
                unmatched_rows.append(report_no)
            continue
        matched += 1
        if dry_run:
            values_written += sum(1 for h in header_to_attr if (row.get(h) or "").strip())
            continue

        pcr = db.scalar(
            select(PoliceCrashReport).where(PoliceCrashReport.crash_id == crash.id)
        ) or PoliceCrashReport(
            crash_id=crash.id, state_code=state_code, ingestion_path="DIRECT_STATE",
            source_repository=file.filename, pcr_number=report_no,
        )
        pcr.mapping_status = "MAPPED"
        pcr.mapped_by = current.id
        db.add(pcr)

        src = SourceRecord(
            crash_id=crash.id, source_system=f"STATE_PCR_{state_code}", source_type="PCR",
            external_id=report_no, provenance_note=f"Bulk import from {file.filename}",
        )
        db.add(src)
        db.flush()

        for header, attribute in header_to_attr.items():
            raw = (row.get(header) or "").strip()
            if not raw:
                continue
            # Append-only history, identical to every other attribute write:
            # retire the current row, insert the new one with provenance.
            db.query(CrashAttributeValue).filter(
                CrashAttributeValue.crash_id == crash.id,
                CrashAttributeValue.attribute_id == attribute.id,
                CrashAttributeValue.is_current.is_(True),
            ).update({"is_current": False})
            db.add(CrashAttributeValue(
                crash_id=crash.id, attribute_id=attribute.id, value_text=raw,
                source_system=f"STATE_PCR_{state_code}", source_record_id=src.id,
                is_current=True, is_edited=False,
            ))
            values_written += 1

        record_audit(
            db, actor=current, action="IMPORT", entity_type="police_crash_report",
            entity_id=pcr.id, crash_id=crash.id, after={"source_file": file.filename},
        )

    if not dry_run:
        db.commit()

    return {
        "dry_run": dry_run,
        "state_code": state_code,
        "mapped_columns": {h: a.code for h, a in header_to_attr.items()},
        "unmapped_columns": unmapped_headers,
        "crashes_matched": matched,
        "rows_unmatched": unmatched,
        "unmatched_report_numbers": unmatched_rows,
        "attribute_values_written": values_written,
    }


router = APIRouter()
router.include_router(crash_router)
router.include_router(study_router)
