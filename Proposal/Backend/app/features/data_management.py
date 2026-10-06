"""Data management & QC: raw/aggregated views, QC rules, contributing factors
(documentation §8.8, §5 Phase 5/6).

Also owns **CCFP Aggregated Data** (BRD January 2026): the assembled
document that links raw CCFP crash data to records in the Appendix D external
systems, together with the linkage endpoints that produce it.
"""
from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.common import ORMModel
from app.core.audit import record_audit
from app.core.database import get_db
from app.core.errors import BadRequest, Conflict, NotFound
from app.core.permissions import require
from app.core.security import CurrentUser, get_current_user
from app.enums import CrashLifecyclePhase, LinkMethod, RuleSeverity
from app.features.crashes import AttributeValueOut, advance_phase, load_crash
from app.models import (
    AttributeRequirement,
    ContributingFactorSelection,
    Crash,
    CrashAttributeValue,
    CrashExternalLink,
    DataAttribute,
    DataQualityRule,
    EldFile,
    PoliceCrashReport,
    PostCrashInspection,
    PostCrashInvestigation,
    ReconstructionReport,
    RefContributingFactorGroup,
    RefContributingFactorValue,
    RefExternalSystem,
    RefPcrSection,
    SourceRecord,
    StudyParameter,
    User,
)

router = APIRouter(tags=["data-management"])


# =========================================================================== QC rules
class QcRuleIn(BaseModel):
    code: str
    name: str
    rule_type: str
    severity: RuleSeverity = RuleSeverity.WARNING
    attribute_id: uuid.UUID | None = None
    definition: dict[str, Any] | None = None
    is_active: bool = True


class QcRuleUpdate(BaseModel):
    name: str | None = None
    rule_type: str | None = None
    severity: RuleSeverity | None = None
    definition: dict[str, Any] | None = None
    is_active: bool | None = None


class QcRuleOut(ORMModel):
    id: uuid.UUID
    code: str
    name: str
    rule_type: str
    severity: str
    attribute_id: uuid.UUID | None
    definition: Any | None
    is_active: bool


@router.get("/data-quality-rules", response_model=list[QcRuleOut])
def list_qc_rules(db: Session = Depends(get_db), current: CurrentUser = Depends(require("data_mgmt:qc", "crash:read"))):
    return list(db.scalars(select(DataQualityRule).order_by(DataQualityRule.code)))


@router.post("/data-quality-rules", response_model=QcRuleOut, status_code=201)
def create_qc_rule(body: QcRuleIn, db: Session = Depends(get_db), current: CurrentUser = Depends(require("admin:system", "study:configure"))):
    if db.scalar(select(DataQualityRule).where(DataQualityRule.code == body.code)):
        raise BadRequest("Rule code already exists")
    data = body.model_dump()
    data["severity"] = body.severity.value
    rule = DataQualityRule(**data)
    db.add(rule)
    db.flush()
    record_audit(db, actor=current, action="CREATE", entity_type="data_quality_rule", entity_id=rule.id)
    db.commit()
    return rule


@router.patch("/data-quality-rules/{rule_id}", response_model=QcRuleOut)
def update_qc_rule(rule_id: uuid.UUID, body: QcRuleUpdate, db: Session = Depends(get_db), current: CurrentUser = Depends(require("admin:system", "study:configure"))):
    rule = db.get(DataQualityRule, rule_id)
    if rule is None:
        raise NotFound("QC rule")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(rule, k, v.value if hasattr(v, "value") else v)
    record_audit(db, actor=current, action="UPDATE", entity_type="data_quality_rule", entity_id=rule.id)
    db.commit()
    return rule


# =========================================================================== raw & aggregated views
@router.get("/crashes/{crash_id}/raw-data")
def raw_data(crash_id: uuid.UUID, db: Session = Depends(get_db), current: CurrentUser = Depends(require("data_mgmt:read_raw"))):
    load_crash(db, crash_id, current)

    def count(model) -> int:
        return db.scalar(select(func.count()).select_from(model).where(model.crash_id == crash_id)) or 0

    sources = list(db.scalars(select(SourceRecord).where(SourceRecord.crash_id == crash_id)))
    return {
        "crash_id": str(crash_id),
        "counts": {
            "inspections": count(PostCrashInspection),
            "investigations": count(PostCrashInvestigation),
            "police_crash_reports": count(PoliceCrashReport),
            "reconstruction_reports": count(ReconstructionReport),
            "eld_files": count(EldFile),
            "source_records": len(sources),
        },
        "source_records": [
            {"source_system": s.source_system, "source_type": s.source_type, "external_id": s.external_id, "uri": s.raw_zone_uri}
            for s in sources
        ],
    }


