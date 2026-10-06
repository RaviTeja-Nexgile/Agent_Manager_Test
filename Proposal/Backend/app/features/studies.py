"""Studies & study configuration (documentation §12.2, §8.1)."""
from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import and_, func, literal, null, select
from sqlalchemy.orm import Session

from app.common import ORMModel
from app.core.audit import record_audit
from app.core.database import get_db
from app.core.errors import BadRequest, Conflict, Forbidden, NotFound
from app.core.notifications import create_notification, users_with_role
from app.core.permissions import require
from app.core.security import CurrentUser, get_current_user
from app.enums import (
    AttributeDataType,
    DataSensitivity,
    DeidentificationPolicy,
    PublicScope,
    StudyStatus,
)
from app.models import (
    AttributeRequirement,
    CompletenessRule,
    Crash,
    CrashAttributeValue,
    DataAttribute,
    RefAttributeValue,
    RefPcrSection,
    RefUsState,
    StateAttributeCoverage,
    StatePcrCoverage,
    Study,
    StudyParameter,
    StudyState,
)
from app.workers.tasks import (
    COMPLETENESS_TOKEN_NAMES,
    COMPLETENESS_TOKEN_PARAMS,
    completeness_token_catalog,
)

router = APIRouter(tags=["studies"])


# --------------------------------------------------------------------------- schemas
class StudyIn(BaseModel):
    code: str
    name: str
    phase_number: int
    vehicle_type: str
    crash_severity: str
    description: str | None = None
    start_date: dt.date | None = None
    end_date: dt.date | None = None
    pilot_start_date: dt.date | None = None
    status: StudyStatus = StudyStatus.PLANNING
    # Publication settings (STUD-5, §8.1 / §5 Phase 7). Defaulted so a new study
    # is created with the same policy the DB column defaults to.
    deidentification_policy: DeidentificationPolicy = DeidentificationPolicy.STANDARD
    public_scope: PublicScope = PublicScope.AGGREGATE_ONLY
    publication_enabled: bool = False
    publication_notes: str | None = None


class StudyUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    vehicle_type: str | None = None
    crash_severity: str | None = None
    start_date: dt.date | None = None
    end_date: dt.date | None = None
    pilot_start_date: dt.date | None = None
    status: StudyStatus | None = None
    # Per-study publication settings — editable via the existing PATCH (STUD-5).
    deidentification_policy: DeidentificationPolicy | None = None
    public_scope: PublicScope | None = None
    publication_enabled: bool | None = None
    publication_notes: str | None = None


class StudyOut(ORMModel):
    id: uuid.UUID
    code: str
    name: str
    phase_number: int
    vehicle_type: str
    crash_severity: str
    description: str | None
    start_date: dt.date | None
    end_date: dt.date | None
    pilot_start_date: dt.date | None
    status: str
    # Publication settings — NOT NULL DEFAULT columns, so never null (STUD-5).
    deidentification_policy: str
    public_scope: str
    publication_enabled: bool
    publication_notes: str | None


class AttributeRequirementOut(BaseModel):
    attribute_id: uuid.UUID
    code: str
    name: str
    category: str
    pcr_section: str | None
    data_type: str
    sensitivity: str
    is_required: bool
    is_optional: bool
    is_read_only: bool
    is_editable: bool


class RequirementUpdate(BaseModel):
    is_required: bool | None = None
    is_optional: bool | None = None
    is_read_only: bool | None = None
    is_editable: bool | None = None


class CompletenessRuleIn(BaseModel):
    name: str
    description: str | None = None
    definition: dict[str, Any] | None = None
    is_active: bool = True


class CompletenessRuleOut(ORMModel):
    id: uuid.UUID
    study_id: uuid.UUID
    name: str
    description: str | None
    definition: dict[str, Any] | None
    is_active: bool


class StudyStateIn(BaseModel):
    state_code: str
    is_participating: bool = False
    agreement_status: str = "PENDING"
    onboarded_at: dt.date | None = None
    notes: str | None = None


class StudyStateOut(ORMModel):
    id: uuid.UUID
    study_id: uuid.UUID
    state_code: str
    is_participating: bool
    agreement_status: str
    onboarded_at: dt.date | None
    notes: str | None


class ParameterIn(BaseModel):
    param_key: str
    param_value: Any
    description: str | None = None


class ParameterOut(ORMModel):
    id: uuid.UUID
    study_id: uuid.UUID
    param_key: str
    param_value: Any
    description: str | None


class DataAttributeIn(BaseModel):
    code: str
    name: str
    category: str
    pcr_section: str | None = None
    data_type: AttributeDataType = AttributeDataType.TEXT
    sensitivity: DataSensitivity = DataSensitivity.INTERNAL
    description: str | None = None


class DataAttributeOut(ORMModel):
    id: uuid.UUID
    code: str
    name: str
    category: str
    pcr_section: str | None
    data_type: str
    sensitivity: str
    description: str | None
    is_active: bool
    # Repeat / cardinality / supersession metadata (GAP-PCR-02, -03).
    repeats_on: str | None = None
    max_selections: int | None = None
    applies_to: str | None = None
    superseded_by_code: str | None = None


class AttributeValueOut(ORMModel):
    """One enumerated value for an attribute (GAP-PCR-09b).

    ``is_active=False`` means the value was retired by a later specification: it
    is no longer offered for new collection but still resolves, so a historical
    crash value written under the old form remains readable.
    """

    code: str | None
    label: str
    sort_order: int
    is_active: bool
    spec_version: str
    superseded_by: str | None = None
    notes: str | None = None


