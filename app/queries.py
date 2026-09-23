"""Readable SQL helpers for explorers and assignment CRUD.

Pools were removed: each license product is its own software row with
seat_count + yearly_cost. Assignments link person ↔ software only.
"""

from __future__ import annotations

import sqlite3
from typing import Any


# ---------------------------------------------------------------------------
# Software
# ---------------------------------------------------------------------------

_SOFTWARE_SORT = {
    "name": "s.name COLLATE NOCASE",
    "publisher": "s.publisher COLLATE NOCASE",
    "yearly_cost": "s.yearly_cost",
    "seat_count": "s.seat_count",
    "license_type": "s.license_type COLLATE NOCASE",
}


def list_software(
    conn: sqlite3.Connection,
    *,
    q: str | None = None,
    license_type: str | None = None,
    status: str | None = None,
    is_contract: str | None = None,
    primary_department: str | None = None,
    sort: str = "name",
    order: str = "asc",
) -> list[sqlite3.Row]:
    where: list[str] = []
    params: list[Any] = []

    if q:
        where.append(
            "(s.name LIKE ? OR s.publisher LIKE ? OR s.software_key LIKE ?)"
        )
        like = f"%{q.strip()}%"
        params.extend([like, like, like])
    if license_type:
        where.append("s.license_type = ?")
        params.append(license_type)
    if status:
        where.append("s.status = ?")
        params.append(status)
    if is_contract in {"0", "1"}:
        where.append("s.is_contract = ?")
        params.append(int(is_contract))
    if primary_department:
        where.append("s.primary_department = ?")
        params.append(primary_department)

    sort_col = _SOFTWARE_SORT.get(sort, _SOFTWARE_SORT["name"])
    direction = "DESC" if order.lower() == "desc" else "ASC"
    where_sql = ("WHERE " + " AND ".join(where)) if where else ""

    sql = f"""
        SELECT
            s.*,
            s.seat_count AS seat_count_sum,
            s.yearly_cost AS yearly_cost_sum,
            CASE
                WHEN s.license_type = 'per-seat' AND s.seat_count > 0
                THEN s.yearly_cost * 1.0 / s.seat_count
                ELSE NULL
            END AS per_seat_cost
        FROM software s
        {where_sql}
        ORDER BY {sort_col} {direction}, s.name COLLATE NOCASE ASC
    """
    return list(conn.execute(sql, params).fetchall())


def get_software(conn: sqlite3.Connection, id_or_key: str) -> sqlite3.Row | None:
    """Look up by integer id or software_key."""
    row = None
    if id_or_key.isdigit():
        row = conn.execute(
            "SELECT * FROM software WHERE id = ?", (int(id_or_key),)
        ).fetchone()
    if row is None:
        row = conn.execute(
            "SELECT * FROM software WHERE software_key = ?", (id_or_key,)
        ).fetchone()
    return row


def software_assignments(
    conn: sqlite3.Connection, software_id: int
) -> list[sqlite3.Row]:
    return list(
        conn.execute(
            """
            SELECT
                a.id AS assignment_id,
                a.notes,
                a.assigned_on,
                p.employee_id,
                p.first_name,
                p.last_name,
                p.department_name,
                p.fund_code,
                f.label AS fund_label
            FROM assignment a
            JOIN person p ON p.employee_id = a.person_id
            JOIN fund f ON f.code = p.fund_code
            WHERE a.software_id = ?
            ORDER BY p.last_name COLLATE NOCASE, p.first_name COLLATE NOCASE
            """,
            (software_id,),
        ).fetchall()
    )


def software_filter_options(conn: sqlite3.Connection) -> dict[str, list[str]]:
    depts = [
        r[0]
        for r in conn.execute(
            """
            SELECT DISTINCT primary_department FROM software
            WHERE primary_department IS NOT NULL AND primary_department != ''
            ORDER BY primary_department COLLATE NOCASE
            """
        ).fetchall()
    ]
    statuses = [
        r[0]
        for r in conn.execute(
            """
            SELECT DISTINCT status FROM software
            WHERE status IS NOT NULL AND status != ''
            ORDER BY status COLLATE NOCASE
            """
        ).fetchall()
    ]
    license_types = [
        r[0]
        for r in conn.execute(
            """
            SELECT DISTINCT license_type FROM software
            ORDER BY license_type COLLATE NOCASE
            """
        ).fetchall()
    ]
    return {
        "departments": depts,
        "statuses": statuses,
        "license_types": license_types,
    }


