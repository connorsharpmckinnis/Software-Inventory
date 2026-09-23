"""Health check, admin seed, backup, and CSV export endpoints."""

from __future__ import annotations

import csv
import io
import zipfile
from datetime import datetime, timezone
from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.templating import Jinja2Templates

from app.db import connect, get_db_path
from app.seed import counts_snapshot, import_seed

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/health")
def health() -> dict:
    return {"status": "ok"}


@router.get("/admin", response_class=HTMLResponse)
def admin_page(request: Request) -> HTMLResponse:
    counts = None
    try:
        conn = connect()
        try:
            counts = counts_snapshot(conn)
        finally:
            conn.close()
    except Exception:
        counts = None
    return templates.TemplateResponse(
        request,
        "admin.html",
        {"title": "Admin", "counts": counts},
    )


@router.get("/admin/stats")
def admin_stats() -> dict:
    """Return current table row counts (handy for verifying seed)."""
    conn = connect()
    try:
        return {"counts": counts_snapshot(conn)}
    finally:
        conn.close()


@router.post("/admin/import-seed")
def admin_import_seed(force: bool = True) -> JSONResponse:
    """Re-import seed CSVs. Prototype: force clears/rebuilds DB — document in README."""
    counts = import_seed(force=force)
    return JSONResponse({"ok": True, "counts": counts})


@router.get("/admin/backup", response_model=None)
def admin_backup():
    """Download the live SQLite database file."""
    db_path = get_db_path()
    if not db_path.exists():
        return JSONResponse(
            {"ok": False, "error": f"Database not found: {db_path}"},
            status_code=404,
        )
    # Checkpoint WAL so the file is consistent for copy
    conn = connect()
    try:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    finally:
        conn.close()
    return FileResponse(
        path=str(db_path),
        media_type="application/x-sqlite3",
        filename="inventory.db",
    )


def _csv_bytes(headers: list[str], rows: list[list]) -> bytes:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(headers)
    for row in rows:
        writer.writerow(row)
    return buf.getvalue().encode("utf-8")


@router.get("/admin/export")
@router.get("/admin/export.csv.zip")
def admin_export_csv_zip() -> Response:
    """Zip of funds, people, software, assignments CSVs (COLUMN_MAP-aligned). No pools file."""
    conn = connect()
    try:
        funds = list(
            conn.execute("SELECT code, label FROM fund ORDER BY code COLLATE NOCASE")
        )
        people = list(
            conn.execute(
                """
                SELECT
                    p.employee_id, p.first_name, p.last_name, p.department_name,
                    p.fund_code, f.label AS fund_label, p.status, p.email
                FROM person p
                JOIN fund f ON f.code = p.fund_code
                ORDER BY p.last_name COLLATE NOCASE, p.first_name COLLATE NOCASE
                """
            )
        )
        software = list(
            conn.execute(
                """
                SELECT
                    s.software_key, s.name, s.publisher, s.license_type,
                    s.seat_count, s.yearly_cost,
                    CASE WHEN s.is_contract = 1 THEN 'yes' ELSE 'no' END AS is_contract,
                    s.primary_department, s.owner_employee_id, s.owner_name,
                    s.status, s.notes
                FROM software s
                ORDER BY s.name COLLATE NOCASE
                """
            )
        )
        assignments = list(
            conn.execute(
                """
                SELECT
                    s.software_key,
                    a.person_id AS employee_id,
                    a.notes,
                    a.assigned_on
                FROM assignment a
                JOIN software s ON s.id = a.software_id
                ORDER BY s.software_key COLLATE NOCASE, a.person_id COLLATE NOCASE
                """
            )
        )
    finally:
        conn.close()

    files: dict[str, bytes] = {
        "funds.csv": _csv_bytes(
            ["fund_code", "fund_label"],
            [[r["code"], r["label"]] for r in funds],
        ),
        "people.csv": _csv_bytes(
            [
                "employee_id",
                "first_name",
                "last_name",
                "department_name",
                "fund_code",
                "fund_label",
                "status",
                "email",
            ],
            [
                [
                    r["employee_id"],
                    r["first_name"],
                    r["last_name"],
                    r["department_name"] or "",
                    r["fund_code"],
                    r["fund_label"],
                    r["status"] or "",
                    r["email"] or "",
                ]
                for r in people
            ],
        ),
        "software.csv": _csv_bytes(
            [
                "software_key",
                "name",
                "publisher",
                "license_type",
                "seat_count",
                "yearly_cost",
                "is_contract",
                "primary_department",
                "owner_employee_id",
                "owner_name",
                "status",
                "notes",
            ],
            [
                [
                    r["software_key"],
                    r["name"],
                    r["publisher"] or "",
                    r["license_type"],
                    r["seat_count"],
                    r["yearly_cost"],
                    r["is_contract"],
                    r["primary_department"] or "",
                    r["owner_employee_id"] or "",
                    r["owner_name"] or "",
                    r["status"] or "",
                    r["notes"] or "",
                ]
                for r in software
            ],
        ),
        "assignments.csv": _csv_bytes(
            ["software_key", "employee_id", "notes", "assigned_on"],
            [
                [
                    r["software_key"],
                    r["employee_id"],
                    r["notes"] or "",
                    r["assigned_on"] or "",
                ]
                for r in assignments
            ],
        ),
    }

    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name, data in files.items():
            zf.writestr(name, data)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    return Response(
        content=zip_buf.getvalue(),
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="inventory-export-{stamp}.zip"'
        },
    )
