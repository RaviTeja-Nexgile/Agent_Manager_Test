"""Statistical analysis in the CCFP Analysis Environment.

Serves the January 2026 BRD's "Analyze CCFP Data" requirements (p. 16) —
descriptive and inferential statistics, distributions, thematic analysis and
risk modelling — over the crash-level cohorts materialized by
``workers/cohorts.py``, plus the saved investigations and statistical-tool
exports the same chapter asks for.

Three things are worth knowing before reading the routes.

**Nothing here reads an operational table.** Every statistic is computed over
``analysis_cohort_members``, a snapshot written by a refresh. A result therefore
always names the cohort version it describes, and re-running an analysis after a
refresh produces a *new* answer with a *new* version stamp rather than silently
changing the old one.

**A risk model cannot be computed without a control cohort.** The BRD makes that
capability conditional — "given the availability of control such as non-fatal
crashes" — and :func:`run_risk_model` enforces the conditional rather than
quietly comparing a population against itself. When no CONTROL cohort exists the
API says so, in those terms.

**The permission split is the BRD's, not a convenience.** ``analysis_stats:run``
executes a method; ``analysis_stats:manage`` defines the cohorts and saves the
investigations. Defining a cohort silently changes every result later computed
from it, which is a larger power than running one analysis, so they are separate
grants. Neither is held by State, Federal or public users — the "Analyze CCFP
Data" access table lists only the CCFP Project Team, and those users receive
analysis *outputs* through the Analysis Environment dataset shares.
"""
from __future__ import annotations

import csv
import datetime as dt
import io
import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.common import ORMModel
from app.core.audit import record_audit
from app.core.database import get_db
from app.core.errors import BadRequest, NotFound
from app.core.permissions import require
from app.core.security import CurrentUser
from app.enums import (
    AnalysisMethod,
    CohortRole,
    CohortStatus,
    InvestigationStatus,
    InvestigationVisibility,
    StatisticalExportFormat,
)
from app.models import (
    AnalysisCohort,
    AnalysisCohortMember,
    AnalysisCohortVersion,
    AnalysisEnvironment,
    AnalysisInvestigation,
)
from app.workers import cohorts as cohort_worker
from app.workers import statistics as stats_worker

router = APIRouter(tags=["analysis-statistics"])

MAX_MEMBER_LIMIT = 1000
DEFAULT_MEMBER_LIMIT = 100

# Columns exported for external statistical tools, in a fixed order so a saved
# R or SAS script keeps working across refreshes.
EXPORT_COLUMNS = [
    "ccfp_identifier",
    "state_code",
    "county",
    "crash_date",
    "crash_year",
    "crash_month",
    "lifecycle_phase",
    "num_fatalities",
    "num_vehicles",
    "num_persons",
    "is_fatal",
    "scope",
    "is_qualifying",
    "factors",
]


# ===========================================================================
# Schemas
# ===========================================================================
class CohortOut(ORMModel):
    id: uuid.UUID
    environment_id: uuid.UUID
    code: str
    name: str
    description: str | None = None
    cohort_role: str
    definition: dict[str, Any] = {}
    status: str
    current_version_id: uuid.UUID | None = None
    created_at: dt.datetime
    updated_at: dt.datetime
    # Derived, so the UI never has to make a second call to answer "how many
    # crashes, as of when?" — the two questions a cohort card exists to answer.
    version_no: int | None = None
    member_count: int | None = None
    materialized_at: dt.datetime | None = None


class CohortIn(BaseModel):
    environment_id: uuid.UUID
    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    cohort_role: CohortRole = CohortRole.GENERAL
    definition: dict[str, Any] = {}


class CohortUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    cohort_role: CohortRole | None = None
    definition: dict[str, Any] | None = None
    status: CohortStatus | None = None


class MembersOut(BaseModel):
    cohort_id: uuid.UUID
    version_no: int | None = None
    materialized_at: dt.datetime | None = None
    member_count: int
    returned: int
    members: list[dict[str, Any]]


class InvestigationOut(ORMModel):
    id: uuid.UUID
    environment_id: uuid.UUID
    code: str
    name: str
    description: str | None = None
    method: str
    parameters: dict[str, Any] = {}
    visibility: str
    status: str
    last_run_at: dt.datetime | None = None
    created_by: uuid.UUID | None = None
    created_at: dt.datetime
    updated_at: dt.datetime


class InvestigationIn(BaseModel):
    environment_id: uuid.UUID
    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    method: AnalysisMethod
    parameters: dict[str, Any] = {}
    visibility: InvestigationVisibility = InvestigationVisibility.TEAM


class InvestigationUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    parameters: dict[str, Any] | None = None
    visibility: InvestigationVisibility | None = None
    status: InvestigationStatus | None = None


class RiskModelIn(BaseModel):
    case_cohort_id: uuid.UUID
    control_cohort_id: uuid.UUID
    exposure_factor: str = Field(min_length=1)
    confidence: float = 0.95


class CompareIn(BaseModel):
    cohort_a_id: uuid.UUID
    cohort_b_id: uuid.UUID
    # Exactly one of these: a numeric variable compares means (Welch), a factor
    # compares prevalence (two-proportion z). Modelled as two optional fields
    # rather than a discriminated union because the UI presents them as one
    # "what are you comparing?" control.
    variable: str | None = None
    factor: str | None = None
    confidence: float = 0.95


# ===========================================================================
# Helpers
# ===========================================================================
def _allowed_states(current: CurrentUser) -> list[str] | None:
    """State scope for the current principal, or None when unrestricted.

    ``analysis_stats:run`` is granted only to unscoped CCFP roles today, so this
    returns None in practice. It is threaded through every statistical call
    anyway — a scoping rule that holds only because nobody currently has the
    permission is not a scoping rule, and the grant is a table row a later
    migration can change.
    """
    return list(current.allowed_states) if current.allowed_states is not None else None


def _load_cohort(db: Session, cohort_id: uuid.UUID) -> AnalysisCohort:
    cohort = db.get(AnalysisCohort, cohort_id)
    if cohort is None:
        raise NotFound("Analysis cohort")
    return cohort


