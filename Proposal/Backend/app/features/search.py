"""Cross-entity search (documentation §8.10, §3.4, §15).

Searches crashes, persons, motor carriers, reports, and documents, honoring the
caller's State scope and PII clearance.

The set of searchable entities and the columns searched per entity is
**configuration-driven** (SEAR-3): the active study's ``study_parameters`` row
with ``param_key = 'searchable_entities'`` selects which entities/columns are
enabled. Config can only *toggle* members of a code-owned whitelist
(``SEARCH_REGISTRY``) — it never carries raw SQL or arbitrary column names —
and it never relaxes authorization (the per-entity permission gate and the
State-scope / PII / sensitivity checks are applied unchanged regardless of
config). When no config row exists the full registry is used, reproducing the
historical (hardcoded) coverage exactly.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.orm import InstrumentedAttribute, Session

from app.core.database import get_db
from app.core.permissions import require, scope_crash_query
from app.core.security import CurrentUser
from app.models import (
    Crash,
    Document,
    IncidentPerson,
    IncidentVehicle,
    Report,
    StudyParameter,
)

router = APIRouter(tags=["search"])

SEARCH_PARAM_KEY = "searchable_entities"


@dataclass(frozen=True)
class EntitySearch:
    """Code-owned whitelist entry for one searchable entity.

    ``model``      — the ORM model searched.
    ``columns``    — the searchable columns enabled by default (a mapping of
                     column *code* -> ORM attribute). This is the safe set;
                     study config can only enable a subset of these codes,
                     never an arbitrary name, and never raw SQL.
    ``gate``       — permission code required to search the entity (or ``None``
                     when the entity is gated by data sensitivity instead).
    ``sensitivity``— sensitivity level whose clearance gates the entity
                     (e.g. ``"PII"`` for persons), or ``None``.
    """

    model: type
    columns: dict[str, InstrumentedAttribute]
    gate: str | None = None
    sensitivity: str | None = None


# ---------------------------------------------------------------------------
# Code-owned whitelist. Config can only toggle entries/columns within this set;
# the default-enabled columns reproduce the historical hardcoded coverage so
# behaviour is unchanged when no config exists.
# ---------------------------------------------------------------------------
SEARCH_REGISTRY: dict[str, EntitySearch] = {
    "crashes": EntitySearch(
        model=Crash,
        gate="crash:read",
        columns={
            "ccfp_identifier": Crash.ccfp_identifier,
            "local_report_number": Crash.local_report_number,
            "city": Crash.city,
            "county": Crash.county,
            "street_highway": Crash.street_highway,
        },
    ),
    "persons": EntitySearch(
        model=IncidentPerson,
        sensitivity="PII",
        columns={"full_name": IncidentPerson.full_name},
    ),
    "carriers": EntitySearch(
        model=IncidentVehicle,
        gate="crash:read",
        columns={
            "carrier_name": IncidentVehicle.carrier_name,
            "make": IncidentVehicle.make,
            "us_dot_number": IncidentVehicle.us_dot_number,
        },
    ),
    "reports": EntitySearch(
        model=Report,
        gate="report:read",
        columns={
            "name": Report.name,
            "description": Report.description,
        },
    ),
    "documents": EntitySearch(
        model=Document,
        gate="crash:read",
        columns={
            "file_name": Document.file_name,
            "content_text": Document.content_text,
        },
    ),
}


class SearchHit(BaseModel):
    type: str
    id: uuid.UUID
    label: str
    crash_id: uuid.UUID | None = None


class SearchResults(BaseModel):
    query: str
    hits: list[SearchHit]


# ---------------------------------------------------------------------------
# PostgreSQL-native search engine (SEAR-2). No external search engine: every
# predicate below is built from in-stack PostgreSQL features only —
# ``to_tsvector``/``websearch_to_tsquery`` full-text, ``pg_trgm`` fuzzy match
# (``column % q``) and a plain ``ILIKE`` substring safety-net so exact
# identifier queries (e.g. ``CCFP-2026-KS``) keep matching. The GIN full-text
# and trigram indexes from migration ``0003_search_fulltext`` back these
# predicates so they stay fast.
# ---------------------------------------------------------------------------
_FTS_CONFIG = "english"


def _searchable_columns(spec: EntitySearch, cols: set[str]) -> list[InstrumentedAttribute]:
    """Resolve the enabled, whitelisted ORM columns for an entity (config-safe)."""
    return [spec.columns[c] for c in cols if c in spec.columns]


def _document_expr(columns: list[InstrumentedAttribute]):
    """A single text "document" concatenating the searched columns (NULL-safe)."""
    # ``concat_ws`` ignores NULLs and joins with a space, mirroring the
    # ``coalesce(...)||' '||...`` expressions the GIN indexes are built on.
    return func.concat_ws(" ", *columns)


def _tsvector(columns: list[InstrumentedAttribute]):
    return func.to_tsvector(_FTS_CONFIG, _document_expr(columns))


def _search_predicate(spec: EntitySearch, cols: set[str], q: str, like: str):
    """Combined full-text + trigram + substring predicate over enabled columns.

    Returns ``None`` when no whitelisted column is enabled (the entity is then
    skipped), exactly as the previous ILIKE-only helper did. The OR-of-three
    keeps three complementary behaviours:

    * ``to_tsvector @@ websearch_to_tsquery`` — natural-language / multi-word
      content search (document content, report descriptions, narratives);
    * ``column % q`` (``pg_trgm``) — fuzzy / partial-token matches;
    * ``column ILIKE %q%`` — exact substring safety-net so identifier-style
      queries such as ``CCFP-2026-KS`` always match.
    """
    columns = _searchable_columns(spec, cols)
    if not columns:
        return None
    tsq = func.websearch_to_tsquery(_FTS_CONFIG, q)
    clauses = [_tsvector(columns).op("@@")(tsq)]
    for col in columns:
        clauses.append(col.op("%")(q))      # pg_trgm fuzzy
        clauses.append(col.ilike(like))      # exact-substring safety net
    return or_(*clauses)


def _rank_order(spec: EntitySearch, cols: set[str], q: str):
    """``ts_rank`` ordering expression (most relevant first); ``None`` if empty."""
    columns = _searchable_columns(spec, cols)
    if not columns:
        return None
    tsq = func.websearch_to_tsquery(_FTS_CONFIG, q)
    return func.ts_rank(_tsvector(columns), tsq).desc()


def _resolve_searchable(db: Session, current: CurrentUser) -> dict[str, set[str]]:
    """Resolve the enabled (entity -> enabled column codes) map from config.

    Reads the active study's ``searchable_entities`` config (per-study, keyed by
    ``param_key``) and validates every value against ``SEARCH_REGISTRY``:
    unknown entity keys and unknown/disabled column codes are silently dropped
    (never interpolated into SQL). When no config exists, the full registry is
    returned so coverage matches the historical default.

    The active study set follows the same convention as other study-scoped
    reads: the user's assigned ``study_ids`` when present, otherwise all
    studies. When multiple studies apply, their enabled entities are unioned.
    """
    stmt = select(StudyParameter.study_id, StudyParameter.param_value).where(
        StudyParameter.param_key == SEARCH_PARAM_KEY
    )
    if current.study_ids:
        stmt = stmt.where(StudyParameter.study_id.in_(current.study_ids))
    rows = list(db.execute(stmt).all())

    if not rows:
        # No config anywhere that applies -> full registry (historical default).
        return {key: set(spec.columns) for key, spec in SEARCH_REGISTRY.items()}

    enabled: dict[str, set[str]] = {}
    for _study_id, value in rows:
        if not isinstance(value, dict):
            continue
        entities = value.get("entities")
        if entities is None:
            continue
        # `entities` may be a list of keys (all default columns enabled) or a
        # mapping of key -> list of column codes to restrict which are searched.
        if isinstance(entities, dict):
            items = entities.items()
        elif isinstance(entities, (list, tuple, set)):
            items = ((key, None) for key in entities)
        else:
            continue
        for key, cols in items:
            spec = SEARCH_REGISTRY.get(key)
            if spec is None:
                continue  # unknown entity -> ignored, never trusted
            if cols is None:
                resolved = set(spec.columns)
            elif isinstance(cols, (list, tuple, set)):
                resolved = {c for c in cols if c in spec.columns}
            else:
                resolved = set()
            # When an explicit column list resolves to nothing valid, the entity
            # has no searchable columns and is skipped; an entity listed without
            # columns keeps its full default whitelist.
            if not resolved:
                continue
            enabled.setdefault(key, set()).update(resolved)
    return enabled


@router.get("/search", response_model=SearchResults)
def search(
    q: str = Query(..., min_length=2),
    types: str | None = Query(None, description="Comma-separated subset of: crashes,persons,carriers,reports,documents"),
    limit: int = Query(25, ge=1, le=100),
    db: Session = Depends(get_db),
    current: CurrentUser = Depends(require("crash:read", "report:read")),
):
    enabled = _resolve_searchable(db, current)
    if types:
        requested = {t.strip() for t in types.split(",")}
        wanted = {key: cols for key, cols in enabled.items() if key in requested}
    else:
        wanted = enabled

    like = f"%{q}%"
    hits: list[SearchHit] = []

    def _predicate(spec: EntitySearch, cols: set[str]):
        # Combined full-text + pg_trgm fuzzy + ILIKE substring predicate over
        # only the enabled, whitelisted columns (see _search_predicate).
        return _search_predicate(spec, cols, q, like)

    if "crashes" in wanted and current.has_permission("crash:read"):
        spec = SEARCH_REGISTRY["crashes"]
        pred = _predicate(spec, wanted["crashes"])
        if pred is not None:
            stmt = scope_crash_query(select(Crash), current).where(pred)
            order = _rank_order(spec, wanted["crashes"], q)
            if order is not None:
                stmt = stmt.order_by(order)
            stmt = stmt.limit(limit)
            hits += [
                SearchHit(type="crash", id=c.id, label=c.ccfp_identifier, crash_id=c.id)
                for c in db.scalars(stmt)
            ]

    # Person search requires PII clearance.
    if "persons" in wanted and current.can_view_sensitivity("PII"):
        spec = SEARCH_REGISTRY["persons"]
        pred = _predicate(spec, wanted["persons"])
        if pred is not None:
            stmt = select(IncidentPerson).where(pred)
            order = _rank_order(spec, wanted["persons"], q)
            if order is not None:
                stmt = stmt.order_by(order)
            stmt = stmt.limit(limit)
            for p in db.scalars(stmt):
                crash = db.get(Crash, p.crash_id)
                if crash and current.can_access_state(crash.state_code):
                    hits.append(SearchHit(type="person", id=p.id, label=p.full_name or "(unnamed)", crash_id=p.crash_id))

    if "carriers" in wanted and current.has_permission("crash:read"):
        spec = SEARCH_REGISTRY["carriers"]
        pred = _predicate(spec, wanted["carriers"])
        if pred is not None:
            stmt = select(IncidentVehicle).where(pred)
            order = _rank_order(spec, wanted["carriers"], q)
            if order is not None:
                stmt = stmt.order_by(order)
            stmt = stmt.limit(limit)
            for v in db.scalars(stmt):
                crash = db.get(Crash, v.crash_id)
                if crash and current.can_access_state(crash.state_code):
                    hits.append(SearchHit(type="carrier", id=v.id, label=v.carrier_name or "(carrier)", crash_id=v.crash_id))

    if "reports" in wanted and current.has_permission("report:read"):
        spec = SEARCH_REGISTRY["reports"]
        pred = _predicate(spec, wanted["reports"])
        if pred is not None:
            stmt = select(Report).where(pred)
            order = _rank_order(spec, wanted["reports"], q)
            if order is not None:
                stmt = stmt.order_by(order)
            stmt = stmt.limit(limit)
            hits += [SearchHit(type="report", id=r.id, label=r.name) for r in db.scalars(stmt)]

    if "documents" in wanted and current.has_permission("crash:read"):
        spec = SEARCH_REGISTRY["documents"]
        pred = _predicate(spec, wanted["documents"])
        if pred is not None:
            stmt = select(Document).where(pred)
            order = _rank_order(spec, wanted["documents"], q)
            if order is not None:
                stmt = stmt.order_by(order)
            stmt = stmt.limit(limit)
            for d in db.scalars(stmt):
                if not current.can_view_sensitivity(d.sensitivity):
                    continue
                # State scope: a crash-bound document is only visible to callers
                # who can access its crash's State (mirrors the person/carrier
                # branches above). Documents with no crash are not State-bound.
                if d.crash_id is not None:
                    crash = db.get(Crash, d.crash_id)
                    if crash is None or not current.can_access_state(crash.state_code):
                        continue
                hits.append(SearchHit(type="document", id=d.id, label=d.file_name, crash_id=d.crash_id))

    return SearchResults(query=q, hits=hits[:limit])
