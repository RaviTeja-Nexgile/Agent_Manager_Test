"""Public, de-identified outputs — no authentication (documentation §3, §7, §14).

Only reports that are published, de-identified, and PUBLIC-visibility are exposed.
"""
from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

import jwt
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.errors import BadRequest, NotFound
from app.features.reports import render_report_csv_response
from app.models import (
    AnalysisDataset,
    AnalysisDatasetRow,
    AnalysisDatasetVersion,
    AnalysisShare,
    Crash,
    CrashAttributeValue,
    DataAttribute,
    Report,
    Study,
)

router = APIRouter(prefix="/public", tags=["public"])

# Absolute API base for catalog distribution URLs (e.g. /api/v1/public).
_PUBLIC_BASE = f"{settings.api_v1_prefix}/public"


class PublicReportOut(BaseModel):
    id: uuid.UUID
    name: str
    report_type: str
    study_id: uuid.UUID | None
    description: str | None
    definition: Any | None
    published_at: dt.datetime | None
    # Open-data (Project Open Data) metadata surfaced on every published output.
    license: str | None = None
    keywords: list[str] | None = None
    publisher: str | None = None
    contact_name: str | None = None
    contact_email: str | None = None
    update_cadence: str | None = None


# --- Open-data catalog constants (Project Open Data §14.1) ------------------
# Published CCFP outputs are U.S. federal open data: public-domain, published by
# the CCFP program. Each report MAY carry its own open-data metadata in dedicated
# columns (license/keywords/publisher/contact_name/contact_email/update_cadence);
# where a column is NULL the program-level defaults below are advertised instead,
# so every published output is standards-conformant and machine-harvestable.
_OPEN_DATA_LICENSE = "https://creativecommons.org/publicdomain/zero/1.0/"
_OPEN_DATA_PUBLISHER = "FMCSA Crash Causal Factors Program"
_OPEN_DATA_CONTACT_NAME = "CCFP Open Data"
_OPEN_DATA_CONTACT_EMAIL = "opendata@ccfp.gov"
_OPEN_DATA_CADENCE = "R/P1Y"  # ISO 8601 recurring interval — annual (accrualPeriodicity)
_OPEN_DATA_BASE_KEYWORDS = (
    "commercial motor vehicle",
    "crash",
    "heavy-duty truck",
    "FMCSA",
    "safety",
)
_POD_SCHEMA = "https://project-open-data.cio.gov/v1.1/schema"
_POD_CATALOG_CONTEXT = "https://project-open-data.cio.gov/v1.1/schema/catalog.jsonld"


def _report_keywords(report: Report) -> list[str]:
    """Effective keyword list for a report.

    Prefers the report's own ``keywords`` column (a Postgres ``TEXT[]``) when
    populated; otherwise falls back to the program base terms plus the report
    type so the catalog is never keyword-empty.
    """
    if report.keywords:
        return [k for k in report.keywords if k]
    keywords = list(_OPEN_DATA_BASE_KEYWORDS)
    if report.report_type:
        rt = report.report_type.replace("_", " ").strip().lower()
        if rt and rt not in keywords:
            keywords.append(rt)
    return keywords


def _report_license(report: Report) -> str:
    return report.license or _OPEN_DATA_LICENSE


def _report_publisher(report: Report) -> str:
    return report.publisher or _OPEN_DATA_PUBLISHER


def _report_contact_name(report: Report) -> str:
    return report.contact_name or _OPEN_DATA_CONTACT_NAME


def _report_contact_email(report: Report) -> str:
    return report.contact_email or _OPEN_DATA_CONTACT_EMAIL


def _report_cadence(report: Report) -> str:
    return report.update_cadence or _OPEN_DATA_CADENCE


def _publicreport_out(report: Report) -> PublicReportOut:
    """Map a Report row to the public DTO, attaching open-data metadata.

    Each metadata field reflects the report's own column when set, falling back
    to the program-level open-data defaults when NULL.
    """
    return PublicReportOut(
        id=report.id,
        name=report.name,
        report_type=report.report_type,
        study_id=report.study_id,
        description=report.description,
        definition=report.definition,
        published_at=report.published_at,
        license=_report_license(report),
        keywords=_report_keywords(report),
        publisher=_report_publisher(report),
        contact_name=_report_contact_name(report),
        contact_email=_report_contact_email(report),
        update_cadence=_report_cadence(report),
    )


