"""Software explorer + software CRUD (Jinja forms + PRG).

No pools: seats and yearly cost live on the software row itself.
"""

from __future__ import annotations

import re

from fastapi import APIRouter, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.status import HTTP_303_SEE_OTHER

from app.db import connect
from app import queries

router = APIRouter(prefix="/software", tags=["software"])
templates = Jinja2Templates(directory="app/templates")

LICENSE_CHOICES = list(queries.LICENSE_TYPES)

_EMPTY_FORM = {
    "software_key": "",
    "name": "",
    "publisher": "",
    "license_type": "unknown",
    "primary_department": "",
    "owner_employee_id": "",
    "owner_name": "",
    "is_contract": False,
    "status": "active",
    "notes": "",
    "seat_count": "0",
    "yearly_cost": "0",
    "users": "",
    "external_use": False,
    "external_facing": False,
    "support_link": "",
    "support_email": "",
    "support_phone": "",
    "support_hours": "",
    "able_to_retire": "",
    "able_to_replace": "",
    "sensitive_data": "",
    "sensitive_data_details": "",
}


def _parse_bool_flag(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "yes", "true", "on", "y"}


def _int_default(value: str | None, default: int = 0) -> int:
    raw = (value or "").strip()
    if raw == "":
        return default
    try:
        return int(float(raw))
    except ValueError:
        return default


def _float_default(value: str | None, default: float = 0.0) -> float:
    raw = re.sub(r"[^\d.\-]", "", (value or "").strip())
    if raw == "":
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _form_from_software(soft) -> dict:
    return {
        "software_key": soft["software_key"],
        "name": soft["name"],
        "publisher": soft["publisher"] or "",
        "license_type": soft["license_type"],
        "primary_department": soft["primary_department"] or "",
        "owner_employee_id": soft["owner_employee_id"] or "",
        "owner_name": soft["owner_name"] or "",
        "is_contract": bool(soft["is_contract"]),
        "status": soft["status"] or "active",
        "notes": soft["notes"] or "",
        "seat_count": str(soft["seat_count"]),
        "yearly_cost": str(soft["yearly_cost"]),
        "users": soft["users"] or "",
        "external_use": bool(soft["external_use"]),
        "external_facing": bool(soft["external_facing"]),
        "support_link": soft["support_link"] or "",
        "support_email": soft["support_email"] or "",
        "support_phone": soft["support_phone"] or "",
        "support_hours": soft["support_hours"] or "",
        "able_to_retire": soft["able_to_retire"] or "",
        "able_to_replace": soft["able_to_replace"] or "",
        "sensitive_data": soft["sensitive_data"] or "",
        "sensitive_data_details": soft["sensitive_data_details"] or "",
    }


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
def software_list(
    request: Request,
    q: str | None = None,
    license_type: str | None = None,
    status: str | None = None,
    is_contract: str | None = None,
    primary_department: str | None = None,
    sort: str = Query(default="name"),
    order: str = Query(default="asc"),
    flash: str | None = None,
) -> HTMLResponse:
    conn = connect()
    try:
        rows = queries.list_software(
            conn,
            q=q,
            license_type=license_type or None,
            status=status or None,
            is_contract=is_contract or None,
            primary_department=primary_department or None,
            sort=sort,
            order=order,
        )
        options = queries.software_filter_options(conn)
    finally:
        conn.close()

    return templates.TemplateResponse(
        request,
        "software/list.html",
        {
            "title": "Software",
            "rows": rows,
            "options": options,
            "filters": {
                "q": q or "",
                "license_type": license_type or "",
                "status": status or "",
                "is_contract": is_contract or "",
                "primary_department": primary_department or "",
                "sort": sort,
                "order": order,
            },
            "flash": flash,
        },
    )


@router.get("/new", response_class=HTMLResponse)
def software_new(request: Request, error: str | None = None) -> HTMLResponse:
    conn = connect()
    try:
        people = queries.all_people_options(conn)
        options = queries.software_filter_options(conn)
    finally:
        conn.close()
    return templates.TemplateResponse(
        request,
        "software/form.html",
        {
            "title": "New software",
            "mode": "create",
            "software": None,
            "people": people,
            "license_choices": LICENSE_CHOICES,
            "departments": options["departments"],
            "form": dict(_EMPTY_FORM),
            "error": error,
        },
    )