class DataDictionaryEntry(BaseModel):
    """One row of the CCFP PCR Data Dictionary (GAP-PCR-09, also GAP-SOO-10).

    The new HDTS PCR data form carries no element codes, so the traceability
    from "field on the published form" to the internal attribute code had no
    written record. This is that record, generated from the catalog rather than
    hand-maintained: form section and label as printed, the CCFP code, its MMUCC
    lineage, data type, cardinality, repeat unit, sensitivity, and value list.
    """

    code: str
    form_section: str | None
    form_label: str | None
    mmucc_code: str | None
    name: str
    pcr_section: str | None
    data_type: str
    sensitivity: str
    # Cardinality: NULL max_selections means single-valued.
    max_selections: int | None
    repeats_on: str | None
    applies_to: str | None
    is_required: bool
    is_active: bool
    superseded_by_code: str | None
    description: str | None
    values: list[AttributeValueOut]


class PcrSectionOut(ORMModel):
    """One PCR form section (GAP-PCR-01).

    ``name`` is the label as written on the HDTS PCR data form; ``code`` is the
    stable internal key that ``data_attributes.pcr_section`` and
    ``state_pcr_coverage`` join on. ``sort_order`` is the form's own order.
    """

    code: str
    name: str
    sort_order: int
    is_active: bool


class PcrCoverageOut(ORMModel):
    pcr_section_code: str
    state_code: str
    required_collected: int
    total_required: int
    optional_collected: int
    total_optional: int
    completion_pct: float | None
    # Which PCR specification these numbers belong to (GAP-PCR-05). Percentages
    # are NOT comparable across versions — the denominators changed — so the UI
    # surfaces it rather than letting a step change read as a real one.
    spec_version: str | None = None


class PcrCoverageIn(BaseModel):
    """Upsert payload for a single ``(state, pcr_section)`` reported-coverage row."""

    state_code: str
    pcr_section_code: str
    required_collected: int = 0
    total_required: int = 0
    optional_collected: int = 0
    total_optional: int = 0


class PcrCoverageUpdate(BaseModel):
    """Partial update of the reported counts for one coverage row."""

    required_collected: int | None = None
    total_required: int | None = None
    optional_collected: int | None = None
    total_optional: int | None = None


class AttributeCoverageOut(BaseModel):
    """Per-State, per-attribute collection status (PCR-3, §8.5).

    ``status`` collapses the (is_required/is_optional, is_collected) facts into
    the three documented colour buckets:
    ``REQUIRED_COLLECTED`` / ``REQUIRED_NOT_COLLECTED`` / ``OPTIONAL_NOT_COLLECTED``.
    """

    attribute_id: uuid.UUID
    code: str
    name: str
    pcr_section: str | None
    is_required: bool
    is_optional: bool
    is_collected: bool
    status: str


def _get_study(db: Session, study_id: uuid.UUID, current: CurrentUser) -> Study:
    """Resolve a study or 404 — and enforce the caller's study restriction
    (AUTH-2) so detail/sub-resource endpoints match the narrowed catalog that
    ``GET /studies`` returns for a study-restricted principal."""
    study = db.get(Study, study_id)
    if study is None:
        raise NotFound("Study")
    if not current.can_access_study(study.id):
        raise Forbidden("Study is outside your authorized study scope")
    return study


def _validate_completeness_definition(definition: dict[str, Any] | None) -> None:
    """Reject completeness rule definitions the evaluator cannot resolve.

    The data-driven evaluator (workers/tasks.py) resolves each token in
    ``definition.requires`` against the code-owned token registry. Validating at
    write time — against the SAME ``COMPLETENESS_TOKEN_NAMES`` vocabulary the
    evaluator uses — stops a typo'd token from silently making a crash
    permanently incomplete (STUD-4). Threshold params must be non-negative
    integers, matching the numeric thresholds the registry reads.
    """
    if not definition:
        return
    requires = definition.get("requires", [])
    if not isinstance(requires, list):
        raise BadRequest("'requires' must be a list of completeness tokens.")
    for token in requires:
        if token not in COMPLETENESS_TOKEN_NAMES:
            raise BadRequest(f"Unknown completeness token: {token}")
    params = definition.get("params") or definition.get("thresholds") or {}
    if not isinstance(params, dict):
        raise BadRequest("'params' must be an object of threshold values.")
    # Tokens that read a threshold from params, with the param names they accept.
    allowed_param_names = {
        name for token in requires for name in COMPLETENESS_TOKEN_PARAMS.get(token, {})
    }
    for key, value in params.items():
        if allowed_param_names and key not in allowed_param_names:
            raise BadRequest(f"Unknown completeness threshold parameter: {key}")
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise BadRequest(f"Threshold '{key}' must be a non-negative integer.")


