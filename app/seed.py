"""Import seed CSVs into the inventory SQLite database.

Usage:
    python -m app.seed
    python -m app.seed --db /path/to/inventory.db
    python -m app.seed --force   # drop tables, rebuild schema, re-import

Prototype note: --force clears and rebuilds the DB (schema changes are not
migrated in-place). Empty DB on app startup still auto-seeds via import_seed.
"""

from __future__ import annotations

import argparse
import csv
import sqlite3
import sys
from pathlib import Path

from app.db import REPO_ROOT, connect, get_db_path, init_schema, is_db_empty

SEED_DIR = REPO_ROOT / "data" / "seed"


def _truthy(value: str | None) -> bool:
    """Treat yes/true/1 (case-insensitive) as True."""
    if value is None:
        return False
    return value.strip().lower() in {"yes", "true", "1", "y"}


def _int_or_zero(value: str | None) -> int:
    if value is None or str(value).strip() == "":
        return 0
    try:
        return int(float(str(value).strip()))
    except ValueError:
        return 0


def _float_or_zero(value: str | None) -> float:
    if value is None or str(value).strip() == "":
        return 0.0
    try:
        return float(str(value).strip())
    except ValueError:
        return 0.0


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        raise FileNotFoundError(f"Seed file not found: {path}")
    with path.open(newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def clear_all_tables(conn: sqlite3.Connection) -> None:
    """Drop all inventory tables (including legacy software_pool) then recreate schema."""
    conn.executescript(
        """
        PRAGMA foreign_keys = OFF;
        DROP TABLE IF EXISTS assignment;
        DROP TABLE IF EXISTS software_pool;
        DROP TABLE IF EXISTS software;
        DROP TABLE IF EXISTS person;
        DROP TABLE IF EXISTS fund;
        PRAGMA foreign_keys = ON;
        """
    )
    conn.commit()
    init_schema(conn)


def upsert_funds(conn: sqlite3.Connection, employees: list[dict[str, str]]) -> int:
    """Upsert funds from employee fund_code + fund_label. Returns distinct count written."""
    seen: dict[str, str] = {}
    for row in employees:
        code = (row.get("fund_code") or "").strip()
        label = (row.get("fund_label") or "").strip() or code
        if code:
            seen[code] = label
    for code, label in seen.items():
        conn.execute(
            """
            INSERT INTO fund (code, label) VALUES (?, ?)
            ON CONFLICT(code) DO UPDATE SET label = excluded.label
            """,
            (code, label),
        )
    return len(seen)


def upsert_people(conn: sqlite3.Connection, employees: list[dict[str, str]]) -> int:
    n = 0
    for row in employees:
        employee_id = (row.get("employee_id") or "").strip()
        if not employee_id:
            continue
        person_type = (row.get("type") or "employee").strip().lower() or "employee"
        status = (row.get("status") or "active").strip().lower() or "active"
        conn.execute(
            """
            INSERT INTO person (
                employee_id, first_name, last_name, department_name,
                fund_code, email, status, type
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(employee_id) DO UPDATE SET
                first_name = excluded.first_name,
                last_name = excluded.last_name,
                department_name = excluded.department_name,
                fund_code = excluded.fund_code,
                email = excluded.email,
                status = excluded.status,
                type = excluded.type
            """,
            (
                employee_id,
                (row.get("first_name") or "").strip(),
                (row.get("last_name") or "").strip(),
                (row.get("department_name") or "").strip() or None,
                (row.get("fund_code") or "").strip(),
                (row.get("email") or "").strip() or None,
                status,
                person_type,
            ),
        )
        n += 1
    return n


def upsert_software(
    conn: sqlite3.Connection, software_rows: list[dict[str, str]]
) -> int:
    """Upsert software rows with seat_count + yearly_cost on the software itself."""
    software_n = 0
    for row in software_rows:
        key = (row.get("software_key") or "").strip()
        if not key:
            continue
        owner_id = (row.get("owner_employee_id") or "").strip() or None
        license_type = (row.get("license_type") or "unknown").strip().lower() or "unknown"
        if license_type not in {"per-seat", "concurrent", "site", "unknown"}:
            license_type = "unknown"

        conn.execute(
            """
            INSERT INTO software (
                software_key, name, publisher, license_type,
                seat_count, yearly_cost,
                primary_department, owner_employee_id, owner_name,
                is_contract, status, notes,
                users, external_use, external_facing,
                support_link, support_email, support_phone, support_hours,
                able_to_retire, able_to_replace,
                sensitive_data, sensitive_data_details
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(software_key) DO UPDATE SET
                name = excluded.name,
                publisher = excluded.publisher,
                license_type = excluded.license_type,
                seat_count = excluded.seat_count,
                yearly_cost = excluded.yearly_cost,
                primary_department = excluded.primary_department,
                owner_employee_id = excluded.owner_employee_id,
                owner_name = excluded.owner_name,
                is_contract = excluded.is_contract,
                status = excluded.status,
                notes = excluded.notes,
                users = excluded.users,
                external_use = excluded.external_use,
                external_facing = excluded.external_facing,
                support_link = excluded.support_link,
                support_email = excluded.support_email,
                support_phone = excluded.support_phone,
                support_hours = excluded.support_hours,
                able_to_retire = excluded.able_to_retire,
                able_to_replace = excluded.able_to_replace,
                sensitive_data = excluded.sensitive_data,
                sensitive_data_details = excluded.sensitive_data_details
            """,
            (
                key,
                (row.get("name") or "").strip() or key,
                (row.get("publisher") or "").strip() or None,
                license_type,
                _int_or_zero(row.get("seat_count")),
                _float_or_zero(row.get("yearly_cost")),
                (row.get("primary_department") or "").strip() or None,
                owner_id,
                (row.get("owner_name") or "").strip() or None,
                1 if _truthy(row.get("is_contract")) else 0,
                (row.get("status") or "active").strip() or "active",
                (row.get("notes") or "").strip() or None,
                (row.get("users") or "").strip() or None,
                1 if _truthy(row.get("external_use")) else 0,
                1 if _truthy(row.get("external_facing")) else 0,
                (row.get("support_link") or "").strip() or None,
                (row.get("support_email") or "").strip() or None,
                (row.get("support_phone") or "").strip() or None,
                (row.get("support_hours") or "").strip() or None,
                (row.get("able_to_retire") or "").strip() or None,
                (row.get("able_to_replace") or "").strip() or None,
                (row.get("sensitive_data") or "").strip() or None,
                (row.get("sensitive_data_details") or "").strip() or None,
            ),
        )
        software_n += 1
    return software_n


def upsert_assignments(
    conn: sqlite3.Connection, assignment_rows: list[dict[str, str]]
) -> int:
    n = 0
    for row in assignment_rows:
        key = (row.get("software_key") or "").strip()
        employee_id = (row.get("employee_id") or "").strip()
        if not key or not employee_id:
            continue

        soft = conn.execute(
            "SELECT id FROM software WHERE software_key = ?", (key,)
        ).fetchone()
        if soft is None:
            print(f"  WARN: skip assignment — unknown software_key={key!r}", file=sys.stderr)
            continue
        software_id = soft["id"]

        person = conn.execute(
            "SELECT employee_id FROM person WHERE employee_id = ?", (employee_id,)
        ).fetchone()
        if person is None:
            print(
                f"  WARN: skip assignment — unknown employee_id={employee_id!r}",
                file=sys.stderr,
            )
            continue

        notes = (row.get("notes") or "").strip() or None
        conn.execute(
            """
            INSERT INTO assignment (software_id, person_id, assigned_on, notes)
            VALUES (?, ?, NULL, ?)
            ON CONFLICT(software_id, person_id) DO UPDATE SET
                notes = excluded.notes
            """,
            (software_id, employee_id, notes),
        )
        n += 1
    return n


def import_seed(
    db_path: Path | None = None,
    seed_dir: Path | None = None,
    force: bool = False,
) -> dict[str, int]:
    """Create schema and upsert all seed CSVs. Returns row counts written.

    With force=True, drops all tables (including legacy software_pool) and rebuilds.
    """
    seed_dir = seed_dir or SEED_DIR
    path = db_path or get_db_path()
    conn = connect(path)
    try:
        if force:
            print(f"Force re-seed: clearing tables and rebuilding schema at {path}")
            clear_all_tables(conn)
        else:
            init_schema(conn)
            if not is_db_empty(conn):
                print(
                    f"DB already has data at {path}; skipping seed "
                    "(use --force to clear/rebuild)."
                )
                return counts_snapshot(conn)

        employees = _read_csv(seed_dir / "employees.csv")
        software_rows = _read_csv(seed_dir / "software.csv")
        assignment_rows = _read_csv(seed_dir / "assignments.csv")

        funds_n = upsert_funds(conn, employees)
        people_n = upsert_people(conn, employees)
        software_n = upsert_software(conn, software_rows)
        assignments_n = upsert_assignments(conn, assignment_rows)
        conn.commit()

        counts = {
            "funds": funds_n,
            "people": people_n,
            "software": software_n,
            "assignments": assignments_n,
        }
        print(f"Seed import complete → {path}")
        for k, v in counts.items():
            print(f"  {k}: {v}")
        return counts
    finally:
        conn.close()


def counts_snapshot(conn: sqlite3.Connection) -> dict[str, int]:
    return {
        "funds": conn.execute("SELECT COUNT(*) AS n FROM fund").fetchone()["n"],
        "people": conn.execute("SELECT COUNT(*) AS n FROM person").fetchone()["n"],
        "software": conn.execute("SELECT COUNT(*) AS n FROM software").fetchone()["n"],
        "assignments": conn.execute("SELECT COUNT(*) AS n FROM assignment").fetchone()["n"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Import seed CSVs into inventory.db")
    parser.add_argument(
        "--db",
        type=Path,
        default=None,
        help="Path to SQLite DB (default: INVENTORY_DB or data/inventory.db)",
    )
    parser.add_argument(
        "--seed-dir",
        type=Path,
        default=None,
        help="Directory with employees.csv, software.csv, assignments.csv",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Drop tables, rebuild schema, and re-import seed CSVs",
    )
    args = parser.parse_args(argv)
    import_seed(db_path=args.db, seed_dir=args.seed_dir, force=args.force)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