def _published_only(stmt):
    return stmt.where(
        Report.is_published.is_(True),
        Report.is_deidentified.is_(True),
        Report.visibility == "PUBLIC",
    )


class PublicNarrativeOut(BaseModel):
    """One crash's public-releasable narrative (GAP-PCR-06).

    The HDTS PCR data form carries a Public Narrative "written for and available
    to the public", deliberately separate from the internal Crash Description.
    Only the former is served here.
    """

    ccfp_identifier: str
    state_code: str | None
    crash_date: dt.date | None
    narrative: str


@router.get("/crash-narratives", response_model=list[PublicNarrativeOut])
def public_crash_narratives(study_id: uuid.UUID | None = None, db: Session = Depends(get_db)):
    """Public-releasable crash narratives (GAP-PCR-06). No authentication.

    Three gates, all of which must hold, because this is an anonymous endpoint
    serving crash-level text:

    1. **Only C31.** The query is pinned to the attribute whose sensitivity is
       PUBLIC. The internal description (CX1) is SENSITIVE and is never
       reachable here — publishing it in C31's place is the disclosure incident
       the separation exists to prevent.
    2. **Sensitivity re-checked at query time**, not assumed from the code. If
       someone were to reclassify C31 away from PUBLIC, this endpoint stops
       serving it rather than continuing on a stale assumption.
    3. **The study must permit publication** — `publication_enabled` and a
       `public_scope` other than NONE. A narrative is crash-level text, so a
       study configured to share nothing publicly must not leak one.

    Returns only the identifier, State, date and narrative: enough to be useful
    as open data, and nothing that would re-identify a person.
    """
    stmt = (
        select(
            Crash.ccfp_identifier,
            Crash.state_code,
            Crash.crash_date,
            CrashAttributeValue.value_text,
        )
        .select_from(CrashAttributeValue)
        .join(DataAttribute, DataAttribute.id == CrashAttributeValue.attribute_id)
        .join(Crash, Crash.id == CrashAttributeValue.crash_id)
        .join(Study, Study.id == Crash.study_id)
        .where(
            CrashAttributeValue.is_current.is_(True),
            CrashAttributeValue.value_text.is_not(None),
            CrashAttributeValue.value_text != "",
            DataAttribute.code == "C31",
            DataAttribute.sensitivity == "PUBLIC",
            DataAttribute.is_active.is_(True),
            Study.publication_enabled.is_(True),
            Study.public_scope != "NONE",
        )
        .order_by(Crash.crash_date.desc().nulls_last(), Crash.ccfp_identifier)
    )
    if study_id:
        stmt = stmt.where(Crash.study_id == study_id)
    return [
        PublicNarrativeOut(
            ccfp_identifier=ident, state_code=state, crash_date=date, narrative=text
        )
        for ident, state, date, text in db.execute(stmt)
    ]


@router.get("/outputs", response_model=list[PublicReportOut])
def public_all_outputs(db: Session = Depends(get_db)):
    """All published, de-identified, public outputs across studies (open data, no auth)."""
    stmt = _published_only(select(Report)).order_by(Report.published_at.desc())
    return [_publicreport_out(r) for r in db.scalars(stmt)]


@router.get("/studies/{study_id}/outputs", response_model=list[PublicReportOut])
def public_study_outputs(study_id: uuid.UUID, db: Session = Depends(get_db)):
    stmt = _published_only(select(Report).where(Report.study_id == study_id)).order_by(Report.published_at.desc())
    return [_publicreport_out(r) for r in db.scalars(stmt)]