# --------------------------------------------------------------------------- studies
@router.get("/studies", response_model=list[StudyOut])
def list_studies(
    status: StudyStatus | None = None,
    db: Session = Depends(get_db),
    current: CurrentUser = Depends(get_current_user),
):
    """Study catalog for any authenticated user (auth-only: crash-creating roles
    such as the MCSAP CMV Inspector do not hold ``study:read`` yet must resolve
    study names for the New-crash selector). A study-restricted principal
    (AUTH-2) sees only its assigned studies, mirroring ``scope_study_query``.
    Ordered by phase then code so the first ACTIVE row is the current phase —
    the default the study selector applies.
    """
    # Public-only principals work exclusively with published data products
    # (documentation §4) — the internal study catalog (publication settings,
    # unannounced PLANNING phases) is not part of them.
    if current.is_public_only:
        raise Forbidden("The study catalog is not available to public accounts")
    stmt = select(Study).order_by(Study.phase_number, Study.code)
    if current.study_restricted and current.study_ids:
        stmt = stmt.where(Study.id.in_(current.study_ids))
    if status is not None:
        stmt = stmt.where(Study.status == status.value)
    return list(db.scalars(stmt))


@router.post("/studies", response_model=StudyOut, status_code=201)
def create_study(body: StudyIn, db: Session = Depends(get_db), current: CurrentUser = Depends(require("study:create"))):
    if db.scalar(select(Study).where(Study.code == body.code)):
        raise Conflict("Study code already exists")
    data = body.model_dump()
    data["status"] = body.status.value
    data["deidentification_policy"] = body.deidentification_policy.value
    data["public_scope"] = body.public_scope.value
    study = Study(**data)
    db.add(study)
    db.flush()
    record_audit(db, actor=current, action="CREATE", entity_type="study", entity_id=study.id)
    db.commit()
    return study


@router.get("/studies/{study_id}", response_model=StudyOut)
def get_study(study_id: uuid.UUID, db: Session = Depends(get_db), current: CurrentUser = Depends(get_current_user)):
    return _get_study(db, study_id, current)


@router.patch("/studies/{study_id}", response_model=StudyOut)
def update_study(study_id: uuid.UUID, body: StudyUpdate, db: Session = Depends(get_db), current: CurrentUser = Depends(require("study:update", "study:configure"))):
    study = _get_study(db, study_id, current)
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(study, k, v.value if hasattr(v, "value") else v)
    record_audit(db, actor=current, action="UPDATE", entity_type="study", entity_id=study.id)
    db.commit()
    return study


# --------------------------------------------------------------------------- attribute requirements
@router.get("/studies/{study_id}/attributes", response_model=list[AttributeRequirementOut])
def list_study_attributes(study_id: uuid.UUID, db: Session = Depends(get_db), current: CurrentUser = Depends(get_current_user)):
    _get_study(db, study_id, current)
    rows = db.execute(
        select(AttributeRequirement, DataAttribute)
        .join(DataAttribute, DataAttribute.id == AttributeRequirement.attribute_id)
        .where(AttributeRequirement.study_id == study_id)
        .order_by(DataAttribute.code)
    ).all()
    return [
        AttributeRequirementOut(
            attribute_id=da.id, code=da.code, name=da.name, category=da.category,
            pcr_section=da.pcr_section, data_type=da.data_type, sensitivity=da.sensitivity,
            is_required=req.is_required, is_optional=req.is_optional,
            is_read_only=req.is_read_only, is_editable=req.is_editable,
        )
        for req, da in rows
    ]


@router.patch("/studies/{study_id}/attributes/{attribute_id}", response_model=AttributeRequirementOut)
def update_study_attribute(
    study_id: uuid.UUID, attribute_id: uuid.UUID, body: RequirementUpdate,
    db: Session = Depends(get_db), current: CurrentUser = Depends(require("study:configure", "admin:attributes")),
):
    _get_study(db, study_id, current)
    req = db.scalar(
        select(AttributeRequirement).where(
            AttributeRequirement.study_id == study_id, AttributeRequirement.attribute_id == attribute_id
        )
    )
    da = db.get(DataAttribute, attribute_id)
    if da is None:
        raise NotFound("Data attribute")
    if req is None:
        req = AttributeRequirement(study_id=study_id, attribute_id=attribute_id)
        db.add(req)
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(req, k, v)
    db.flush()
    record_audit(db, actor=current, action="UPDATE", entity_type="attribute_requirement", entity_id=req.id)
    db.commit()
    return AttributeRequirementOut(
        attribute_id=da.id, code=da.code, name=da.name, category=da.category,
        pcr_section=da.pcr_section, data_type=da.data_type, sensitivity=da.sensitivity,
        is_required=req.is_required, is_optional=req.is_optional,
        is_read_only=req.is_read_only, is_editable=req.is_editable,
    )


# --------------------------------------------------------------------------- completeness rules
@router.get("/completeness-rule-tokens")
def completeness_rule_tokens(current: CurrentUser = Depends(get_current_user)):
    """Token vocabulary + numeric thresholds for the completeness rule builder.

    Backend-driven so the UI picker and the data-driven evaluator share one
    source of truth (STUD-4). Any authenticated user may read it.
    """
    return {"tokens": completeness_token_catalog()}


@router.get("/studies/{study_id}/completeness-rules", response_model=list[CompletenessRuleOut])
def list_completeness_rules(study_id: uuid.UUID, db: Session = Depends(get_db), current: CurrentUser = Depends(get_current_user)):
    _get_study(db, study_id, current)
    return list(db.scalars(select(CompletenessRule).where(CompletenessRule.study_id == study_id).order_by(CompletenessRule.name)))


