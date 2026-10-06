#!/usr/bin/env python3
"""CCFP database migration & seed runner.

This runner intentionally has ZERO third-party dependencies beyond psycopg2,
so it can bootstrap the database before the full FastAPI/SQLAlchemy stack
exists.

Per the project rule in CLAUDE.md, the PostgreSQL connection string is ALWAYS
read from CLAUDE.md (or the DATABASE_URL environment variable if explicitly
set) — it is never hardcoded here.

Usage:
    python migrate.py status          # show applied / pending files
    python migrate.py migrate         # apply pending schema migrations only
    python migrate.py seed            # apply pending seed files only
    python migrate.py up              # apply migrations, then seeds (default)

Each .sql file in migrations/ and seeds/ is applied exactly once (tracked in
the ccfp_schema_migrations table) inside its own transaction.
"""
from __future__ import annotations

import hashlib
import os
import re
import sys
from pathlib import Path

import psycopg2

HERE = Path(__file__).resolve().parent
MIGRATIONS_DIR = HERE / "migrations"
SEEDS_DIR = HERE / "seeds"


def find_connection_string() -> str:
    """Resolve the DB connection string.

    Priority:
      1. DATABASE_URL environment variable (if set).
      2. The postgresql:// URL found in the nearest CLAUDE.md (walking upward).
    """
    env = os.environ.get("DATABASE_URL")
    if env:
        return env

    pattern = re.compile(r"postgresql://[^\s`'\"<>]+")
    for parent in [HERE, *HERE.parents]:
        candidate = parent / "CLAUDE.md"
        if candidate.exists():
            match = pattern.search(candidate.read_text(encoding="utf-8"))
            if match:
                return match.group(0)
    raise SystemExit(
        "ERROR: could not find a postgresql:// connection string in CLAUDE.md "
        "and DATABASE_URL is not set."
    )


def ensure_tracking_table(cur) -> None:
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS ccfp_schema_migrations (
            filename     TEXT PRIMARY KEY,
            kind         TEXT NOT NULL,
            checksum     TEXT NOT NULL,
            applied_at   TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """
    )


def applied_set(cur) -> dict[str, str]:
    cur.execute("SELECT filename, checksum FROM ccfp_schema_migrations;")
    return {row[0]: row[1] for row in cur.fetchall()}


def sql_files(directory: Path) -> list[Path]:
    if not directory.exists():
        return []
    return sorted(p for p in directory.iterdir() if p.suffix == ".sql")


def checksum(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def apply_files(conn, directory: Path, kind: str) -> int:
    count = 0
    with conn.cursor() as cur:
        ensure_tracking_table(cur)
        conn.commit()
        already = applied_set(cur)

    for path in sql_files(directory):
        name = path.name
        body = path.read_text(encoding="utf-8")
        digest = checksum(body)
        if name in already:
            if already[name] != digest:
                print(f"  ! {name} already applied but checksum CHANGED "
                      f"(stored {already[name]} != current {digest}) — skipping")
            else:
                print(f"  = {name} (already applied)")
            continue
        print(f"  + applying {name} ...", end="", flush=True)
        try:
            with conn.cursor() as cur:
                cur.execute(body)
                cur.execute(
                    "INSERT INTO ccfp_schema_migrations (filename, kind, checksum) "
                    "VALUES (%s, %s, %s);",
                    (name, kind, digest),
                )
            conn.commit()
            print(" done")
            count += 1
        except Exception as exc:  # noqa: BLE001
            conn.rollback()
            print(" FAILED")
            print(f"\nERROR while applying {name}:\n{exc}")
            raise SystemExit(1)
    return count


def cmd_status(conn) -> None:
    with conn.cursor() as cur:
        ensure_tracking_table(cur)
        conn.commit()
        already = applied_set(cur)
    for label, directory in (("migrations", MIGRATIONS_DIR), ("seeds", SEEDS_DIR)):
        print(f"\n[{label}]")
        for path in sql_files(directory):
            mark = "applied" if path.name in already else "PENDING"
            print(f"  {mark:8} {path.name}")


def main() -> None:
    command = sys.argv[1] if len(sys.argv) > 1 else "up"
    url = find_connection_string()
    safe = re.sub(r"//([^:]+):[^@]+@", r"//\1:***@", url)
    print(f"Connecting to {safe}")
    conn = psycopg2.connect(url, connect_timeout=15)
    try:
        if command == "status":
            cmd_status(conn)
        elif command == "migrate":
            n = apply_files(conn, MIGRATIONS_DIR, "migration")
            print(f"\nApplied {n} migration file(s).")
        elif command == "seed":
            n = apply_files(conn, SEEDS_DIR, "seed")
            print(f"\nApplied {n} seed file(s).")
        elif command == "up":
            print("Applying schema migrations:")
            m = apply_files(conn, MIGRATIONS_DIR, "migration")
            print("Applying seed data:")
            s = apply_files(conn, SEEDS_DIR, "seed")
            print(f"\nApplied {m} migration file(s) and {s} seed file(s).")
        else:
            raise SystemExit(f"Unknown command: {command}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
