"""CCFP Analysis Environment — manage/share, analyze, visualize (GAP-BRD-02).

Implements the January 2026 BRD's "Data Analysis and Sharing" chapter (pp. 13-16)
as a tier distinct from the operational crash tables:

  Manage/Share  environments + datasets + shares, with the four audience tiers
  Analyze       materialized rows, descriptive statistics, distributions
  Visualize     the same rows/statistics feed the UI charts, plus CSV/JSON export
                for the external tools the BRD names (Python, SAS, R, Tableau,
                ArcGIS)

Every read in this module is served from ``analysis_dataset_rows`` — a snapshot
captured by ``workers/analysis.py`` at a known time — never from a live join
across the operational tables. That is the architectural point of the tier, and
it is what lets the API answer "as of when?" for any number it returns.

Refresh model: the snapshot is refreshed WHEN AN ANALYST OPENS THE PAGE. The
stored snapshot is returned immediately; if it has aged past the environment's
cadence, a refresh runs in a ``BackgroundTasks`` so the next look is current, and
a "Refresh now" control forces one synchronously. The BRD's "daily or hourly" is
therefore honoured as a staleness threshold rather than a firing schedule —
which is the truthful reading for a stack with no scheduler. ``refresh_cadence``
is unchanged and still configuration, so adding Celery Beat later means pointing
it at ``refresh_stale_environments`` with no schema change and no second path.

Authorization has two layers. The permission gate (``analysis_env:*``) decides
who may reach the endpoint at all; the audience resolution below decides which
datasets and which rows they see once inside. A State-scoped principal never
falls through to the unrestricted branch — the two are decided by the same
``allowed_states`` primitive the rest of the app scopes on, so there is no second
notion of "who is a State user" to drift out of sync.
"""
from __future__ import annotations

import csv
import datetime as dt
import io
import json
import uuid
from typing import Any

import jwt

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from app.common import ORMModel
from app.core.audit import record_audit
from app.core.config import settings
from app.core.database import get_db
from app.core.errors import BadRequest, NotFound
from app.core.permissions import require
from app.core.security import CurrentUser
from app.enums import (
    AnalysisAudience,
    AnalysisDatasetKind,
    AnalysisPiiLevel,
    AnalysisShareStatus,
    RefreshCadence,
    RefreshTrigger,
)
from app.models import (
    AnalysisDataset,
    AnalysisDatasetRow,
    AnalysisDatasetVersion,
    AnalysisEnvironment,
    AnalysisRefreshRun,
    AnalysisShare,
)
from app.workers import analysis as analysis_worker

router = APIRouter(tags=["analysis-environment"])

# Rows returned in one page of a dataset preview. Export streams the whole
# version; the preview is bounded so a 200k-row dataset cannot be pulled into a
# browser table by accident.
MAX_ROW_LIMIT = 1000
DEFAULT_ROW_LIMIT = 100
HISTOGRAM_BINS = 10


# ===========================================================================
# Schemas
# ===========================================================================
class EnvironmentOut(ORMModel):
    id: uuid.UUID
    code: str
    name: str
    description: str | None = None
    study_id: uuid.UUID | None = None
    status: str
    refresh_cadence: str
    last_refreshed_at: dt.datetime | None = None
    next_refresh_due: dt.datetime | None = None
    created_at: dt.datetime
    updated_at: dt.datetime
    # Derived, not stored. `is_stale` says the snapshot has aged past its cadence
    # and the next open will trigger a refresh; `refresh_in_progress` says one is
    # already running. The UI needs both to describe what it is showing without
    # guessing — a stale snapshot is still valid data, just not current, and
    # saying so is better than silently serving old numbers.
    is_stale: bool = False
    refresh_in_progress: bool = False


class EnvironmentIn(BaseModel):
    code: str
    name: str
    description: str | None = None
    study_id: uuid.UUID | None = None
    refresh_cadence: RefreshCadence = RefreshCadence.DAILY


class EnvironmentUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    status: str | None = None
    refresh_cadence: RefreshCadence | None = None


class DatasetOut(ORMModel):
    id: uuid.UUID
    environment_id: uuid.UUID
    code: str
    name: str
    description: str | None = None
    kind: str
    definition: dict[str, Any] = {}
    pii_level: str
    is_state_partitioned: bool
    status: str
    current_version_id: uuid.UUID | None = None
    created_at: dt.datetime
    updated_at: dt.datetime
    # Version facts, filled in by the serializer so a caller never has to make a
    # second round-trip to answer "is this stale?".
    version_no: int | None = None
    row_count: int | None = None
    materialized_at: dt.datetime | None = None
    columns: list[str] = []


class DatasetIn(BaseModel):
    environment_id: uuid.UUID
    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1)
    description: str | None = None
    kind: AnalysisDatasetKind = AnalysisDatasetKind.DERIVED_VIEW
    pii_level: AnalysisPiiLevel = AnalysisPiiLevel.NO_PII
    definition: dict[str, Any]

    @field_validator("code")
    @classmethod
    def _code_shape(cls, v: str) -> str:
        cleaned = v.strip().upper().replace(" ", "_")
        if not cleaned.replace("_", "").isalnum():
            raise ValueError("code must be alphanumeric with underscores")
        return cleaned


class DatasetUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    pii_level: AnalysisPiiLevel | None = None
    status: str | None = None
    definition: dict[str, Any] | None = None


class ShareOut(ORMModel):
    id: uuid.UUID
    dataset_id: uuid.UUID
    audience: str
    state_code: str | None = None
    refresh_cadence: str
    status: str
    note: str | None = None
    shared_at: dt.datetime
    revoked_at: dt.datetime | None = None


class ShareIn(BaseModel):
    audience: AnalysisAudience
    state_code: str | None = None
    refresh_cadence: RefreshCadence = RefreshCadence.DAILY
    note: str | None = None


class RefreshRunOut(ORMModel):
    id: uuid.UUID
    environment_id: uuid.UUID
    dataset_id: uuid.UUID | None = None
    trigger: str
    status: str
    started_at: dt.datetime
    finished_at: dt.datetime | None = None
    datasets_refreshed: int
    rows_written: int
    message: str | None = None


class RowsOut(BaseModel):
    dataset_id: uuid.UUID
    version_no: int | None = None
    materialized_at: dt.datetime | None = None
    columns: list[str]
    rows: list[dict[str, Any]]
    total: int
    limit: int
    offset: int
    # True when the caller is seeing a State-filtered slice rather than the whole
    # dataset. Surfaced so the UI can say so out loud instead of presenting a
    # partial view as if it were the national picture.
    state_scoped: bool = False


class StatisticsOut(BaseModel):
    """Descriptive statistics over one column of Analysis Environment data.

    Covers the BRD's "central tendency and dispersion, data distributions" line.
    Computed in PostgreSQL rather than in Python so it stays usable as the
    dataset grows — the BRD asks for large datasets "with minimal performance
    impact".
    """

    dataset_id: uuid.UUID
    column: str
    version_no: int | None = None
    materialized_at: dt.datetime | None = None
    n: int
    # Central tendency
    mean: float | None = None
    median: float | None = None
    # Dispersion
    stddev: float | None = None
    variance: float | None = None
    minimum: float | None = None
    maximum: float | None = None
    p25: float | None = None
    p75: float | None = None
    iqr: float | None = None
    total: float | None = None
    # Distribution
    histogram: list[dict[str, Any]] = []


# ===========================================================================
# Audience resolution & visibility
# ===========================================================================
def _is_state_principal(current: CurrentUser) -> bool:
    """A State-scoped principal, in the same sense the rest of the app means it.

    ``allowed_states is None`` denotes an unrestricted (Federal-tier) principal;
    anything else is confined to named States. Reusing this primitive rather than
    inspecting role codes means a user whose scope changes gets the right
    Analysis Environment view automatically.
    """
    return current.allowed_states is not None


def _visible_datasets(stmt, current: CurrentUser):
    """Restrict a datasets SELECT to what this principal may see.

    Federal-tier principals see the environment's datasets directly. A
    State-scoped principal sees only datasets carrying an ACTIVE
    PARTICIPATING_STATE share for one of their States — the BRD gives States
    access to shared data, not to the environment's contents at large. The
    database trigger guarantees such a dataset is both non-PII and
    State-partitioned, so this filter cannot admit a dataset whose rows the
    State is not entitled to.
    """
    if not _is_state_principal(current):
        return stmt
    shared = select(AnalysisShare.dataset_id).where(
        AnalysisShare.status == AnalysisShareStatus.ACTIVE.value,
        AnalysisShare.audience == AnalysisAudience.PARTICIPATING_STATE.value,
        AnalysisShare.state_code.in_(current.allowed_states),
    )
    return stmt.where(AnalysisDataset.id.in_(shared))


def _load_dataset(db: Session, dataset_id: uuid.UUID, current: CurrentUser) -> AnalysisDataset:
    """Fetch a dataset the caller may see, else 404.

    404 rather than 403 on a dataset outside the caller's audience: telling a
    State analyst that a dataset exists but is not for them discloses the shape
    of the environment to someone who has no share.
    """
    dataset = db.scalar(
        _visible_datasets(select(AnalysisDataset).where(AnalysisDataset.id == dataset_id), current)
    )
    if dataset is None:
        raise NotFound("Analysis dataset")
    return dataset


def _version_for(db: Session, dataset: AnalysisDataset) -> AnalysisDatasetVersion | None:
    if dataset.current_version_id is None:
        return None
    return db.get(AnalysisDatasetVersion, dataset.current_version_id)


def _dataset_out(
    db: Session,
    dataset: AnalysisDataset,
    current: CurrentUser,
    scoped_counts: dict[uuid.UUID, int] | None = None,
) -> DatasetOut:
    """Serialize a dataset with its current version's facts.

    ``row_count`` is the number of rows THIS CALLER can see. For an unrestricted
    principal that is the version's own count; for a State-scoped one it is their
    slice. Reporting the version total to a State user would quote a national
    figure to someone entitled only to State-specific data — and would contradict
    the row table rendered right beside it.

    ``scoped_counts`` is the batch path: the list endpoint computes every
    dataset's scoped count in one grouped query and passes it in. A caller
    serializing a single dataset omits it and the count is resolved here, so no
    endpoint can accidentally fall back to the unscoped total by forgetting.
    """
    out = DatasetOut.model_validate(dataset)
    version = _version_for(db, dataset)
    if version is None:
        return out

    out.version_no = version.version_no
    out.materialized_at = version.materialized_at
    out.columns = list(version.columns or [])

    if scoped_counts is None:
        scoped_counts = _scoped_row_counts(db, [dataset], current)
    out.row_count = (
        version.row_count if scoped_counts is None else scoped_counts.get(version.id, 0)
    )
    return out