# =========================================================================== CCFP Aggregated Data
# BRD January 2026. "CCFP Aggregated Data" is a defined term:
#   "Linked CCFP crash data (e.g., data from post-crash inspections, PCRs,
#    post-crash investigations, and crash reconstructions), and data from
#    external systems (e.g., SafeSpect Inspections, Drug and Alcohol
#    Clearinghouse, etc.) that are related to a specific crash."
# Producing it is a CCFP Database Administrator duty with Create/Update/Read.
# Before this change the endpoint below returned four integers; it now returns
# the aggregated document itself, with those integers retained (top level AND
# under `summary`) so existing callers keep working.
READ_AGGREGATED = ("aggregated:read", "data_mgmt:read_aggregated", "crash:read")


class ExternalSystemOut(ORMModel):
    """One Appendix D external data source."""
    code: str
    name: str
    owner: str | None
    is_fmcsa_owned: bool
    relevant_data: str | None
    is_active: bool


class SourceRecordOut(ORMModel):
    """A raw CCFP-collected record registered against the crash."""
    id: uuid.UUID
    source_system: str
    source_type: str
    external_id: str | None
    raw_zone_uri: str | None
    provenance_note: str | None
    received_at: dt.datetime


class ExternalLinkIn(BaseModel):
    source_system: str
    external_ref: str
    link_method: LinkMethod = LinkMethod.MANUAL
    matched_on: dict[str, Any] | None = None
    confidence: float | None = None
    notes: str | None = None


class ExternalLinkOut(BaseModel):
    id: uuid.UUID
    crash_id: uuid.UUID
    source_system: str
    source_system_name: str | None
    external_ref: str
    link_method: str
    matched_on: Any | None
    confidence: float | None
    notes: str | None
    linked_by: uuid.UUID | None
    linked_by_name: str | None
    linked_at: dt.datetime
    is_current: bool


class AggregatedSummary(BaseModel):
    """Completeness counters — the pre-existing payload of this endpoint."""
    current_attribute_count: int
    required_attribute_count: int
    required_present: int
    required_missing: int
    source_record_count: int
    external_link_count: int


class AggregatedOut(BaseModel):
    """The full CCFP Aggregated Data document for one crash."""
    crash_id: uuid.UUID
    ccfp_identifier: str | None
    study_id: uuid.UUID | None
    summary: AggregatedSummary
    # Retained at the top level for backward compatibility with callers written
    # against the counts-only response this endpoint used to return.
    current_attribute_count: int
    required_attribute_count: int
    required_present: int
    required_missing: int
    attributes: list[AttributeValueOut]
    source_records: list[SourceRecordOut]
    external_links: list[ExternalLinkOut]


def _system_names(db: Session) -> dict[str, str]:
    return dict(db.execute(select(RefExternalSystem.code, RefExternalSystem.name)).all())


def _linker_names(db: Session, links: list[CrashExternalLink]) -> dict[uuid.UUID, str]:
    ids = {ln.linked_by for ln in links if ln.linked_by}
    if not ids:
        return {}
    return dict(db.execute(select(User.id, User.full_name).where(User.id.in_(ids))).all())


def _link_out(
    link: CrashExternalLink,
    system_names: dict[str, str],
    linker_names: dict[uuid.UUID, str],
) -> ExternalLinkOut:
    return ExternalLinkOut(
        id=link.id,
        crash_id=link.crash_id,
        source_system=link.source_system,
        source_system_name=system_names.get(link.source_system),
        external_ref=link.external_ref,
        link_method=link.link_method,
        matched_on=link.matched_on,
        confidence=float(link.confidence) if link.confidence is not None else None,
        notes=link.notes,
        linked_by=link.linked_by,
        linked_by_name=linker_names.get(link.linked_by) if link.linked_by else None,
        linked_at=link.linked_at,
        is_current=link.is_current,
    )


