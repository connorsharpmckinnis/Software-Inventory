"""Server-rendered pages (Jinja)."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.db import connect
from app.seed import counts_snapshot

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/", response_class=HTMLResponse)
def home(request: Request) -> HTMLResponse:
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
        "home.html",
        {
            "title": "Software Inventory",
            "counts": counts,
        },
    )