def _scoped_row_counts(
    db: Session, datasets: list[AnalysisDataset], current: CurrentUser
) -> dict[uuid.UUID, int] | None:
    """Per-version row counts within the caller's State scope, or None if
    unrestricted.

    One grouped query for the whole list rather than a count per dataset: this
    runs on the page-open path, and an N+1 against the shared database is a cost
    every analyst would pay on every visit.
    """
    if not _is_state_principal(current):
        return None
    version_ids = [d.current_version_id for d in datasets if d.current_version_id]
    if not version_ids:
        return {}
    rows = db.execute(
        select(AnalysisDatasetRow.version_id, func.count())
        .where(
            AnalysisDatasetRow.version_id.in_(version_ids),
            AnalysisDatasetRow.state_code.in_(current.allowed_states),
        )
        .group_by(AnalysisDatasetRow.version_id)
    )
    counts = {vid: count for vid, count in rows}
    # A version with no rows in scope is absent from the GROUP BY; report 0
    # rather than falling back to the unscoped total.
    return {vid: counts.get(vid, 0) for vid in version_ids}


# ===========================================================================
# Environments — "Manage the Analysis Environment"
# ===========================================================================
def _kick_refresh_if_stale(background: BackgroundTasks, db: Session) -> None:
    """Start a background refresh for any environment whose snapshot is stale.

    This is the refresh-on-open mechanism. The BRD asks for "regular refreshes
    (daily or hourly)", which implies a scheduler; this stack has none, and a
    "daily" refresh that in practice fired whenever someone happened to hit the
    API would be a claim the system could not keep. So the cadence is honoured as
    a STALENESS THRESHOLD instead: opening the Analysis Environment serves the
    stored snapshot immediately, and if it has aged past the cadence a refresh
    runs in the background so the next look is current.

    Deliberately fire-and-forget. ``BackgroundTasks`` runs after the response has
    been sent, so the analyst never waits on a materialization; and the refresh
    writes only to ``analysis_*`` tables, so a failure degrades to a stale
    snapshot plus a FAILED row in the run log — never to a failed page load.

    Concurrency is handled one level down: ``refresh_environment`` takes a
    PostgreSQL advisory lock, so ten analysts opening the page at once produce
    one refresh and nine no-ops.
    """
    if analysis_worker.stale_environments(db):
        background.add_task(analysis_worker.refresh_stale_environments)


def _environment_out(db: Session, environment: AnalysisEnvironment) -> EnvironmentOut:
    """Serialize an environment with the two facts the UI needs to be honest
    about what it is showing: whether the snapshot is stale, and whether a
    refresh is already running (so it reports progress instead of offering the
    button again)."""
    out = EnvironmentOut.model_validate(environment)
    now = dt.datetime.now(dt.timezone.utc)
    out.is_stale = (
        environment.status == "ACTIVE"
        and environment.refresh_cadence != RefreshCadence.MANUAL.value
        and (environment.next_refresh_due is None or environment.next_refresh_due <= now)
    )
    out.refresh_in_progress = analysis_worker.refresh_in_progress(db, environment.id)
    return out


@router.get("/analysis-environments", response_model=list[EnvironmentOut])
def list_environments(
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    current: CurrentUser = Depends(require("analysis_env:read")),
):
    """List Analysis Environments, refreshing any stale snapshot in the background."""
    _kick_refresh_if_stale(background, db)
    return [
        _environment_out(db, e)
        for e in db.scalars(select(AnalysisEnvironment).order_by(AnalysisEnvironment.name))
    ]


@router.post("/analysis-environments", response_model=EnvironmentOut, status_code=201)
def create_environment(
    body: EnvironmentIn,
    db: Session = Depends(get_db),
    current: CurrentUser = Depends(require("analysis_env:manage")),
):
    environment = AnalysisEnvironment(
        code=body.code.strip().upper(),
        name=body.name,
        description=body.description,
        study_id=body.study_id,
        refresh_cadence=body.refresh_cadence.value,
        created_by=current.id,
    )
    db.add(environment)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise BadRequest(f"An Analysis Environment with code '{body.code}' already exists")
    record_audit(
        db, actor=current, action="CREATE", entity_type="analysis_environment",
        entity_id=environment.id, after={"code": environment.code, "name": environment.name},
    )
    db.commit()
    db.refresh(environment)
    return environment


@router.get("/analysis-environments/{environment_id}", response_model=EnvironmentOut)
def get_environment(
    environment_id: uuid.UUID,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    current: CurrentUser = Depends(require("analysis_env:read")),
):
    """One environment. Also a page-open, so a stale snapshot refreshes behind it —
    the UI polls this endpoint while a refresh is in flight."""
    environment = db.get(AnalysisEnvironment, environment_id)
    if environment is None:
        raise NotFound("Analysis environment")
    _kick_refresh_if_stale(background, db)
    return _environment_out(db, environment)


