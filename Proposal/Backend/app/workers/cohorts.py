"""Crash-level cohort materialization for the Analysis Environment.

:mod:`app.workers.analysis` materializes *aggregated* rows — one per
(state, year, …) group — which is the right shape for the BRD's
"visualization-ready outputs". This module materializes the other half: the
*crash-level* populations that the January 2026 BRD's remaining statistical
methods need.

The split is not cosmetic. Thematic analysis asks which contributing factors
co-occur, and risk modelling needs crashes cross-classified by exposure and
outcome. Both are questions about individual crashes, and neither survives
aggregation — once crashes are summed into groups, you cannot recover which
factors appeared on the same crash.

A cohort therefore materializes into ``analysis_cohort_members``: one row per
crash, with the analysis variables copied onto it. The same discipline as
datasets applies — versioned, appended, pointer flipped last, read-only toward
the operational tables — so a statistic always describes the population as it
was at a stated version, and an operational edit can never silently change a
number that has already been reported.

The filter vocabulary here is deliberately wider than the dataset one. It has to
reach ``crash_scope_classifications`` and the contributing-factor selections,
because without those two the BRD's control population is not expressible: the
non-fatal and non-qualifying crashes that make a comparison denominator possible
are distinguished by exactly those columns.
"""
from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from sqlalchemy import Integer, and_, exists, extract, func, or_, select
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models import (
    AnalysisCohort,
    AnalysisCohortMember,
    AnalysisCohortVersion,
    AnalysisEnvironment,
    ContributingFactorSelection,
    Crash,
    CrashScopeClassification,
)

# Keep in step with datasets: the same number of versions is retained so the two
# halves of the environment age out together.
VERSIONS_RETAINED = 3

# Members materialized per cohort. A guard, not a design limit — Phase 1 is a
# few thousand crashes nationally, and a definition that somehow matched
# everything should fail loudly rather than write an unbounded table.
MAX_MEMBERS = 200_000


# ---------------------------------------------------------------------------
# Constrained filter vocabulary
#
# Same contract as the dataset definitions: every caller-supplied name is
# resolved through these maps to a mapped SQLAlchemy expression, so nothing
# reaches SQL as text. A cohort definition is:
#
#   {"filters": [{"column": ..., "op": ..., "value": ...}], "study_id": "..."}
# ---------------------------------------------------------------------------
COHORT_FILTER_COLUMNS: dict[str, Any] = {
    "state_code": Crash.state_code,
    "county": Crash.county,
    "lifecycle_phase": Crash.lifecycle_phase,
    "study_id": Crash.study_id,
    "crash_date": Crash.crash_date,
    "crash_year": extract("year", Crash.crash_date).cast(Integer),
    "crash_month": extract("month", Crash.crash_date).cast(Integer),
    "num_fatalities": Crash.num_fatalities,
    "num_vehicles": Crash.num_vehicles,
    "num_persons": Crash.num_persons,
    # The three columns that make a control population expressible at all.
    # `scope` distinguishes the Phase 1 study population from the crashes that
    # were recorded and then classified out; `is_qualifying` distinguishes
    # "did not meet the Phase 1 definition" from "met it but in a
    # non-participating State".
    "scope": CrashScopeClassification.scope,
    "is_qualifying": CrashScopeClassification.is_qualifying,
    "is_supplemental": CrashScopeClassification.is_supplemental,
    # Derived outcome. Written out rather than left to the analyst as
    # `num_fatalities gte 1` because "fatal" is the outcome variable of every
    # risk model in this study, and it should be spelled the same way every time
    # it is used. coalesce so an unrecorded count reads as not-fatal rather than
    # dropping the crash out of both arms of a comparison.
    "is_fatal": func.coalesce(Crash.num_fatalities, 0) > 0,
}

# `has_factor` is not a column — it is an EXISTS over the crash's contributing
# factor selections, handled separately in :func:`_clause_expression`. It is what
# lets a cohort be defined by exposure ("crashes where the driver was fatigued"),
# which is the other half of a risk model.
FACTOR_COLUMNS = {"has_factor", "has_factor_group"}

COHORT_FILTER_OPERATORS: dict[str, Any] = {
    "eq": lambda col, val: col == val,
    "neq": lambda col, val: col != val,
    "gt": lambda col, val: col > val,
    "gte": lambda col, val: col >= val,
    "lt": lambda col, val: col < val,
    "lte": lambda col, val: col <= val,
    "in": lambda col, val: col.in_(val),
    "not_in": lambda col, val: ~col.in_(val),
}