@router.get("/data.json")
def public_open_data_catalog(db: Session = Depends(get_db)) -> dict[str, Any]:
    """Project Open Data ``data.json`` catalog of published outputs (open data, no auth).

    Emits a machine-readable, harvestable catalog (documentation §14.1) describing
    every published, de-identified, PUBLIC report. Each dataset advertises license,
    keywords, publisher, point-of-contact, and update cadence, plus distribution
    entries pointing at the existing public JSON detail and CSV download URLs.
    Sourced via ``_published_only`` so internal/FEDERAL/STATE/unpublished reports
    are never leaked.
    """
    stmt = _published_only(select(Report)).order_by(Report.published_at.desc())
    reports = list(db.scalars(stmt))

    datasets: list[dict[str, Any]] = []
    for report in reports:
        identifier = str(report.id)
        detail_url = f"{_PUBLIC_BASE}/reports/{identifier}"
        download_url = f"{detail_url}/download"
        dataset: dict[str, Any] = {
            "@type": "dcat:Dataset",
            "identifier": identifier,
            "title": report.name,
            "description": report.description or report.name,
            "keyword": _report_keywords(report),
            "accessLevel": "public",
            "license": _report_license(report),
            "publisher": {"@type": "org:Organization", "name": _report_publisher(report)},
            "contactPoint": {
                "@type": "vcard:Contact",
                "fn": _report_contact_name(report),
                "hasEmail": f"mailto:{_report_contact_email(report)}",
            },
            "accrualPeriodicity": _report_cadence(report),
            "distribution": [
                {
                    "@type": "dcat:Distribution",
                    "title": f"{report.name} (JSON)",
                    "downloadURL": detail_url,
                    "mediaType": "application/json",
                    "format": "JSON",
                },
                {
                    "@type": "dcat:Distribution",
                    "title": f"{report.name} (CSV)",
                    "downloadURL": download_url,
                    "mediaType": "text/csv",
                    "format": "CSV",
                },
            ],
        }
        if report.published_at is not None:
            dataset["modified"] = report.published_at.isoformat()
        datasets.append(dataset)

    return {
        "@context": _POD_CATALOG_CONTEXT,
        "@type": "dcat:Catalog",
        "conformsTo": _POD_SCHEMA,
        "describedBy": "https://project-open-data.cio.gov/v1.1/schema/catalog.json",
        "dataset": datasets,
    }


@router.get("/reports/{report_id}", response_model=PublicReportOut)
def public_report(report_id: uuid.UUID, db: Session = Depends(get_db)):
    report = db.scalar(_published_only(select(Report).where(Report.id == report_id)))
    if report is None:
        raise NotFound("Published report")
    return _publicreport_out(report)


@router.get("/reports/{report_id}/download")
def public_report_download(report_id: uuid.UUID, db: Session = Depends(get_db)):
    """Download a published, de-identified, PUBLIC report as CSV (open data, no auth).

    Only published + de-identified + PUBLIC reports are downloadable; anything
    else (including private/unpublished ids) is indistinguishable from missing.
    """
    report = db.scalar(_published_only(select(Report).where(Report.id == report_id)))
    if report is None:
        raise NotFound("Published report")
    return render_report_csv_response(report)


