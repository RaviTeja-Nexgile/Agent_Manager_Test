"""Pagination helpers: limit/offset query params and a list envelope."""
from __future__ import annotations

from typing import Generic, TypeVar

from fastapi import Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

T = TypeVar("T")


class PageParams:
    def __init__(
        self,
        limit: int = Query(50, ge=1, le=500, description="Max items to return"),
        offset: int = Query(0, ge=0, description="Items to skip"),
    ) -> None:
        self.limit = limit
        self.offset = offset


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    limit: int
    offset: int


def paginate(db: Session, stmt, params: PageParams) -> tuple[list, int]:
    """Return (rows, total) for a SELECT statement with limit/offset applied."""
    total = db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0
    rows = list(db.scalars(stmt.limit(params.limit).offset(params.offset)).all())
    return rows, total
