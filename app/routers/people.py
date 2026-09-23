"""People explorer (read-only)."""

from __future__ import annotations

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.db import connect
from app import queries

router = APIRouter(prefix="/people", tags=["people"])
templates = Jinja2Templates(directory="app/templates")


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
def people_list(
    request: Request,
    q: str | None = None,
    department: str | None = None,
    fund_code: str | None = None,
    status: str | None = None,
    sort: str = Query(default="name"),
    order: str = Query(default="asc"),
) -> HTMLResponse:
    conn = connect()
    try:
        rows = queries.list_people(
            conn,
            q=q,
            department=department or None,
            fund_code=fund_code or None,
            status=status or None,
            sort=sort,
            order=order,
        )
        options = queries.people_filter_options(conn)
    finally:
        conn.close()

    return templates.TemplateResponse(
        request,
        "people/list.html",
        {
            "title": "People",
            "rows": rows,
            "options": options,
            "filters": {
                "q": q or "",
                "department": department or "",
                "fund_code": fund_code or "",
                "status": status or "",
                "sort": sort,
                "order": order,
            },
        },
    )


@router.get("/{employee_id}", response_class=HTMLResponse)
def people_detail(request: Request, employee_id: str) -> HTMLResponse:
    conn = connect()
    try:
        person = queries.get_person(conn, employee_id)
        if person is None:
            return templates.TemplateResponse(
                request,
                "error.html",
                {"title": "Not found", "message": f"Person not found: {employee_id}"},
                status_code=404,
            )
        assignments = queries.person_assignments(conn, employee_id)
    finally:
        conn.close()

    return templates.TemplateResponse(
        request,
        "people/detail.html",
        {
            "title": f"{person['first_name']} {person['last_name']}",
            "person": person,
            "assignments": assignments,
        },
    )
