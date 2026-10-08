"""SQLite connection helpers for the software inventory app."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

# Default DB path relative to repo root (parent of app/)
REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = REPO_ROOT / "data" / "inventory.db"
SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"


def get_db_path() -> Path:
    """Return the SQLite database path from INVENTORY_DB or the default."""
    env = os.environ.get("INVENTORY_DB")
    if env:
        return Path(env)
    return DEFAULT_DB_PATH


def connect(db_path: Path | None = None) -> sqlite3.Connection:
    """Open a SQLite connection with foreign keys enabled and row factory."""
    path = db_path or get_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


# Columns added after initial prototype schema (ALTER TABLE migrations).
_PERSON_MIGRATIONS: list[tuple[str, str]] = [
    ("type", "TEXT DEFAULT 'employee'"),
]

_SOFTWARE_MIGRATIONS: list[tuple[str, str]] = [
    ("users", "TEXT"),
    ("external_use", "INTEGER NOT NULL DEFAULT 0"),
    ("external_facing", "INTEGER NOT NULL DEFAULT 0"),
    ("support_link", "TEXT"),
    ("support_email", "TEXT"),
    ("support_phone", "TEXT"),
    ("support_hours", "TEXT"),
    ("able_to_retire", "TEXT"),
    ("able_to_replace", "TEXT"),
    ("sensitive_data", "TEXT"),
    ("sensitive_data_details", "TEXT"),
]


def migrate_schema(conn: sqlite3.Connection) -> None:
    """Apply lightweight in-place migrations for existing databases."""
    tables = {
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }
    if "person" in tables:
        cols = _table_columns(conn, "person")
        for name, decl in _PERSON_MIGRATIONS:
            if name not in cols:
                conn.execute(f"ALTER TABLE person ADD COLUMN {name} {decl}")
    if "software" in tables:
        cols = _table_columns(conn, "software")
        for name, decl in _SOFTWARE_MIGRATIONS:
            if name not in cols:
                conn.execute(f"ALTER TABLE software ADD COLUMN {name} {decl}")


def init_schema(conn: sqlite3.Connection | None = None) -> None:
    """Create tables if they do not exist, then apply migrations."""
    own_conn = conn is None
    if own_conn:
        conn = connect()
    try:
        schema_sql = SCHEMA_PATH.read_text(encoding="utf-8")
        conn.executescript(schema_sql)
        migrate_schema(conn)
        conn.commit()
    finally:
        if own_conn and conn is not None:
            conn.close()


def is_db_empty(conn: sqlite3.Connection) -> bool:
    """Return True if core tables have no rows (or do not exist yet)."""
    try:
        row = conn.execute("SELECT COUNT(*) AS n FROM software").fetchone()
        return row["n"] == 0
    except sqlite3.OperationalError:
        return True