def _current_links(db: Session, crash_id: uuid.UUID) -> list[CrashExternalLink]:
    return list(
        db.scalars(
            select(CrashExternalLink)
            .where(CrashExternalLink.crash_id == crash_id, CrashExternalLink.is_current.is_(True))
            .order_by(CrashExternalLink.source_system, CrashExternalLink.external_ref)
        )
    )


@router.get("/external-systems", response_model=list[ExternalSystemOut])
def list_external_systems(
    include_inactive: bool = False,
    db: Session = Depends(get_db),
    current: CurrentUser = Depends(get_current_user),
):
    """Appendix D external data sources.

    A non-sensitive reference catalog — readable by any authenticated user, the
    same treatment as ``/contributing-factor-groups`` and ``/roles``. Retired
    sources are hidden unless ``?include_inactive=true``, so a historical link
    to a decommissioned system still resolves to a name.
    """
    stmt = select(RefExternalSystem)
    if not include_inactive:
        stmt = stmt.where(RefExternalSystem.is_active.is_(True))
    return list(db.scalars(stmt.order_by(RefExternalSystem.sort_order, RefExternalSystem.code)))


@router.get("/crashes/{crash_id}/aggregated", response_model=AggregatedOut)
def aggregated(crash_id: uuid.UUID, db: Session = Depends(get_db), current: CurrentUser = Depends(require(*READ_AGGREGATED))):
    """Return the CCFP Aggregated Data document for one crash.

    Three parts, matching the BRD's definition: the canonical attribute values
    with their provenance, the raw CCFP-collected source records, and the links
    to Appendix D external systems. Attribute sensitivity redaction is identical
    to ``GET /crashes/{id}/attributes`` — a caller who fails
    ``can_view_sensitivity`` sees ``redacted=True`` with the value nulled, so
    assembling the document cannot become a disclosure path.
    """
    crash = load_crash(db, crash_id, current)

    rows = db.execute(
        select(CrashAttributeValue, DataAttribute)
        .join(DataAttribute, DataAttribute.id == CrashAttributeValue.attribute_id)
        .where(CrashAttributeValue.crash_id == crash_id, CrashAttributeValue.is_current.is_(True))
        # Same ordering as GET /crashes/{id}/attributes (GAP-PCR-03): crash-level
        # values first, then each repeating unit in position order. The tab
        # groups on this, so ordering by code alone would interleave Trailer 1
        # and Trailer 2 rows.
        .order_by(
            CrashAttributeValue.unit_type.nulls_first(),
            CrashAttributeValue.unit_number.nulls_first(),
            DataAttribute.code,
        )
    ).all()
    attributes = []
    for cav, da in rows:
        allowed = current.can_view_sensitivity(da.sensitivity)
        attributes.append(
            AttributeValueOut(
                attribute_id=da.id, code=da.code, name=da.name, pcr_section=da.pcr_section,
                sensitivity=da.sensitivity,
                value_text=cav.value_text if allowed else None,
                value_json=cav.value_json if allowed else None,
                source_system=cav.source_system,
                confidence=float(cav.confidence) if cav.confidence is not None else None,
                source_record_id=cav.source_record_id,
                is_edited=cav.is_edited, redacted=not allowed,
                # Repeat + cardinality metadata (GAP-PCR-02/-03/-04). This
                # endpoint reuses AttributeValueOut, so omitting these left them
                # defaulting to None: the aggregated view silently lost per-unit
                # grouping and the selection caps that the crash attributes
                # endpoint returns.
                unit_type=cav.unit_type, unit_number=cav.unit_number,
                repeats_on=da.repeats_on, max_selections=da.max_selections,
                applies_to=da.applies_to,
            )
        )

    sources = list(
        db.scalars(
            select(SourceRecord)
            .where(SourceRecord.crash_id == crash_id)
            .order_by(SourceRecord.received_at)
        )
    )
    links = _current_links(db, crash_id)
    system_names = _system_names(db)
    linker_names = _linker_names(db, links)

    present = {cav.attribute_id for cav, _ in rows}
    required = set(
        db.scalars(
            select(AttributeRequirement.attribute_id).where(
                AttributeRequirement.study_id == crash.study_id,
                AttributeRequirement.is_required.is_(True),
            )
        )
    )
    summary = AggregatedSummary(
        current_attribute_count=len(present),
        required_attribute_count=len(required),
        required_present=len(required & present),
        required_missing=len(required - present),
        source_record_count=len(sources),
        external_link_count=len(links),
    )
    return AggregatedOut(
        crash_id=crash_id,
        ccfp_identifier=crash.ccfp_identifier,
        study_id=crash.study_id,
        summary=summary,
        current_attribute_count=summary.current_attribute_count,
        required_attribute_count=summary.required_attribute_count,
        required_present=summary.required_present,
        required_missing=summary.required_missing,
        attributes=attributes,
        source_records=[SourceRecordOut.model_validate(s) for s in sources],
        external_links=[_link_out(ln, system_names, linker_names) for ln in links],
    )