@router.post("/studies/{study_id}/completeness-rules", response_model=CompletenessRuleOut, status_code=201)
def create_completeness_rule(
    study_id: uuid.UUID, body: CompletenessRuleIn, db: Session = Depends(get_db),
    current: CurrentUser = Depends(require("admin:completeness", "study:configure")),
):
    _get_study(db, study_id, current)
    _validate_completeness_definition(body.definition)
    rule = CompletenessRule(study_id=study_id, **body.model_dump())
    db.add(rule)
    db.flush()
    record_audit(db, actor=current, action="CREATE", entity_type="completeness_rule", entity_id=rule.id)
    db.commit()
    return rule


@router.patch("/completeness-rules/{rule_id}", response_model=CompletenessRuleOut)
def update_completeness_rule(
    rule_id: uuid.UUID, body: CompletenessRuleIn, db: Session = Depends(get_db),
    current: CurrentUser = Depends(require("admin:completeness", "study:configure")),
):
    rule = db.get(CompletenessRule, rule_id)
    if rule is None:
        raise NotFound("Completeness rule")
    _validate_completeness_definition(body.definition)
    for k, v in body.model_dump().items():
        setattr(rule, k, v)
    record_audit(db, actor=current, action="UPDATE", entity_type="completeness_rule", entity_id=rule.id)
    db.commit()
    return rule


@router.delete("/completeness-rules/{rule_id}", status_code=204)
def delete_completeness_rule(rule_id: uuid.UUID, db: Session = Depends(get_db), current: CurrentUser = Depends(require("admin:completeness", "study:configure"))):
    rule = db.get(CompletenessRule, rule_id)
    if rule is None:
        raise NotFound("Completeness rule")
    db.delete(rule)
    record_audit(db, actor=current, action="DELETE", entity_type="completeness_rule", entity_id=rule_id)
    db.commit()
    return None


# --------------------------------------------------------------------------- study states
@router.get("/studies/{study_id}/states", response_model=list[StudyStateOut])
def list_study_states(study_id: uuid.UUID, db: Session = Depends(get_db), current: CurrentUser = Depends(get_current_user)):
    _get_study(db, study_id, current)
    return list(db.scalars(select(StudyState).where(StudyState.study_id == study_id).order_by(StudyState.state_code)))


@router.post("/studies/{study_id}/states", response_model=StudyStateOut, status_code=201)
def add_study_state(
    study_id: uuid.UUID, body: StudyStateIn, db: Session = Depends(get_db),
    current: CurrentUser = Depends(require("study:configure")),
):
    _get_study(db, study_id, current)
    if db.scalar(select(StudyState).where(StudyState.study_id == study_id, StudyState.state_code == body.state_code)):
        raise Conflict("State already configured for this study")
    ss = StudyState(study_id=study_id, **body.model_dump())
    db.add(ss)
    db.flush()
    record_audit(db, actor=current, action="CREATE", entity_type="study_state", entity_id=ss.id)
    db.commit()
    return ss


@router.patch("/studies/{study_id}/states/{state_code}", response_model=StudyStateOut)
def update_study_state(
    study_id: uuid.UUID, state_code: str, body: StudyStateIn, db: Session = Depends(get_db),
    current: CurrentUser = Depends(require("study:configure")),
):
    _get_study(db, study_id, current)
    ss = db.scalar(select(StudyState).where(StudyState.study_id == study_id, StudyState.state_code == state_code))
    if ss is None:
        raise NotFound("Study state")
    for k, v in body.model_dump().items():
        setattr(ss, k, v)
    record_audit(db, actor=current, action="UPDATE", entity_type="study_state", entity_id=ss.id)
    db.commit()
    return ss


# --------------------------------------------------------------------------- parameters
@router.get("/studies/{study_id}/parameters", response_model=list[ParameterOut])
def list_parameters(study_id: uuid.UUID, db: Session = Depends(get_db), current: CurrentUser = Depends(get_current_user)):
    _get_study(db, study_id, current)
    return list(db.scalars(select(StudyParameter).where(StudyParameter.study_id == study_id).order_by(StudyParameter.param_key)))


@router.post("/studies/{study_id}/parameters", response_model=ParameterOut, status_code=201)
def upsert_parameter(
    study_id: uuid.UUID, body: ParameterIn, db: Session = Depends(get_db),
    current: CurrentUser = Depends(require("study:configure")),
):
    _get_study(db, study_id, current)
    param = db.scalar(select(StudyParameter).where(StudyParameter.study_id == study_id, StudyParameter.param_key == body.param_key))
    if param is None:
        param = StudyParameter(study_id=study_id, param_key=body.param_key)
        db.add(param)
    param.param_value = body.param_value
    param.description = body.description
    db.flush()
    record_audit(db, actor=current, action="UPSERT", entity_type="study_parameter", entity_id=param.id)
    db.commit()
    return param


@router.delete("/studies/{study_id}/parameters/{param_key}", status_code=204)
def delete_parameter(study_id: uuid.UUID, param_key: str, db: Session = Depends(get_db), current: CurrentUser = Depends(require("study:configure"))):
    _get_study(db, study_id, current)
    param = db.scalar(select(StudyParameter).where(StudyParameter.study_id == study_id, StudyParameter.param_key == param_key))
    if param is None:
        raise NotFound("Parameter")
    db.delete(param)
    record_audit(db, actor=current, action="DELETE", entity_type="study_parameter", entity_id=param.id)
    db.commit()
    return None


