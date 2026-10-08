"""Assignments CRUD (Jinja forms + PRG). Person ↔ software only (no pool)."""

from __future__ import annotations

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.status import HTTP_303_SEE_OTHER

from app.db import connect
from app import queries

router = APIRouter(prefix="/assignments", tags=["assignments"])
templates = Jinja2Templates(directory="app/templates")


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
def assignments_list(
    request: Request,
    software_id: str | None = None,
    person_id: str | None = None,
    department: str | None = None,
    fund_code: str | None = None,
    flash: str | None = None,
) -> HTMLResponse:
    conn = connect()
    try:
        rows = queries.list_assignments(
            conn,
            software_id=software_id or None,
            person_id=person_id or None,
            department=department or None,
            fund_code=fund_code or None,
        )
        software_opts = queries.all_software_options(conn)
        people_opts = queries.all_people_options(conn)
        people_filters = queries.people_filter_options(conn)
    finally:
        conn.close()

    return templates.TemplateResponse(
        request,
        "assignments/list.html",
        {
            "title": "Assignments",
            "rows": rows,
            "software_opts": software_opts,
            "people_opts": people_opts,
            "people_filters": people_filters,
            "filters": {
                "software_id": software_id or "",
                "person_id": person_id or "",
                "department": department or "",
                "fund_code": fund_code or "",
            },
            "flash": flash,
        },
    )


@router.get("/new", response_class=HTMLResponse)
def assignment_new(
    request: Request,
    software_id: str | None = None,
    person_id: str | None = None,
    error: str | None = None,
) -> HTMLResponse:
    conn = connect()
    try:
        software_opts = queries.all_software_options(conn)
        people_opts = queries.all_people_options(conn)
    finally:
        conn.close()

    return templates.TemplateResponse(
        request,
        "assignments/form.html",
        {
            "title": "New assignment",
            "mode": "create",
            "assignment": None,
            "software_opts": software_opts,
            "people_opts": people_opts,
            "selected_software": software_id or "",
            "selected_person": person_id or "",
            "notes": "",
            "error": error,
        },
    )


@router.post("/new")
def assignment_create(
    software_id: int = Form(...),
    person_id: str = Form(...),
    notes: str = Form(""),
) -> RedirectResponse:
    conn = connect()
    try:
        person = queries.get_person(conn, person_id.strip())
        soft = queries.get_software(conn, str(software_id))
        if person is None or soft is None:
            return RedirectResponse(
                "/assignments/new?error=Invalid+person+or+software",
                status_code=HTTP_303_SEE_OTHER,
            )
        try:
            queries.create_assignment(
                conn,
                software_id=software_id,
                person_id=person_id.strip(),
                notes=notes.strip() or None,
            )
        except Exception as exc:
            msg = str(exc).replace(" ", "+")[:120]
            return RedirectResponse(
                f"/assignments/new?software_id={software_id}&person_id={person_id}"
                f"&error={msg}",
                status_code=HTTP_303_SEE_OTHER,
            )
    finally:
        conn.close()

    return RedirectResponse(
        "/assignments?flash=Assignment+created",
        status_code=HTTP_303_SEE_OTHER,
    )


@router.get("/bulk", response_class=HTMLResponse)
def assignment_bulk_form(
    request: Request,
    software_id: str | None = None,
    department: str | None = None,
    status: str | None = None,
    q: str | None = None,
    error: str | None = None,
) -> HTMLResponse:
    conn = connect()
    try:
        software_opts = queries.all_software_options(conn)
        people = queries.list_people(
            conn,
            q=q or None,
            department=department or None,
            status=status or None,
            sort="name",
            order="asc",
        )
        options = queries.people_filter_options(conn)
        already: set[str] = set()
        if software_id:
            soft = queries.get_software(conn, software_id)
            if soft is not None:
                already = {
                    r["employee_id"]
                    for r in queries.software_assignments(conn, int(soft["id"]))
                }
    finally:
        conn.close()

    return templates.TemplateResponse(
        request,
        "assignments/bulk.html",
        {
            "title": "Bulk assign",
            "software_opts": software_opts,
            "people": people,
            "options": options,
            "already_assigned": already,
            "filters": {
                "software_id": software_id or "",
                "department": department or "",
                "status": status or "",
                "q": q or "",
            },
            "error": error or request.query_params.get("error"),
        },
    )


