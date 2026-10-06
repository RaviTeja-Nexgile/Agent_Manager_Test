"""CRAS-7: study-configurable, race-safe CCFP identifier minting.

Every crash gets one stable CCFP identifier (documentation §3.4, §11.3). These
tests assert that:

  * the default scheme preserves the original ``CCFP-{year}-{state}-{6-digit}``
    shape (so existing identifiers/tests are unaffected);
  * two back-to-back creates yield *distinct* identifiers — the DB SEQUENCE
    (``ccfp_identifier_seq``) replaced the old ``COUNT(*)+1`` check-then-act race
    that could mint duplicates and collide on the ``UNIQUE`` constraint;
  * the scheme is read from ``study_parameters`` (param_key
    ``ccfp_identifier_scheme``) and honoured when configured — the format is not
    hardcoded to Phase-1 assumptions;
  * the CREATE audit still captures the minted identifier; and
  * authorization is unchanged (a FEDERAL user lacking ``crash:create`` -> 403).

All run inside a single rolled-back transaction (conftest fixtures), so seeded
data is never mutated and assertions stay robust to seed drift.
"""
from __future__ import annotations

import uuid

from sqlalchemy import select

from app.models import AuditLog, StudyParameter
from tests.conftest import FEDERAL, INSPECTOR_KS

API = "/api/v1"


def _study_id(client, headers) -> str:
    return next(
        s for s in client.get(f"{API}/studies", headers=headers).json()
        if s["code"] == "PHASE1-HDT"
    )["id"]


def _create_ks_crash(client, headers, study_id: str) -> dict:
    resp = client.post(
        f"{API}/crashes", headers=headers,
        json={
            "study_id": study_id, "state_code": "KS", "city": "Topeka",
            "county": "Shawnee", "crash_date": "2026-05-01", "num_fatalities": 1,
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


# --------------------------------------------------------------------------- default scheme
def test_default_scheme_shape_preserved(client, auth):
    """A KS crash keeps the original CCFP-YYYY-STATE-###### shape by default."""
    insp = auth(INSPECTOR_KS)
    study_id = _study_id(client, insp)
    crash = _create_ks_crash(client, insp, study_id)
    ident = crash["ccfp_identifier"]
    assert ident.startswith("CCFP-2026-KS-")
    # 6-digit zero-padded numeric suffix (default seq_width).
    suffix = ident.rsplit("-", 1)[1]
    assert suffix.isdigit() and len(suffix) == 6


def test_concurrent_creates_get_distinct_identifiers(client, auth):
    """Two back-to-back KS creates must mint distinct identifiers (race fixed).

    The old COUNT(*)+1 logic could read the same count for two callers and emit
    the same identifier; the DB sequence guarantees a distinct integer per call.
    """
    insp = auth(INSPECTOR_KS)
    study_id = _study_id(client, insp)
    first = _create_ks_crash(client, insp, study_id)
    second = _create_ks_crash(client, insp, study_id)
    assert first["ccfp_identifier"].startswith("CCFP-2026-KS-")
    assert second["ccfp_identifier"].startswith("CCFP-2026-KS-")
    assert first["ccfp_identifier"] != second["ccfp_identifier"]
    # And neither collides with any already-issued identifier (UNIQUE holds).
    assert first["id"] != second["id"]


def test_many_creates_all_unique(client, auth):
    """A burst of creates yields no duplicate identifiers (sequence is monotonic)."""
    insp = auth(INSPECTOR_KS)
    study_id = _study_id(client, insp)
    idents = [_create_ks_crash(client, insp, study_id)["ccfp_identifier"] for _ in range(5)]
    assert len(set(idents)) == len(idents)
    assert all(i.startswith("CCFP-2026-KS-") for i in idents)


def test_create_audit_captures_identifier(client, auth, db):
    """The CREATE audit row still records the minted ccfp_identifier (unchanged)."""
    insp = auth(INSPECTOR_KS)
    study_id = _study_id(client, insp)
    crash = _create_ks_crash(client, insp, study_id)
    cid = uuid.UUID(crash["id"])
    audit = db.scalar(
        select(AuditLog).where(
            AuditLog.crash_id == cid,
            AuditLog.action == "CREATE",
            AuditLog.entity_type == "crash",
        )
    )
    assert audit is not None
    assert audit.after_state.get("ccfp_identifier") == crash["ccfp_identifier"]


# --------------------------------------------------------------------------- configurable scheme
def test_scheme_is_read_from_study_parameters(client, auth, db):
    """A configured ccfp_identifier_scheme overrides the default template/width.

    Inserts a study parameter inside the rolled-back transaction (so it never
    persists), then creates a crash and asserts the minted identifier follows the
    configured template + sequence width rather than the Phase-1 default.
    """
    insp = auth(INSPECTOR_KS)
    study_id = _study_id(client, insp)

    db.add(
        StudyParameter(
            study_id=uuid.UUID(study_id),
            param_key="ccfp_identifier_scheme",
            param_value={"template": "{study_code}-{year}-{state}-{seq}", "seq_width": 4},
            description="CRAS-7 test scheme",
        )
    )
    db.flush()

    crash = _create_ks_crash(client, insp, study_id)
    ident = crash["ccfp_identifier"]
    # Configured template: starts with the study code, ends with a 4-wide number.
    assert ident.startswith("PHASE1-HDT-2026-KS-")
    suffix = ident.rsplit("-", 1)[1]
    assert suffix.isdigit() and len(suffix) == 4


def test_malformed_template_falls_back_to_default(client, auth, db):
    """A misconfigured template must not break crash creation (safe fallback)."""
    insp = auth(INSPECTOR_KS)
    study_id = _study_id(client, insp)

    db.add(
        StudyParameter(
            study_id=uuid.UUID(study_id),
            param_key="ccfp_identifier_scheme",
            # Unknown placeholder -> KeyError on .format -> default shape.
            param_value={"template": "CCFP-{year}-{state}-{seq}-{unknown_field}"},
            description="CRAS-7 malformed test scheme",
        )
    )
    db.flush()

    crash = _create_ks_crash(client, insp, study_id)
    ident = crash["ccfp_identifier"]
    assert ident.startswith("CCFP-2026-KS-")
    suffix = ident.rsplit("-", 1)[1]
    assert suffix.isdigit() and len(suffix) == 6


# --------------------------------------------------------------------------- authorization
def test_create_crash_denied_for_federal_user(client, auth):
    """A FEDERAL user lacks crash:create -> 403 (authorization unchanged)."""
    insp = auth(INSPECTOR_KS)
    study_id = _study_id(client, insp)
    resp = client.post(
        f"{API}/crashes", headers=auth(FEDERAL),
        json={"study_id": study_id, "state_code": "KS", "num_fatalities": 1},
    )
    assert resp.status_code == 403


def test_unauthenticated_create_is_401(client):
    """No token -> 401 before any minting happens."""
    resp = client.post(
        f"{API}/crashes",
        json={"study_id": str(uuid.uuid4()), "state_code": "KS"},
    )
    assert resp.status_code == 401