def _version_of(db: Session, cohort: AnalysisCohort) -> AnalysisCohortVersion:
    """The cohort's current materialized version, or a 400 explaining why not.

    A statistic over a cohort that has never been materialized is not an empty
    result — it is an unanswerable question, and saying so is more useful than
    returning n=0, which reads as "there are no such crashes".
    """
    if cohort.current_version_id is None:
        raise BadRequest(
            f"Cohort '{cohort.code}' has not been materialized yet. Refresh the "
            "Analysis Environment (or the cohort) before running analyses on it."
        )
    version = db.get(AnalysisCohortVersion, cohort.current_version_id)
    if version is None:
        raise BadRequest(
            f"Cohort '{cohort.code}' points at a version that no longer exists; "
            "refresh it to rebuild."
        )
    return version


def _cohort_out(db: Session, cohort: AnalysisCohort) -> CohortOut:
    out = CohortOut.model_validate(cohort)
    if cohort.current_version_id:
        version = db.get(AnalysisCohortVersion, cohort.current_version_id)
        if version is not None:
            out.version_no = version.version_no
            out.member_count = version.member_count
            out.materialized_at = version.materialized_at
    return out


# Two cohorts materialized in the same refresh run land within seconds of each
# other. An hour is comfortably outside that, so a larger gap means the two
# populations really were captured at different times.
_SKEW_TOLERANCE = dt.timedelta(hours=1)


def _time_skew_caveat(
    result: dict,
    left: tuple[AnalysisCohort, AnalysisCohortVersion],
    right: tuple[AnalysisCohort, AnalysisCohortVersion],
) -> None:
    """Warn when two compared cohorts describe different points in time.

    Every method that takes two cohorts is silently vulnerable to this: refresh
    one and not the other — or archive one, which stops it refreshing entirely —
    and the comparison is between populations captured days apart. The numbers
    stay internally consistent and the result looks completely normal, which is
    exactly why it needs saying. Nothing else in the payload would reveal it,
    because each cohort's own version stamp is individually correct.
    """
    (cohort_a, version_a), (cohort_b, version_b) = left, right
    at_a, at_b = version_a.materialized_at, version_b.materialized_at
    if at_a is None or at_b is None:
        return
    skew = abs(at_a - at_b)
    if skew <= _SKEW_TOLERANCE:
        return
    hours = skew.total_seconds() / 3600
    older, newer = (
        ((cohort_a, at_a), (cohort_b, at_b))
        if at_a < at_b
        else ((cohort_b, at_b), (cohort_a, at_a))
    )
    stale = [c for c in (cohort_a, cohort_b) if c.status != CohortStatus.ACTIVE.value]
    result.setdefault("caveats", []).insert(
        0,
        f"The two cohorts were materialized {hours:.1f} hours apart — "
        f"{older[0].code} at {older[1]:%Y-%m-%d %H:%M} and {newer[0].code} at "
        f"{newer[1]:%Y-%m-%d %H:%M} — so this compares populations captured at "
        "different points in time. Refresh both before relying on the result."
        + (
            f" {', '.join(c.code for c in stale)} is archived and no longer refreshes."
            if stale
            else ""
        ),
    )


def _stamp(version: AnalysisCohortVersion, cohort: AnalysisCohort, result: dict) -> dict:
    """Attach the provenance every statistical result must carry.

    Without this a number is unreproducible: the same request against the same
    cohort returns different answers after a refresh, and nothing in the payload
    would say which snapshot produced which.
    """
    result["cohort_id"] = str(cohort.id)
    result["cohort_code"] = cohort.code
    result["cohort_name"] = cohort.name
    result["cohort_role"] = cohort.cohort_role
    result["version_no"] = version.version_no
    result["materialized_at"] = version.materialized_at
    result["member_count"] = version.member_count
    return result


# ===========================================================================
# Vocabulary
# ===========================================================================
@router.get("/analysis-cohorts/fields", response_model=dict)
def cohort_fields(current: CurrentUser = Depends(require("analysis_stats:run"))):
    """The constrained vocabulary a cohort definition and an analysis may use.

    Served rather than duplicated in the frontend so the UI's pickers cannot
    drift from what the server will accept — the allow-list has exactly one
    definition, and it is the server's.
    """
    return {
        "filter_columns": sorted(
            [*cohort_worker.COHORT_FILTER_COLUMNS, *cohort_worker.FACTOR_COLUMNS]
        ),
        "filter_operators": sorted(cohort_worker.COHORT_FILTER_OPERATORS),
        "list_operators": sorted(cohort_worker.LIST_OPERATORS),
        "factor_columns": sorted(cohort_worker.FACTOR_COLUMNS),
        "boolean_columns": sorted(cohort_worker._BOOLEAN_COLUMNS),
        "numeric_variables": stats_worker.NUMERIC_VARIABLES,
        "categorical_variables": stats_worker.CATEGORICAL_VARIABLES,
        "trend_periods": sorted(stats_worker.TREND_PERIODS),
        "trend_measures": ["crash_count", "sum_fatalities", "avg_fatalities", "sum_persons"],
        "cohort_roles": [r.value for r in CohortRole],
        "methods": [m.value for m in AnalysisMethod],
        "export_formats": [f.value for f in StatisticalExportFormat],
    }


@router.get("/analysis-cohorts/factors", response_model=list[dict])
def available_factors(
    cohort_id: uuid.UUID | None = None,
    db: Session = Depends(get_db),
    current: CurrentUser = Depends(require("analysis_stats:run")),
):
    """Contributing-factor values actually present in materialized cohorts.

    Drawn from the snapshot rather than from the reference catalog on purpose: an
    exposure that appears in the catalog but on no crash produces an all-zero
    risk model, and offering it as a choice wastes the analyst's time. This lists
    what can actually be modelled.
    """
    # DISTINCT crash, not distinct member row: a crash belongs to several
    # cohorts at once (it is in ALL_CRASHES and in FATAL_INSCOPE and in
    # KS_FATAL), so a plain count would report one crash three times and the
    # number beside each exposure would be meaningless.
    crashes = func.count(func.distinct(AnalysisCohortMember.crash_id))
    stmt = (
        select(func.unnest(AnalysisCohortMember.factors).label("factor"), crashes.label("crashes"))
        .group_by("factor")
        .order_by(crashes.desc(), "factor")
    )
    if cohort_id is not None:
        version = _version_of(db, _load_cohort(db, cohort_id))
        stmt = stmt.where(AnalysisCohortMember.version_id == version.id)
    else:
        current_versions = select(AnalysisCohort.current_version_id).where(
            AnalysisCohort.current_version_id.isnot(None)
        )
        stmt = stmt.where(AnalysisCohortMember.version_id.in_(current_versions))
    states = _allowed_states(current)
    if states:
        stmt = stmt.where(AnalysisCohortMember.state_code.in_(states))
    return [{"factor": r.factor, "crashes": int(r.crashes)} for r in db.execute(stmt)]