# --------------------------------------------------------------------------- PCR coverage (documentation §8.5 / §19.3)
@router.get("/studies/{study_id}/pcr-coverage", response_model=list[PcrCoverageOut])
def pcr_coverage(
    study_id: uuid.UUID, state: str | None = None, db: Session = Depends(get_db),
    current: CurrentUser = Depends(get_current_user),
):
    """Per-State PCR coverage (§8.5 / §19.3) **derived from collected data**.

    Section totals are computed from the study-scoped ``attribute_requirements``
    (grouped by ``pcr_section``); the per-State collected counts come from the
    live per-attribute collection facts (``crash_attribute_values`` joined to
    crashes in that State within the study). The seeded ``state_pcr_coverage``
    rows are kept only as the catalog of (State, section) pairs to report on —
    their stored counts are no longer trusted. ``completion_pct`` is recomputed
    from the derived required counts, mirroring the generated-column formula.
    """
    _get_study(db, study_id, current)

    # Denominators: count of attributes per section that the study marks
    # required / optional. (Grouped by pcr_section, joined to study-scoped
    # attribute_requirements.)
    totals = (
        select(
            DataAttribute.pcr_section.label("section"),
            func.count().filter(AttributeRequirement.is_required.is_(True)).label("total_required"),
            func.count().filter(AttributeRequirement.is_optional.is_(True)).label("total_optional"),
        )
        .join(
            AttributeRequirement,
            and_(
                AttributeRequirement.attribute_id == DataAttribute.id,
                AttributeRequirement.study_id == study_id,
            ),
        )
        .where(DataAttribute.pcr_section.is_not(None))
        .group_by(DataAttribute.pcr_section)
        .subquery()
    )

    # Numerators: distinct attributes per (State, section) that actually have a
    # current collected value on a crash in that State within the study.
    collected = (
        select(
            Crash.state_code.label("state_code"),
            DataAttribute.pcr_section.label("section"),
            func.count(func.distinct(DataAttribute.id))
            .filter(AttributeRequirement.is_required.is_(True))
            .label("required_collected"),
            func.count(func.distinct(DataAttribute.id))
            .filter(AttributeRequirement.is_optional.is_(True))
            .label("optional_collected"),
        )
        .select_from(CrashAttributeValue)
        .join(Crash, and_(Crash.id == CrashAttributeValue.crash_id, Crash.study_id == study_id))
        .join(DataAttribute, DataAttribute.id == CrashAttributeValue.attribute_id)
        .join(
            AttributeRequirement,
            and_(
                AttributeRequirement.attribute_id == DataAttribute.id,
                AttributeRequirement.study_id == study_id,
            ),
        )
        .where(CrashAttributeValue.is_current.is_(True), DataAttribute.pcr_section.is_not(None))
        .group_by(Crash.state_code, DataAttribute.pcr_section)
        .subquery()
    )

    req_collected = func.coalesce(collected.c.required_collected, 0)
    tot_required = func.coalesce(totals.c.total_required, 0)
    # Optional tier zeroed (GAP-PCR-05). The old KS worksheet defined 50 optional
    # attribute-values; the new HDTS PCR data form has NO optional tier —
    # everything on it is CCFP-required. `attribute_requirements.is_optional`
    # still exists and still means "an administrator may collect this", but it is
    # no longer a *specification* tier, so reporting a count against it would
    # present an internal configuration flag as a readiness measure. The columns
    # stay (a future phase may reintroduce the tier) but report zero until a
    # source defines one.
    opt_collected = literal(0)
    tot_optional = literal(0)
    # Mirror the StatePcrCoverage.completion_pct generated column:
    #   round(required_collected * 100 / total_required, 2), 0 when no required.
    completion = func.round(req_collected * 100.0 / func.nullif(tot_required, 0), 2)

    # Drive the reported (State, section) pairs from the existing coverage rows
    # (keeps the seed as a catalog) but attach the *derived* counts to each.
    stmt = (
        select(
            StatePcrCoverage.state_code.label("state_code"),
            StatePcrCoverage.pcr_section_code.label("pcr_section_code"),
            req_collected.label("required_collected"),
            tot_required.label("total_required"),
            opt_collected.label("optional_collected"),
            tot_optional.label("total_optional"),
            completion.label("completion_pct"),
            StatePcrCoverage.spec_version.label("spec_version"),
        )
        .outerjoin(totals, totals.c.section == StatePcrCoverage.pcr_section_code)
        .outerjoin(
            collected,
            and_(
                collected.c.section == StatePcrCoverage.pcr_section_code,
                collected.c.state_code == StatePcrCoverage.state_code,
            ),
        )
        .where(StatePcrCoverage.study_id == study_id)
    )
    if state:
        stmt = stmt.where(StatePcrCoverage.state_code == state)
    elif current.allowed_states is not None:
        stmt = stmt.where(StatePcrCoverage.state_code.in_(current.allowed_states))

    rows = db.execute(
        stmt.order_by(StatePcrCoverage.state_code, StatePcrCoverage.pcr_section_code)
    ).all()
    return [
        PcrCoverageOut(
            pcr_section_code=r.pcr_section_code,
            state_code=r.state_code,
            required_collected=r.required_collected,
            total_required=r.total_required,
            optional_collected=r.optional_collected,
            total_optional=r.total_optional,
            # NULL, not 0.0, when the section has no required attributes
            # (GAP-PCR-05). Under the new form several sections carry no
            # required attribute yet, and coercing that to 0% renders a section
            # nobody has to collect as "0% complete" — indistinguishable from a
            # State that collected nothing. Null means "not applicable" and the
            # UI shows a dash instead of a red bar.
            completion_pct=float(r.completion_pct) if r.completion_pct is not None else None,
            spec_version=r.spec_version,
        )
        for r in rows
    ]


