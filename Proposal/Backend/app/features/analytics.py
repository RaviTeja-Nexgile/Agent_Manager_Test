"""Analytics: dashboards and whitelisted parameterized queries (documentation §12.6, §8.9)."""
from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ValidationError, field_validator
from sqlalchemy import Date, func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.errors import BadRequest, NotFound
from app.core.permissions import require, scope_crash_query, scope_study_query
from app.core.security import CurrentUser
from app.features.reports import ReportOut, _visible_filter
from app.models import Crash, DataQualityResult, DataQualityRule, Report

router = APIRouter(prefix="/analytics", tags=["analytics"])

# Visualization kinds a dashboard panel may request. Whitelisted so a stored
# definition can never reference an arbitrary renderer (documentation §8.9).
ALLOWED_PANEL_VIZ = {"bars", "donut", "line", "table"}

# Whitelisted analytical queries — no free-form SQL is accepted (documentation §14).
ALLOWED_QUERIES = {
    "crash_counts_by_state": "Crash counts grouped by State",
    "crash_counts_by_phase": "Crash counts grouped by lifecycle phase",
    "fatalities_by_state": "Sum of fatalities grouped by State",
    "qc_failure_summary": "Count of QC failures grouped by rule",
}

# ---------------------------------------------------------------------------
# Constrained ad-hoc query builder (documentation §8.9 / §14, ANAL-6).
#
# Every group-by column, filter column, operator, and aggregation is validated
# against these server-side allow-lists and the statement is assembled from
# mapped SQLAlchemy column/func objects — never from caller-supplied strings.
# Low-cardinality dimensions only, so a GROUP BY cannot fan out unbounded.
# ---------------------------------------------------------------------------
GROUPABLE_COLUMNS = {
    "state_code": Crash.state_code,
    "county": Crash.county,
    "lifecycle_phase": Crash.lifecycle_phase,
    "study_id": Crash.study_id,
    # Time dimensions (GAP-BRD-11). `crash_date` was filterable but not
    # groupable, so "crashes over time" — the BRD's time-series requirement —
    # could not be expressed at all through the builder. Truncation happens in
    # SQL via date_trunc so the grouping key is a real date, not a formatted
    # string, and therefore sorts chronologically rather than alphabetically
    # (the reason "April" must not become a text key).
    # `.cast(Date)` is load-bearing. date_trunc returns TIMESTAMPTZ, which
    # serialises with the SERVER's UTC offset (e.g. 2026-01-01T00:00:00+01:00).
    # A client formatting that in UTC shifts it back an hour, so January 2026
    # renders as "Dec 25" — every period on the trend chart mislabelled, and
    # silently, because the shape of the data still looks right. Casting to DATE
    # drops the time and offset entirely: the wire value is "2026-01-01", which
    # means the same day in every timezone.
    "crash_date": Crash.crash_date,
    "crash_month": func.date_trunc("month", Crash.crash_date).cast(Date),
    "crash_quarter": func.date_trunc("quarter", Crash.crash_date).cast(Date),
    "crash_year": func.date_trunc("year", Crash.crash_date).cast(Date),
}
FILTERABLE_COLUMNS = {
    **GROUPABLE_COLUMNS,
    "num_fatalities": Crash.num_fatalities,
    "crash_date": Crash.crash_date,
}
AGGREGATIONS = {
    "count": func.count(),
    "sum_fatalities": func.coalesce(func.sum(Crash.num_fatalities), 0),
    "sum_vehicles": func.coalesce(func.sum(Crash.num_vehicles), 0),
    "avg_fatalities": func.avg(Crash.num_fatalities),
}
# Comparators mapped to bound-method builders so the SQL is composed from
# expression objects, never string-interpolated.
FILTER_OPERATORS = {
    "eq": lambda col, val: col == val,
    "neq": lambda col, val: col != val,
    "gte": lambda col, val: col >= val,
    "lte": lambda col, val: col <= val,
}


class QueryRequest(BaseModel):
    query_name: str
    study_id: str | None = None


class QueryResult(BaseModel):
    query_name: str
    columns: list[str]
    rows: list[dict[str, Any]]