# ===========================================================================
# Cohorts
# ===========================================================================
@router.get("/analysis-cohorts", response_model=list[CohortOut])
def list_cohorts(
    environment_id: uuid.UUID | None = None,
    cohort_role: CohortRole | None = None,
    include_archived: bool = False,
    db: Session = Depends(get_db),
    current: CurrentUser = Depends(require("analysis_stats:run")),
):
    """Cohorts in the environment.

    Archived cohorts are excluded by default. They stop refreshing when archived,
    so leaving them in the default list would offer an analyst a population whose
    snapshot is frozen at an arbitrary past date — and the picker gives no hint
    of that. They remain fetchable by id so saved investigations and audit
    entries that reference them still resolve.
    """
    stmt = select(AnalysisCohort).order_by(AnalysisCohort.cohort_role, AnalysisCohort.code)
    if environment_id is not None:
        stmt = stmt.where(AnalysisCohort.environment_id == environment_id)
    if cohort_role is not None:
        stmt = stmt.where(AnalysisCohort.cohort_role == cohort_role.value)
    if not include_archived:
        stmt = stmt.where(AnalysisCohort.status == CohortStatus.ACTIVE.value)
    return [_cohort_out(db, c) for c in db.scalars(stmt)]


@router.post("/analysis-cohorts", response_model=CohortOut, status_code=201)
def create_cohort(
    body: CohortIn,
    db: Session = Depends(get_db),
    current: CurrentUser = Depends(require("analysis_stats:manage")),
):
    environment = db.get(AnalysisEnvironment, body.environment_id)
    if environment is None:
        raise NotFound("Analysis environment")

    try:
        definition = cohort_worker.validate_cohort_definition(body.definition)
    except cohort_worker.CohortDefinitionError as exc:
        raise BadRequest(str(exc))

    cohort = AnalysisCohort(
        environment_id=environment.id,
        code=body.code,
        name=body.name,
        description=body.description,
        cohort_role=body.cohort_role.value,
        definition=definition,
        created_by=current.id,
    )
    db.add(cohort)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise BadRequest(f"A cohort with code '{body.code}' already exists in this environment")

    # Materialize immediately: a cohort that reports no members until the next
    # refresh is indistinguishable from a definition that matches nothing, and
    # the author is standing right there to see which it is.
    try:
        cohort_worker.materialize_cohort(cohort.id, db=db)
    except Exception as exc:  # noqa: BLE001 — report, don't lose the definition
        db.rollback()
        raise BadRequest(f"Cohort definition could not be materialized: {exc}")

    record_audit(
        db, actor=current, action="CREATE", entity_type="analysis_cohort",
        entity_id=cohort.id,
        after={"code": cohort.code, "cohort_role": cohort.cohort_role, "definition": definition},
    )
    db.commit()
    db.refresh(cohort)
    return _cohort_out(db, cohort)


@router.get("/analysis-cohorts/{cohort_id}", response_model=CohortOut)
def get_cohort(
    cohort_id: uuid.UUID,
    db: Session = Depends(get_db),
    current: CurrentUser = Depends(require("analysis_stats:run")),
):
    return _cohort_out(db, _load_cohort(db, cohort_id))


@router.patch("/analysis-cohorts/{cohort_id}", response_model=CohortOut)
def update_cohort(
    cohort_id: uuid.UUID,
    body: CohortUpdate,
    db: Session = Depends(get_db),
    current: CurrentUser = Depends(require("analysis_stats:manage")),
):
    """Update a cohort, re-materializing when the definition changes.

    A definition edit re-materializes immediately rather than waiting for the
    next refresh. Leaving the old members in place would mean the cohort's stated
    definition and its actual contents disagreed — and every statistic run in
    between would silently describe the old population under the new name.
    """
    cohort = _load_cohort(db, cohort_id)
    before = {
        "name": cohort.name,
        "cohort_role": cohort.cohort_role,
        "definition": cohort.definition,
        "status": cohort.status,
    }

    definition_changed = False
    if body.definition is not None:
        try:
            cohort.definition = cohort_worker.validate_cohort_definition(body.definition)
        except cohort_worker.CohortDefinitionError as exc:
            raise BadRequest(str(exc))
        definition_changed = True
    if body.name is not None:
        cohort.name = body.name
    if body.description is not None:
        cohort.description = body.description
    if body.cohort_role is not None:
        cohort.cohort_role = body.cohort_role.value
    if body.status is not None:
        cohort.status = body.status.value

    if definition_changed:
        try:
            cohort_worker.materialize_cohort(cohort.id, db=db)
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            raise BadRequest(f"Cohort definition could not be materialized: {exc}")

    record_audit(
        db, actor=current, action="UPDATE", entity_type="analysis_cohort",
        entity_id=cohort.id, before=before,
        after={
            "name": cohort.name,
            "cohort_role": cohort.cohort_role,
            "definition": cohort.definition,
            "status": cohort.status,
        },
    )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        # The database refuses to demote a cohort that a saved risk model still
        # depends on; pass its reason through rather than a generic 500.
        raise BadRequest(str(getattr(exc, "orig", exc)).strip())
    db.refresh(cohort)
    return _cohort_out(db, cohort)


@router.delete("/analysis-cohorts/{cohort_id}", status_code=204)
def delete_cohort(
    cohort_id: uuid.UUID,
    db: Session = Depends(get_db),
    current: CurrentUser = Depends(require("analysis_stats:manage")),
):
    """Archive a cohort. Never a hard delete.

    Saved investigations reference cohorts by id, and audit entries reference the
    analyses that were run against them. Removing the row would strand both, so
    the cohort stops refreshing and stops appearing in pickers but remains
    resolvable.
    """
    cohort = _load_cohort(db, cohort_id)
    cohort.status = CohortStatus.ARCHIVED.value
    record_audit(
        db, actor=current, action="DELETE", entity_type="analysis_cohort",
        entity_id=cohort.id, before={"code": cohort.code, "status": "ACTIVE"},
        after={"status": cohort.status},
    )
    db.commit()
    return Response(status_code=204)