@router.post("/new")
def software_create(
    software_key: str = Form(""),
    name: str = Form(...),
    publisher: str = Form(""),
    license_type: str = Form("unknown"),
    primary_department: str = Form(""),
    owner_employee_id: str = Form(""),
    owner_name: str = Form(""),
    is_contract: str = Form(""),
    status: str = Form("active"),
    notes: str = Form(""),
    seat_count: str = Form("0"),
    yearly_cost: str = Form("0"),
    users: str = Form(""),
    external_use: str = Form(""),
    external_facing: str = Form(""),
    support_link: str = Form(""),
    support_email: str = Form(""),
    support_phone: str = Form(""),
    support_hours: str = Form(""),
    able_to_retire: str = Form(""),
    able_to_replace: str = Form(""),
    sensitive_data: str = Form(""),
    sensitive_data_details: str = Form(""),
) -> RedirectResponse:
    conn = connect()
    try:
        try:
            sid = queries.create_software(
                conn,
                software_key=software_key,
                name=name,
                publisher=publisher,
                license_type=license_type,
                primary_department=primary_department,
                owner_employee_id=owner_employee_id,
                owner_name=owner_name,
                is_contract=_parse_bool_flag(is_contract),
                status=status,
                notes=notes,
                seat_count=_int_default(seat_count, 0),
                yearly_cost=_float_default(yearly_cost, 0.0),
                users=users,
                external_use=_parse_bool_flag(external_use),
                external_facing=_parse_bool_flag(external_facing),
                support_link=support_link,
                support_email=support_email,
                support_phone=support_phone,
                support_hours=support_hours,
                able_to_retire=able_to_retire,
                able_to_replace=able_to_replace,
                sensitive_data=sensitive_data,
                sensitive_data_details=sensitive_data_details,
            )
            soft = queries.get_software(conn, str(sid))
        except Exception as exc:
            msg = str(exc).replace(" ", "+")[:160]
            return RedirectResponse(
                f"/software/new?error={msg}",
                status_code=HTTP_303_SEE_OTHER,
            )
    finally:
        conn.close()

    key = soft["software_key"] if soft else software_key.strip()
    return RedirectResponse(
        f"/software/{key}?flash=Software+created",
        status_code=HTTP_303_SEE_OTHER,
    )


@router.get("/{id_or_key}/edit", response_class=HTMLResponse)
def software_edit(
    request: Request, id_or_key: str, error: str | None = None
) -> HTMLResponse:
    conn = connect()
    try:
        soft = queries.get_software(conn, id_or_key)
        if soft is None:
            return templates.TemplateResponse(
                request,
                "error.html",
                {"title": "Not found", "message": f"Software not found: {id_or_key}"},
                status_code=404,
            )
        people = queries.all_people_options(conn)
        options = queries.software_filter_options(conn)
    finally:
        conn.close()

    return templates.TemplateResponse(
        request,
        "software/form.html",
        {
            "title": f"Edit {soft['name']}",
            "mode": "edit",
            "software": soft,
            "people": people,
            "license_choices": LICENSE_CHOICES,
            "departments": options["departments"],
            "form": _form_from_software(soft),
            "error": error,
        },
    )


