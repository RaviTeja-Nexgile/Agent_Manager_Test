"""Materialization and refresh for the CCFP Analysis Environment (GAP-BRD-02).

The January 2026 BRD makes the Analysis Environment a tier that data is *shared
into* and then *refreshed on a cadence* — as opposed to a name for querying the
operational tables live. The cadence is applied as a staleness threshold: the
refresh is triggered by an analyst opening the page (or pressing "Refresh now"),
not by a scheduler this stack does not have. This module is where that distinction becomes real:
:func:`materialize_dataset` runs a dataset's constrained definition against the
CCFP Aggregated Data once, writes the result into ``analysis_dataset_rows`` as a
new immutable version, and everything downstream (rows, statistics, export,
shares) reads only from there.

Two properties are load-bearing:

* **Read-only toward the source.** The BRD is explicit that the analysis
  capabilities "will not modify original data from CCFP (SafeSpect) or any other
  system." Every statement issued against an operational table here is a SELECT;
  the only writes go to ``analysis_*`` tables.
* **Versioned, not overwritten.** A refresh appends a new version and then flips
  ``current_version_id``, so a long-running read is never pulled out from under
  and "as of when?" has an answer. Old versions are pruned by count, not by
  truncating the live one.

The definition vocabulary below is an allow-list for the same reason the ad-hoc
query builder has one (documentation §14) — but the stakes are higher here,
because a stored definition is replayed unattended by every later refresh — long
after whoever wrote it has stopped watching, and on behalf of whichever analyst
happens to open the page next.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import Integer, extract, func, select, text
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.enums import (
    AnalysisEnvironmentStatus,
    RefreshCadence,
    RefreshRunStatus,
    RefreshTrigger,
)
from app.models import (
    AnalysisDataset,
    AnalysisDatasetRow,
    AnalysisDatasetVersion,
    AnalysisEnvironment,
    AnalysisRefreshRun,
    Crash,
)

# ---------------------------------------------------------------------------
# Constrained definition vocabulary
#
# A dataset definition is:
#   {"dimensions": [...], "measures": [...], "filters": [{column, op, value}],
#    "study_id": "<uuid>"|null}
#
# Every name is resolved through these maps to a mapped SQLAlchemy expression;
# nothing caller-supplied is ever interpolated into SQL text.
# ---------------------------------------------------------------------------
DIMENSIONS: dict[str, Any] = {
    "state_code": Crash.state_code,
    "county": Crash.county,
    "lifecycle_phase": Crash.lifecycle_phase,
    "study_id": Crash.study_id,
    # Time dimensions are computed, not stored, so a dataset can be grouped by
    # period without the caller supplying a date expression of their own.
    "crash_year": extract("year", Crash.crash_date).cast(Integer),
    "crash_month": extract("month", Crash.crash_date).cast(Integer),
}

MEASURES: dict[str, Any] = {
    "crash_count": func.count(),
    "sum_fatalities": func.coalesce(func.sum(Crash.num_fatalities), 0),
    "sum_vehicles": func.coalesce(func.sum(Crash.num_vehicles), 0),
    "sum_persons": func.coalesce(func.sum(Crash.num_persons), 0),
    "avg_fatalities": func.round(func.coalesce(func.avg(Crash.num_fatalities), 0), 2),
    "max_fatalities": func.coalesce(func.max(Crash.num_fatalities), 0),
}

FILTER_COLUMNS: dict[str, Any] = {
    **{k: v for k, v in DIMENSIONS.items()},
    "num_fatalities": Crash.num_fatalities,
    "num_vehicles": Crash.num_vehicles,
    "crash_date": Crash.crash_date,
}

FILTER_OPERATORS = {
    "eq": lambda col, val: col == val,
    "neq": lambda col, val: col != val,
    "gte": lambda col, val: col >= val,
    "lte": lambda col, val: col <= val,
}

# Keep a bounded version history so repeated refreshes cannot grow the
# row table without limit. Two spare versions is enough to answer "what changed
# in the last refresh?" without becoming a de-facto archive — NARA retention is
# served by the operational tables, which are never touched here.
VERSIONS_RETAINED = 3


class DefinitionError(ValueError):
    """A dataset definition names something outside the allow-lists."""


def validate_definition(definition: Any) -> dict:
    """Normalize and validate a dataset definition, or raise DefinitionError.

    Returns the cleaned definition. Called both when a dataset is created/updated
    (so a bad spec is a 400 at write time) and again at materialization (so a row
    edited around the API cannot widen its own reach on the next refresh).
    """
    if not isinstance(definition, dict):
        raise DefinitionError("definition must be an object")

    dimensions = definition.get("dimensions") or []
    measures = definition.get("measures") or []
    filters = definition.get("filters") or []

    if not isinstance(dimensions, list) or not dimensions:
        raise DefinitionError("definition.dimensions must be a non-empty list")
    if not isinstance(measures, list) or not measures:
        raise DefinitionError("definition.measures must be a non-empty list")
    if not isinstance(filters, list):
        raise DefinitionError("definition.filters must be a list")

    for name in dimensions:
        if name not in DIMENSIONS:
            raise DefinitionError(
                f"Unknown dimension '{name}'. Allowed: {sorted(DIMENSIONS)}"
            )
    if len(set(dimensions)) != len(dimensions):
        raise DefinitionError("definition.dimensions contains duplicates")

    for name in measures:
        if name not in MEASURES:
            raise DefinitionError(
                f"Unknown measure '{name}'. Allowed: {sorted(MEASURES)}"
            )
    if len(set(measures)) != len(measures):
        raise DefinitionError("definition.measures contains duplicates")

    clean_filters = []
    for clause in filters:
        if not isinstance(clause, dict):
            raise DefinitionError("each filter must be an object")
        column, op = clause.get("column"), clause.get("op")
        if column not in FILTER_COLUMNS:
            raise DefinitionError(
                f"Unknown filter column '{column}'. Allowed: {sorted(FILTER_COLUMNS)}"
            )
        if op not in FILTER_OPERATORS:
            raise DefinitionError(
                f"Unknown filter operator '{op}'. Allowed: {sorted(FILTER_OPERATORS)}"
            )
        if "value" not in clause:
            raise DefinitionError("each filter requires a value")
        clean_filters.append({"column": column, "op": op, "value": clause["value"]})

    clean: dict[str, Any] = {
        "dimensions": list(dimensions),
        "measures": list(measures),
        "filters": clean_filters,
    }
    study_id = definition.get("study_id")
    if study_id:
        try:
            clean["study_id"] = str(uuid.UUID(str(study_id)))
        except (ValueError, AttributeError, TypeError):
            raise DefinitionError("definition.study_id must be a UUID")
    return clean


def definition_columns(definition: dict) -> list[str]:
    """Ordered output column names for a validated definition."""
    return [*definition["dimensions"], *definition["measures"]]


def is_state_partitioned(definition: dict) -> bool:
    """True when every row carries a State, the precondition for sharing a
    dataset to a single participating State (BRD: State data "will be
    State-specific"). A dataset not grouped by State holds cross-State
    aggregates that no single State is entitled to see."""
    return "state_code" in (definition.get("dimensions") or [])


# ---------------------------------------------------------------------------
# Materialization
# ---------------------------------------------------------------------------
def _jsonable(value: Any) -> Any:
    """Coerce a DB scalar into something JSONB and FastAPI can both carry."""
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, Decimal):
        # Whole numbers stay ints so a count reads as `12`, not `12.0`.
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, (dt.date, dt.datetime)):
        return value.isoformat()
    return value


def _build_statement(definition: dict, environment: AnalysisEnvironment):
    """Compose the aggregation SELECT from mapped expression objects only.

    Note what is deliberately absent: any per-user State scope. This runs as the
    environment's own refresh, not as a request, and the environment holds the
    full Aggregated Data by design — the BRD's audience restrictions are applied
    when the data is *shared out* (analysis_shares), not when it is brought in.
    Applying a caller's scope here would silently bake one user's visibility into
    a shared dataset.
    """
    dims = [DIMENSIONS[name].label(name) for name in definition["dimensions"]]
    measures = [MEASURES[name].label(name) for name in definition["measures"]]

    stmt = select(*dims, *measures)

    # An environment scoped to a study only ever materializes that study.
    if environment.study_id is not None:
        stmt = stmt.where(Crash.study_id == environment.study_id)
    elif definition.get("study_id"):
        stmt = stmt.where(Crash.study_id == definition["study_id"])

    for clause in definition["filters"]:
        column = FILTER_COLUMNS[clause["column"]]
        stmt = stmt.where(FILTER_OPERATORS[clause["op"]](column, clause["value"]))

    return stmt.group_by(*dims).order_by(*dims)


def materialize_dataset(
    dataset_id: uuid.UUID,
    db: Session | None = None,
    refresh_run_id: uuid.UUID | None = None,
) -> dict:
    """Run one dataset's definition and store the result as a new version.

    Returns ``{"dataset_id", "version_no", "row_count"}`` on success. Raises on
    a bad definition or a query failure so the caller can mark the refresh run
    FAILED — a refresh that quietly wrote zero rows would be indistinguishable
    from a genuine empty result, which is precisely the ambiguity the run log
    exists to remove.
    """
    own = db is None
    db = db or SessionLocal()
    try:
        dataset = db.get(AnalysisDataset, dataset_id)
        if dataset is None:
            raise ValueError(f"analysis dataset {dataset_id} not found")
        environment = db.get(AnalysisEnvironment, dataset.environment_id)
        if environment is None:
            raise ValueError(f"analysis environment {dataset.environment_id} not found")

        definition = validate_definition(dataset.definition)
        columns = definition_columns(definition)
        state_index = (
            definition["dimensions"].index("state_code")
            if "state_code" in definition["dimensions"]
            else None
        )

        rows = list(db.execute(_build_statement(definition, environment)))

        next_no = (
            db.scalar(
                select(func.coalesce(func.max(AnalysisDatasetVersion.version_no), 0)).where(
                    AnalysisDatasetVersion.dataset_id == dataset.id
                )
            )
            or 0
        ) + 1

        version = AnalysisDatasetVersion(
            dataset_id=dataset.id,
            version_no=next_no,
            materialized_at=dt.datetime.now(dt.timezone.utc),
            row_count=len(rows),
            columns=columns,
            refresh_run_id=refresh_run_id,
        )
        db.add(version)
        db.flush()  # assign version.id before the rows reference it

        for index, row in enumerate(rows):
            values = [_jsonable(v) for v in row]
            payload = dict(zip(columns, values))
            db.add(
                AnalysisDatasetRow(
                    version_id=version.id,
                    row_index=index,
                    state_code=values[state_index] if state_index is not None else None,
                    data=payload,
                )
            )

        # Flip the pointer last: until this line the previous version is still
        # the one being served, so a reader concurrent with the refresh sees a
        # complete old version rather than a half-written new one.
        dataset.current_version_id = version.id
        dataset.is_state_partitioned = is_state_partitioned(definition)
        dataset.updated_at = dt.datetime.now(dt.timezone.utc)

        _prune_versions(db, dataset.id, keep=VERSIONS_RETAINED)

        if own:
            db.commit()
        else:
            db.flush()
        return {
            "dataset_id": str(dataset.id),
            "version_no": next_no,
            "row_count": len(rows),
        }
    except Exception:
        if own:
            db.rollback()
        raise
    finally:
        if own:
            db.close()


def _prune_versions(db: Session, dataset_id: uuid.UUID, keep: int) -> None:
    """Drop all but the newest ``keep`` versions of a dataset (rows cascade)."""
    stale = list(
        db.scalars(
            select(AnalysisDatasetVersion.id)
            .where(AnalysisDatasetVersion.dataset_id == dataset_id)
            .order_by(AnalysisDatasetVersion.version_no.desc())
            .offset(keep)
        )
    )
    if not stale:
        return
    db.query(AnalysisDatasetVersion).filter(
        AnalysisDatasetVersion.id.in_(stale)
    ).delete(synchronize_session=False)


# ---------------------------------------------------------------------------
# Environment refresh
# ---------------------------------------------------------------------------
def next_due(cadence: str, frm: dt.datetime | None = None) -> dt.datetime | None:
    """When the snapshot goes stale, measured from the last refresh.

    Under the refresh-on-open model this is not a firing time — nothing wakes up
    to act on it. It is the instant after which the next analyst to open the
    Analysis Environment triggers a background refresh. MANUAL has no such
    instant: that snapshot only moves when someone presses the button.
    """
    base = frm or dt.datetime.now(dt.timezone.utc)
    if cadence == RefreshCadence.HOURLY.value:
        return base + dt.timedelta(hours=1)
    if cadence == RefreshCadence.DAILY.value:
        return base + dt.timedelta(days=1)
    return None


# Namespace for the advisory lock below, so a key collision with any other
# advisory lock in the application is not possible.
_REFRESH_LOCK_NAMESPACE = 0x0CCF9A11


def _advisory_key(environment_id: uuid.UUID) -> int:
    """A stable signed 32-bit key for an environment, for pg_try_advisory_lock.

    PostgreSQL's two-argument advisory locks take two int4s; the namespace above
    is one and this derives the other from the UUID. Truncating a hash to 32 bits
    risks a collision between two environments, whose only consequence would be
    that their refreshes serialise against each other — harmless, and vanishingly
    unlikely with the handful of environments this deployment will ever hold.
    """
    digest = hashlib.blake2b(environment_id.bytes, digest_size=4).digest()
    return int.from_bytes(digest, "big", signed=True)


def refresh_in_progress(db: Session, environment_id: uuid.UUID) -> bool:
    """True when a refresh for this environment is in flight right now.

    Backs the UI's "refreshing…" state, so that a second analyst opening the page
    mid-refresh is told what is happening instead of being offered a button that
    would come back SKIPPED.

    Asks ``pg_locks`` rather than looking for a RUNNING row, because the run row
    is written inside the refresh's own transaction and is therefore invisible to
    every other connection until that transaction commits — by which point the
    run is no longer RUNNING. Querying for RUNNING rows would return False for
    the entire duration of every refresh, which is exactly backwards.

    The lock is the real authority, and it self-heals: it is transaction-scoped,
    so a crashed worker or a dropped connection releases it automatically. There
    is no abandoned-state to time out and no way for the indicator to wedge on.
    """
    return bool(
        db.scalar(
            text(
                """
                SELECT EXISTS (
                    SELECT 1 FROM pg_locks
                     WHERE locktype = 'advisory'
                       AND classid  = :namespace
                       AND objid    = :key
                       AND granted
                )
                """
            ),
            {
                # pg_locks stores both halves of a two-argument advisory lock as
                # unsigned oid columns; the key is generated signed, so mask it
                # back into the same 32-bit representation PostgreSQL reports.
                "namespace": _REFRESH_LOCK_NAMESPACE,
                "key": _advisory_key(environment_id) & 0xFFFFFFFF,
            },
        )
    )


def refresh_environment(
    environment_id: uuid.UUID,
    trigger: str = RefreshTrigger.MANUAL.value,
    triggered_by: uuid.UUID | None = None,
    db: Session | None = None,
) -> dict:
    """Refresh every ACTIVE dataset in an environment, logging one run row.

    Per-dataset failures are collected rather than aborting the run: one
    malformed definition should not stop the other datasets from refreshing, but
    it must still turn the run FAILED so the failure is visible on the
    environment page instead of being swallowed.

    Guarded by a PostgreSQL advisory lock. Refresh-on-open introduces a race the
    scheduled model did not have — two analysts opening the page in the same
    second both see a stale snapshot and both start a refresh — and the result
    would not merely be wasted work: two concurrent materializations of the same
    dataset each create a version and each flip ``current_version_id``, so the
    pointer can end up on the older of the two. Taking the lock makes the second
    caller a no-op instead. It is an *advisory* lock held for the transaction, so
    it is released on commit, rollback, or a dropped connection; a crashed worker
    cannot leave the environment locked.
    """
    own = db is None
    db = db or SessionLocal()
    try:
        environment = db.get(AnalysisEnvironment, environment_id)
        if environment is None:
            return {"error": "analysis environment not found"}

        acquired = db.scalar(
            select(func.pg_try_advisory_xact_lock(_REFRESH_LOCK_NAMESPACE, _advisory_key(environment_id)))
        )
        if not acquired:
            # Someone else is already doing exactly this work. Reporting it as a
            # skip rather than an error matters for the manual button: "a refresh
            # is already running" is a true, useful answer, not a failure.
            return {
                "environment_id": str(environment_id),
                "status": "SKIPPED",
                "reason": "A refresh for this environment is already in progress.",
                "datasets_refreshed": 0,
                "rows_written": 0,
            }

        run = AnalysisRefreshRun(
            environment_id=environment.id,
            trigger=trigger,
            status=RefreshRunStatus.RUNNING.value,
            started_at=dt.datetime.now(dt.timezone.utc),
            triggered_by=triggered_by,
        )
        db.add(run)
        db.flush()

        datasets = list(
            db.scalars(
                select(AnalysisDataset).where(
                    AnalysisDataset.environment_id == environment.id,
                    AnalysisDataset.status == "ACTIVE",
                )
            )
        )

        refreshed = 0
        rows_written = 0
        failures: list[str] = []
        for dataset in datasets:
            try:
                result = materialize_dataset(dataset.id, db=db, refresh_run_id=run.id)
                refreshed += 1
                rows_written += result["row_count"]
            except Exception as exc:  # noqa: BLE001 — surfaced in the run log
                failures.append(f"{dataset.code}: {exc}")

        # Crash-level cohorts materialize in the SAME run, under the
        # same advisory lock. Doing it here rather than on its own cadence is
        # what keeps the aggregated and crash-level views of the environment at
        # one point in time — otherwise a dataset could say 43 crashes while the
        # cohort it is compared against still held 40, and neither number would
        # be wrong, which is the worst kind of disagreement to debug.
        #
        # Imported inside the function: cohorts imports nothing from this module,
        # but keeping the edge out of the import graph means a failure to load
        # the cohort machinery cannot stop dataset refreshes from working.
        from app.workers import cohorts as cohort_worker

        cohorts_refreshed, members_written, cohort_failures = cohort_worker.refresh_cohorts(
            db, environment.id, refresh_run_id=run.id
        )
        failures.extend(cohort_failures)

        now = dt.datetime.now(dt.timezone.utc)
        run.status = (
            RefreshRunStatus.FAILED.value if failures else RefreshRunStatus.SUCCEEDED.value
        )
        run.finished_at = now
        run.datasets_refreshed = refreshed
        run.rows_written = rows_written
        run.cohorts_refreshed = cohorts_refreshed
        run.members_written = members_written
        run.message = (
            "; ".join(failures)
            if failures
            else (
                f"Refreshed {refreshed} dataset(s), {rows_written} row(s); "
                f"{cohorts_refreshed} cohort(s), {members_written} member(s)."
            )
        )

        # The environment is stamped as refreshed even on a partial failure —
        # some datasets did move — but the run row carries the truth about which
        # ones did not, and the next due date is set either way so a permanently
        # broken dataset cannot pin the scheduler into a hot retry loop.
        environment.last_refreshed_at = now
        environment.next_refresh_due = next_due(environment.refresh_cadence, now)
        environment.updated_at = now

        db.commit()
        return {
            "environment_id": str(environment.id),
            "run_id": str(run.id),
            "status": run.status,
            "datasets_refreshed": refreshed,
            "rows_written": rows_written,
            "cohorts_refreshed": cohorts_refreshed,
            "members_written": members_written,
            "message": run.message,
        }
    except Exception:
        db.rollback()
        raise
    finally:
        if own:
            db.close()


def stale_environments(db: Session) -> list[uuid.UUID]:
    """ACTIVE environments whose stored snapshot has aged past its cadence.

    This is the read behind refresh-on-open: the page serves the stored snapshot
    immediately and, if this returns the environment, a background refresh is
    started so the *next* look is current. Nothing here blocks the response.

    MANUAL is excluded by design — that cadence means "only when someone asks".

    A NULL ``next_refresh_due`` counts as stale so a freshly created or seeded
    environment materializes the first time it is opened, instead of sitting
    empty until someone finds the button.
    """
    stmt = select(AnalysisEnvironment.id).where(
        AnalysisEnvironment.status == AnalysisEnvironmentStatus.ACTIVE.value,
        AnalysisEnvironment.refresh_cadence != RefreshCadence.MANUAL.value,
        (AnalysisEnvironment.next_refresh_due.is_(None))
        | (AnalysisEnvironment.next_refresh_due <= dt.datetime.now(dt.timezone.utc)),
    )
    return list(db.scalars(stmt))


def refresh_stale_environments(
    db: Session | None = None,
    trigger: str = RefreshTrigger.SCHEDULED.value,
) -> dict:
    """Refresh every environment whose snapshot is stale.

    Called from a FastAPI ``BackgroundTasks`` when an analyst opens the Analysis
    Environment, so it runs after the response has been sent and never delays the
    page. The concurrent-open race is handled inside ``refresh_environment`` by an
    advisory lock, so several simultaneous opens collapse to one refresh.

    Runs are logged as SCHEDULED because the *cadence* decided they were needed,
    not a person — see ``RefreshTrigger``. This is also the single entry point a
    future scheduler would call, which is why the trigger stays a parameter.
    Adding Celery Beat later means scheduling this function: no schema change, no
    second code path, no new trigger value.
    """
    own = db is None
    db = db or SessionLocal()
    try:
        stale = stale_environments(db)
        results = []
        for environment_id in stale:
            try:
                results.append(refresh_environment(environment_id, trigger=trigger, db=db))
            except Exception as exc:  # noqa: BLE001 — one bad env must not stop the rest
                results.append({"environment_id": str(environment_id), "error": str(exc)})
        return {"stale": len(stale), "results": results}
    finally:
        if own:
            db.close()