@router.patch("/analysis-environments/{environment_id}", response_model=EnvironmentOut)
def update_environment(
    environment_id: uuid.UUID,
    body: EnvironmentUpdate,
    db: Session = Depends(get_db),
    current: CurrentUser = Depends(require("analysis_env:manage")),
):
    environment = db.get(AnalysisEnvironment, environment_id)
    if environment is None:
        raise NotFound("Analysis environment")
    before = {"status": environment.status, "refresh_cadence": environment.refresh_cadence}

    if body.name is not None:
        environment.name = body.name
    if body.description is not None:
        environment.description = body.description
    if body.status is not None:
        if body.status not in ("ACTIVE", "PAUSED", "ARCHIVED"):
            raise BadRequest("status must be ACTIVE, PAUSED or ARCHIVED")
        environment.status = body.status
    if body.refresh_cadence is not None:
        environment.refresh_cadence = body.refresh_cadence.value
        # Re-base the due date off the new cadence rather than leaving a due
        # date computed under the old one — switching DAILY -> HOURLY should
        # take effect now, not up to a day from now.
        environment.next_refresh_due = analysis_worker.next_due(
            environment.refresh_cadence, environment.last_refreshed_at
        )
    environment.updated_at = dt.datetime.now(dt.timezone.utc)

    record_audit(
        db, actor=current, action="UPDATE", entity_type="analysis_environment",
        entity_id=environment.id, before=before,
        after={"status": environment.status, "refresh_cadence": environment.refresh_cadence},
    )
    db.commit()
    db.refresh(environment)
    return environment


@router.post("/analysis-environments/{environment_id}/refresh")
def refresh_environment(
    environment_id: uuid.UUID,
    db: Session = Depends(get_db),
    current: CurrentUser = Depends(require("analysis_env:manage")),
):
    """"Refresh now" — re-materialize Aggregated Data into the environment.

    Runs synchronously, unlike the refresh-on-open path: someone who pressed a
    button is waiting for an answer, and returning row counts lets the UI show
    what changed rather than an optimistic "started…" that may have failed.

    May come back ``SKIPPED`` when a background refresh triggered by another
    analyst's page-open is already holding the advisory lock. That is reported as
    a normal outcome, not an error — the data *is* being refreshed, just not by
    this request, and a 4xx would wrongly suggest the user did something wrong.
    """
    environment = db.get(AnalysisEnvironment, environment_id)
    if environment is None:
        raise NotFound("Analysis environment")
    if environment.status != "ACTIVE":
        raise BadRequest(f"Environment is {environment.status}; only an ACTIVE environment refreshes")

    result = analysis_worker.refresh_environment(
        environment.id,
        trigger=RefreshTrigger.MANUAL.value,
        triggered_by=current.id,
        db=db,
    )
    # A skipped refresh performed no state change, so there is nothing to audit;
    # the run that actually holds the lock logs itself.
    if result.get("status") != "SKIPPED":
        record_audit(
            db, actor=current, action="REFRESH", entity_type="analysis_environment",
            entity_id=environment.id, after=result,
        )
    db.commit()
    return result


@router.get("/analysis-environments/{environment_id}/refresh-runs", response_model=list[RefreshRunOut])
def list_refresh_runs(
    environment_id: uuid.UUID,
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current: CurrentUser = Depends(require("analysis_env:read")),
):
    """The refresh history — so a stale dataset can be told apart from a broken one."""
    return list(
        db.scalars(
            select(AnalysisRefreshRun)
            .where(AnalysisRefreshRun.environment_id == environment_id)
            .order_by(AnalysisRefreshRun.started_at.desc())
            .limit(limit)
        )
    )


# ===========================================================================
# Datasets — "create new data/views of data derived from CCFP Aggregated Data"
# ===========================================================================
@router.get("/analysis-datasets/fields", response_model=dict)
def dataset_fields(current: CurrentUser = Depends(require("analysis_env:read"))):
    """The allow-listed dimensions/measures/operators a definition may name, so
    the builder UI renders from the server's vocabulary instead of its own copy."""
    return {
        "dimensions": sorted(analysis_worker.DIMENSIONS),
        "measures": sorted(analysis_worker.MEASURES),
        "filter_columns": sorted(analysis_worker.FILTER_COLUMNS),
        "operators": sorted(analysis_worker.FILTER_OPERATORS),
        "pii_levels": [p.value for p in AnalysisPiiLevel],
        "audiences": [a.value for a in AnalysisAudience],
        "cadences": [c.value for c in RefreshCadence],
    }


@router.get("/analysis-datasets", response_model=list[DatasetOut])
def list_datasets(
    background: BackgroundTasks,
    environment_id: uuid.UUID | None = None,
    db: Session = Depends(get_db),
    current: CurrentUser = Depends(require("analysis_env:read")),
):
    """List datasets visible to the caller, serving the stored snapshot.

    Also treated as a page-open for refresh purposes. The environment list is not
    the only way in — a deep link straight to a dataset loads this first — so the
    staleness check rides here too rather than on one privileged entry point.
    """
    _kick_refresh_if_stale(background, db)
    stmt = select(AnalysisDataset)
    if environment_id is not None:
        stmt = stmt.where(AnalysisDataset.environment_id == environment_id)
    stmt = _visible_datasets(stmt, current).order_by(AnalysisDataset.name)
    visible = list(db.scalars(stmt))
    scoped = _scoped_row_counts(db, visible, current)
    return [_dataset_out(db, d, current, scoped) for d in visible]