@router.get("/crashes/{crash_id}/external-links", response_model=list[ExternalLinkOut])
def list_external_links(
    crash_id: uuid.UUID,
    include_historical: bool = False,
    db: Session = Depends(get_db),
    current: CurrentUser = Depends(require(*READ_AGGREGATED)),
):
    """List the crash's external-system links.

    Current links only by default; ``?include_historical=true`` adds the
    superseded rows retained by the append-only unlink.
    """
    load_crash(db, crash_id, current)
    if include_historical:
        links = list(
            db.scalars(
                select(CrashExternalLink)
                .where(CrashExternalLink.crash_id == crash_id)
                .order_by(CrashExternalLink.is_current.desc(), CrashExternalLink.linked_at.desc())
            )
        )
    else:
        links = _current_links(db, crash_id)
    system_names = _system_names(db)
    return [_link_out(ln, system_names, _linker_names(db, links)) for ln in links]


@router.post("/crashes/{crash_id}/external-links", response_model=ExternalLinkOut, status_code=201)
def add_external_link(
    crash_id: uuid.UUID,
    body: ExternalLinkIn,
    db: Session = Depends(get_db),
    current: CurrentUser = Depends(require("aggregated:link")),
):
    """Link this crash to a record in an Appendix D external system.

    Deliberately NOT gated on the completeness lock. The lock (DATA-1, §8.8)
    protects the canonical crash record from silent edits; an external link adds
    a reference alongside it and never mutates source or canonical data — and
    external enrichment is precisely what happens after a record completes. The
    CCFP Database Administrator, who owns this action, holds no ``crash:unlock``
    permission, so a lock gate here would make the assigned duty unperformable.
    """
    load_crash(db, crash_id, current)

    code = body.source_system.strip().upper()
    system = db.get(RefExternalSystem, code)
    if system is None:
        raise BadRequest(f"Unknown external system code: {body.source_system}")
    if not system.is_active:
        raise BadRequest(f"External system {code} is retired and cannot receive new links")

    external_ref = body.external_ref.strip()
    if not external_ref:
        raise BadRequest("external_ref is required")
    if body.confidence is not None and not 0 <= body.confidence <= 100:
        raise BadRequest("confidence must be between 0 and 100")

    existing = db.scalar(
        select(CrashExternalLink).where(
            CrashExternalLink.crash_id == crash_id,
            CrashExternalLink.source_system == code,
            CrashExternalLink.external_ref == external_ref,
            CrashExternalLink.is_current.is_(True),
        )
    )
    if existing is not None:
        raise Conflict(f"{code} record {external_ref} is already linked to this crash")

    link = CrashExternalLink(
        crash_id=crash_id,
        source_system=code,
        external_ref=external_ref,
        link_method=body.link_method.value,
        matched_on=body.matched_on,
        confidence=body.confidence,
        notes=body.notes,
        linked_by=current.id,
    )
    db.add(link)
    db.flush()
    record_audit(
        db, actor=current, action="LINK_EXTERNAL", entity_type="crash_external_link",
        entity_id=link.id, crash_id=crash_id,
        after={"source_system": code, "external_ref": external_ref, "link_method": link.link_method},
    )
    db.commit()
    db.refresh(link)
    return _link_out(link, _system_names(db), _linker_names(db, [link]))


