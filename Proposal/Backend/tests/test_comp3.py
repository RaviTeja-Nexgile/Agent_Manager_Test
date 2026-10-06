"""COMP-3 (#70): audit_logs immutability enforced at the DATABASE level.

Spec §14.2 (immutable audit logs for state-changing actions) / §11.1 (audit_logs
= immutable audit event records). Migration 0003_audit_immutability.sql installs a
BEFORE UPDATE OR DELETE trigger (ccfp_block_audit_mutation) that RAISEs an
exception, plus a REVOKE of UPDATE/DELETE as defense-in-depth.

These tests use the `db` fixture (a single connection whose outer transaction is
rolled back on teardown; nested commits become SAVEPOINTs). They prove:
  * INSERT into audit_logs still works (append path unchanged);
  * a direct UPDATE raises a database error and leaves the row unchanged;
  * a direct DELETE raises a database error and leaves the row present.

Defense-in-depth note: the migration installs BOTH a trigger (raises
"audit_logs is append-only: ...") AND a REVOKE of UPDATE/DELETE on the app role.
The application role connects as a NON-owner of the table, so the REVOKE is
genuinely effective: PostgreSQL rejects the statement with InsufficientPrivilege
("permission denied for table audit_logs") at the privilege layer, BEFORE the
BEFORE-trigger ever fires. Either rejection (privilege denial or the trigger's
append-only message) is a valid immutability guarantee, so the assertion accepts
both — the load-bearing fact is that the mutation is blocked at the DB and the
row is untouched.

Each mutating attempt is wrapped in a SAVEPOINT (db.begin_nested) so the error
aborts only that nested block, leaving the session usable afterwards.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

# Substrings that prove the DB itself rejected the mutation (either guard layer).
_BLOCKED_MARKERS = ("append-only", "permission denied")


def _insert_audit_row(db) -> uuid.UUID:
    """Insert one audit_logs row via raw SQL and return its id (INSERT path works)."""
    row_id = uuid.uuid4()
    db.execute(
        text(
            "INSERT INTO audit_logs (id, action, entity_type) "
            "VALUES (:id, :action, :entity_type)"
        ),
        {"id": row_id, "action": "CREATE", "entity_type": "test_comp3"},
    )
    db.flush()
    return row_id


def test_audit_insert_succeeds(db):
    """The append path must still work: a fresh audit row inserts and is readable."""
    row_id = _insert_audit_row(db)
    found = db.execute(
        text("SELECT action FROM audit_logs WHERE id = :id"), {"id": row_id}
    ).scalar_one()
    assert found == "CREATE"


def test_audit_update_is_blocked(db):
    """A direct UPDATE of an existing audit_logs row must raise a DB error."""
    row_id = _insert_audit_row(db)

    with pytest.raises(DBAPIError) as exc_info:
        with db.begin_nested():  # SAVEPOINT so the abort is contained
            db.execute(
                text("UPDATE audit_logs SET action = 'TAMPER' WHERE id = :id"),
                {"id": row_id},
            )
            db.flush()
    assert any(m in str(exc_info.value).lower() for m in _BLOCKED_MARKERS)

    # Session remains usable and the row is unchanged (UPDATE never applied).
    still = db.execute(
        text("SELECT action FROM audit_logs WHERE id = :id"), {"id": row_id}
    ).scalar_one()
    assert still == "CREATE"


def test_audit_delete_is_blocked(db):
    """A direct DELETE of an existing audit_logs row must raise a DB error."""
    row_id = _insert_audit_row(db)

    with pytest.raises(DBAPIError) as exc_info:
        with db.begin_nested():  # SAVEPOINT so the abort is contained
            db.execute(
                text("DELETE FROM audit_logs WHERE id = :id"),
                {"id": row_id},
            )
            db.flush()
    assert any(m in str(exc_info.value).lower() for m in _BLOCKED_MARKERS)

    # Session remains usable and the row still exists (DELETE never applied).
    count = db.execute(
        text("SELECT count(*) FROM audit_logs WHERE id = :id"), {"id": row_id}
    ).scalar_one()
    assert count == 1