@router.post("/analysis-cohorts/{cohort_id}/refresh", response_model=CohortOut)
def refresh_cohort(
    cohort_id: uuid.UUID,
    db: Session = Depends(get_db),
    current: CurrentUser = Depends(require("analysis_stats:manage")),
):
    """Re-materialize one cohort now, without refreshing the environment."""
    cohort = _load_cohort(db, cohort_id)
    try:
        cohort_worker.materialize_cohort(cohort.id, db=db)
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        raise BadRequest(f"Cohort could not be materialized: {exc}")
    record_audit(
        db, actor=current, action="UPDATE", entity_type="analysis_cohort",
        entity_id=cohort.id, after={"refreshed": True},
    )
    db.commit()
    db.refresh(cohort)
    return _cohort_out(db, cohort)


@router.get("/analysis-cohorts/{cohort_id}/members", response_model=MembersOut)
def cohort_members(
    cohort_id: uuid.UUID,
    limit: int = Query(DEFAULT_MEMBER_LIMIT, ge=1, le=MAX_MEMBER_LIMIT),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current: CurrentUser = Depends(require("analysis_stats:run")),
):
    """Preview the crashes in a cohort — the "present data as is for user
    exploration" half of the BRD's descriptive requirement."""
    cohort = _load_cohort(db, cohort_id)
    version = _version_of(db, cohort)

    stmt = select(AnalysisCohortMember).where(
        AnalysisCohortMember.version_id == version.id
    )
    states = _allowed_states(current)
    if states:
        stmt = stmt.where(AnalysisCohortMember.state_code.in_(states))

    total = db.scalar(
        select(func.count()).select_from(stmt.subquery())
    ) or 0
    rows = db.scalars(
        stmt.order_by(
            AnalysisCohortMember.crash_date.desc().nullslast(),
            AnalysisCohortMember.ccfp_identifier,
        )
        .offset(offset)
        .limit(limit)
    ).all()

    return MembersOut(
        cohort_id=cohort.id,
        version_no=version.version_no,
        materialized_at=version.materialized_at,
        # The count a State-scoped caller can see, not the cohort total — the
        # same rule the dataset row counts follow.
        member_count=int(total),
        returned=len(rows),
        members=[
            {
                "crash_id": str(m.crash_id) if m.crash_id else None,
                "ccfp_identifier": m.ccfp_identifier,
                "state_code": m.state_code,
                "county": m.county,
                "crash_date": m.crash_date.isoformat() if m.crash_date else None,
                "crash_year": m.crash_year,
                "crash_month": m.crash_month,
                "lifecycle_phase": m.lifecycle_phase,
                "num_fatalities": m.num_fatalities,
                "num_vehicles": m.num_vehicles,
                "num_persons": m.num_persons,
                "is_fatal": m.is_fatal,
                "scope": m.scope,
                "is_qualifying": m.is_qualifying,
                "factors": list(m.factors or []),
            }
            for m in rows
        ],
    )


# ===========================================================================
# Statistical methods
# ===========================================================================
@router.get("/analysis-cohorts/{cohort_id}/describe", response_model=dict)
def cohort_describe(
    cohort_id: uuid.UUID,
    variable: str = Query(..., min_length=1),
    confidence: float = Query(0.95, gt=0.5, lt=1.0),
    db: Session = Depends(get_db),
    current: CurrentUser = Depends(require("analysis_stats:run")),
):
    """Central tendency and dispersion (BRD p. 16)."""
    cohort = _load_cohort(db, cohort_id)
    version = _version_of(db, cohort)
    try:
        result = stats_worker.describe(
            db, version.id, variable, _allowed_states(current), confidence
        )
    except stats_worker.StatisticsError as exc:
        raise BadRequest(str(exc))
    return _stamp(version, cohort, result)


@router.get("/analysis-cohorts/{cohort_id}/distribution", response_model=dict)
def cohort_distribution(
    cohort_id: uuid.UUID,
    variable: str = Query(..., min_length=1),
    bins: int = Query(stats_worker.HISTOGRAM_BINS, ge=2, le=50),
    db: Session = Depends(get_db),
    current: CurrentUser = Depends(require("analysis_stats:run")),
):
    """Data distributions — frequency table or histogram (BRD p. 16)."""
    cohort = _load_cohort(db, cohort_id)
    version = _version_of(db, cohort)
    try:
        result = stats_worker.distribution(
            db, version.id, variable, _allowed_states(current), bins
        )
    except stats_worker.StatisticsError as exc:
        raise BadRequest(str(exc))
    return _stamp(version, cohort, result)


@router.get("/analysis-cohorts/{cohort_id}/thematic", response_model=dict)
def cohort_thematic(
    cohort_id: uuid.UUID,
    min_support: int = Query(1, ge=1, le=1000),
    top_n: int = Query(25, ge=1, le=200),
    db: Session = Depends(get_db),
    current: CurrentUser = Depends(require("analysis_stats:run")),
):
    """Thematic analysis over contributing factors (BRD p. 16)."""
    cohort = _load_cohort(db, cohort_id)
    version = _version_of(db, cohort)
    result = stats_worker.thematic(
        db, version.id, _allowed_states(current), min_support, top_n
    )
    return _stamp(version, cohort, result)


@router.get("/analysis-cohorts/{cohort_id}/trend", response_model=dict)
def cohort_trend(
    cohort_id: uuid.UUID,
    period: str = Query("YEAR"),
    measure: str = Query("crash_count"),
    db: Session = Depends(get_db),
    current: CurrentUser = Depends(require("analysis_stats:run")),
):
    """Trend analysis with an ordinary-least-squares fit."""
    cohort = _load_cohort(db, cohort_id)
    version = _version_of(db, cohort)
    try:
        result = stats_worker.trend(
            db, version.id, period, measure, _allowed_states(current)
        )
    except stats_worker.StatisticsError as exc:
        raise BadRequest(str(exc))
    return _stamp(version, cohort, result)