@router.post("/{id_or_key}/edit")
def software_update(
    id_or_key: str,
    name: str = Form(...),
    publisher: str = Form(""),
    license_type: str = Form("unknown"),
    primary_department: str = Form(""),
    owner_employee_id: str = Form(""),
    owner_name: str = Form(""),
    is_contract: str = Form(""),
    status: str = Form("active"),
    notes: str = Form(""),
    seat_count: str = Form("0"),
    yearly_cost: str = Form("0"),
    users: str = Form(""),
    external_use: str = Form(""),
    external_facing: str = Form(""),
    support_link: str = Form(""),
    support_email: str = Form(""),
    support_phone: str = Form(""),
    support_hours: str = Form(""),
    able_to_retire: str = Form(""),
    able_to_replace: str = Form(""),
    sensitive_data: str = Form(""),
    sensitive_data_details: str = Form(""),
) -> RedirectResponse:
    conn = connect()
    try:
        soft = queries.get_software(conn, id_or_key)
        if soft is None:
            return RedirectResponse(
                "/software?flash=Software+not+found",
                status_code=HTTP_303_SEE_OTHER,
            )
        try:
            queries.update_software(
                conn,
                soft["id"],
                name=name,
                publisher=publisher,
                license_type=license_type,
                primary_department=primary_department,
                owner_employee_id=owner_employee_id,
                owner_name=owner_name,
                is_contract=_parse_bool_flag(is_contract),
                status=status,
                notes=notes,
                seat_count=_int_default(seat_count, 0),
                yearly_cost=_float_default(yearly_cost, 0.0),
                users=users,
                external_use=_parse_bool_flag(external_use),
                external_facing=_parse_bool_flag(external_facing),
                support_link=support_link,
                support_email=support_email,
                support_phone=support_phone,
                support_hours=support_hours,
                able_to_retire=able_to_retire,
                able_to_replace=able_to_replace,
                sensitive_data=sensitive_data,
                sensitive_data_details=sensitive_data_details,
            )
        except Exception as exc:
            msg = str(exc).replace(" ", "+")[:160]
            return RedirectResponse(
                f"/software/{soft['software_key']}/edit?error={msg}",
                status_code=HTTP_303_SEE_OTHER,
            )
        key = soft["software_key"]
    finally:
        conn.close()

    return RedirectResponse(
        f"/software/{key}?flash=Software+updated",
        status_code=HTTP_303_SEE_OTHER,
    )


@router.get("/{id_or_key}/delete", response_class=HTMLResponse)
def software_delete_confirm(request: Request, id_or_key: str) -> HTMLResponse:
    conn = connect()
    try:
        soft = queries.get_software(conn, id_or_key)
        if soft is None:
            return templates.TemplateResponse(
                request,
                "error.html",
                {"title": "Not found", "message": f"Software not found: {id_or_key}"},
                status_code=404,
            )
        assignment_count = queries.count_software_assignments(conn, soft["id"])
    finally:
        conn.close()

    return templates.TemplateResponse(
        request,
        "software/delete.html",
        {
            "title": "Delete software",
            "software": soft,
            "assignment_count": assignment_count,
            "blocked": assignment_count > 0,
        },
    )


@router.post("/{id_or_key}/delete")
def software_delete(id_or_key: str) -> RedirectResponse:
    conn = connect()
    try:
        soft = queries.get_software(conn, id_or_key)
        if soft is None:
            return RedirectResponse(
                "/software?flash=Software+not+found",
                status_code=HTTP_303_SEE_OTHER,
            )
        try:
            queries.delete_software(conn, soft["id"])
        except ValueError as exc:
            msg = str(exc).replace(" ", "+")[:200]
            return RedirectResponse(
                f"/software/{soft['software_key']}/delete?flash={msg}",
                status_code=HTTP_303_SEE_OTHER,
            )
    finally:
        conn.close()

    return RedirectResponse(
        "/software?flash=Software+deleted",
        status_code=HTTP_303_SEE_OTHER,
    )


@router.get("/{id_or_key}", response_class=HTMLResponse)
def software_detail(
    request: Request, id_or_key: str, flash: str | None = None
) -> HTMLResponse:
    conn = connect()
    try:
        soft = queries.get_software(conn, id_or_key)
        if soft is None:
            return templates.TemplateResponse(
                request,
                "error.html",
                {"title": "Not found", "message": f"Software not found: {id_or_key}"},
                status_code=404,
            )
        assignments = queries.software_assignments(conn, soft["id"])
        seat_count = int(soft["seat_count"] or 0)
        yearly_cost = float(soft["yearly_cost"] or 0)
        per_seat = None
        if soft["license_type"] == "per-seat" and seat_count > 0:
            per_seat = yearly_cost / seat_count
        assignment_count = len(assignments)
    finally:
        conn.close()

    return templates.TemplateResponse(
        request,
        "software/detail.html",
        {
            "title": soft["name"],
            "software": soft,
            "assignments": assignments,
            "seat_count": seat_count,
            "yearly_cost": yearly_cost,
            "per_seat": per_seat,
            "assignment_count": assignment_count,
            "flash": flash,
        },
    )