@router.post("/bulk")
async def assignment_bulk_create(request: Request) -> RedirectResponse:
    form = await request.form()
    software_id_raw = (form.get("software_id") or "").strip()
    notes = (form.get("notes") or "").strip()
    person_ids = [
        str(v).strip()
        for v in form.getlist("person_ids")
        if str(v).strip()
    ]

    if not software_id_raw:
        return RedirectResponse(
            "/assignments/bulk?error=Select+a+software+title",
            status_code=HTTP_303_SEE_OTHER,
        )
    if not person_ids:
        return RedirectResponse(
            f"/assignments/bulk?software_id={software_id_raw}"
            f"&error=Select+at+least+one+person",
            status_code=HTTP_303_SEE_OTHER,
        )

    conn = connect()
    try:
        soft = queries.get_software(conn, software_id_raw)
        if soft is None:
            return RedirectResponse(
                "/assignments/bulk?error=Software+not+found",
                status_code=HTTP_303_SEE_OTHER,
            )
        counts = queries.bulk_create_assignments(
            conn,
            software_id=int(soft["id"]),
            person_ids=person_ids,
            notes=notes or None,
        )
        key = soft["software_key"]
    finally:
        conn.close()

    flash = (
        f"Assigned {counts['created']} people to {key}"
        + (
            f" ({counts['skipped']} already assigned)"
            if counts["skipped"]
            else ""
        )
        + (
            f"; {counts['invalid']} invalid ID(s) skipped"
            if counts["invalid"]
            else ""
        )
    )
    return RedirectResponse(
        f"/software/{key}?flash={flash.replace(' ', '+')}",
        status_code=HTTP_303_SEE_OTHER,
    )


@router.get("/{assignment_id}/edit", response_class=HTMLResponse)
def assignment_edit(
    request: Request,
    assignment_id: int,
    error: str | None = None,
) -> HTMLResponse:
    conn = connect()
    try:
        row = queries.get_assignment(conn, assignment_id)
        if row is None:
            return templates.TemplateResponse(
                request,
                "error.html",
                {"title": "Not found", "message": f"Assignment {assignment_id} not found"},
                status_code=404,
            )
    finally:
        conn.close()

    return templates.TemplateResponse(
        request,
        "assignments/form.html",
        {
            "title": "Edit assignment",
            "mode": "edit",
            "assignment": row,
            "software_opts": [],
            "people_opts": [],
            "selected_software": str(row["software_id"]),
            "selected_person": row["person_id"],
            "notes": row["notes"] or "",
            "error": error,
        },
    )


@router.post("/{assignment_id}/edit")
def assignment_update(
    assignment_id: int,
    notes: str = Form(""),
) -> RedirectResponse:
    conn = connect()
    try:
        row = queries.get_assignment(conn, assignment_id)
        if row is None:
            return RedirectResponse(
                "/assignments?flash=Assignment+not+found",
                status_code=HTTP_303_SEE_OTHER,
            )
        try:
            queries.update_assignment(
                conn,
                assignment_id,
                notes=notes.strip() or None,
            )
        except Exception as exc:
            msg = str(exc).replace(" ", "+")[:120]
            return RedirectResponse(
                f"/assignments/{assignment_id}/edit?error={msg}",
                status_code=HTTP_303_SEE_OTHER,
            )
    finally:
        conn.close()

    return RedirectResponse(
        "/assignments?flash=Assignment+updated",
        status_code=HTTP_303_SEE_OTHER,
    )


@router.get("/{assignment_id}/delete", response_class=HTMLResponse)
def assignment_delete_confirm(
    request: Request, assignment_id: int
) -> HTMLResponse:
    conn = connect()
    try:
        row = queries.get_assignment(conn, assignment_id)
        if row is None:
            return templates.TemplateResponse(
                request,
                "error.html",
                {"title": "Not found", "message": f"Assignment {assignment_id} not found"},
                status_code=404,
            )
    finally:
        conn.close()

    return templates.TemplateResponse(
        request,
        "assignments/delete.html",
        {"title": "Delete assignment", "assignment": row},
    )


@router.post("/{assignment_id}/delete")
def assignment_delete(assignment_id: int) -> RedirectResponse:
    conn = connect()
    try:
        queries.delete_assignment(conn, assignment_id)
    finally:
        conn.close()
    return RedirectResponse(
        "/assignments?flash=Assignment+deleted",
        status_code=HTTP_303_SEE_OTHER,
    )
