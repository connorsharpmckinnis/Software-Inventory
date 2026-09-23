"""Reports: cost by fund/dept, seats used vs purchased."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.db import connect
from app import queries

router = APIRouter(tags=["reports"])
templates = Jinja2Templates(directory="app/templates")


@router.get("/reports", response_class=HTMLResponse)
def reports_page(request: Request) -> HTMLResponse:
    conn = connect()
    try:
        kpis = queries.report_kpis(conn)
        by_fund = queries.report_cost_by_fund(conn)
        by_dept = queries.report_cost_by_department(conn)
        seats = queries.report_seats_used_vs_purchased(conn)
    finally:
        conn.close()

    return templates.TemplateResponse(
        request,
        "reports.html",
        {
            "title": "Reports",
            "kpis": kpis,
            "by_fund": by_fund,
            "by_dept": by_dept,
            "seats": seats,
        },
    )