# Operators that take a list. Separated so a scalar passed to `in` is a clear
# 400 rather than a SQL error at refresh time, hours after the mistake.
LIST_OPERATORS = {"in", "not_in"}

# Booleans arrive from JSON as real booleans, but a definition hand-written into
# the database (or typed into the UI) may carry the string. Normalizing here
# keeps `is_qualifying eq "false"` from silently matching everything, which in a
# control-cohort definition would be a serious, invisible error.
_TRUE = {"true", "t", "yes", "y", "1"}
_FALSE = {"false", "f", "no", "n", "0"}
_BOOLEAN_COLUMNS = {"is_qualifying", "is_supplemental", "is_fatal"}


class CohortDefinitionError(ValueError):
    """A cohort definition names something outside the allow-lists."""


def _coerce(column_name: str, value: Any) -> Any:
    if column_name in _BOOLEAN_COLUMNS and isinstance(value, str):
        low = value.strip().lower()
        if low in _TRUE:
            return True
        if low in _FALSE:
            return False
        raise CohortDefinitionError(
            f"filter on '{column_name}' expects a boolean, got {value!r}"
        )
    return value


def validate_cohort_definition(definition: Any) -> dict:
    """Normalize and validate a cohort definition, or raise.

    Run both at write time (so a bad definition is a 400 while someone is
    watching) and again at materialization (so a row edited around the API
    cannot widen its own reach on the next refresh).
    """
    if not isinstance(definition, dict):
        raise CohortDefinitionError("definition must be an object")

    filters = definition.get("filters") or []
    if not isinstance(filters, list):
        raise CohortDefinitionError("definition.filters must be a list")

    clean_filters: list[dict[str, Any]] = []
    for clause in filters:
        if not isinstance(clause, dict):
            raise CohortDefinitionError("each filter must be an object")
        column, op = clause.get("column"), clause.get("op")
        allowed = sorted({*COHORT_FILTER_COLUMNS, *FACTOR_COLUMNS})
        if column not in COHORT_FILTER_COLUMNS and column not in FACTOR_COLUMNS:
            raise CohortDefinitionError(
                f"Unknown filter column '{column}'. Allowed: {allowed}"
            )
        if column in FACTOR_COLUMNS:
            # Membership is the only sensible question about a factor list.
            if op not in {"eq", "neq", "in", "not_in"}:
                raise CohortDefinitionError(
                    f"filter on '{column}' supports eq, neq, in, not_in — got '{op}'"
                )
        elif op not in COHORT_FILTER_OPERATORS:
            raise CohortDefinitionError(
                f"Unknown filter operator '{op}'. Allowed: {sorted(COHORT_FILTER_OPERATORS)}"
            )
        if "value" not in clause:
            raise CohortDefinitionError("each filter requires a value")

        value = clause["value"]
        if op in LIST_OPERATORS:
            if not isinstance(value, list) or not value:
                raise CohortDefinitionError(
                    f"operator '{op}' requires a non-empty list value"
                )
            value = [_coerce(column, v) for v in value]
        else:
            if isinstance(value, list):
                raise CohortDefinitionError(
                    f"operator '{op}' takes a single value, not a list"
                )
            value = _coerce(column, value)
        clean_filters.append({"column": column, "op": op, "value": value})

    clean: dict[str, Any] = {"filters": clean_filters}
    study_id = definition.get("study_id")
    if study_id:
        try:
            clean["study_id"] = str(uuid.UUID(str(study_id)))
        except (ValueError, AttributeError, TypeError):
            raise CohortDefinitionError("definition.study_id must be a UUID")
    return clean


def _factor_exists(value: Any, by_group: bool) -> Any:
    """EXISTS clause for a contributing-factor filter."""
    column = (
        ContributingFactorSelection.factor_group_id
        if by_group
        else ContributingFactorSelection.factor_value
    )
    target = column.in_(value) if isinstance(value, list) else column == value
    return exists(
        select(ContributingFactorSelection.id).where(
            and_(ContributingFactorSelection.crash_id == Crash.id, target)
        )
    )