@router.get("/studies/{study_id}/attribute-coverage", response_model=list[AttributeCoverageOut])
def attribute_coverage(
    study_id: uuid.UUID, state: str | None = None, db: Session = Depends(get_db),
    current: CurrentUser = Depends(get_current_user),
):
    """Per-State, per-attribute collection status (§8.5, PCR-3).

    Returns the three-way colour status the documented per-State PCR form needs:
    each study-required/optional attribute is bucketed into
    ``REQUIRED_COLLECTED`` / ``REQUIRED_NOT_COLLECTED`` / ``OPTIONAL_NOT_COLLECTED``
    using the new per-State ``state_attribute_coverage`` collected flag.

    Selects ``DataAttribute`` joined to the study-scoped ``AttributeRequirement``,
    left-joined to ``StateAttributeCoverage`` for the requested State (a missing
    row means not-collected). The same State-scope filter and ``_get_study`` guard
    as ``pcr_coverage`` apply: a State-scoped caller only ever sees their States.
    """
    _get_study(db, study_id, current)

    state_code = state.upper() if state else None
    if state_code is not None:
        # Honour an explicit ?state= but never let it escape the caller's scope.
        if current.allowed_states is not None and state_code not in current.allowed_states:
            return []
    elif current.allowed_states is not None:
        # No explicit State: default to the caller's first allowed State so a
        # State-scoped user gets a meaningful per-attribute view, never another
        # State's facts.
        if not current.allowed_states:
            return []
        # allowed_states is a set; pick a deterministic State for the view.
        state_code = sorted(current.allowed_states)[0]

    if state_code is not None:
        # One concrete State: left-join its collection facts (a missing row ⇒
        # not-collected). The State predicate lives inside the join ON clause so
        # attributes with no coverage row still appear, with is_collected NULL.
        collected_col = StateAttributeCoverage.is_collected
        stmt = (
            select(DataAttribute, AttributeRequirement, collected_col)
            .join(
                AttributeRequirement,
                and_(
                    AttributeRequirement.attribute_id == DataAttribute.id,
                    AttributeRequirement.study_id == study_id,
                ),
            )
            .outerjoin(
                StateAttributeCoverage,
                and_(
                    StateAttributeCoverage.attribute_id == DataAttribute.id,
                    StateAttributeCoverage.study_id == study_id,
                    StateAttributeCoverage.state_code == state_code,
                ),
            )
        )
    else:
        # Unrestricted caller with no ?state=: no single State is in view, so we
        # report the catalog with everything not-collected (one row per
        # attribute) rather than multiplying rows across every State's facts.
        stmt = select(
            DataAttribute, AttributeRequirement, null().label("is_collected")
        ).join(
            AttributeRequirement,
            and_(
                AttributeRequirement.attribute_id == DataAttribute.id,
                AttributeRequirement.study_id == study_id,
            ),
        )

    stmt = stmt.where(
        (AttributeRequirement.is_required.is_(True))
        | (AttributeRequirement.is_optional.is_(True))
    ).order_by(DataAttribute.pcr_section, DataAttribute.code)

    rows = db.execute(stmt).all()

    out: list[AttributeCoverageOut] = []
    for da, req, is_collected_raw in rows:
        is_collected = bool(is_collected_raw)
        is_required = bool(req.is_required)
        is_optional = bool(req.is_optional)
        if is_required:
            status = "REQUIRED_COLLECTED" if is_collected else "REQUIRED_NOT_COLLECTED"
        else:
            # Optional attributes only ever surface a not-collected amber state;
            # an optional-collected attribute is not part of the documented
            # three-way colour status (§8.5), so it carries no separate bucket.
            status = "OPTIONAL_NOT_COLLECTED"
        out.append(
            AttributeCoverageOut(
                attribute_id=da.id,
                code=da.code,
                name=da.name,
                pcr_section=da.pcr_section,
                is_required=is_required,
                is_optional=is_optional,
                is_collected=is_collected,
                status=status,
            )
        )
    return out


def _coverage_out(row: StatePcrCoverage) -> PcrCoverageOut:
    return PcrCoverageOut(
        pcr_section_code=row.pcr_section_code,
        state_code=row.state_code,
        required_collected=row.required_collected,
        total_required=row.total_required,
        optional_collected=row.optional_collected,
        total_optional=row.total_optional,
        completion_pct=float(row.completion_pct) if row.completion_pct is not None else 0.0,
    )


def _enforce_state_scope(current: CurrentUser, state_code: str) -> None:
    """Reject writes to a State the caller is not scoped to (mirrors the read filter)."""
    if current.allowed_states is not None and state_code not in current.allowed_states:
        raise Forbidden(f"Not authorized to record coverage for State {state_code}")


def _notify_reconcile(db: Session, *, current: CurrentUser, study: Study, row: StatePcrCoverage) -> None:
    """Tell the CCFP project team a State-reported coverage update was reconciled (§8.5)."""
    for member in users_with_role(db, "CCFP_PROJECT_TEAM"):
        create_notification(
            db,
            recipient_user_id=member.id,
            notification_type="PCR_COVERAGE_RECONCILED",
            title="State PCR coverage reconciled",
            message=(
                f"{row.state_code} / {row.pcr_section_code} coverage updated for "
                f"{study.code}: required collected {row.required_collected}/{row.total_required}."
            ),
            channel="IN_APP",
        )


