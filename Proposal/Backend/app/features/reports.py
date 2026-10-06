"""Reports: create, share, publish, download (documentation §12.6, §8.9)."""
from __future__ import annotations

import csv
import datetime as dt
import io
import re
import uuid
from typing import Any

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.common import ORMModel
from app.core.audit import record_audit
from app.core.database import get_db
from app.core.errors import BadRequest, Forbidden, NotFound
from app.core.notifications import create_notification, users_with_role
from app.core.permissions import require
from app.core.security import (
    FMCSA_FEDERAL_ROLES,
    OTHER_FEDERAL_ROLES,
    CurrentUser,
    get_current_user,
)
from app.enums import ReportType, ReportVisibility, ShareAudience
from app.models import RefUsState, Report, ReportShare, Role, User

# The Jan-2026 BRD splits the federal audience in two — FMCSA
# Federal Users and Other Federal Users (BTS, NHTSA, NTSB) — because they
# receive data through different sharing actions with different authorization
# rows. Both tiers are sourced from the single backend grouping map in
# core/security.py so the audience model cannot drift between the two files.
#
# SYSTEM_ADMIN is added to the FMCSA tier here (not in ROLE_GROUPS, which
# describes business audiences) because it holds every permission and must not
# lose report visibility it already had.
FMCSA_FEDERAL_ROLE_CODES = set(FMCSA_FEDERAL_ROLES) | {"SYSTEM_ADMIN"}
OTHER_FEDERAL_ROLE_CODES = set(OTHER_FEDERAL_ROLES)
# The union. A FEDERAL-visibility report predates the split and means "the whole
# federal audience", so it stays visible to both tiers.
FEDERAL_ROLE_CODES = FMCSA_FEDERAL_ROLE_CODES | OTHER_FEDERAL_ROLE_CODES

# Audiences only the CCFP Database Administrator may release to.
# The BRD assigns every outward-sharing row to the DBA (FMCSA CTO Resource); the
# Project Team keeps sharing dashboards, but only within FMCSA Federal.
DBA_ONLY_AUDIENCES = {
    ShareAudience.OTHER_FEDERAL.value,
    ShareAudience.STATE.value,
    ShareAudience.PUBLIC.value,
}
OUTWARD_SHARING_ROLE_CODES = {"CCFP_DB_ADMIN", "SYSTEM_ADMIN"}

router = APIRouter(tags=["reports"])


class ReportIn(BaseModel):
    name: str
    report_type: ReportType = ReportType.REPORT
    study_id: uuid.UUID | None = None
    description: str | None = None
    definition: dict[str, Any] | None = None
    visibility: ReportVisibility = ReportVisibility.PRIVATE
    # Bind a STATE-visibility report to one State. None = not
    # State-bound (visible to every State user).
    state_code: str | None = None
    is_deidentified: bool = False


class ReportUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    definition: dict[str, Any] | None = None
    visibility: ReportVisibility | None = None
    state_code: str | None = None
    is_deidentified: bool | None = None


class ReportOut(ORMModel):
    id: uuid.UUID
    name: str
    report_type: str
    study_id: uuid.UUID | None
    description: str | None
    definition: Any | None
    visibility: str
    state_code: str | None
    is_published: bool
    is_deidentified: bool
    owner_id: uuid.UUID | None
    published_at: dt.datetime | None


class ShareIn(BaseModel):
    shared_with_user_id: uuid.UUID | None = None
    shared_with_role_code: str | None = None
    shared_with_org_id: uuid.UUID | None = None
    # Release to an audience tier rather than a named target. Only
    # the CCFP Database Administrator may use OTHER_FEDERAL / STATE / PUBLIC.
    audience: ShareAudience | None = None
    audience_state_code: str | None = None
    can_download: bool = False