def _clause_expression(clause: dict) -> Any:
    column, op, value = clause["column"], clause["op"], clause["value"]
    if column in FACTOR_COLUMNS:
        clause_expr = _factor_exists(value, by_group=(column == "has_factor_group"))
        return ~clause_expr if op in {"neq", "not_in"} else clause_expr
    return COHORT_FILTER_OPERATORS[op](COHORT_FILTER_COLUMNS[column], value)


# ---------------------------------------------------------------------------
# Materialization
# ---------------------------------------------------------------------------
def _factor_values_subquery():
    """Per-crash contributing-factor values, as a sorted distinct array.

    Sorted so two crashes carrying the same factors produce identical arrays —
    co-occurrence and theme counting both rely on that being stable across
    refreshes, otherwise a "new" theme would appear whenever the selection order
    changed.
    """
    return (
        select(func.array_agg(func.distinct(ContributingFactorSelection.factor_value)))
        .where(ContributingFactorSelection.crash_id == Crash.id)
        .correlate(Crash)
        .scalar_subquery()
    )


def _factor_groups_subquery():
    from app.models import RefContributingFactorGroup

    return (
        select(func.array_agg(func.distinct(RefContributingFactorGroup.code)))
        .select_from(ContributingFactorSelection)
        .join(
            RefContributingFactorGroup,
            RefContributingFactorGroup.id == ContributingFactorSelection.factor_group_id,
        )
        .where(ContributingFactorSelection.crash_id == Crash.id)
        .correlate(Crash)
        .scalar_subquery()
    )


def _build_member_statement(definition: dict, environment: AnalysisEnvironment):
    """Compose the crash-level SELECT from mapped expression objects only.

    The join to ``crash_scope_classifications`` is an OUTER join on purpose: a
    crash that has not been classified yet still exists and still belongs in a
    descriptive population. Making it an inner join would silently drop
    unclassified crashes from every cohort, which would understate counts in a
    way nothing downstream could detect.

    As in the dataset builder, no per-user State scope is applied — this runs as
    the environment's own refresh and the environment holds the full Aggregated
    Data by design. Scope is applied when the data is read or shared out.
    """
    stmt = select(
        Crash.id.label("crash_id"),
        Crash.ccfp_identifier.label("ccfp_identifier"),
        Crash.state_code.label("state_code"),
        Crash.county.label("county"),
        Crash.crash_date.label("crash_date"),
        extract("year", Crash.crash_date).cast(Integer).label("crash_year"),
        extract("month", Crash.crash_date).cast(Integer).label("crash_month"),
        Crash.lifecycle_phase.label("lifecycle_phase"),
        Crash.study_id.label("study_id"),
        Crash.num_fatalities.label("num_fatalities"),
        Crash.num_vehicles.label("num_vehicles"),
        Crash.num_persons.label("num_persons"),
        (func.coalesce(Crash.num_fatalities, 0) > 0).label("is_fatal"),
        CrashScopeClassification.scope.label("scope"),
        CrashScopeClassification.is_qualifying.label("is_qualifying"),
        # array_agg over no rows yields NULL rather than an empty array; that is
        # normalized to [] when the member row is built, so a crash with no
        # recorded factors is "no factors" rather than "unknown".
        _factor_values_subquery().label("factors"),
        _factor_groups_subquery().label("factor_groups"),
    ).select_from(
        Crash.__table__.outerjoin(
            CrashScopeClassification.__table__,
            CrashScopeClassification.crash_id == Crash.id,
        )
    )

    if environment.study_id is not None:
        stmt = stmt.where(Crash.study_id == environment.study_id)
    elif definition.get("study_id"):
        stmt = stmt.where(Crash.study_id == definition["study_id"])

    for clause in definition["filters"]:
        stmt = stmt.where(_clause_expression(clause))

    return stmt.order_by(Crash.crash_date.desc().nullslast(), Crash.ccfp_identifier)