@router.post("/analysis-statistics/risk-model", response_model=dict)
def run_risk_model(
    body: RiskModelIn,
    db: Session = Depends(get_db),
    current: CurrentUser = Depends(require("analysis_stats:run")),
):
    """Statistical risk modelling against a control population (BRD p. 16).

    The BRD's clause — "given the availability of control such as non-fatal
    crashes" — is enforced here as a precondition, not treated as advisory. The
    named control cohort must actually be designated CONTROL: a risk model whose
    denominator is another case population produces an odds ratio that looks
    authoritative and means nothing, and there is no way to spot that from the
    output alone.
    """
    case_cohort = _load_cohort(db, body.case_cohort_id)
    control_cohort = _load_cohort(db, body.control_cohort_id)

    if control_cohort.cohort_role != CohortRole.CONTROL.value:
        raise BadRequest(
            f"Cohort '{control_cohort.code}' is designated {control_cohort.cohort_role}, "
            "not CONTROL. Risk modelling requires a control population — the BRD "
            "makes the capability conditional on one being available. Designate a "
            "control cohort (for example, non-fatal or non-qualifying crashes) "
            "before running a risk model."
        )
    if case_cohort.id == control_cohort.id:
        raise BadRequest("The case and control cohorts must be different populations.")

    case_version = _version_of(db, case_cohort)
    control_version = _version_of(db, control_cohort)

    try:
        result = stats_worker.risk_model(
            db,
            case_version.id,
            control_version.id,
            body.exposure_factor,
            _allowed_states(current),
            body.confidence,
        )
    except stats_worker.StatisticsError as exc:
        raise BadRequest(str(exc))

    result["case_cohort"] = {
        "id": str(case_cohort.id),
        "code": case_cohort.code,
        "name": case_cohort.name,
        "version_no": case_version.version_no,
        "materialized_at": case_version.materialized_at,
    }
    result["control_cohort"] = {
        "id": str(control_cohort.id),
        "code": control_cohort.code,
        "name": control_cohort.name,
        "version_no": control_version.version_no,
        "materialized_at": control_version.materialized_at,
    }
    _time_skew_caveat(
        result, (case_cohort, case_version), (control_cohort, control_version)
    )
    return result


@router.post("/analysis-statistics/compare", response_model=dict)
def run_compare(
    body: CompareIn,
    db: Session = Depends(get_db),
    current: CurrentUser = Depends(require("analysis_stats:run")),
):
    """Comparative analysis of two crash populations.

    Compares either a numeric variable (difference of means, Welch's t-test) or
    the prevalence of one contributing factor (two-proportion z-test). Unlike the
    risk model this places no role requirement on either cohort — comparing two
    States or two years is a legitimate question that has nothing to do with
    case-control design.
    """
    if bool(body.variable) == bool(body.factor):
        raise BadRequest("Provide exactly one of 'variable' or 'factor' to compare.")

    cohort_a = _load_cohort(db, body.cohort_a_id)
    cohort_b = _load_cohort(db, body.cohort_b_id)
    if cohort_a.id == cohort_b.id:
        raise BadRequest("Select two different cohorts to compare.")
    version_a = _version_of(db, cohort_a)
    version_b = _version_of(db, cohort_b)

    try:
        if body.variable:
            result = stats_worker.compare(
                db, version_a.id, version_b.id, body.variable,
                _allowed_states(current), body.confidence,
            )
        else:
            result = stats_worker.compare_proportions(
                db, version_a.id, version_b.id, body.factor,
                _allowed_states(current), body.confidence,
            )
    except stats_worker.StatisticsError as exc:
        raise BadRequest(str(exc))

    for key, cohort, version in (
        ("cohort_a", cohort_a, version_a),
        ("cohort_b", cohort_b, version_b),
    ):
        result[key] = {
            **result.get(key, {}),
            "id": str(cohort.id),
            "code": cohort.code,
            "name": cohort.name,
            "version_no": version.version_no,
            "materialized_at": version.materialized_at,
        }
    _time_skew_caveat(result, (cohort_a, version_a), (cohort_b, version_b))
    return result


# ===========================================================================
# Saved investigations
# ===========================================================================
def _investigation_visible(stmt, current: CurrentUser):
    """PRIVATE investigations are visible only to their author."""
    return stmt.where(
        (AnalysisInvestigation.visibility == InvestigationVisibility.TEAM.value)
        | (AnalysisInvestigation.created_by == current.id)
    )


@router.get("/analysis-investigations", response_model=list[InvestigationOut])
def list_investigations(
    environment_id: uuid.UUID | None = None,
    method: AnalysisMethod | None = None,
    db: Session = Depends(get_db),
    current: CurrentUser = Depends(require("analysis_stats:run")),
):
    stmt = select(AnalysisInvestigation).order_by(
        AnalysisInvestigation.updated_at.desc()
    )
    if environment_id is not None:
        stmt = stmt.where(AnalysisInvestigation.environment_id == environment_id)
    if method is not None:
        stmt = stmt.where(AnalysisInvestigation.method == method.value)
    return list(db.scalars(_investigation_visible(stmt, current)))


@router.post("/analysis-investigations", response_model=InvestigationOut, status_code=201)
def create_investigation(
    body: InvestigationIn,
    db: Session = Depends(get_db),
    current: CurrentUser = Depends(require("analysis_stats:manage")),
):
    """Save a reusable analytical investigation.

    The parameters are validated against the method now, so a saved
    investigation that cannot run is rejected at save time rather than
    discovered by whoever opens it next week.
    """
    environment = db.get(AnalysisEnvironment, body.environment_id)
    if environment is None:
        raise NotFound("Analysis environment")

    parameters = _validate_parameters(db, body.method, body.parameters)

    investigation = AnalysisInvestigation(
        environment_id=environment.id,
        code=body.code,
        name=body.name,
        description=body.description,
        method=body.method.value,
        parameters=parameters,
        visibility=body.visibility.value,
        created_by=current.id,
    )
    db.add(investigation)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise BadRequest(
            f"An investigation with code '{body.code}' already exists in this environment"
        )
    record_audit(
        db, actor=current, action="CREATE", entity_type="analysis_investigation",
        entity_id=investigation.id,
        after={"code": investigation.code, "method": investigation.method},
    )
    db.commit()
    db.refresh(investigation)
    return investigation


@router.get("/analysis-investigations/{investigation_id}", response_model=InvestigationOut)
def get_investigation(
    investigation_id: uuid.UUID,
    db: Session = Depends(get_db),
    current: CurrentUser = Depends(require("analysis_stats:run")),
):
    return _load_investigation(db, investigation_id, current)


@router.patch("/analysis-investigations/{investigation_id}", response_model=InvestigationOut)
def update_investigation(
    investigation_id: uuid.UUID,
    body: InvestigationUpdate,
    db: Session = Depends(get_db),
    current: CurrentUser = Depends(require("analysis_stats:manage")),
):
    investigation = _load_investigation(db, investigation_id, current)
    before = {
        "name": investigation.name,
        "parameters": investigation.parameters,
        "visibility": investigation.visibility,
        "status": investigation.status,
    }
    if body.parameters is not None:
        investigation.parameters = _validate_parameters(
            db, AnalysisMethod(investigation.method), body.parameters
        )
    if body.name is not None:
        investigation.name = body.name
    if body.description is not None:
        investigation.description = body.description
    if body.visibility is not None:
        investigation.visibility = body.visibility.value
    if body.status is not None:
        investigation.status = body.status.value
    investigation.updated_at = dt.datetime.now(dt.timezone.utc)

    record_audit(
        db, actor=current, action="UPDATE", entity_type="analysis_investigation",
        entity_id=investigation.id, before=before,
        after={
            "name": investigation.name,
            "parameters": investigation.parameters,
            "visibility": investigation.visibility,
            "status": investigation.status,
        },
    )
    db.commit()
    db.refresh(investigation)
    return investigation