def _share_conditions(current: CurrentUser) -> list:
    """Share-match predicates: a share targeting the caller by user, org, role,
    or audience tier.

    Role shares (ANAL-3) resolve ``current.role_codes`` to ``roles.id`` via a
    correlated subquery (``CurrentUser`` carries codes, not ids). The empty-roles
    case is guarded so an empty ``IN ()`` never degrades into "match everything".

    Audience shares are matched here too. A release to an audience tier has to
    actually reach that audience, otherwise the share row is inert bookkeeping —
    so the tier is matched here alongside the directed targets. A STATE-audience
    share is additionally confined to the named State, carrying the BRD's "Only
    View Own Data" rule through the sharing path as well as the report path.
    """
    share_conditions = [
        ReportShare.shared_with_user_id == current.id,
        ReportShare.shared_with_org_id == current.organization_id,
    ]
    if current.role_codes:
        role_ids = select(Role.id).where(Role.code.in_(current.role_codes))
        share_conditions.append(ReportShare.shared_with_role_id.in_(role_ids))

    if current.role_codes & FMCSA_FEDERAL_ROLE_CODES:
        share_conditions.append(ReportShare.audience == ShareAudience.FMCSA_FEDERAL.value)
    if current.role_codes & OTHER_FEDERAL_ROLE_CODES:
        share_conditions.append(ReportShare.audience == ShareAudience.OTHER_FEDERAL.value)
    if current.allowed_states is not None:
        share_conditions.append(
            and_(
                ReportShare.audience == ShareAudience.STATE.value,
                ReportShare.audience_state_code.in_(current.allowed_states),
            )
        )
    else:
        # Unrestricted by State — sees State-audience releases, mirroring how
        # scope_crash_query and _visible_filter treat an unscoped principal.
        share_conditions.append(ReportShare.audience == ShareAudience.STATE.value)
    share_conditions.append(ReportShare.audience == ShareAudience.PUBLIC.value)
    return share_conditions


def _validated_state_code(db: Session, raw: str | None, current: CurrentUser) -> str | None:
    """Normalise and validate a report's State binding.

    ``None``/blank means "not State-bound". An unknown code is a 400 rather than
    a silently-dropped field. A State-scoped author may only bind a report to a
    State they are themselves scoped to — otherwise the read-side fix could be
    sidestepped by mislabelling a report on the way in.
    """
    if raw is None:
        return None
    code = raw.strip().upper()
    if not code:
        return None
    if db.get(RefUsState, code) is None:
        raise BadRequest(f"Unknown State code: {raw}")
    if current.allowed_states is not None and code not in current.allowed_states:
        raise Forbidden(f"Cannot bind a report to {code}: outside your authorized State scope")
    return code


def _visible_filter(current: CurrentUser):
    """Reports the caller may see: owned, published, org-wide for their org,
    shared to them (by user/org/role), or matching the FEDERAL/STATE audience tier.

    AUTH-1/AUTH-2: org and study scope are layered on as additive AND-constraints
    that narrow the whole visible set. An org-restricted caller only sees reports
    owned by users in their org(s); a study-restricted caller only sees reports
    whose study_id is in their authorized set (a report carrying no study_id is
    not study-bound and stays visible). Both are default-permissive: an
    unrestricted caller (org_ids is None / not study_restricted) is unaffected,
    so existing behaviour is preserved."""
    conditions = [Report.owner_id == current.id, Report.is_published.is_(True)]
    if current.organization_id:
        conditions.append((Report.visibility == "ORGANIZATION"))
    # ANAL-12: FEDERAL reports are visible to federal-role callers; STATE reports
    # are visible to State-scoped callers (allowed_states is not None).
    # A legacy FEDERAL report addresses the whole federal audience;
    # the two new tiers address exactly one each, so an Other-Federal consumer
    # (BTS/NHTSA/NTSB) never sees an FMCSA-internal report and vice versa. A
    # producer still sees their own work through the owner_id condition above.
    if current.role_codes & FEDERAL_ROLE_CODES:
        conditions.append(Report.visibility == ReportVisibility.FEDERAL.value)
    if current.role_codes & FMCSA_FEDERAL_ROLE_CODES:
        conditions.append(Report.visibility == ReportVisibility.FMCSA_FEDERAL.value)
    if current.role_codes & OTHER_FEDERAL_ROLE_CODES:
        conditions.append(Report.visibility == ReportVisibility.OTHER_FEDERAL.value)
    if current.allowed_states is not None:
        # "Participating State Users (No PII, Only View Own Data)".
        # A State-scoped caller sees a STATE report only when it is unbound
        # (state_code IS NULL — not State-specific, and the state of every report
        # created before this column existed) or bound to a State they are scoped
        # to. Without the second predicate this granted every State user every
        # STATE report, so a Kansas analyst could read a Texas report.
        conditions.append(
            and_(
                Report.visibility == ReportVisibility.STATE.value,
                or_(
                    Report.state_code.is_(None),
                    Report.state_code.in_(current.allowed_states),
                ),
            )
        )
    # ANAL-3: role shares now grant visibility alongside user/org shares.
    shared_ids = select(ReportShare.report_id).where(or_(*_share_conditions(current)))
    conditions.append(Report.id.in_(shared_ids))

    visible = or_(*conditions)
    scope_constraints = []
    # AUTH-1: confine to reports owned by users in the caller's authorized org(s).
    if current.org_ids is not None:
        org_owner_ids = select(User.id).where(User.organization_id.in_(current.org_ids))
        scope_constraints.append(Report.owner_id.in_(org_owner_ids))
    # AUTH-2: confine to reports in the caller's authorized study set; a report
    # with no study_id is not study-bound and remains visible.
    if current.study_restricted and current.study_ids:
        scope_constraints.append(
            or_(Report.study_id.is_(None), Report.study_id.in_(current.study_ids))
        )
    if scope_constraints:
        return and_(visible, *scope_constraints)
    return visible