@router.post("/studies/{study_id}/pcr-coverage", response_model=PcrCoverageOut, status_code=201)
def upsert_pcr_coverage(
    study_id: uuid.UUID, body: PcrCoverageIn, db: Session = Depends(get_db),
    current: CurrentUser = Depends(require("study:configure")),
):
    """Record what a State reports it collects for one ``(state, section)`` pair (§8.5).

    Upserts the reported counts onto the ``state_pcr_coverage`` catalog row; the
    GET endpoint still *derives* live counts from collected data (PCR-6). The
    generated ``completion_pct`` column recomputes on commit, so we re-fetch the
    row before responding.
    """
    study = _get_study(db, study_id, current)
    state_code = body.state_code.upper()
    section = body.pcr_section_code
    _enforce_state_scope(current, state_code)
    if db.get(RefUsState, state_code) is None:
        raise NotFound("State")
    if db.get(RefPcrSection, section) is None:
        raise NotFound("PCR section")

    row = db.scalar(
        select(StatePcrCoverage).where(
            StatePcrCoverage.study_id == study_id,
            StatePcrCoverage.state_code == state_code,
            StatePcrCoverage.pcr_section_code == section,
        )
    )
    if row is None:
        row = StatePcrCoverage(study_id=study_id, state_code=state_code, pcr_section_code=section)
        db.add(row)
    row.required_collected = body.required_collected
    row.total_required = body.total_required
    row.optional_collected = body.optional_collected
    row.total_optional = body.total_optional
    row.updated_at = dt.datetime.now(dt.timezone.utc)
    db.flush()
    record_audit(db, actor=current, action="UPSERT", entity_type="state_pcr_coverage", entity_id=row.id)
    _notify_reconcile(db, current=current, study=study, row=row)
    db.commit()
    db.refresh(row)  # carry the recomputed generated completion_pct
    return _coverage_out(row)


@router.patch("/studies/{study_id}/pcr-coverage/{state}/{section}", response_model=PcrCoverageOut)
def update_pcr_coverage(
    study_id: uuid.UUID, state: str, section: str, body: PcrCoverageUpdate,
    db: Session = Depends(get_db), current: CurrentUser = Depends(require("study:configure")),
):
    """Reconcile reported counts for an existing ``(state, section)`` coverage row (§8.5)."""
    study = _get_study(db, study_id, current)
    state_code = state.upper()
    _enforce_state_scope(current, state_code)
    row = db.scalar(
        select(StatePcrCoverage).where(
            StatePcrCoverage.study_id == study_id,
            StatePcrCoverage.state_code == state_code,
            StatePcrCoverage.pcr_section_code == section,
        )
    )
    if row is None:
        raise NotFound("PCR coverage row")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(row, k, v)
    row.updated_at = dt.datetime.now(dt.timezone.utc)
    db.flush()
    record_audit(db, actor=current, action="UPDATE", entity_type="state_pcr_coverage", entity_id=row.id)
    _notify_reconcile(db, current=current, study=study, row=row)
    db.commit()
    db.refresh(row)  # carry the recomputed generated completion_pct
    return _coverage_out(row)


# --------------------------------------------------------------------------- PCR section catalog
@router.get("/pcr-sections", response_model=list[PcrSectionOut])
def list_pcr_sections(
    include_inactive: bool = False,
    db: Session = Depends(get_db), current: CurrentUser = Depends(get_current_user),
):
    """The PCR section catalog in form order (GAP-PCR-01).

    Exists so clients render the *specification's* section names ("Large Vehicle
    and Hazardous Material (HM) Data Elements") instead of humanizing the
    internal code ("Large Veh Hazmat"). Codes stay the stable join key.

    Retired sections (``is_active=false`` — DYNAMIC, removed by the new HDTS PCR
    data form) are excluded by default so they are not offered for new
    collection, but remain fetchable with ``?include_inactive=true`` for reading
    crashes recorded under the old specification.
    """
    stmt = select(RefPcrSection).order_by(RefPcrSection.sort_order, RefPcrSection.code)
    if not include_inactive:
        stmt = stmt.where(RefPcrSection.is_active.is_(True))
    return list(db.scalars(stmt))