@router.delete("/analysis-investigations/{investigation_id}", status_code=204)
def delete_investigation(
    investigation_id: uuid.UUID,
    db: Session = Depends(get_db),
    current: CurrentUser = Depends(require("analysis_stats:manage")),
):
    investigation = _load_investigation(db, investigation_id, current)
    investigation.status = InvestigationStatus.ARCHIVED.value
    record_audit(
        db, actor=current, action="DELETE", entity_type="analysis_investigation",
        entity_id=investigation.id, before={"code": investigation.code},
        after={"status": investigation.status},
    )
    db.commit()
    return Response(status_code=204)


@router.post("/analysis-investigations/{investigation_id}/run", response_model=dict)
def run_investigation(
    investigation_id: uuid.UUID,
    db: Session = Depends(get_db),
    current: CurrentUser = Depends(require("analysis_stats:run")),
):
    """Re-run a saved investigation against the current cohort versions.

    The result is computed fresh rather than replayed from a store: the point of
    saving an investigation is to ask the same question of newer data, so the
    answer carries today's version stamp and may legitimately differ from the
    last run.
    """
    investigation = _load_investigation(db, investigation_id, current)
    method = AnalysisMethod(investigation.method)
    parameters = dict(investigation.parameters or {})
    states = _allowed_states(current)
    # Conditions discovered while resolving the saved references, merged into the
    # result's caveats below so they travel with the numbers like every other one.
    result_notes: list[str] = []

    def cohort_and_version(key: str) -> tuple[AnalysisCohort, AnalysisCohortVersion]:
        """Resolve one of the saved investigation's cohort references.

        The reference lives inside ``parameters`` JSONB, so no foreign key
        protects it. Deleting a cohort is not reachable through this API — the
        delete route archives — but a direct database write could still strand
        it, and "Analysis cohort not found" would send the reader looking for a
        missing URL rather than a broken saved object. Name what is actually
        wrong instead.
        """
        raw = parameters.get(key)
        if not raw:
            raise BadRequest(f"Saved investigation is missing '{key}'.")
        try:
            cohort_id = uuid.UUID(str(raw))
        except (ValueError, TypeError):
            raise BadRequest(
                f"Saved investigation '{investigation.code}' has a malformed "
                f"cohort reference in '{key}'."
            )
        cohort = db.get(AnalysisCohort, cohort_id)
        if cohort is None:
            raise BadRequest(
                f"Saved investigation '{investigation.code}' refers to a cohort "
                f"({key}) that no longer exists. Re-point it at a current cohort, "
                "or archive the investigation."
            )
        if cohort.status != CohortStatus.ACTIVE.value:
            # Archived cohorts stop refreshing, so the snapshot underneath this
            # investigation is frozen at whenever it was archived. Still
            # runnable — the version stamp on the result stays truthful — but
            # the reader should know the number will not move again.
            result_notes.append(
                f"Cohort '{cohort.code}' is archived and no longer refreshes; "
                "this result is computed from the snapshot taken before it was "
                "archived."
            )
        return cohort, _version_of(db, cohort)

    try:
        if method is AnalysisMethod.DESCRIPTIVE:
            cohort, version = cohort_and_version("cohort_id")
            result = _stamp(version, cohort, stats_worker.describe(
                db, version.id, parameters["variable"], states,
                float(parameters.get("confidence", 0.95)),
            ))
        elif method is AnalysisMethod.DISTRIBUTION:
            cohort, version = cohort_and_version("cohort_id")
            result = _stamp(version, cohort, stats_worker.distribution(
                db, version.id, parameters["variable"], states,
                int(parameters.get("bins", stats_worker.HISTOGRAM_BINS)),
            ))
        elif method is AnalysisMethod.THEMATIC:
            cohort, version = cohort_and_version("cohort_id")
            result = _stamp(version, cohort, stats_worker.thematic(
                db, version.id, states,
                int(parameters.get("min_support", 1)),
                int(parameters.get("top_n", 25)),
            ))
        elif method is AnalysisMethod.TREND:
            cohort, version = cohort_and_version("cohort_id")
            result = _stamp(version, cohort, stats_worker.trend(
                db, version.id, parameters.get("period", "YEAR"),
                parameters.get("measure", "crash_count"), states,
            ))
        elif method is AnalysisMethod.RISK_MODEL:
            case_cohort, case_version = cohort_and_version("case_cohort_id")
            control_cohort, control_version = cohort_and_version("control_cohort_id")
            if control_cohort.cohort_role != CohortRole.CONTROL.value:
                raise BadRequest(
                    f"Cohort '{control_cohort.code}' is no longer designated CONTROL; "
                    "this saved risk model cannot run until a control population is set."
                )
            result = stats_worker.risk_model(
                db, case_version.id, control_version.id,
                parameters["exposure_factor"], states,
                float(parameters.get("confidence", 0.95)),
            )
            result["case_cohort"] = {
                "id": str(case_cohort.id), "code": case_cohort.code,
                "name": case_cohort.name, "version_no": case_version.version_no,
                "materialized_at": case_version.materialized_at,
            }
            result["control_cohort"] = {
                "id": str(control_cohort.id), "code": control_cohort.code,
                "name": control_cohort.name, "version_no": control_version.version_no,
                "materialized_at": control_version.materialized_at,
            }
            _time_skew_caveat(
                result, (case_cohort, case_version), (control_cohort, control_version)
            )
        elif method is AnalysisMethod.COMPARATIVE:
            cohort_a, version_a = cohort_and_version("cohort_a_id")
            cohort_b, version_b = cohort_and_version("cohort_b_id")
            confidence = float(parameters.get("confidence", 0.95))
            if parameters.get("variable"):
                result = stats_worker.compare(
                    db, version_a.id, version_b.id, parameters["variable"], states, confidence
                )
            else:
                result = stats_worker.compare_proportions(
                    db, version_a.id, version_b.id, parameters["factor"], states, confidence
                )
            for key, cohort, version in (
                ("cohort_a", cohort_a, version_a),
                ("cohort_b", cohort_b, version_b),
            ):
                result[key] = {
                    **result.get(key, {}),
                    "id": str(cohort.id), "code": cohort.code, "name": cohort.name,
                    "version_no": version.version_no,
                    "materialized_at": version.materialized_at,
                }
            _time_skew_caveat(result, (cohort_a, version_a), (cohort_b, version_b))
        else:  # pragma: no cover — AnalysisMethod is closed and fully covered
            raise BadRequest(f"Method '{method.value}' cannot be run.")
    except stats_worker.StatisticsError as exc:
        raise BadRequest(str(exc))
    except (KeyError, ValueError) as exc:
        raise BadRequest(f"Saved investigation has invalid parameters: {exc}")

    investigation.last_run_at = dt.datetime.now(dt.timezone.utc)
    db.commit()

    # Prepended, not appended: a frozen cohort underneath the result changes how
    # every figure below it should be read, so it belongs above the method's own
    # statistical caveats rather than at the bottom of the list.
    if result_notes:
        result["caveats"] = [*result_notes, *result.get("caveats", [])]

    result["investigation"] = {
        "id": str(investigation.id),
        "code": investigation.code,
        "name": investigation.name,
        "method": investigation.method,
    }
    return result


