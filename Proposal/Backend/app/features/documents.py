"""Documents: upload, metadata, signed-URL download (documentation §8 object storage, §14)."""
from __future__ import annotations

import datetime as dt
import uuid

from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common import ORMModel
from app.core import storage
from app.core.audit import record_audit
from app.core.config import settings
from app.core.database import get_db
from app.core.errors import BadRequest, Forbidden, NotFound
from app.core.permissions import assert_crash_access, require
from app.core.security import CurrentUser, get_current_user
from app.enums import DataSensitivity, DocumentType
from app.models import Crash, Document

router = APIRouter(tags=["documents"])

# SOO: "upload and store crash reconstruction files, including but not limited to
# narrative reports, images, and videos, in various file formats". "Various" is a
# breadth instruction, not an invitation to accept anything — an unbounded upload
# surface on a federal system is an attack surface, and the malware scan below is
# a stand-in rather than a real engine. So the allow-list is deliberately wide
# across the three named categories and closed to everything else.
#
# Keyed by the prefix so a whole family (image/*, video/*) is admitted without
# enumerating every codec container, plus an explicit list for the document
# formats a reconstruction narrative actually arrives in.
_ALLOWED_MIME_PREFIXES: tuple[str, ...] = ("image/", "video/")
_ALLOWED_MIME_TYPES: frozenset[str] = frozenset({
    # Narrative reports and their common exports
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/rtf",
    "text/plain",
    "text/markdown",
    # Tabular source data (ELD CSV arrives through this path too)
    "text/csv",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    # Scene/diagram exchange formats used by reconstruction tools
    "application/zip",
    "image/svg+xml",
    "application/octet-stream",  # browsers send this for unknown-but-legitimate types
})


def _assert_acceptable(content_type: str | None, size: int) -> None:
    """Reject uploads outside the configured ceiling or the accepted formats.

    Size is checked first: an oversized file is rejected on the number we already
    have, so the caller gets the actionable error rather than a type complaint
    about a file that would have been refused anyway.
    """
    limit = settings.max_upload_mb * 1024 * 1024
    if size > limit:
        raise BadRequest(
            f"File is {size / 1024 / 1024:.1f} MB; the maximum accepted upload is "
            f"{settings.max_upload_mb} MB"
        )
    if not content_type:
        # No declared type at all — treat as the generic binary the allow-list
        # already admits rather than guessing from the extension.
        return
    mime = content_type.split(";")[0].strip().lower()
    if mime in _ALLOWED_MIME_TYPES or mime.startswith(_ALLOWED_MIME_PREFIXES):
        return
    raise BadRequest(f"File type '{mime}' is not accepted for CCFP uploads")


class DocumentOut(ORMModel):
    id: uuid.UUID
    crash_id: uuid.UUID | None
    doc_type: str
    file_name: str
    mime_type: str | None
    storage_uri: str
    size_bytes: int | None
    sensitivity: str
    malware_scan: str
    uploaded_at: dt.datetime


@router.post("/documents", response_model=DocumentOut, status_code=201)
def upload_document(
    crash_id: uuid.UUID = Form(...),
    file: UploadFile = File(...),
    doc_type: DocumentType = Form(DocumentType.DOCUMENT),
    sensitivity: DataSensitivity = Form(DataSensitivity.INTERNAL),
    db: Session = Depends(get_db),
    current: CurrentUser = Depends(require("source_data:ingest", "crash:update")),
):
    crash = db.get(Crash, crash_id)
    if crash is None:
        raise BadRequest("Unknown crash_id")
    assert_crash_access(crash, current)
    content = file.file.read()
    _assert_acceptable(file.content_type, len(content))
    scan = storage.scan_for_malware(content)
    if scan == "INFECTED":
        raise BadRequest("Uploaded file failed malware scanning")
    uri, size = storage.put_object(content, key_prefix=f"docs/{crash_id}", file_name=file.filename or "upload.bin")
    doc = Document(
        crash_id=crash_id, doc_type=doc_type.value, file_name=file.filename or "upload.bin",
        mime_type=file.content_type, storage_uri=uri, size_bytes=size,
        sensitivity=sensitivity.value, malware_scan=scan, uploaded_by=current.id,
    )
    db.add(doc)
    db.flush()
    record_audit(db, actor=current, action="UPLOAD", entity_type="document", entity_id=doc.id, crash_id=crash_id)
    db.commit()
    return doc


@router.get("/crashes/{crash_id}/documents", response_model=list[DocumentOut])
def list_crash_documents(crash_id: uuid.UUID, db: Session = Depends(get_db), current: CurrentUser = Depends(require("crash:read"))):
    crash = db.get(Crash, crash_id)
    if crash is None:
        raise NotFound("Crash")
    assert_crash_access(crash, current)
    docs = db.scalars(select(Document).where(Document.crash_id == crash_id).order_by(Document.uploaded_at.desc()))
    return [d for d in docs if current.can_view_sensitivity(d.sensitivity)]


def _load_doc(db: Session, document_id: uuid.UUID, current: CurrentUser) -> Document:
    doc = db.get(Document, document_id)
    if doc is None:
        raise NotFound("Document")
    if not current.can_view_sensitivity(doc.sensitivity):
        raise Forbidden("Insufficient clearance for this document's sensitivity level")
    if doc.crash_id:
        crash = db.get(Crash, doc.crash_id)
        if crash:
            assert_crash_access(crash, current)
    return doc


@router.get("/documents/{document_id}", response_model=DocumentOut)
def get_document(document_id: uuid.UUID, db: Session = Depends(get_db), current: CurrentUser = Depends(require("crash:read"))):
    return _load_doc(db, document_id, current)


@router.get("/documents/{document_id}/download")
def download_document(document_id: uuid.UUID, db: Session = Depends(get_db), current: CurrentUser = Depends(require("crash:read"))):
    doc = _load_doc(db, document_id, current)
    return {"signed_url": storage.make_signed_url(doc.storage_uri), "expires_in_minutes": storage.settings.signed_url_ttl_minutes}


@router.get("/documents/blob")
def get_blob(token: str = Query(...)):
    """Serve object bytes for a valid signed token (stand-in for cloud signed URL)."""
    try:
        uri = storage.verify_signed_token(token)
        content = storage.read_object(uri)
    except Exception as exc:  # noqa: BLE001
        raise NotFound("Object or token invalid") from exc
    return Response(content=content, media_type="application/octet-stream")