class FilterClause(BaseModel):
    column: str
    op: str
    value: str | int


class QueryBuilderRequest(BaseModel):
    group_by: str
    aggregation: str = "count"
    filters: list[FilterClause] = []
    study_id: str | None = None


# ---------------------------------------------------------------------------
# Composable dashboard / panel schema (documentation §8.9, ANAL-7).
#
# A DASHBOARD report's free-form ``definition`` JSONB is validated against this
# schema on render. Every panel may only declare a whitelisted ``viz`` and may
# only bind to a whitelisted ``query_name`` (the same server-side ALLOWED_QUERIES
# allow-list the canned queries use) — never free-form SQL or an arbitrary
# renderer. The renderer executes each panel's query through the existing,
# State-scoped POST /analytics/queries endpoint; nothing is executed here.
# ---------------------------------------------------------------------------
class PanelQuery(BaseModel):
    query_name: str
    study_id: str | None = None

    @field_validator("query_name")
    @classmethod
    def _query_name_allowed(cls, v: str) -> str:
        if v not in ALLOWED_QUERIES:
            raise ValueError(f"Unknown query_name. Allowed: {sorted(ALLOWED_QUERIES)}")
        return v


class PanelDef(BaseModel):
    id: str
    title: str
    viz: str
    query: PanelQuery
    labelKey: str | None = None
    valueKey: str | None = None

    @field_validator("viz")
    @classmethod
    def _viz_allowed(cls, v: str) -> str:
        if v not in ALLOWED_PANEL_VIZ:
            raise ValueError(f"Unknown viz. Allowed: {sorted(ALLOWED_PANEL_VIZ)}")
        return v


class DashboardDefinition(BaseModel):
    layout: str = "grid"
    panels: list[PanelDef] = []


class DashboardOut(ReportOut):
    """A single DASHBOARD report with its definition re-emitted as a validated
    ``DashboardDefinition`` so the renderer can trust the panel shape."""

    definition: DashboardDefinition


@router.get("/dashboards", response_model=list[ReportOut])
def list_dashboards(db: Session = Depends(get_db), current: CurrentUser = Depends(require("analytics:dashboard", "report:read"))):
    stmt = select(Report).where(Report.report_type == "DASHBOARD", _visible_filter(current)).order_by(Report.name)
    return list(db.scalars(stmt))


@router.get("/dashboards/{report_id}", response_model=DashboardOut)
def get_dashboard(
    report_id: uuid.UUID,
    db: Session = Depends(get_db),
    current: CurrentUser = Depends(require("analytics:dashboard", "report:read")),
):
    """Return one DASHBOARD report with its panel definition validated against
    the whitelisted panel schema (documentation §8.9, ANAL-7).

    Visibility is layered on top of the permission gate: the report is loaded
    through ``_visible_filter`` (a caller who may not see it gets 404, no
    existence disclosure), and only DASHBOARD reports resolve here. The stored
    ``definition`` is re-validated so a panel can only reference a whitelisted
    ``viz`` and a known, scoped ``query_name`` — a malformed/unsafe definition is
    a 400, never silently rendered. The panel queries themselves are not executed
    here; the renderer calls the existing State-scoped POST /analytics/queries.
    """
    report = db.scalar(
        select(Report).where(
            Report.id == report_id,
            Report.report_type == "DASHBOARD",
            _visible_filter(current),
        )
    )
    if report is None:
        raise NotFound("Dashboard")
    raw = report.definition if isinstance(report.definition, dict) else {}
    try:
        definition = DashboardDefinition.model_validate(raw)
    except ValidationError as exc:
        raise BadRequest(f"Invalid dashboard definition: {exc.errors()}")
    # Build the response from the report attributes plus the *validated*,
    # normalized definition so the renderer always receives a trusted panel
    # shape. Constructed field-by-field (not model_validate(report)) so a
    # NULL/legacy ``definition`` never fails coercion — it serialises as empty
    # panels instead.
    base = ReportOut.model_validate(report).model_dump()
    base["definition"] = definition
    return DashboardOut(**base)


@router.get("/queries", response_model=dict)
def list_queries(current: CurrentUser = Depends(require("analytics:query"))):
    return {"available_queries": ALLOWED_QUERIES}