# ---------------------------------------------------------------------------
# People
# ---------------------------------------------------------------------------

_PEOPLE_SORT = {
    "name": "p.last_name COLLATE NOCASE, p.first_name COLLATE NOCASE",
    "department": "p.department_name COLLATE NOCASE",
    "fund": "p.fund_code COLLATE NOCASE",
    "assignment_count": "assignment_count",
}


def list_people(
    conn: sqlite3.Connection,
    *,
    q: str | None = None,
    department: str | None = None,
    fund_code: str | None = None,
    status: str | None = None,
    sort: str = "name",
    order: str = "asc",
) -> list[sqlite3.Row]:
    where: list[str] = []
    params: list[Any] = []

    if q:
        where.append(
            """(
                p.first_name LIKE ? OR p.last_name LIKE ?
                OR (p.first_name || ' ' || p.last_name) LIKE ?
                OR p.email LIKE ? OR p.employee_id LIKE ?
            )"""
        )
        like = f"%{q.strip()}%"
        params.extend([like, like, like, like, like])
    if department:
        where.append("p.department_name = ?")
        params.append(department)
    if fund_code:
        where.append("p.fund_code = ?")
        params.append(fund_code)
    if status:
        where.append("p.status = ?")
        params.append(status)

    sort_expr = _PEOPLE_SORT.get(sort, _PEOPLE_SORT["name"])
    direction = "DESC" if order.lower() == "desc" else "ASC"
    where_sql = ("WHERE " + " AND ".join(where)) if where else ""

    if sort == "name":
        order_sql = (
            f"p.last_name COLLATE NOCASE {direction}, "
            f"p.first_name COLLATE NOCASE {direction}"
        )
    else:
        order_sql = f"{sort_expr} {direction}, p.last_name COLLATE NOCASE ASC"

    sql = f"""
        SELECT
            p.*,
            f.label AS fund_label,
            COUNT(a.id) AS assignment_count
        FROM person p
        JOIN fund f ON f.code = p.fund_code
        LEFT JOIN assignment a ON a.person_id = p.employee_id
        {where_sql}
        GROUP BY p.employee_id
        ORDER BY {order_sql}
    """
    return list(conn.execute(sql, params).fetchall())