def _load_investigation(
    db: Session, investigation_id: uuid.UUID, current: CurrentUser
) -> AnalysisInvestigation:
    investigation = db.get(AnalysisInvestigation, investigation_id)
    if investigation is None:
        raise NotFound("Analysis investigation")
    # A PRIVATE investigation belonging to someone else is reported as absent
    # rather than forbidden, so its existence is not disclosed.
    if (
        investigation.visibility == InvestigationVisibility.PRIVATE.value
        and investigation.created_by != current.id
    ):
        raise NotFound("Analysis investigation")
    return investigation


def _validate_parameters(
    db: Session, method: AnalysisMethod, parameters: dict[str, Any]
) -> dict[str, Any]:
    """Check a saved investigation's parameters against its method.

    Every cohort reference is resolved now, so a saved investigation cannot name
    a cohort that does not exist, and every variable is checked against the same
    allow-list the live endpoints use.
    """
    params = dict(parameters or {})

    def require_cohort(key: str) -> AnalysisCohort:
        raw = params.get(key)
        if not raw:
            raise BadRequest(f"Method {method.value} requires '{key}'.")
        try:
            cohort_id = uuid.UUID(str(raw))
        except (ValueError, TypeError):
            raise BadRequest(f"'{key}' must be a cohort id.")
        cohort = db.get(AnalysisCohort, cohort_id)
        if cohort is None:
            raise BadRequest(f"Cohort named by '{key}' does not exist.")
        params[key] = str(cohort.id)
        return cohort

    if method in (AnalysisMethod.DESCRIPTIVE, AnalysisMethod.DISTRIBUTION):
        require_cohort("cohort_id")
        variable = params.get("variable")
        known = (
            stats_worker.NUMERIC_VARIABLES
            if method is AnalysisMethod.DESCRIPTIVE
            else {**stats_worker.NUMERIC_VARIABLES, **stats_worker.CATEGORICAL_VARIABLES}
        )
        if variable not in known:
            raise BadRequest(f"Unknown variable '{variable}'. Allowed: {sorted(known)}")
    elif method is AnalysisMethod.THEMATIC:
        require_cohort("cohort_id")
    elif method is AnalysisMethod.TREND:
        require_cohort("cohort_id")
        if params.get("period", "YEAR") not in stats_worker.TREND_PERIODS:
            raise BadRequest(f"Unknown period. Allowed: {sorted(stats_worker.TREND_PERIODS)}")
    elif method is AnalysisMethod.RISK_MODEL:
        require_cohort("case_cohort_id")
        control = require_cohort("control_cohort_id")
        if control.cohort_role != CohortRole.CONTROL.value:
            raise BadRequest(
                f"Cohort '{control.code}' is designated {control.cohort_role}, not "
                "CONTROL. A risk model requires a control population."
            )
        if params["case_cohort_id"] == params["control_cohort_id"]:
            raise BadRequest("The case and control cohorts must be different populations.")
        if not params.get("exposure_factor"):
            raise BadRequest("A risk model requires an 'exposure_factor'.")
    elif method is AnalysisMethod.COMPARATIVE:
        require_cohort("cohort_a_id")
        require_cohort("cohort_b_id")
        if params["cohort_a_id"] == params["cohort_b_id"]:
            raise BadRequest("Select two different cohorts to compare.")
        if bool(params.get("variable")) == bool(params.get("factor")):
            raise BadRequest("Provide exactly one of 'variable' or 'factor'.")
        if params.get("variable") and params["variable"] not in stats_worker.NUMERIC_VARIABLES:
            raise BadRequest(
                f"Unknown variable. Allowed: {sorted(stats_worker.NUMERIC_VARIABLES)}"
            )
    return params


# ===========================================================================
# Export to external statistical tools
# ===========================================================================
@router.get("/analysis-cohorts/{cohort_id}/export")
def export_cohort(
    cohort_id: uuid.UUID,
    format: StatisticalExportFormat = Query(StatisticalExportFormat.CSV),
    db: Session = Depends(get_db),
    current: CurrentUser = Depends(require("analysis_stats:run")),
):
    """Export a cohort for the external tools the BRD names (p. 17).

        "Data should be exportable to any statistical summary or
         visualization/report builder tools ... e.g. Python, SAS, R."

    CSV is the data. The PYTHON, R and SAS formats return a ready-to-run loader
    script for that same CSV, carrying the column types, the factor separator and
    the cohort's provenance. A bare CSV forces every analyst to re-derive the
    schema and guess how the factor list is encoded, and they will not all guess
    the same way — which is how two analysts produce two different answers from
    one export.
    """
    cohort = _load_cohort(db, cohort_id)
    version = _version_of(db, cohort)

    stmt = select(AnalysisCohortMember).where(
        AnalysisCohortMember.version_id == version.id
    )
    states = _allowed_states(current)
    if states:
        stmt = stmt.where(AnalysisCohortMember.state_code.in_(states))
    members = db.scalars(
        stmt.order_by(
            AnalysisCohortMember.crash_date.desc().nullslast(),
            AnalysisCohortMember.ccfp_identifier,
        )
    ).all()

    base = f"{cohort.code.lower()}_v{version.version_no}"
    stamp = version.materialized_at.isoformat() if version.materialized_at else "unknown"

    if format is StatisticalExportFormat.CSV:
        buffer = io.StringIO()
        writer = csv.writer(buffer, lineterminator="\n")
        writer.writerow(EXPORT_COLUMNS)
        for m in members:
            writer.writerow(
                [
                    m.ccfp_identifier or "",
                    m.state_code or "",
                    m.county or "",
                    m.crash_date.isoformat() if m.crash_date else "",
                    m.crash_year if m.crash_year is not None else "",
                    m.crash_month if m.crash_month is not None else "",
                    m.lifecycle_phase or "",
                    m.num_fatalities if m.num_fatalities is not None else "",
                    m.num_vehicles if m.num_vehicles is not None else "",
                    m.num_persons if m.num_persons is not None else "",
                    "TRUE" if m.is_fatal else "FALSE",
                    m.scope or "",
                    "" if m.is_qualifying is None else ("TRUE" if m.is_qualifying else "FALSE"),
                    # Semicolon, not comma: the factor list lives inside one CSV
                    # field, and every generated script splits on this character.
                    ";".join(m.factors or []),
                ]
            )
        return Response(
            content=buffer.getvalue(),
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{base}.csv"'},
        )

    script, media, extension = _loader_script(format, cohort, version, base, stamp, len(members))
    return Response(
        content=script,
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{base}{extension}"'},
    )