@router.post("/analysis-datasets", response_model=DatasetOut, status_code=201)
def create_dataset(
    body: DatasetIn,
    db: Session = Depends(get_db),
    current: CurrentUser = Depends(require("analysis_env:dataset")),
):
    """Create a derived view in the environment (CCFP Project Team, CRUD).

    The definition is validated here rather than only at refresh time so a
    malformed spec is a 400 the author sees, not a failed background run
    discovered later in the log.
    """
    environment = db.get(AnalysisEnvironment, body.environment_id)
    if environment is None:
        raise NotFound("Analysis environment")

    try:
        definition = analysis_worker.validate_definition(body.definition)
    except analysis_worker.DefinitionError as exc:
        raise BadRequest(str(exc))

    dataset = AnalysisDataset(
        environment_id=environment.id,
        code=body.code,
        name=body.name,
        description=body.description,
        kind=body.kind.value,
        definition=definition,
        pii_level=body.pii_level.value,
        is_state_partitioned=analysis_worker.is_state_partitioned(definition),
        created_by=current.id,
    )
    db.add(dataset)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise BadRequest(f"A dataset with code '{body.code}' already exists in this environment")

    # Materialize immediately: a dataset that exists but holds nothing until the
    # next scheduled refresh looks broken to the person who just created it.
    try:
        analysis_worker.materialize_dataset(dataset.id, db=db)
    except Exception as exc:  # noqa: BLE001 — report, don't lose the definition
        db.rollback()
        raise BadRequest(f"Dataset definition could not be materialized: {exc}")

    record_audit(
        db, actor=current, action="CREATE", entity_type="analysis_dataset",
        entity_id=dataset.id,
        after={"code": dataset.code, "kind": dataset.kind, "pii_level": dataset.pii_level},
    )
    db.commit()
    db.refresh(dataset)
    return _dataset_out(db, dataset, current)


@router.get("/analysis-datasets/{dataset_id}", response_model=DatasetOut)
def get_dataset(
    dataset_id: uuid.UUID,
    db: Session = Depends(get_db),
    current: CurrentUser = Depends(require("analysis_env:read")),
):
    return _dataset_out(db, _load_dataset(db, dataset_id, current), current)


@router.patch("/analysis-datasets/{dataset_id}", response_model=DatasetOut)
def update_dataset(
    dataset_id: uuid.UUID,
    body: DatasetUpdate,
    db: Session = Depends(get_db),
    current: CurrentUser = Depends(require("analysis_env:dataset")),
):
    dataset = _load_dataset(db, dataset_id, current)
    before = {"pii_level": dataset.pii_level, "status": dataset.status}

    if body.name is not None:
        dataset.name = body.name
    if body.description is not None:
        dataset.description = body.description
    if body.status is not None:
        if body.status not in ("ACTIVE", "ARCHIVED"):
            raise BadRequest("status must be ACTIVE or ARCHIVED")
        dataset.status = body.status
    if body.pii_level is not None:
        dataset.pii_level = body.pii_level.value

    remateralize = False
    if body.definition is not None:
        try:
            definition = analysis_worker.validate_definition(body.definition)
        except analysis_worker.DefinitionError as exc:
            raise BadRequest(str(exc))
        dataset.definition = definition
        dataset.is_state_partitioned = analysis_worker.is_state_partitioned(definition)
        remateralize = True

    dataset.updated_at = dt.datetime.now(dt.timezone.utc)

    # Raising sensitivity or dropping State partitioning under a live share is
    # refused by the database trigger; translate that into a 400 the caller can
    # act on rather than a 500.
    try:
        db.flush()
    except DBAPIError as exc:
        db.rollback()
        raise BadRequest(_pg_message(exc))

    if remateralize:
        try:
            analysis_worker.materialize_dataset(dataset.id, db=db)
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            raise BadRequest(f"Updated definition could not be materialized: {exc}")

    record_audit(
        db, actor=current, action="UPDATE", entity_type="analysis_dataset",
        entity_id=dataset.id, before=before,
        after={"pii_level": dataset.pii_level, "status": dataset.status},
    )
    db.commit()
    db.refresh(dataset)
    return _dataset_out(db, dataset, current)


@router.delete("/analysis-datasets/{dataset_id}", status_code=204)
def delete_dataset(
    dataset_id: uuid.UUID,
    db: Session = Depends(get_db),
    current: CurrentUser = Depends(require("analysis_env:dataset")),
):
    dataset = _load_dataset(db, dataset_id, current)
    record_audit(
        db, actor=current, action="DELETE", entity_type="analysis_dataset",
        entity_id=dataset.id, before={"code": dataset.code, "name": dataset.name},
    )
    # Versions, rows and shares cascade. Nothing operational is touched: the
    # environment only ever held a copy.
    db.delete(dataset)
    db.commit()
    return Response(status_code=204)