def get_person(conn: sqlite3.Connection, employee_id: str) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT p.*, f.label AS fund_label
        FROM person p
        JOIN fund f ON f.code = p.fund_code
        WHERE p.employee_id = ?
        """,
        (employee_id,),
    ).fetchone()


def person_assignments(
    conn: sqlite3.Connection, employee_id: str
) -> list[sqlite3.Row]:
    return list(
        conn.execute(
            """
            SELECT
                a.id AS assignment_id,
                a.notes,
                a.assigned_on,
                s.id AS software_id,
                s.software_key,
                s.name AS software_name,
                s.publisher
            FROM assignment a
            JOIN software s ON s.id = a.software_id
            WHERE a.person_id = ?
            ORDER BY s.name COLLATE NOCASE
            """,
            (employee_id,),
        ).fetchall()
    )


def people_filter_options(conn: sqlite3.Connection) -> dict[str, list]:
    depts = [
        r[0]
        for r in conn.execute(
            """
            SELECT DISTINCT department_name FROM person
            WHERE department_name IS NOT NULL AND department_name != ''
            ORDER BY department_name COLLATE NOCASE
            """
        ).fetchall()
    ]
    funds = list(
        conn.execute(
            "SELECT code, label FROM fund ORDER BY code COLLATE NOCASE"
        ).fetchall()
    )
    statuses = [
        r[0]
        for r in conn.execute(
            """
            SELECT DISTINCT status FROM person
            WHERE status IS NOT NULL AND status != ''
            ORDER BY status COLLATE NOCASE
            """
        ).fetchall()
    ]
    return {"departments": depts, "funds": funds, "statuses": statuses}


# ---------------------------------------------------------------------------
# Assignments
# ---------------------------------------------------------------------------


def list_assignments(
    conn: sqlite3.Connection,
    *,
    software_id: str | None = None,
    person_id: str | None = None,
    department: str | None = None,
    fund_code: str | None = None,
) -> list[sqlite3.Row]:
    where: list[str] = []
    params: list[Any] = []

    if software_id:
        where.append("a.software_id = ?")
        params.append(int(software_id))
    if person_id:
        where.append("a.person_id = ?")
        params.append(person_id)
    if department:
        where.append("p.department_name = ?")
        params.append(department)
    if fund_code:
        where.append("p.fund_code = ?")
        params.append(fund_code)

    where_sql = ("WHERE " + " AND ".join(where)) if where else ""
    sql = f"""
        SELECT
            a.id AS assignment_id,
            a.notes,
            a.assigned_on,
            a.software_id,
            a.person_id,
            s.software_key,
            s.name AS software_name,
            p.first_name,
            p.last_name,
            p.department_name,
            p.fund_code,
            f.label AS fund_label
        FROM assignment a
        JOIN software s ON s.id = a.software_id
        JOIN person p ON p.employee_id = a.person_id
        JOIN fund f ON f.code = p.fund_code
        {where_sql}
        ORDER BY s.name COLLATE NOCASE, p.last_name COLLATE NOCASE
    """
    return list(conn.execute(sql, params).fetchall())


def get_assignment(conn: sqlite3.Connection, assignment_id: int) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT
            a.id AS assignment_id,
            a.notes,
            a.assigned_on,
            a.software_id,
            a.person_id,
            s.software_key,
            s.name AS software_name,
            p.first_name,
            p.last_name,
            p.department_name,
            p.fund_code,
            f.label AS fund_label
        FROM assignment a
        JOIN software s ON s.id = a.software_id
        JOIN person p ON p.employee_id = a.person_id
        JOIN fund f ON f.code = p.fund_code
        WHERE a.id = ?
        """,
        (assignment_id,),
    ).fetchone()


def create_assignment(
    conn: sqlite3.Connection,
    *,
    software_id: int,
    person_id: str,
    notes: str | None,
) -> int:
    cur = conn.execute(
        """
        INSERT INTO assignment (software_id, person_id, assigned_on, notes)
        VALUES (?, ?, date('now'), ?)
        """,
        (software_id, person_id, notes),
    )
    conn.commit()
    return int(cur.lastrowid)


def update_assignment(
    conn: sqlite3.Connection,
    assignment_id: int,
    *,
    notes: str | None,
) -> None:
    conn.execute(
        """
        UPDATE assignment
        SET notes = ?
        WHERE id = ?
        """,
        (notes, assignment_id),
    )
    conn.commit()


def delete_assignment(conn: sqlite3.Connection, assignment_id: int) -> None:
    conn.execute("DELETE FROM assignment WHERE id = ?", (assignment_id,))
    conn.commit()