@router.get("/reports", response_model=list[ReportOut])
def list_reports(report_type: ReportType | None = None, db: Session = Depends(get_db), current: CurrentUser = Depends(require("report:read"))):
    stmt = select(Report).where(_visible_filter(current)).order_by(Report.created_at.desc())
    if report_type:
        stmt = stmt.where(Report.report_type == report_type.value)
    return list(db.scalars(stmt))


@router.post("/reports", response_model=ReportOut, status_code=201)
def create_report(body: ReportIn, db: Session = Depends(get_db), current: CurrentUser = Depends(require("report:create"))):
    data = body.model_dump()
    data["report_type"] = body.report_type.value
    data["visibility"] = body.visibility.value
    data["state_code"] = _validated_state_code(db, body.state_code, current)
    report = Report(owner_id=current.id, **data)
    db.add(report)
    db.flush()
    record_audit(db, actor=current, action="CREATE", entity_type="report", entity_id=report.id)
    db.commit()
    return report


def _load_report(db: Session, report_id: uuid.UUID) -> Report:
    report = db.get(Report, report_id)
    if report is None:
        raise NotFound("Report")
    return report


@router.get("/reports/{report_id}", response_model=ReportOut)
def get_report(report_id: uuid.UUID, db: Session = Depends(get_db), current: CurrentUser = Depends(require("report:read"))):
    # Enforce the same visibility/share scoping as list_reports: a caller who may
    # not see the report gets 404 (no existence disclosure), not the report.
    report = db.scalar(select(Report).where(Report.id == report_id, _visible_filter(current)))
    if report is None:
        raise NotFound("Report")
    return report


@router.patch("/reports/{report_id}", response_model=ReportOut)
def update_report(report_id: uuid.UUID, body: ReportUpdate, db: Session = Depends(get_db), current: CurrentUser = Depends(require("report:create"))):
    report = _load_report(db, report_id)
    if report.owner_id != current.id and not current.has_permission("admin:system"):
        raise Forbidden("Only the owner can edit this report")
    updates = body.model_dump(exclude_unset=True)
    # Re-validate a changed State binding; an unsent state_code is
    # left untouched (exclude_unset), so an unrelated PATCH cannot silently
    # unbind a report and widen its audience.
    if "state_code" in updates:
        updates["state_code"] = _validated_state_code(db, body.state_code, current)
    for k, v in updates.items():
        setattr(report, k, v.value if hasattr(v, "value") else v)
    record_audit(db, actor=current, action="UPDATE", entity_type="report", entity_id=report.id)
    db.commit()
    return report


@router.delete("/reports/{report_id}", status_code=204)
def delete_report(report_id: uuid.UUID, db: Session = Depends(get_db), current: CurrentUser = Depends(require("report:create"))):
    report = _load_report(db, report_id)
    if report.owner_id != current.id and not current.has_permission("admin:system"):
        raise Forbidden("Only the owner can delete this report")
    db.delete(report)
    record_audit(db, actor=current, action="DELETE", entity_type="report", entity_id=report_id)
    db.commit()
    return None