# --------------------------------------------------------------------------- data dictionary
@router.get("/data-dictionary", response_model=list[DataDictionaryEntry])
def data_dictionary(
    study_id: uuid.UUID | None = None,
    include_inactive: bool = False,
    db: Session = Depends(get_db), current: CurrentUser = Depends(get_current_user),
):
    """The CCFP PCR Data Dictionary (GAP-PCR-09; also the SOO's data-dictionary deliverable).

    Generated from the catalog, not hand-maintained, so it cannot drift from
    what the application actually collects. One row per attribute: the form
    section and label as printed on the HDTS PCR data form, the internal CCFP
    code, its MMUCC lineage, data type, selection cap, repeat unit, conditional
    population, sensitivity, and the enumerated value list where one is defined.

    ``study_id`` marks which attributes that study requires; without it
    ``is_required`` is reported False for every row (the requirement is a
    per-study setting, not a property of the attribute).

    Retired attributes are excluded by default. Retired VALUES are always
    included and flagged, because the dictionary's job is to let a reader
    resolve historical data as well as current data.
    """
    stmt = select(DataAttribute).order_by(DataAttribute.pcr_section, DataAttribute.code)
    if not include_inactive:
        stmt = stmt.where(DataAttribute.is_active.is_(True))
    attributes = list(db.scalars(stmt))

    required_ids: set[uuid.UUID] = set()
    if study_id is not None:
        _get_study(db, study_id, current)
        required_ids = set(
            db.scalars(
                select(AttributeRequirement.attribute_id).where(
                    AttributeRequirement.study_id == study_id,
                    AttributeRequirement.is_required.is_(True),
                )
            )
        )

    # One query for every value, grouped in Python: the alternative is a query
    # per attribute, which is ~175 round trips against a remote database.
    values = list(
        db.scalars(
            select(RefAttributeValue).order_by(
                RefAttributeValue.attribute_id, RefAttributeValue.sort_order
            )
        )
    )
    label_by_id = {v.id: v.label for v in values}
    by_attribute: dict[uuid.UUID, list[RefAttributeValue]] = {}
    for v in values:
        by_attribute.setdefault(v.attribute_id, []).append(v)

    return [
        DataDictionaryEntry(
            code=da.code,
            # form_label is returned AS RECORDED — null when no printed label has
            # been captured — and deliberately NOT defaulted to the attribute's
            # own name. Falling back looked tidier but made the dictionary lie:
            # every row rendered as though it were traceable to the published
            # form, so a reader could not tell the 37 genuine labels from the
            # 138 internal names standing in for them. For a traceability
            # artefact a visible gap is worth far more than a plausible
            # fabrication, so the gap is surfaced instead (GAP-PCR-09).
            form_section=da.form_section,
            form_label=da.form_label,
            mmucc_code=da.mmucc_code,
            name=da.name,
            pcr_section=da.pcr_section,
            data_type=da.data_type,
            sensitivity=da.sensitivity,
            max_selections=da.max_selections,
            repeats_on=da.repeats_on,
            applies_to=da.applies_to,
            is_required=da.id in required_ids,
            is_active=da.is_active,
            superseded_by_code=da.superseded_by_code,
            description=da.description,
            values=[
                AttributeValueOut(
                    code=v.code, label=v.label, sort_order=v.sort_order,
                    is_active=v.is_active, spec_version=v.spec_version,
                    superseded_by=label_by_id.get(v.superseded_by_id) if v.superseded_by_id else None,
                    notes=v.notes,
                )
                for v in by_attribute.get(da.id, [])
            ],
        )
        for da in attributes
    ]


# --------------------------------------------------------------------------- data attribute catalog
@router.get("/data-attributes", response_model=list[DataAttributeOut])
def list_data_attributes(
    pcr_section: str | None = None, category: str | None = None,
    include_inactive: bool = False,
    db: Session = Depends(get_db), current: CurrentUser = Depends(get_current_user),
):
    """List the canonical attribute catalog.

    ``include_inactive`` surfaces attributes retired by a later specification
    (GAP-PCR-01 deactivated DV01 with its Dynamic Data Elements section). They
    are hidden by default so the catalog reflects what the current form
    collects, without deleting rows that historical values still reference.
    """
    stmt = select(DataAttribute).order_by(DataAttribute.code)
    if pcr_section:
        stmt = stmt.where(DataAttribute.pcr_section == pcr_section)
    if category:
        stmt = stmt.where(DataAttribute.category == category)
    if not include_inactive:
        stmt = stmt.where(DataAttribute.is_active.is_(True))
    return list(db.scalars(stmt))


@router.post("/data-attributes", response_model=DataAttributeOut, status_code=201)
def create_data_attribute(body: DataAttributeIn, db: Session = Depends(get_db), current: CurrentUser = Depends(require("admin:attributes"))):
    if db.scalar(select(DataAttribute).where(DataAttribute.code == body.code)):
        raise Conflict("Attribute code already exists")
    data = body.model_dump()
    data["data_type"] = body.data_type.value
    data["sensitivity"] = body.sensitivity.value
    da = DataAttribute(**data)
    db.add(da)
    db.flush()
    record_audit(db, actor=current, action="CREATE", entity_type="data_attribute", entity_id=da.id)
    db.commit()
    return da


@router.get("/data-attributes/{attribute_id}", response_model=DataAttributeOut)
def get_data_attribute(attribute_id: uuid.UUID, db: Session = Depends(get_db), current: CurrentUser = Depends(get_current_user)):
    da = db.get(DataAttribute, attribute_id)
    if da is None:
        raise NotFound("Data attribute")
    return da


@router.patch("/data-attributes/{attribute_id}", response_model=DataAttributeOut)
def update_data_attribute(attribute_id: uuid.UUID, body: DataAttributeIn, db: Session = Depends(get_db), current: CurrentUser = Depends(require("admin:attributes"))):
    da = db.get(DataAttribute, attribute_id)
    if da is None:
        raise NotFound("Data attribute")
    data = body.model_dump()
    data["data_type"] = body.data_type.value
    data["sensitivity"] = body.sensitivity.value
    for k, v in data.items():
        setattr(da, k, v)
    record_audit(db, actor=current, action="UPDATE", entity_type="data_attribute", entity_id=da.id)
    db.commit()
    return da
