"""Object storage abstraction.

Development stand-in for encrypted cloud object storage with signed-URL access
(documentation §6, §14). Files are written under `settings.storage_dir`; a
short-lived signed token gates downloads. A mock malware scan marks uploads
CLEAN. Swap this module for a real S3/GCS client + AV pipeline in production.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import uuid
from pathlib import Path

import jwt

from app.core.config import settings
from app.enums import MalwareScanStatus


def _root() -> Path:
    root = Path(settings.storage_dir).resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def put_object(content: bytes, *, key_prefix: str, file_name: str) -> tuple[str, int]:
    """Store bytes; return (storage_uri, size_bytes)."""
    obj_id = uuid.uuid4().hex
    safe_name = Path(file_name).name
    rel = f"{key_prefix.strip('/')}/{obj_id}_{safe_name}"
    path = _root() / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return f"file://{rel}", len(content)


def scan_for_malware(content: bytes) -> str:
    """Mock AV scan. Flags the EICAR test signature; otherwise CLEAN."""
    if b"EICAR-STANDARD-ANTIVIRUS-TEST-FILE" in content:
        return MalwareScanStatus.INFECTED.value
    return MalwareScanStatus.CLEAN.value


def make_signed_url(storage_uri: str) -> str:
    now = dt.datetime.now(dt.timezone.utc)
    token = jwt.encode(
        {
            "uri": storage_uri,
            "exp": now + dt.timedelta(minutes=settings.signed_url_ttl_minutes),
        },
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )
    return f"/api/v1/documents/blob?token={token}"


def verify_signed_token(token: str) -> str:
    payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    return payload["uri"]


def read_object(storage_uri: str) -> bytes:
    rel = storage_uri.replace("file://", "", 1)
    path = _root() / rel
    return path.read_bytes()


def content_digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()