@router.post("/queries", response_model=QueryResult)
def run_query(body: QueryRequest, db: Session = Depends(get_db), current: CurrentUser = Depends(require("analytics:query"))):
    if body.query_name not in ALLOWED_QUERIES:
        raise BadRequest(f"Unknown query. Allowed: {sorted(ALLOWED_QUERIES)}")

    def scoped_crash_base():
        # AUTH-2: study scope is additive to the existing State scope.
        return scope_study_query(scope_crash_query(select(Crash), current), current)

    if body.query_name == "crash_counts_by_state":
        sub = scoped_crash_base().subquery()
        stmt = select(sub.c.state_code, func.count()).group_by(sub.c.state_code).order_by(sub.c.state_code)
        rows = [{"state_code": s, "count": c} for s, c in db.execute(stmt)]
        return QueryResult(query_name=body.query_name, columns=["state_code", "count"], rows=rows)

    if body.query_name == "crash_counts_by_phase":
        sub = scoped_crash_base().subquery()
        stmt = select(sub.c.lifecycle_phase, func.count()).group_by(sub.c.lifecycle_phase)
        rows = [{"lifecycle_phase": p, "count": c} for p, c in db.execute(stmt)]
        return QueryResult(query_name=body.query_name, columns=["lifecycle_phase", "count"], rows=rows)

    if body.query_name == "fatalities_by_state":
        sub = scoped_crash_base().subquery()
        stmt = select(sub.c.state_code, func.coalesce(func.sum(sub.c.num_fatalities), 0)).group_by(sub.c.state_code).order_by(sub.c.state_code)
        rows = [{"state_code": s, "fatalities": int(f)} for s, f in db.execute(stmt)]
        return QueryResult(query_name=body.query_name, columns=["state_code", "fatalities"], rows=rows)

    # qc_failure_summary
    crash_sub = scoped_crash_base().subquery()
    stmt = (
        select(DataQualityRule.code, func.count())
        .join(DataQualityResult, DataQualityResult.rule_id == DataQualityRule.id)
        .join(crash_sub, crash_sub.c.id == DataQualityResult.crash_id)
        .where(DataQualityResult.status == "FAIL")
        .group_by(DataQualityRule.code)
        .order_by(DataQualityRule.code)
    )
    rows = [{"rule_code": code, "failures": c} for code, c in db.execute(stmt)]
    return QueryResult(query_name=body.query_name, columns=["rule_code", "failures"], rows=rows)


@router.get("/query-builder/fields", response_model=dict)
def query_builder_fields(current: CurrentUser = Depends(require("analytics:query"))):
    """Expose the allow-listed dimensions/aggregations/operators so the UI can
    render the builder form without hardcoding the lists (documentation §8.9)."""
    return {
        "group_by": sorted(GROUPABLE_COLUMNS),
        "aggregations": sorted(AGGREGATIONS),
        "filter_columns": sorted(FILTERABLE_COLUMNS),
        "operators": sorted(FILTER_OPERATORS),
    }


# --------------------------------------------------------------------------- geospatial
class GeoPoint(BaseModel):
    """One plottable crash (GAP-BRD-11).

    ``crashes.latitude``/``longitude`` were captured and editable but rendered
    only as text fields and never plotted, so the BRD's mapping requirement had
    no data path at all. Deliberately narrow: identifier, position, State and
    fatality count — enough to plot and label, and nothing that would turn a map
    into a disclosure surface.
    """

    id: uuid.UUID
    ccfp_identifier: str
    latitude: float
    longitude: float
    state_code: str | None
    num_fatalities: int | None
    lifecycle_phase: str


class GeoResponse(BaseModel):
    points: list[GeoPoint]
    # Points carrying no coordinates are reported rather than silently dropped:
    # a map showing 12 of 39 crashes without saying so reads as "12 crashes".
    total_in_scope: int
    plotted: int
    missing_coordinates: int