def _loader_script(
    format: StatisticalExportFormat,
    cohort: AnalysisCohort,
    version: AnalysisCohortVersion,
    base: str,
    stamp: str,
    n: int,
) -> tuple[str, str, str]:
    """Generate a loader script for one of the BRD's named statistical tools.

    Each script states the cohort, its version and when it was materialized, so
    an analysis run months later can be traced back to the exact snapshot — the
    same provenance the API attaches to every computed statistic, carried into
    the tool where the work actually continues.
    """
    header_lines = [
        f"CCFP Analysis Environment export - cohort {cohort.code} ({cohort.name})",
        f"Cohort role     : {cohort.cohort_role}",
        f"Version         : {version.version_no}",
        f"Materialized at : {stamp}",
        f"Rows            : {n}",
        "",
        "This is a point-in-time snapshot of CCFP Analysis Environment data.",
        "Statistics computed from it describe the population as of the",
        "materialization time above, not the current operational record.",
        "'factors' holds the crash's contributing factors, semicolon-separated.",
    ]

    if format is StatisticalExportFormat.PYTHON:
        head = "\n".join(f"# {line}".rstrip() for line in header_lines)
        body = f'''
import pandas as pd

CSV_PATH = "{base}.csv"

DTYPES = {{
    "ccfp_identifier": "string",
    "state_code": "category",
    "county": "string",
    "crash_year": "Int64",
    "crash_month": "Int64",
    "lifecycle_phase": "category",
    "num_fatalities": "Int64",
    "num_vehicles": "Int64",
    "num_persons": "Int64",
    "scope": "category",
}}

df = pd.read_csv(CSV_PATH, dtype=DTYPES, parse_dates=["crash_date"])

# TRUE/FALSE are written as text so R and SAS read them natively; map them back.
for column in ("is_fatal", "is_qualifying"):
    df[column] = df[column].map({{"TRUE": True, "FALSE": False}}).astype("boolean")

# One row per crash-factor pair, for thematic work.
df["factor_list"] = df["factors"].fillna("").apply(
    lambda value: [f for f in value.split(";") if f]
)
factors_long = df.explode("factor_list").dropna(subset=["factor_list"])

print(df.describe(include="all"))
print(factors_long["factor_list"].value_counts())
'''
        return head + "\n" + body, "text/x-python", ".py"

    if format is StatisticalExportFormat.R:
        head = "\n".join(f"# {line}".rstrip() for line in header_lines)
        body = f'''
csv_path <- "{base}.csv"

ccfp <- read.csv(
  csv_path,
  stringsAsFactors = FALSE,
  na.strings = c("", "NA")
)

ccfp$crash_date    <- as.Date(ccfp$crash_date)
ccfp$state_code    <- factor(ccfp$state_code)
ccfp$lifecycle_phase <- factor(ccfp$lifecycle_phase)
ccfp$scope         <- factor(ccfp$scope)
ccfp$is_fatal      <- ccfp$is_fatal == "TRUE"
ccfp$is_qualifying <- ccfp$is_qualifying == "TRUE"

# Long form: one row per crash-factor pair, for thematic work.
factor_list <- strsplit(ifelse(is.na(ccfp$factors), "", ccfp$factors), ";")
factors_long <- data.frame(
  ccfp_identifier = rep(ccfp$ccfp_identifier, lengths(factor_list)),
  factor          = unlist(factor_list),
  stringsAsFactors = FALSE
)

summary(ccfp)
table(factors_long$factor)
'''
        return head + "\n" + body, "text/plain", ".R"

    # SAS
    head = "\n".join(["/*"] + [f" * {line}".rstrip() for line in header_lines] + [" */"])
    body = f'''
/* Point FILENAME at wherever the CSV was saved. */
filename ccfpcsv "{base}.csv";

proc import datafile=ccfpcsv out=work.ccfp_raw dbms=csv replace;
    getnames=yes;
    guessingrows=max;
run;

data work.ccfp;
    set work.ccfp_raw;
    /* PROC IMPORT with guessingrows=max has already sized every column from the
       data, so no LENGTH statement is used here — one placed after SET would be
       ignored with a warning anyway, because the variables already exist. */
    fatal_flag     = (upcase(is_fatal) = "TRUE");
    qualifying_flag = (upcase(is_qualifying) = "TRUE");
    label
        num_fatalities = "Fatalities"
        num_vehicles   = "Vehicles involved"
        num_persons    = "Persons involved"
        fatal_flag     = "Fatal crash"
        scope          = "Study scope";
run;

/* Long form: one row per crash-factor pair, for thematic work. */
data work.ccfp_factors;
    /* LENGTH before SET: `factor` is a new variable, and declaring it first
       stops SAS sizing it from the first assignment it happens to see. */
    length factor $ 200;
    set work.ccfp;
    if not missing(factors) then do i = 1 to countw(factors, ";");
        factor = scan(factors, i, ";");
        output;
    end;
    keep ccfp_identifier factor;
run;

proc means data=work.ccfp n mean median std min max;
    var num_fatalities num_vehicles num_persons;
run;

proc freq data=work.ccfp_factors;
    tables factor / nocum;
run;
'''
    return head + "\n" + body, "text/plain", ".sas"