@router.post("/reports/{report_id}/share", status_code=201)
def share_report(report_id: uuid.UUID, body: ShareIn, db: Session = Depends(get_db), current: CurrentUser = Depends(require("report:share"))):
    report = _load_report(db, report_id)
    role_id = None
    if body.shared_with_role_code:
        role = db.scalar(select(Role).where(Role.code == body.shared_with_role_code))
        if role is None:
            raise BadRequest("Unknown role code")
        role_id = role.id
    if not any([body.shared_with_user_id, role_id, body.shared_with_org_id, body.audience]):
        raise BadRequest("Specify a user, role, organization, or audience to share with")

    # The Jan-2026 BRD assigns every OUTWARD sharing row — Other
    # Federal (BTS/NHTSA/NTSB), participating States, and the Public — to the
    # CCFP Database Administrator. The Project Team keeps report:share for
    # dashboards but is confined to the FMCSA Federal tier. Enforced here rather
    # than only in the seed, because a permission grant alone cannot express
    # "may share, but not to that audience".
    audience = body.audience.value if body.audience else None
    audience_state = None
    if audience:
        if audience in DBA_ONLY_AUDIENCES and not (
            current.role_codes & OUTWARD_SHARING_ROLE_CODES
        ):
            raise Forbidden(
                f"Sharing to the {audience} audience is reserved to the CCFP "
                "Database Administrator (BRD Jan-2026 Manage/Share access table)"
            )
        if audience == ShareAudience.STATE.value:
            audience_state = _validated_state_code(db, body.audience_state_code, current)
            if audience_state is None:
                raise BadRequest("A STATE-audience share must name the State it targets")
        elif body.audience_state_code:
            raise BadRequest("audience_state_code applies only to a STATE-audience share")

    share = ReportShare(
        report_id=report.id, shared_with_user_id=body.shared_with_user_id,
        shared_with_role_id=role_id, shared_with_org_id=body.shared_with_org_id,
        audience=audience, audience_state_code=audience_state,
        can_download=body.can_download, shared_by=current.id,
    )
    db.add(share)
    db.flush()
    # Releasing to an audience is a disclosure decision, so the tier (and the
    # State, when there is one) is recorded, not just the share id.
    record_audit(
        db, actor=current, action="SHARE", entity_type="report", entity_id=report.id,
        after={
            "share_id": str(share.id),
            "audience": audience,
            "audience_state_code": audience_state,
        },
    )
    # NOTI-6: notify the share target so the recipient gets an inbox/bell alert.
    # Reports are not crash-scoped, so crash_id is omitted; the report name is
    # carried in the title/message instead.
    if body.shared_with_user_id:
        create_notification(
            db, recipient_user_id=body.shared_with_user_id,
            notification_type="REPORT_SHARED",
            title="A report was shared with you",
            message=f"{report.name} was shared with you.",
        )
    elif role_id:
        for u in users_with_role(db, role.code):
            create_notification(
                db, recipient_user_id=u.id,
                notification_type="REPORT_SHARED",
                title="A report was shared with your role",
                message=f"{report.name} was shared with the {role.code} role.",
            )
    elif body.shared_with_org_id:
        org_users = db.scalars(
            select(User).where(
                User.organization_id == body.shared_with_org_id,
                User.status == "ACTIVE",
            )
        )
        for u in org_users:
            create_notification(
                db, recipient_user_id=u.id,
                notification_type="REPORT_SHARED",
                title="A report was shared with your organization",
                message=f"{report.name} was shared with your organization.",
            )
    db.commit()
    return {"share_id": str(share.id), "report_id": str(report.id)}


@router.post("/reports/{report_id}/publish", response_model=ReportOut)
def publish_report(report_id: uuid.UUID, db: Session = Depends(get_db), current: CurrentUser = Depends(require("report:publish"))):
    report = _load_report(db, report_id)
    if not report.is_deidentified:
        raise BadRequest("Report must be de-identified before publication (documentation §7, §14)")
    report.is_published = True
    report.visibility = ReportVisibility.PUBLIC.value
    report.published_at = dt.datetime.now(dt.timezone.utc)
    record_audit(db, actor=current, action="PUBLISH", entity_type="report", entity_id=report.id)
    # NOTI-6: notify the publication audience (the report owner plus the Federal
    # User consumers) so newly published reports surface in the inbox/bell.
    notified: set[uuid.UUID] = set()
    if report.owner_id:
        create_notification(
            db, recipient_user_id=report.owner_id,
            notification_type="REPORT_PUBLISHED",
            title="Your report is now published",
            message=f"{report.name} is now published.",
        )
        notified.add(report.owner_id)
    for u in users_with_role(db, "FEDERAL_USER"):
        if u.id in notified:
            continue
        notified.add(u.id)
        create_notification(
            db, recipient_user_id=u.id,
            notification_type="REPORT_PUBLISHED",
            title="New published report",
            message=f"{report.name} is now published.",
        )
    db.commit()
    return report