@router.get("/geo/crashes", response_model=GeoResponse)
def geo_crashes(
    study_id: str | None = None,
    limit: int = 2000,
    db: Session = Depends(get_db),
    current: CurrentUser = Depends(require("analytics:query")),
):
    """Crash positions for the map (GAP-BRD-11).

    Scope is enforced through the same ``scope_crash_query`` /
    ``scope_study_query`` pair every other analytics read uses — a map must not
    become a way around State scoping, so a Kansas analyst plots Kansas crashes
    and nothing else.

    ``limit`` bounds the payload; the count of everything in scope is returned
    alongside so the UI can say when it is showing a subset rather than
    presenting a truncated map as the whole picture.
    """
    limit = max(1, min(limit, 5000))
    base = scope_study_query(scope_crash_query(select(Crash), current), current)
    if study_id:
        base = base.where(Crash.study_id == study_id)

    total = db.scalar(
        scope_study_query(
            scope_crash_query(select(func.count()).select_from(Crash), current), current
        ).where(Crash.study_id == study_id) if study_id else
        scope_study_query(
            scope_crash_query(select(func.count()).select_from(Crash), current), current
        )
    ) or 0

    rows = list(
        db.scalars(
            base.where(Crash.latitude.is_not(None), Crash.longitude.is_not(None))
            .order_by(Crash.crash_date.desc().nulls_last())
            .limit(limit)
        )
    )
    return GeoResponse(
        points=[
            GeoPoint(
                id=c.id, ccfp_identifier=c.ccfp_identifier,
                latitude=float(c.latitude), longitude=float(c.longitude),
                state_code=c.state_code, num_fatalities=c.num_fatalities,
                lifecycle_phase=c.lifecycle_phase,
            )
            for c in rows
        ],
        total_in_scope=total,
        plotted=len(rows),
        missing_coordinates=max(0, total - len(rows)),
    )


@router.post("/query-builder", response_model=QueryResult)
def run_query_builder(
    body: QueryBuilderRequest,
    db: Session = Depends(get_db),
    current: CurrentUser = Depends(require("analytics:query")),
):
    """Run a constrained ad-hoc aggregation (group-by + aggregation + filters)
    over whitelisted crash columns. No free-form SQL is accepted: every field,
    operator, and aggregation is validated against a server-side allow-list and
    the statement is built from mapped SQLAlchemy expression objects
    (documentation §8.9, §14)."""
    if body.group_by not in GROUPABLE_COLUMNS:
        raise BadRequest(f"Unknown group_by. Allowed: {sorted(GROUPABLE_COLUMNS)}")
    if body.aggregation not in AGGREGATIONS:
        raise BadRequest(f"Unknown aggregation. Allowed: {sorted(AGGREGATIONS)}")
    for f in body.filters:
        if f.column not in FILTERABLE_COLUMNS:
            raise BadRequest(f"Unknown filter column. Allowed: {sorted(FILTERABLE_COLUMNS)}")
        if f.op not in FILTER_OPERATORS:
            raise BadRequest(f"Unknown filter op. Allowed: {sorted(FILTER_OPERATORS)}")

    group_col = GROUPABLE_COLUMNS[body.group_by].label(body.group_by)
    agg_expr = AGGREGATIONS[body.aggregation].label(body.aggregation)

    # State scope is enforced here; never bypass scope_crash_query. AUTH-2:
    # study scope is layered on so a study-restricted user cannot aggregate
    # across studies they are not authorized for.
    stmt = scope_study_query(scope_crash_query(select(group_col, agg_expr), current), current)
    if body.study_id:
        stmt = stmt.where(Crash.study_id == body.study_id)
    for f in body.filters:
        col = FILTERABLE_COLUMNS[f.column]
        stmt = stmt.where(FILTER_OPERATORS[f.op](col, f.value))
    stmt = stmt.group_by(group_col).order_by(group_col)

    rows = [
        {body.group_by: _jsonable(g), body.aggregation: _jsonable(v)}
        for g, v in db.execute(stmt)
    ]
    return QueryResult(
        query_name="query_builder",
        columns=[body.group_by, body.aggregation],
        rows=rows,
    )


def _jsonable(value: Any) -> Any:
    """Coerce DB scalars (UUID / Decimal / date) into JSON-serialisable types."""
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (dt.date, dt.datetime)):
        return value.isoformat()
    return value