@router.delete("/crashes/{crash_id}/external-links/{link_id}", status_code=204)
def remove_external_link(
    crash_id: uuid.UUID,
    link_id: uuid.UUID,
    db: Session = Depends(get_db),
    current: CurrentUser = Depends(require("aggregated:link")),
):
    """Unlink an external-system record from this crash.

    Append-only: the row is retained with ``is_current = False`` plus who removed
    it and when, so the linkage history survives and the same reference can be
    re-linked later. Audited as a state change.
    """
    load_crash(db, crash_id, current)
    link = db.get(CrashExternalLink, link_id)
    if link is None or link.crash_id != crash_id:
        raise NotFound("External link")
    if not link.is_current:
        raise BadRequest("External link has already been removed")

    before = {"source_system": link.source_system, "external_ref": link.external_ref}
    link.is_current = False
    link.unlinked_by = current.id
    link.unlinked_at = dt.datetime.now(dt.timezone.utc)
    record_audit(
        db, actor=current, action="UNLINK_EXTERNAL", entity_type="crash_external_link",
        entity_id=link.id, crash_id=crash_id, before=before,
    )
    db.commit()


# =========================================================================== contributing factors
class FactorIn(BaseModel):
    factor_group_code: str | None = None
    factor_value: str
    rank: int


class FactorsIn(BaseModel):
    factors: list[FactorIn]


class FactorOut(ORMModel):
    id: uuid.UUID
    crash_id: uuid.UUID
    factor_group_id: uuid.UUID | None
    factor_value: str
    rank: int


class FactorGroupOut(ORMModel):
    id: uuid.UUID
    code: str
    name: str
    applies_to: str


class FactorValueOut(ORMModel):
    id: uuid.UUID
    factor_group_id: uuid.UUID
    code: str | None
    label: str


@router.get("/contributing-factor-groups", response_model=list[FactorGroupOut])
def list_factor_groups(db: Session = Depends(get_db), current: CurrentUser = Depends(get_current_user)):
    """BRD-specified contributing-factor groups. This is a non-sensitive reference
    catalog (shown on the Reference page alongside ``/roles`` and ``/permissions``),
    so it is readable by any authenticated user rather than gated on ``crash:read``."""
    return list(db.scalars(select(RefContributingFactorGroup).order_by(RefContributingFactorGroup.sort_order)))


@router.get("/contributing-factor-values", response_model=list[FactorValueOut])
def list_factor_values(
    group_code: str | None = None,
    db: Session = Depends(get_db),
    current: CurrentUser = Depends(get_current_user),
):
    """Per-group catalog of allowed contributing-factor values (DATA-7, §5 Phase 6).

    Optionally filter to a single group via ``?group_code=``. A non-sensitive reference
    catalog readable by any authenticated user, consistent with ``list_factor_groups``."""
    stmt = select(RefContributingFactorValue)
    if group_code:
        stmt = stmt.join(
            RefContributingFactorGroup,
            RefContributingFactorValue.factor_group_id == RefContributingFactorGroup.id,
        ).where(RefContributingFactorGroup.code == group_code)
    return list(db.scalars(stmt.order_by(RefContributingFactorValue.sort_order)))


# --------------------------------------------------------------------------- PCR-section summary (BRD DL4)
# Which PCR sections the contributing-factor prompt summarises. Derived from the
# BRD-named factor groups themselves rather than listed as a literal: each group
# declares the entity it applies to, and that entity is described by one PCR
# section. Only DRIVER needs a translation — drivers are described by the PERSON
# section; ROADWAY / VEHICLE / NON_MOTORIST name their section directly. A study
# overrides the whole list with the `contributing_factor_summary_sections`
# parameter, so a later phase changes the summary as DATA, not code (§3.4).
_FACTOR_ENTITY_SECTION: dict[str, str] = {
    "DRIVER": "PERSON",
    "ROADWAY": "ROADWAY",
    "VEHICLE": "VEHICLE",
    "NON_MOTORIST": "NON_MOTORIST",
}
_SUMMARY_SECTIONS_PARAM = "contributing_factor_summary_sections"