@router.post("/analysis-datasets/{dataset_id}/refresh", response_model=DatasetOut)
def refresh_dataset(
    dataset_id: uuid.UUID,
    db: Session = Depends(get_db),
    current: CurrentUser = Depends(require("analysis_env:manage", "analysis_env:dataset")),
):
    """Re-materialize a single dataset from the current Aggregated Data."""
    dataset = _load_dataset(db, dataset_id, current)
    try:
        analysis_worker.materialize_dataset(dataset.id, db=db)
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        raise BadRequest(f"Refresh failed: {exc}")
    record_audit(
        db, actor=current, action="REFRESH", entity_type="analysis_dataset",
        entity_id=dataset.id,
    )
    db.commit()
    db.refresh(dataset)
    return _dataset_out(db, dataset, current)


# ===========================================================================
# Analyze — rows, statistics, export
# ===========================================================================
def _row_query(dataset: AnalysisDataset, version: AnalysisDatasetVersion, current: CurrentUser):
    """Base row SELECT for a dataset version, State-filtered where required."""
    stmt = select(AnalysisDatasetRow).where(AnalysisDatasetRow.version_id == version.id)
    if _is_state_principal(current):
        # A State principal sees only its own States' rows. NULL state_code rows
        # (national aggregates) are excluded by ``IN`` semantics, which is the
        # intended outcome: those rows are not State-specific and the BRD limits
        # State users to State-specific data.
        stmt = stmt.where(AnalysisDatasetRow.state_code.in_(current.allowed_states))
    return stmt


@router.get("/analysis-datasets/{dataset_id}/rows", response_model=RowsOut)
def dataset_rows(
    dataset_id: uuid.UUID,
    limit: int = Query(DEFAULT_ROW_LIMIT, ge=1, le=MAX_ROW_LIMIT),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current: CurrentUser = Depends(require("analysis_env:read")),
):
    """Read the materialized rows of a dataset's current version."""
    dataset = _load_dataset(db, dataset_id, current)
    version = _version_for(db, dataset)
    if version is None:
        # Honest empty: the dataset has never been refreshed, which is different
        # from a refresh that legitimately produced no rows.
        return RowsOut(
            dataset_id=dataset.id, columns=[], rows=[], total=0,
            limit=limit, offset=offset, state_scoped=_is_state_principal(current),
        )

    base = _row_query(dataset, version, current)
    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0
    rows = list(
        db.scalars(base.order_by(AnalysisDatasetRow.row_index).offset(offset).limit(limit))
    )
    return RowsOut(
        dataset_id=dataset.id,
        version_no=version.version_no,
        materialized_at=version.materialized_at,
        columns=list(version.columns or []),
        rows=[r.data for r in rows],
        total=total,
        limit=limit,
        offset=offset,
        state_scoped=_is_state_principal(current),
    )


@router.get("/analysis-datasets/{dataset_id}/statistics", response_model=StatisticsOut)
def dataset_statistics(
    dataset_id: uuid.UUID,
    column: str = Query(..., min_length=1),
    db: Session = Depends(get_db),
    current: CurrentUser = Depends(require("analysis_env:read")),
):
    """Descriptive statistics for one numeric column of Analysis Environment data.

    Implements the BRD's "statistical summaries: central tendency and dispersion,
    data distributions" over the environment's own data. The column name is
    checked against the version's recorded column list before it reaches SQL, so
    the JSONB key lookup cannot be steered somewhere it was not meant to go.
    """
    dataset = _load_dataset(db, dataset_id, current)
    version = _version_for(db, dataset)
    if version is None:
        raise BadRequest("Dataset has not been refreshed yet — no data to summarize")

    columns = list(version.columns or [])
    if column not in columns:
        raise BadRequest(f"Unknown column '{column}'. Available: {columns}")

    # Scope clause mirrors _row_query; expressed in raw SQL because the
    # percentile aggregates below have no clean ORM spelling.
    params: dict[str, Any] = {"version_id": str(version.id), "col": column}
    scope = ""
    if _is_state_principal(current):
        scope = " AND state_code = ANY(:states)"
        params["states"] = list(current.allowed_states)

    # `~ '^-?[0-9]+(\.[0-9]+)?$'` filters to values that are actually numeric, so
    # a text column returns n=0 rather than raising a cast error mid-aggregate.
    numeric_cte = f"""
        SELECT (data ->> :col)::numeric AS v
          FROM analysis_dataset_rows
         WHERE version_id = :version_id{scope}
           AND data ->> :col ~ '^-?[0-9]+(\\.[0-9]+)?$'
    """

    stats = db.execute(
        text(
            f"""
            WITH vals AS ({numeric_cte})
            SELECT count(*)                                             AS n,
                   avg(v)                                               AS mean,
                   percentile_cont(0.5)  WITHIN GROUP (ORDER BY v)      AS median,
                   stddev_samp(v)                                       AS stddev,
                   var_samp(v)                                          AS variance,
                   min(v)                                               AS minimum,
                   max(v)                                               AS maximum,
                   percentile_cont(0.25) WITHIN GROUP (ORDER BY v)      AS p25,
                   percentile_cont(0.75) WITHIN GROUP (ORDER BY v)      AS p75,
                   sum(v)                                               AS total
              FROM vals
            """
        ),
        params,
    ).mappings().one()

    def _f(value: Any) -> float | None:
        return None if value is None else float(value)

    out = StatisticsOut(
        dataset_id=dataset.id,
        column=column,
        version_no=version.version_no,
        materialized_at=version.materialized_at,
        n=int(stats["n"] or 0),
        mean=_f(stats["mean"]),
        median=_f(stats["median"]),
        stddev=_f(stats["stddev"]),
        variance=_f(stats["variance"]),
        minimum=_f(stats["minimum"]),
        maximum=_f(stats["maximum"]),
        p25=_f(stats["p25"]),
        p75=_f(stats["p75"]),
        total=_f(stats["total"]),
    )
    if out.p25 is not None and out.p75 is not None:
        out.iqr = out.p75 - out.p25

    # Distribution. width_bucket needs a non-degenerate range; when every value
    # is identical the histogram is one full bin, which is the truthful picture
    # rather than an error.
    if out.n and out.minimum is not None and out.maximum is not None:
        if out.maximum > out.minimum:
            buckets = db.execute(
                text(
                    f"""
                    WITH vals AS ({numeric_cte})
                    SELECT width_bucket(v, :lo, :hi, :bins) AS bucket, count(*) AS c
                      FROM vals
                     GROUP BY bucket
                     ORDER BY bucket
                    """
                ),
                {**params, "lo": out.minimum, "hi": out.maximum, "bins": HISTOGRAM_BINS},
            ).mappings().all()
            width = (out.maximum - out.minimum) / HISTOGRAM_BINS
            counts = {int(b["bucket"]): int(b["c"]) for b in buckets}
            out.histogram = [
                {
                    "bin": i,
                    "lower": round(out.minimum + (i - 1) * width, 4),
                    "upper": round(out.minimum + i * width, 4),
                    # width_bucket puts the maximum value in bin bins+1; fold it
                    # into the top bin so the counts sum to n.
                    "count": counts.get(i, 0) + (counts.get(HISTOGRAM_BINS + 1, 0) if i == HISTOGRAM_BINS else 0),
                }
                for i in range(1, HISTOGRAM_BINS + 1)
            ]
        else:
            out.histogram = [
                {"bin": 1, "lower": out.minimum, "upper": out.maximum, "count": out.n}
            ]

    return out


