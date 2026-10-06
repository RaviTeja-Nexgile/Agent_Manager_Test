"""CCFP IT Solution API — application entrypoint.

Mounts every feature router under /api/v1, wires health checks, CORS, and
consistent error handling. Run with:  uvicorn app.main:app --reload
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import sys
from collections.abc import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.core.config import settings
from app.core.database import engine
from app.features import (
    admin,
    analysis_environment,
    analysis_statistics,
    analytics,
    audit,
    auth,
    crashes,
    data_management,
    documents,
    initial_incident,
    integrations,
    notifications,
    public,
    reports,
    search,
    source_data,
    studies,
)

logger = logging.getLogger("ccfp.scheduler")


def _scheduler_should_run() -> bool:
    """Whether this process should own the Analysis Environment refresh loop.

    Disabled under pytest: the suite drives the app through TestClient, whose
    context manager runs the lifespan, and a background task writing refresh runs
    to the shared development database mid-test would be both a data-race and a
    lock-contention source. Detection is by pytest's own marker rather than a
    fixture change, so it holds for every entry point that imports this module.
    """
    if not settings.scheduler_enabled:
        return False
    return "pytest" not in sys.modules and "PYTEST_CURRENT_TEST" not in os.environ


async def _refresh_loop() -> None:
    """Fire ``refresh_stale_environments`` on the configured interval.

    This is what turns the BRD's "daily or hourly" from a staleness *threshold*
    into an actual firing *schedule* — before this, a dataset nobody opened was
    never refreshed. The worker already collapses concurrent refreshes of one
    environment behind a PostgreSQL advisory lock, so this loop racing a
    page-open refresh is safe by construction.

    The blocking DB work runs in a worker thread so the event loop keeps serving
    requests. Every iteration is wrapped: one bad refresh must not kill the loop
    and silently stop all future refreshes — the failure mode this exists to fix.
    """
    from app.workers.analysis import refresh_stale_environments

    interval = max(30, settings.scheduler_interval_seconds)
    while True:
        try:
            await asyncio.sleep(interval)
            result = await asyncio.to_thread(refresh_stale_environments)
            if result.get("stale"):
                logger.info("Refreshed %s stale analysis environment(s)", result["stale"])
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 — never let one failure end the schedule
            logger.exception("Scheduled analysis-environment refresh failed")


@contextlib.asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    task: asyncio.Task | None = None
    if _scheduler_should_run():
        task = asyncio.create_task(_refresh_loop())
        logger.info(
            "Analysis-environment refresh scheduler started (every %ss)",
            settings.scheduler_interval_seconds,
        )
    try:
        yield
    finally:
        if task is not None:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task


app = FastAPI(
    lifespan=lifespan,
    title=settings.app_name,
    version="1.0.0",
    description=(
        "Backend API for the FMCSA Crash Causal Factors Program (CCFP) IT "
        "Solution — Phase 1 Heavy-Duty Truck Study. Implements crash lifecycle, "
        "data collection, mapping, quality control, completeness, analytics, "
        "reporting, public de-identified outputs, role/scope-based access "
        "control, audit logging, and external integrations."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten to the approved frontend origin in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Routers (documentation §12) -------------------------------------------
_PREFIX = settings.api_v1_prefix
for module in (
    auth, admin, studies, crashes, initial_incident, source_data,
    data_management, analytics, analysis_environment, analysis_statistics, reports,
    public, documents,
    notifications, search, audit, integrations,
):
    app.include_router(module.router, prefix=_PREFIX)


# --- Health / meta ---------------------------------------------------------
@app.get("/", tags=["meta"])
def root() -> dict:
    return {"service": settings.app_name, "version": app.version, "docs": "/docs"}


@app.get("/health", tags=["meta"])
def health() -> dict:
    return {"status": "ok", "environment": settings.environment}


@app.get("/health/db", tags=["meta"])
def health_db() -> dict:
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    return {"status": "ok", "database": "reachable"}