# ===========================================================================
# Public audience tier of the CCFP Analysis Environment (GAP-BRD-02)
#
# The BRD's fourth sharing audience: "Share CCFP Aggregated Data and CCFP
# Analysis Environment data with the Public (data will have no PII, summary
# de-identified data only)."
#
# Two independent conditions must both hold before a dataset appears here, and
# neither is expressed only in this file:
#   * an ACTIVE share row with audience = PUBLIC, and
#   * pii_level = DEIDENTIFIED_SUMMARY, which the database trigger
#     ``analysis_shares_enforce_pii`` already requires before such a share can be
#     created at all.
# The redundancy is deliberate. This is the one unauthenticated read path in the
# application, so it re-states the condition rather than trusting that the share
# row could only have been created through the guarded path.
# ===========================================================================
class PublicDatasetOut(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    description: str | None = None
    version_no: int | None = None
    materialized_at: dt.datetime | None = None
    row_count: int | None = None
    columns: list[str] = []
    update_cadence: str | None = None


def _public_dataset_stmt():
    """Datasets cleared for public release, joined to their live PUBLIC share."""
    return (
        select(AnalysisDataset, AnalysisShare, AnalysisDatasetVersion)
        .join(AnalysisShare, AnalysisShare.dataset_id == AnalysisDataset.id)
        .outerjoin(
            AnalysisDatasetVersion,
            AnalysisDatasetVersion.id == AnalysisDataset.current_version_id,
        )
        .where(
            AnalysisShare.status == "ACTIVE",
            AnalysisShare.audience == "PUBLIC",
            AnalysisDataset.status == "ACTIVE",
            AnalysisDataset.pii_level == "DEIDENTIFIED_SUMMARY",
        )
    )


@router.get("/analysis-datasets", response_model=list[PublicDatasetOut])
def public_analysis_datasets(db: Session = Depends(get_db)):
    """De-identified summary datasets published from the CCFP Analysis Environment."""
    out: list[PublicDatasetOut] = []
    for dataset, share, version in db.execute(_public_dataset_stmt().order_by(AnalysisDataset.name)):
        out.append(
            PublicDatasetOut(
                id=dataset.id,
                code=dataset.code,
                name=dataset.name,
                description=dataset.description,
                version_no=version.version_no if version else None,
                materialized_at=version.materialized_at if version else None,
                row_count=version.row_count if version else None,
                columns=list(version.columns or []) if version else [],
                update_cadence=share.refresh_cadence,
            )
        )
    return out


@router.get("/embed")
def public_embed(token: str = Query(...), db: Session = Depends(get_db)):
    """Serve an embedded dashboard's data for a signed embed token.

    BRD p.15: "Provide ability to embed or link dashboards to secure portals and
    public websites (with appropriate data filters)."

    The token is deliberately NOT a capability. It names a dataset and an
    optional row filter; it does not grant access. Every request re-checks the
    live PUBLIC share through the same `_public_dataset_stmt()` the open
    endpoints use, so revoking the share instantly kills every embed of it, and
    a token can never reach a dataset that was never published. The filter can
    only narrow what the share already permits — "appropriate data filters" is a
    scoping instruction, not a widening one.

    Tokens expire (`signed_url_ttl_minutes`), which is why the embed response
    also carries `dataset_id`: a host page can re-mint a link from the public
    dataset id without storing anything sensitive.
    """
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except jwt.ExpiredSignatureError:
        raise BadRequest("Embed link has expired; generate a new one") from None
    except jwt.PyJWTError:
        raise BadRequest("Embed link is not valid") from None
    if payload.get("kind") != "embed":
        raise BadRequest("Embed link is not valid")

    try:
        dataset_id = uuid.UUID(str(payload.get("dataset_id")))
    except (TypeError, ValueError):
        raise BadRequest("Embed link is not valid") from None

    row = db.execute(_public_dataset_stmt().where(AnalysisDataset.id == dataset_id)).first()
    if row is None:
        # Either never published or the share was revoked since the link was cut.
        raise NotFound("Published dataset")
    dataset, share, version = row
    if version is None:
        raise NotFound("Published dataset version")

    rows = [
        r.data
        for r in db.scalars(
            select(AnalysisDatasetRow)
            .where(AnalysisDatasetRow.version_id == version.id)
            .order_by(AnalysisDatasetRow.row_index)
        )
    ]

    # Apply the embed's filters. Unknown columns are ignored rather than
    # erroring: a host page pinned to a column that a later dataset version
    # dropped should degrade to the unfiltered view, not break.
    filters = payload.get("filters") or {}
    columns = set(version.columns or [])
    applied = {k: v for k, v in filters.items() if k in columns}
    for key, value in applied.items():
        rows = [r for r in rows if str(r.get(key)) == str(value)]

    return {
        "dataset_id": str(dataset.id),
        "dataset": dataset.code,
        "name": dataset.name,
        "description": dataset.description,
        "version_no": version.version_no,
        "materialized_at": version.materialized_at.isoformat() if version.materialized_at else None,
        "update_cadence": share.refresh_cadence,
        "columns": list(version.columns or []),
        "filters_applied": applied,
        "filters_ignored": sorted(set(filters) - set(applied)),
        "row_count": len(rows),
        "rows": rows,
    }


@router.get("/analysis-datasets/{dataset_id}/rows")
def public_analysis_dataset_rows(dataset_id: uuid.UUID, db: Session = Depends(get_db)):
    """Rows of a publicly shared, de-identified summary dataset.

    Unpaginated on purpose: a dataset that reaches this endpoint is a summary
    (grouped aggregates, not records), so the whole thing is small and a public
    consumer harvesting it should not have to walk pages. A dataset large enough
    to need paging here would not satisfy "summary de-identified data only".
    """
    row = db.execute(_public_dataset_stmt().where(AnalysisDataset.id == dataset_id)).first()
    if row is None:
        raise NotFound("Published dataset")
    dataset, share, version = row
    if version is None:
        raise NotFound("Published dataset version")
    rows = list(
        db.scalars(
            select(AnalysisDatasetRow)
            .where(AnalysisDatasetRow.version_id == version.id)
            .order_by(AnalysisDatasetRow.row_index)
        )
    )
    return {
        "dataset": dataset.code,
        "name": dataset.name,
        "version_no": version.version_no,
        "materialized_at": version.materialized_at.isoformat() if version.materialized_at else None,
        "update_cadence": share.refresh_cadence,
        "columns": list(version.columns or []),
        "rows": [r.data for r in rows],
    }