@router.get("/analysis-datasets/{dataset_id}/export")
def export_dataset(
    dataset_id: uuid.UUID,
    format: str = Query("csv", pattern="^(csv|json)$"),
    db: Session = Depends(get_db),
    current: CurrentUser = Depends(require("analysis_env:read")),
):
    """Export a dataset version.

    "Data should be exportable to any statistical summary or visualization/report
    builder tools" (BRD p. 15) — CSV for Tableau/ArcGIS/SAS/R, JSON for Python.
    The same audience filtering as ``/rows`` applies, so an export is never a way
    around the State scope shown in the UI.
    """
    dataset = _load_dataset(db, dataset_id, current)
    version = _version_for(db, dataset)
    if version is None:
        raise BadRequest("Dataset has not been refreshed yet — nothing to export")

    columns = list(version.columns or [])
    rows = list(
        db.scalars(_row_query(dataset, version, current).order_by(AnalysisDatasetRow.row_index))
    )
    stamp = version.materialized_at.strftime("%Y%m%dT%H%M%SZ") if version.materialized_at else "unversioned"
    base_name = f"{dataset.code.lower()}_v{version.version_no}_{stamp}"

    record_audit(
        db, actor=current, action="EXPORT", entity_type="analysis_dataset",
        entity_id=dataset.id,
        after={"format": format, "version_no": version.version_no, "rows": len(rows)},
    )
    db.commit()

    if format == "json":
        payload = {
            "dataset": dataset.code,
            "name": dataset.name,
            "version_no": version.version_no,
            "materialized_at": version.materialized_at.isoformat() if version.materialized_at else None,
            "columns": columns,
            "rows": [r.data for r in rows],
        }
        return Response(
            content=json.dumps(payload, indent=2),
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="{base_name}.json"'},
        )

    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow({c: row.data.get(c) for c in columns})
    return Response(
        content=buffer.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{base_name}.csv"'},
    )


# ===========================================================================
# Shares — the four BRD audience tiers
# ===========================================================================
def _pg_message(exc: DBAPIError) -> str:
    """Pull the PostgreSQL RAISE message out of a driver error.

    The share guards live in database triggers so they hold for every writer.
    That means the useful text is inside the driver exception, and without this
    the caller would get a wall of SQL instead of "dataset carries PII and
    cannot be shared to audience PUBLIC".
    """
    original = getattr(exc, "orig", None)
    diag = getattr(original, "diag", None)
    message = getattr(diag, "message_primary", None)
    if message:
        return message
    return str(original or exc).split("\n")[0]


class EmbedIn(BaseModel):
    """Optional row filters to pin an embedded dashboard to a slice."""

    filters: dict[str, str] = Field(default_factory=dict)