def all_software_options(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return list(
        conn.execute(
            """
            SELECT id, software_key, name
            FROM software
            ORDER BY name COLLATE NOCASE
            """
        ).fetchall()
    )


def all_people_options(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return list(
        conn.execute(
            """
            SELECT employee_id, first_name, last_name, department_name, fund_code
            FROM person
            ORDER BY last_name COLLATE NOCASE, first_name COLLATE NOCASE
            """
        ).fetchall()
    )


# ---------------------------------------------------------------------------
# Software CRUD
# ---------------------------------------------------------------------------

LICENSE_TYPES = ("per-seat", "concurrent", "site", "unknown")


def _normalize_license_type(value: str | None) -> str:
    lt = (value or "unknown").strip().lower() or "unknown"
    return lt if lt in LICENSE_TYPES else "unknown"


def count_software_assignments(conn: sqlite3.Connection, software_id: int) -> int:
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM assignment WHERE software_id = ?",
        (software_id,),
    ).fetchone()
    return int(row["n"])


def create_software(
    conn: sqlite3.Connection,
    *,
    software_key: str,
    name: str,
    publisher: str | None = None,
    license_type: str = "unknown",
    primary_department: str | None = None,
    owner_employee_id: str | None = None,
    owner_name: str | None = None,
    is_contract: bool = False,
    status: str = "active",
    notes: str | None = None,
    seat_count: int = 0,
    yearly_cost: float = 0.0,
) -> int:
    """Insert software with seats/cost on the row itself. Returns software id."""
    key = software_key.strip()
    if not key:
        raise ValueError("software_key is required")
    nm = name.strip()
    if not nm:
        raise ValueError("name is required")
    lt = _normalize_license_type(license_type)
    owner_id = (owner_employee_id or "").strip() or None
    if owner_id and get_person(conn, owner_id) is None:
        raise ValueError(f"owner_employee_id not found: {owner_id}")

    cur = conn.execute(
        """
        INSERT INTO software (
            software_key, name, publisher, license_type,
            seat_count, yearly_cost,
            primary_department, owner_employee_id, owner_name,
            is_contract, status, notes
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            key,
            nm,
            (publisher or "").strip() or None,
            lt,
            int(seat_count or 0),
            float(yearly_cost or 0),
            (primary_department or "").strip() or None,
            owner_id,
            (owner_name or "").strip() or None,
            1 if is_contract else 0,
            (status or "active").strip() or "active",
            (notes or "").strip() or None,
        ),
    )
    conn.commit()
    return int(cur.lastrowid)


def update_software(
    conn: sqlite3.Connection,
    software_id: int,
    *,
    name: str,
    publisher: str | None = None,
    license_type: str = "unknown",
    primary_department: str | None = None,
    owner_employee_id: str | None = None,
    owner_name: str | None = None,
    is_contract: bool = False,
    status: str = "active",
    notes: str | None = None,
    seat_count: int = 0,
    yearly_cost: float = 0.0,
) -> None:
    """Update software metadata including seats/cost. software_key is locked after create."""
    nm = name.strip()
    if not nm:
        raise ValueError("name is required")
    lt = _normalize_license_type(license_type)
    owner_id = (owner_employee_id or "").strip() or None
    if owner_id and get_person(conn, owner_id) is None:
        raise ValueError(f"owner_employee_id not found: {owner_id}")

    conn.execute(
        """
        UPDATE software SET
            name = ?,
            publisher = ?,
            license_type = ?,
            seat_count = ?,
            yearly_cost = ?,
            primary_department = ?,
            owner_employee_id = ?,
            owner_name = ?,
            is_contract = ?,
            status = ?,
            notes = ?
        WHERE id = ?
        """,
        (
            nm,
            (publisher or "").strip() or None,
            lt,
            int(seat_count or 0),
            float(yearly_cost or 0),
            (primary_department or "").strip() or None,
            owner_id,
            (owner_name or "").strip() or None,
            1 if is_contract else 0,
            (status or "active").strip() or "active",
            (notes or "").strip() or None,
            software_id,
        ),
    )
    conn.commit()


def delete_software(conn: sqlite3.Connection, software_id: int) -> None:
    """Delete software only when it has no assignments."""
    n = count_software_assignments(conn, software_id)
    if n > 0:
        raise ValueError(
            f"Cannot delete: {n} assignment(s) still reference this software. "
            "Unassign people first."
        )
    conn.execute("DELETE FROM software WHERE id = ?", (software_id,))
    conn.commit()


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------


def report_kpis(conn: sqlite3.Connection) -> dict[str, float | int]:
    soft = conn.execute(
        """
        SELECT
            COALESCE(SUM(yearly_cost), 0) AS total_yearly_cost,
            COALESCE(SUM(seat_count), 0) AS total_seats
        FROM software
        """
    ).fetchone()
    assignments = conn.execute("SELECT COUNT(*) AS n FROM assignment").fetchone()
    return {
        "total_yearly_cost": float(soft["total_yearly_cost"]),
        "total_seats": int(soft["total_seats"]),
        "total_assignments": int(assignments["n"]),
    }


def _allocate_software_costs(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Return per-assignment allocated cost rows with fund and department.

    Allocation rules:
    - Billing always from person.fund / person.department_name.
    - Per-seat with seat_count > 0: each assignment gets yearly_cost / seat_count.
      Unused seats are unallocated; over-assignment can exceed software yearly_cost.
    - Concurrent/site/unknown or seat_count == 0: even-split software.yearly_cost
      across all assignments on that software.
    - KPI total yearly cost = sum of software.yearly_cost (not allocated sum).
    """
    titles = conn.execute(
        """
        SELECT
            s.id AS software_id,
            s.software_key,
            s.name AS software_name,
            s.license_type,
            s.seat_count,
            s.yearly_cost
        FROM software s
        """
    ).fetchall()

    rows: list[dict[str, Any]] = []
    for soft in titles:
        assigns = conn.execute(
            """
            SELECT
                a.id AS assignment_id,
                a.person_id,
                pe.fund_code,
                f.label AS fund_label,
                COALESCE(pe.department_name, '') AS department_name
            FROM assignment a
            JOIN person pe ON pe.employee_id = a.person_id
            JOIN fund f ON f.code = pe.fund_code
            WHERE a.software_id = ?
            """,
            (soft["software_id"],),
        ).fetchall()
        if not assigns:
            continue

        n = len(assigns)
        seat_count = int(soft["seat_count"] or 0)
        yearly = float(soft["yearly_cost"] or 0)
        use_seat = soft["license_type"] == "per-seat" and seat_count > 0

        if use_seat:
            per_assignment = yearly / seat_count
            method = "seat-based"
        else:
            per_assignment = yearly / n if n else 0.0
            method = "even-split"

        for a in assigns:
            rows.append(
                {
                    "assignment_id": a["assignment_id"],
                    "software_id": soft["software_id"],
                    "software_key": soft["software_key"],
                    "software_name": soft["software_name"],
                    "person_id": a["person_id"],
                    "fund_code": a["fund_code"],
                    "fund_label": a["fund_label"],
                    "department_name": a["department_name"] or "(none)",
                    "allocated_cost": per_assignment,
                    "method": method,
                }
            )
    return rows


def report_cost_by_fund(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    allocated = _allocate_software_costs(conn)
    totals: dict[str, dict[str, Any]] = {}
    for row in allocated:
        key = row["fund_code"]
        bucket = totals.setdefault(
            key,
            {
                "fund_code": row["fund_code"],
                "fund_label": row["fund_label"],
                "allocated_cost": 0.0,
                "assignment_count": 0,
            },
        )
        bucket["allocated_cost"] += row["allocated_cost"]
        bucket["assignment_count"] += 1
    return sorted(totals.values(), key=lambda r: (-r["allocated_cost"], r["fund_code"]))


def report_cost_by_department(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    allocated = _allocate_software_costs(conn)
    totals: dict[str, dict[str, Any]] = {}
    for row in allocated:
        key = row["department_name"]
        bucket = totals.setdefault(
            key,
            {
                "department_name": key,
                "allocated_cost": 0.0,
                "assignment_count": 0,
            },
        )
        bucket["allocated_cost"] += row["allocated_cost"]
        bucket["assignment_count"] += 1
    return sorted(
        totals.values(),
        key=lambda r: (-r["allocated_cost"], r["department_name"]),
    )


def report_seats_used_vs_purchased(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return list(
        conn.execute(
            """
            SELECT
                s.id AS software_id,
                s.software_key,
                s.name AS software_name,
                s.license_type,
                s.seat_count AS seats_purchased,
                s.yearly_cost,
                COUNT(a.id) AS seats_used,
                CASE
                    WHEN s.seat_count > 0
                    THEN COUNT(a.id) * 1.0 / s.seat_count
                    ELSE NULL
                END AS utilization
            FROM software s
            LEFT JOIN assignment a ON a.software_id = s.id
            GROUP BY s.id
            ORDER BY s.name COLLATE NOCASE
            """
        ).fetchall()
    )
