"""Application configuration.

The PostgreSQL connection string is resolved per the project rule in CLAUDE.md:
prefer the DATABASE_URL environment variable, otherwise read the
`postgresql://...` URL from the nearest CLAUDE.md (walking up from this file).
It is never hardcoded here.
"""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_CLAUDE_MD_PATTERN = re.compile(r"postgresql://[^\s`'\"<>]+")


def _connection_string_from_claude_md() -> str | None:
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "CLAUDE.md"
        if candidate.exists():
            match = _CLAUDE_MD_PATTERN.search(candidate.read_text(encoding="utf-8"))
            if match:
                return match.group(0)
    return None


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CCFP_", env_file=".env", extra="ignore")

    # --- Application ---
    app_name: str = "CCFP IT Solution API"
    api_v1_prefix: str = "/api/v1"
    environment: str = "development"

    # --- Database (resolved lazily; see database_url property) ---
    database_url: str | None = None

    # --- Auth ---
    jwt_secret: str = "dev-only-ccfp-secret-change-in-production"
    jwt_algorithm: str = "HS256"
    jwt_ttl_minutes: int = 480
    # Dev mock-IdP login endpoint. MUST be disabled in production in favour of
    # the DOT-approved OIDC identity provider (see security.py OIDC hook).
    dev_auth_enabled: bool = True

    # --- Object storage (local filesystem stand-in for encrypted cloud storage) ---
    storage_dir: str = "./_object_store"
    signed_url_ttl_minutes: int = 15
    # BRD p.13: "perform regular refreshes (daily or hourly)" of the Analysis
    # Environment. The per-environment `refresh_cadence` decides WHEN a snapshot
    # is stale; this decides how often the app looks. 300 s means an hourly
    # cadence fires within 5 minutes of becoming due, which is the resolution the
    # requirement needs without polling the database every second. Set
    # `scheduler_enabled=false` when a external scheduler (Celery Beat) owns it.
    scheduler_enabled: bool = True
    scheduler_interval_seconds: int = 300
    # SOO: crash reconstruction files are "narrative reports, images, and videos,
    # in various file formats". Video is the reason this ceiling is measured in
    # hundreds of megabytes rather than tens. Configurable so an operator can
    # lower it without a code change; enforced in features/documents.py.
    max_upload_mb: int = 512

    # --- ELD / eRODS ingestion (BRD Appendix E, §8.7) ---
    # An ELD output file covering a driver's 8-day record is kilobytes; a
    # multi-megabyte upload means the wrong file was selected. Configurable so a
    # future study phase can raise it without a code change.
    eld_max_upload_mb: int = 25
    # Hard caps on one extraction. Exceeding either is reported as an ERROR on
    # the file (never a silent truncation) — see workers/eld_format.py.
    eld_max_events: int = 200_000
    eld_parse_time_budget_seconds: float = 120.0

    # --- External integration feature flags (mock adapters when disabled) ---
    integration_safespect_live: bool = False
    integration_cdlis_live: bool = False
    integration_mcmis_live: bool = False
    integration_erods_live: bool = False
    # Appendix D sources the January 2026 BRD and the SOO name for aggregation.
    # Mocked until FMCSA supplies live clients, exactly like the four above.
    integration_clearinghouse_live: bool = False
    integration_dir_live: bool = False
    integration_sms_live: bool = False
    integration_nrcme_live: bool = False
    integration_dataqs_live: bool = False

    def resolved_database_url(self) -> str:
        if self.database_url:
            return self.database_url
        url = _connection_string_from_claude_md()
        if not url:
            raise RuntimeError(
                "No database URL: set CCFP_DATABASE_URL / DATABASE_URL or ensure "
                "CLAUDE.md contains a postgresql:// connection string."
            )
        return url


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    # Allow the conventional DATABASE_URL (no prefix) as a fallback.
    if not settings.database_url:
        import os

        env_url = os.environ.get("DATABASE_URL")
        if env_url:
            settings.database_url = env_url
    return settings


settings = get_settings()