def materialize_cohort(
    cohort_id: uuid.UUID,
    db: Session | None = None,
    refresh_run_id: uuid.UUID | None = None,
) -> dict:
    """Run one cohort's definition and store the members as a new version."""
    own = db is None
    db = db or SessionLocal()
    try:
        cohort = db.get(AnalysisCohort, cohort_id)
        if cohort is None:
            raise ValueError(f"analysis cohort {cohort_id} not found")
        environment = db.get(AnalysisEnvironment, cohort.environment_id)
        if environment is None:
            raise ValueError(f"analysis environment {cohort.environment_id} not found")

        definition = validate_cohort_definition(cohort.definition)
        rows = list(db.execute(_build_member_statement(definition, environment)))
        if len(rows) > MAX_MEMBERS:
            raise ValueError(
                f"cohort '{cohort.code}' matched {len(rows)} crashes, above the "
                f"{MAX_MEMBERS} materialization limit — narrow the definition"
            )

        next_no = (
            db.scalar(
                select(func.coalesce(func.max(AnalysisCohortVersion.version_no), 0)).where(
                    AnalysisCohortVersion.cohort_id == cohort.id
                )
            )
            or 0
        ) + 1

        version = AnalysisCohortVersion(
            cohort_id=cohort.id,
            version_no=next_no,
            member_count=len(rows),
            definition_snapshot=definition,
            materialized_at=dt.datetime.now(dt.timezone.utc),
            refresh_run_id=refresh_run_id,
        )
        db.add(version)
        db.flush()

        for row in rows:
            mapping = row._mapping
            db.add(
                AnalysisCohortMember(
                    version_id=version.id,
                    crash_id=mapping["crash_id"],
                    ccfp_identifier=mapping["ccfp_identifier"],
                    state_code=mapping["state_code"],
                    county=mapping["county"],
                    crash_date=mapping["crash_date"],
                    crash_year=mapping["crash_year"],
                    crash_month=mapping["crash_month"],
                    lifecycle_phase=mapping["lifecycle_phase"],
                    study_id=mapping["study_id"],
                    num_fatalities=mapping["num_fatalities"],
                    num_vehicles=mapping["num_vehicles"],
                    num_persons=mapping["num_persons"],
                    is_fatal=bool(mapping["is_fatal"]),
                    scope=mapping["scope"],
                    is_qualifying=mapping["is_qualifying"],
                    factors=list(mapping["factors"] or []),
                    factor_groups=list(mapping["factor_groups"] or []),
                )
            )

        # Pointer flipped last, for the same reason as datasets: a reader
        # concurrent with the refresh sees a complete old version rather than a
        # half-written new one.
        cohort.current_version_id = version.id
        cohort.updated_at = dt.datetime.now(dt.timezone.utc)

        _prune_cohort_versions(db, cohort.id, keep=VERSIONS_RETAINED)

        if own:
            db.commit()
        else:
            db.flush()
        return {
            "cohort_id": str(cohort.id),
            "version_no": next_no,
            "member_count": len(rows),
        }
    except Exception:
        if own:
            db.rollback()
        raise
    finally:
        if own:
            db.close()


def _prune_cohort_versions(db: Session, cohort_id: uuid.UUID, keep: int) -> None:
    """Drop all but the newest ``keep`` versions (members cascade)."""
    stale = list(
        db.scalars(
            select(AnalysisCohortVersion.id)
            .where(AnalysisCohortVersion.cohort_id == cohort_id)
            .order_by(AnalysisCohortVersion.version_no.desc())
            .offset(keep)
        )
    )
    if not stale:
        return
    db.query(AnalysisCohortVersion).filter(
        AnalysisCohortVersion.id.in_(stale)
    ).delete(synchronize_session=False)


def refresh_cohorts(
    db: Session, environment_id: uuid.UUID, refresh_run_id: uuid.UUID | None = None
) -> tuple[int, int, list[str]]:
    """Materialize every ACTIVE cohort in an environment.

    Returns ``(cohorts_refreshed, members_written, failures)``. Failures are
    collected rather than raised so one malformed cohort cannot stop the others,
    matching how dataset failures are handled — the run row carries the truth.
    """
    cohorts = list(
        db.scalars(
            select(AnalysisCohort).where(
                AnalysisCohort.environment_id == environment_id,
                AnalysisCohort.status == "ACTIVE",
            )
        )
    )
    refreshed = 0
    members = 0
    failures: list[str] = []
    for cohort in cohorts:
        try:
            result = materialize_cohort(cohort.id, db=db, refresh_run_id=refresh_run_id)
            refreshed += 1
            members += result["member_count"]
        except Exception as exc:  # noqa: BLE001 — surfaced in the run log
            failures.append(f"cohort {cohort.code}: {exc}")
    return refreshed, members, failures