@router.post("/analysis-datasets/{dataset_id}/embed")
def create_embed_link(
    dataset_id: uuid.UUID,
    body: EmbedIn,
    db: Session = Depends(get_db),
    # Same gate as publishing a dashboard: the BRD (p.15) gives "create and share
    # dashboards, visualizations, reports, and tables" to the CCFP Project Team
    # and the CCFP Super User, and report:share is what both already hold for it.
    current: CurrentUser = Depends(require("report:share")),
):
    """Mint an embeddable link for a publicly shared dataset (BRD p.15).

    "Provide ability to embed or link dashboards to secure portals and public
    websites (with appropriate data filters)."

    The link carries a signed token naming the dataset and the filters, and
    nothing else. It is not a capability: /public/embed re-checks the live PUBLIC
    share on every request, so this endpoint cannot publish anything — it can
    only produce a pointer to something the CCFP Database Administrator has
    already shared publicly. Refusing to mint for an unshared dataset is a
    usability guard, not the security boundary.
    """
    dataset = _load_dataset(db, dataset_id, current)

    public_share = db.scalar(
        select(AnalysisShare).where(
            AnalysisShare.dataset_id == dataset.id,
            AnalysisShare.audience == AnalysisAudience.PUBLIC.value,
            AnalysisShare.status == "ACTIVE",
        )
    )
    if public_share is None:
        raise BadRequest(
            "Dataset has no active PUBLIC share; the CCFP Database Administrator "
            "must share it publicly before it can be embedded"
        )

    now = dt.datetime.now(dt.timezone.utc)
    expires = now + dt.timedelta(minutes=settings.signed_url_ttl_minutes)
    token = jwt.encode(
        {
            "kind": "embed",
            "dataset_id": str(dataset.id),
            "filters": body.filters,
            "exp": expires,
        },
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )
    record_audit(
        db, actor=current, action="EMBED", entity_type="analysis_dataset", entity_id=dataset.id,
        after={"filters": body.filters},
    )
    db.commit()
    return {
        "dataset_id": str(dataset.id),
        "dataset": dataset.code,
        "embed_url": f"{settings.api_v1_prefix}/public/embed?token={token}",
        "filters": body.filters,
        "expires_at": expires.isoformat(),
        # The host page can re-mint from this without holding anything secret.
        "public_rows_url": f"{settings.api_v1_prefix}/public/analysis-datasets/{dataset.id}/rows",
    }


@router.get("/analysis-datasets/{dataset_id}/shares", response_model=list[ShareOut])
def list_shares(
    dataset_id: uuid.UUID,
    db: Session = Depends(get_db),
    current: CurrentUser = Depends(require("analysis_env:read")),
):
    dataset = _load_dataset(db, dataset_id, current)
    return list(
        db.scalars(
            select(AnalysisShare)
            .where(AnalysisShare.dataset_id == dataset.id)
            .order_by(AnalysisShare.audience, AnalysisShare.state_code)
        )
    )


@router.post("/analysis-datasets/{dataset_id}/shares", response_model=ShareOut, status_code=201)
def create_share(
    dataset_id: uuid.UUID,
    body: ShareIn,
    db: Session = Depends(get_db),
    current: CurrentUser = Depends(require("analysis_env:share")),
):
    """Share a dataset with one of the BRD's four audiences.

    The PII and State-partitioning rules are enforced by database triggers rather
    than here, so they cannot be sidestepped by a seed file or a future writer;
    this handler's job is to turn a refusal into a readable 400.
    """
    dataset = _load_dataset(db, dataset_id, current)

    state_code = (body.state_code or "").strip().upper() or None
    if body.audience == AnalysisAudience.PARTICIPATING_STATE and not state_code:
        raise BadRequest("A participating-State share must name a State")
    if body.audience != AnalysisAudience.PARTICIPATING_STATE and state_code:
        raise BadRequest(f"state_code applies only to a {AnalysisAudience.PARTICIPATING_STATE.value} share")

    share = AnalysisShare(
        dataset_id=dataset.id,
        audience=body.audience.value,
        state_code=state_code,
        refresh_cadence=body.refresh_cadence.value,
        note=body.note,
        shared_by=current.id,
    )
    db.add(share)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise BadRequest(_pg_message(exc))
    except DBAPIError as exc:
        db.rollback()
        raise BadRequest(_pg_message(exc))

    record_audit(
        db, actor=current, action="SHARE", entity_type="analysis_dataset",
        entity_id=dataset.id,
        after={"audience": share.audience, "state_code": share.state_code},
    )
    db.commit()
    db.refresh(share)
    return share


@router.delete("/analysis-shares/{share_id}", response_model=ShareOut)
def revoke_share(
    share_id: uuid.UUID,
    db: Session = Depends(get_db),
    current: CurrentUser = Depends(require("analysis_env:share")),
):
    """Revoke a share. Kept as a status change rather than a delete so the audit
    trail retains that the data *was* shared, and with whom."""
    share = db.get(AnalysisShare, share_id)
    if share is None:
        raise NotFound("Analysis share")
    if share.status == AnalysisShareStatus.REVOKED.value:
        return share
    share.status = AnalysisShareStatus.REVOKED.value
    share.revoked_at = dt.datetime.now(dt.timezone.utc)
    record_audit(
        db, actor=current, action="REVOKE", entity_type="analysis_dataset",
        entity_id=share.dataset_id,
        before={"audience": share.audience, "state_code": share.state_code},
    )
    db.commit()
    db.refresh(share)
    return share