def _summary_section_codes(db: Session, study_id: uuid.UUID | None) -> list[str]:
    """PCR section codes to summarise for a study's factor prompt.

    Study parameter first (a bare list, or a ``{"sections": [...]}`` wrapper to
    match how other parameters wrap their value); otherwise the sections implied
    by the active contributing-factor groups. Unknown or inactive section codes
    are dropped by the caller's join, so a stale parameter degrades to a smaller
    summary rather than an error.
    """
    if study_id is not None:
        param = db.scalar(
            select(StudyParameter).where(
                StudyParameter.study_id == study_id,
                StudyParameter.param_key == _SUMMARY_SECTIONS_PARAM,
            )
        )
        if param is not None:
            value = param.param_value
            if isinstance(value, dict):
                value = value.get("sections") or value.get("value")
            if isinstance(value, list):
                codes = [str(c) for c in value if isinstance(c, (str, int))]
                if codes:
                    return codes
    entities = db.scalars(select(RefContributingFactorGroup.applies_to).distinct())
    # dict.fromkeys keeps first-seen order and de-duplicates (DRIVER appears on
    # three of the seven groups).
    return list(dict.fromkeys(
        section for e in entities if (section := _FACTOR_ENTITY_SECTION.get(e)) is not None
    ))


class FactorSummaryValue(BaseModel):
    """One collected attribute shown in the prompt's summary."""

    attribute_id: uuid.UUID
    code: str
    name: str
    value_text: str | None
    value_json: Any | None
    sensitivity: str
    # Mirrors AttributeValueOut: the value is nulled and this set when the caller
    # fails can_view_sensitivity, so the summary can never widen PII/CIPSEA access.
    redacted: bool = False
    # Repeat unit the value belongs to (GAP-PCR-03); null for crash-level values.
    unit_type: str | None = None
    unit_number: int | None = None


class FactorSummarySection(BaseModel):
    code: str
    name: str
    # `collected` counts the attributes carrying a current value; `total` is the
    # active catalogue for the section, so the analyst can see how much of the
    # section is actually populated before ranking.
    collected: int
    total: int
    values: list[FactorSummaryValue]


class FactorSummaryOut(BaseModel):
    crash_id: uuid.UUID
    sections: list[FactorSummarySection]
    collected: int


@router.get("/crashes/{crash_id}/contributing-factor-summary", response_model=FactorSummaryOut)
def get_factor_summary(
    crash_id: uuid.UUID,
    db: Session = Depends(get_db),
    current: CurrentUser = Depends(require("crash:read", "data_mgmt:read_aggregated")),
):
    """Summarise the PCR sections that inform the top-three factor prompt (BRD DL4).

    The BRD asks for "a summary of data attributes selected in specific PCR
    sections" so the State CMV Data Analyst can rank the three primary
    contributing factors *from that summary*. Only attributes carrying a current
    value are listed — those are the ones actually "selected" — while `total`
    reports the section's catalogue size so a sparsely populated section is
    visible rather than silently short.

    Reuses the same permission pair and the same ``can_view_sensitivity``
    redaction as ``GET /crashes/{id}/attributes``, so this opens no new path to
    PII or CIPSEA values.
    """
    crash = load_crash(db, crash_id, current)
    codes = _summary_section_codes(db, crash.study_id)
    if not codes:
        return FactorSummaryOut(crash_id=crash_id, sections=[], collected=0)

    # Section metadata + catalogue size in one round-trip (LEFT JOIN so a section
    # with no active attributes still appears, with total 0).
    sections = db.execute(
        select(RefPcrSection.code, RefPcrSection.name, func.count(DataAttribute.id))
        .join(
            DataAttribute,
            and_(
                DataAttribute.pcr_section == RefPcrSection.code,
                DataAttribute.is_active.is_(True),
            ),
            isouter=True,
        )
        .where(RefPcrSection.code.in_(codes), RefPcrSection.is_active.is_(True))
        .group_by(RefPcrSection.code, RefPcrSection.name, RefPcrSection.sort_order)
        .order_by(RefPcrSection.sort_order)
    ).all()

    rows = db.execute(
        select(CrashAttributeValue, DataAttribute)
        .join(DataAttribute, DataAttribute.id == CrashAttributeValue.attribute_id)
        .where(
            CrashAttributeValue.crash_id == crash_id,
            CrashAttributeValue.is_current.is_(True),
            DataAttribute.pcr_section.in_(codes),
        )
        # Same ordering as the Attributes tab: crash-level rows first, then each
        # repeating unit in position order, then by attribute code.
        .order_by(
            CrashAttributeValue.unit_type.nulls_first(),
            CrashAttributeValue.unit_number.nulls_first(),
            DataAttribute.code,
        )
    ).all()

    by_section: dict[str, list[FactorSummaryValue]] = {}
    for cav, da in rows:
        allowed = current.can_view_sensitivity(da.sensitivity)
        by_section.setdefault(da.pcr_section, []).append(
            FactorSummaryValue(
                attribute_id=da.id, code=da.code, name=da.name,
                value_text=cav.value_text if allowed else None,
                value_json=cav.value_json if allowed else None,
                sensitivity=da.sensitivity, redacted=not allowed,
                unit_type=cav.unit_type, unit_number=cav.unit_number,
            )
        )

    out = [
        FactorSummarySection(
            code=code, name=name, total=total,
            collected=len(by_section.get(code, [])),
            values=by_section.get(code, []),
        )
        for code, name, total in sections
    ]
    return FactorSummaryOut(
        crash_id=crash_id, sections=out, collected=sum(s.collected for s in out)
    )