def _safe_filename(name: str | None) -> str:
    """Normalise a report name into a safe CSV filename stem."""
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", (name or "report").strip()).strip("_")
    return stem or "report"


def _render_csv(report: Report) -> str:
    """Render a report's ``definition`` JSON into CSV text (stdlib csv/io only).

    Recognises the known definition shapes and degrades gracefully:
      * ``{"columns": [...], "rows": [...]}`` or ``{"rows": [...]}`` -> header + data rows
      * ``{"metrics": [...]}`` / ``{"widgets": [...]}`` / other scalars -> key,value table
    A small header block (report name, generated_at) leads every export.
    """
    buf = io.StringIO()
    writer = csv.writer(buf)
    generated_at = dt.datetime.now(dt.timezone.utc).isoformat()
    writer.writerow(["report", report.name])
    writer.writerow(["generated_at", generated_at])
    writer.writerow([])

    definition = report.definition if isinstance(report.definition, dict) else {}
    rows = definition.get("rows")

    if isinstance(rows, list) and rows:
        columns = definition.get("columns")
        if not isinstance(columns, list) or not columns:
            # Derive columns from the union of keys across dict rows (stable order).
            columns = []
            for row in rows:
                if isinstance(row, dict):
                    for key in row:
                        if key not in columns:
                            columns.append(key)
        writer.writerow([str(c) for c in columns])
        for row in rows:
            if isinstance(row, dict):
                writer.writerow([row.get(c, "") for c in columns])
            elif isinstance(row, (list, tuple)):
                writer.writerow(list(row))
            else:
                writer.writerow([row])
        return buf.getvalue()

    # Scalar / metrics / widgets shapes -> a two-column key,value table.
    metrics = definition.get("metrics") if isinstance(definition, dict) else None
    writer.writerow(["key", "value"])
    if isinstance(metrics, list) and metrics:
        for metric in metrics:
            if isinstance(metric, dict):
                label = metric.get("label") or metric.get("name") or metric.get("key") or ""
                value = metric.get("value", "")
                writer.writerow([label, value])
            else:
                writer.writerow([metric, ""])
    elif definition:
        for key, value in definition.items():
            if isinstance(value, (dict, list)):
                writer.writerow([key, _json_compact(value)])
            else:
                writer.writerow([key, value])
    return buf.getvalue()


def _json_compact(value: Any) -> str:
    import json

    return json.dumps(value, separators=(",", ":"), default=str)


def render_report_csv_response(report: Report) -> Response:
    """Build a downloadable ``text/csv`` attachment Response for a report.

    Shared by the authenticated and (future) public download routes.
    """
    content = _render_csv(report)
    filename = f"{_safe_filename(report.name)}.csv"
    return Response(
        content=content,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _can_download(db: Session, current: CurrentUser, report: Report) -> bool:
    """ANAL-4: download authorization layered on the report:download permission.

    Permitted when the caller is the owner/admin, the report is published, or a
    ReportShare targeting them (by user/org/role) sets can_download = True.
    """
    if report.owner_id == current.id or current.has_permission("admin:system"):
        return True
    if report.is_published:
        return True
    grant = db.scalar(
        select(ReportShare.id).where(
            ReportShare.report_id == report.id,
            ReportShare.can_download.is_(True),
            or_(*_share_conditions(current)),
        )
    )
    return grant is not None


@router.get("/reports/{report_id}/download")
def download_report(report_id: uuid.UUID, db: Session = Depends(get_db), current: CurrentUser = Depends(require("report:download"))):
    # First enforce visibility: a caller who may not even see the report gets 404
    # (no existence disclosure), matching get_report.
    report = db.scalar(select(Report).where(Report.id == report_id, _visible_filter(current)))
    if report is None:
        raise NotFound("Report")
    if not _can_download(db, current, report):
        record_audit(db, actor=current, action="DOWNLOAD_DENIED", entity_type="report", entity_id=report.id)
        db.commit()
        raise Forbidden("Download not permitted for this report")
    response = render_report_csv_response(report)
    record_audit(db, actor=current, action="DOWNLOAD", entity_type="report", entity_id=report.id)
    db.commit()
    return response