@router.get("/crashes/{crash_id}/contributing-factors", response_model=list[FactorOut])
def get_factors(crash_id: uuid.UUID, db: Session = Depends(get_db), current: CurrentUser = Depends(require("crash:read"))):
    load_crash(db, crash_id, current)
    return list(db.scalars(select(ContributingFactorSelection).where(ContributingFactorSelection.crash_id == crash_id).order_by(ContributingFactorSelection.rank)))


@router.put("/crashes/{crash_id}/contributing-factors", response_model=list[FactorOut])
def set_factors(crash_id: uuid.UUID, body: FactorsIn, db: Session = Depends(get_db), current: CurrentUser = Depends(require("contributing_factor:select"))):
    load_crash(db, crash_id, current)
    if len(body.factors) > 3:
        raise BadRequest("At most three primary contributing factors may be selected")
    ranks = [f.rank for f in body.factors]
    if len(set(ranks)) != len(ranks) or any(r < 1 or r > 3 for r in ranks):
        raise BadRequest("Ranks must be unique values between 1 and 3")
    db.query(ContributingFactorSelection).filter(ContributingFactorSelection.crash_id == crash_id).delete()
    out = []
    for f in body.factors:
        group_id = None
        if f.factor_group_code:
            group = db.scalar(select(RefContributingFactorGroup).where(RefContributingFactorGroup.code == f.factor_group_code))
            if group is None:
                raise BadRequest(f"Unknown factor group code: {f.factor_group_code}")
            group_id = group.id
            # DATA-7: when a group is chosen the value must come from that group's
            # catalog (structured selection per §5 Phase 6). Values with no group
            # remain free-text for back-compat / legacy resilience.
            known = db.scalar(
                select(RefContributingFactorValue.id).where(
                    RefContributingFactorValue.factor_group_id == group_id,
                    RefContributingFactorValue.label == f.factor_value,
                )
            )
            if known is None:
                raise BadRequest(
                    f"Unknown factor value '{f.factor_value}' for group {f.factor_group_code}"
                )
        sel = ContributingFactorSelection(crash_id=crash_id, factor_group_id=group_id, factor_value=f.factor_value, rank=f.rank, selected_by=current.id)
        db.add(sel)
        out.append(sel)
    db.flush()
    record_audit(db, actor=current, action="SELECT_FACTORS", entity_type="contributing_factor_selections", entity_id=crash_id, crash_id=crash_id, after={"count": len(out)})
    # Contributing factors selected -> advance into Analysis (CRAS-4; forward-only, idempotent).
    advance_phase(db, load_crash(db, crash_id, current), CrashLifecyclePhase.ANALYSIS, actor=current)
    db.commit()
    return out
