"""Bulk CSV import wizard (upload → map fields → preview → commit)."""

from __future__ import annotations

from fastapi import APIRouter, File, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.status import HTTP_303_SEE_OTHER

from app import bulk_import as bi
from app.db import connect

router = APIRouter(prefix="/admin/import", tags=["import"])
templates = Jinja2Templates(directory="app/templates")


def _q(msg: str) -> str:
    """Encode flash/error query values the same way as other routers (spaces → +)."""
    return msg.replace(" ", "+")


def _redirect(path: str, *, flash: str | None = None, error: str | None = None) -> RedirectResponse:
    params: list[str] = []
    if flash:
        params.append(f"flash={_q(flash)}")
    if error:
        params.append(f"error={_q(error)}")
    url = path if not params else f"{path}?{'&'.join(params)}"
    return RedirectResponse(url, status_code=HTTP_303_SEE_OTHER)


@router.get("", response_class=HTMLResponse)
def import_index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "import/index.html",
        {
            "title": "Bulk import",
            "targets": list(bi.IMPORT_TARGETS.values()),
            "flash": request.query_params.get("flash"),
            "error": request.query_params.get("error"),
        },
    )


@router.get("/{target_key}", response_class=HTMLResponse)
def import_upload_page(request: Request, target_key: str) -> HTMLResponse:
    target = bi.get_target(target_key)
    if target is None:
        return templates.TemplateResponse(
            request,
            "error.html",
            {"title": "Not found", "message": f"Unknown import target: {target_key}"},
            status_code=404,
        )
    return templates.TemplateResponse(
        request,
        "import/upload.html",
        {
            "title": f"Import {target.label}",
            "target": target,
            "flash": request.query_params.get("flash"),
            "error": request.query_params.get("error"),
        },
    )


@router.post("/{target_key}/upload")
async def import_upload(
    request: Request,
    target_key: str,
    file: UploadFile = File(...),
) -> RedirectResponse:
    target = bi.get_target(target_key)
    if target is None:
        return _redirect("/admin/import", error="Unknown import target")

    filename = file.filename or "upload.csv"
    if not filename.lower().endswith(".csv"):
        return _redirect(
            f"/admin/import/{target_key}",
            error="Please upload a .csv file",
        )

    content = await file.read()
    if not content.strip():
        return _redirect(f"/admin/import/{target_key}", error="Uploaded file is empty")

    try:
        upload_id = bi.save_upload(filename, content)
        headers, rows, _meta = bi.load_upload_rows(upload_id)
    except Exception as exc:  # noqa: BLE001 — surface parse errors to UI
        return _redirect(
            f"/admin/import/{target_key}",
            error=f"Could not read CSV: {exc}",
        )

    if not headers:
        bi.delete_upload(upload_id)
        return _redirect(
            f"/admin/import/{target_key}",
            error="CSV has no header row",
        )
    if not rows:
        bi.delete_upload(upload_id)
        return _redirect(
            f"/admin/import/{target_key}",
            error="CSV has a header but no data rows",
        )

    return _redirect(f"/admin/import/{target_key}/map/{upload_id}")


@router.get("/{target_key}/map/{upload_id}", response_class=HTMLResponse)
def import_map_page(
    request: Request, target_key: str, upload_id: str
) -> HTMLResponse:
    target = bi.get_target(target_key)
    if target is None:
        return templates.TemplateResponse(
            request,
            "error.html",
            {"title": "Not found", "message": f"Unknown import target: {target_key}"},
            status_code=404,
        )
    try:
        headers, rows, meta = bi.load_upload_rows(upload_id)
    except FileNotFoundError:
        return _redirect(
            f"/admin/import/{target_key}",
            error="Upload expired or not found — please upload again",
        )

    mapping = bi.suggest_mapping(headers, target.fields)
    return templates.TemplateResponse(
        request,
        "import/map.html",
        {
            "title": f"Map fields — {target.label}",
            "target": target,
            "upload_id": upload_id,
            "headers": headers,
            "mapping": mapping,
            "row_count": len(rows),
            "filename": meta.get("filename", "upload.csv"),
            "sample_rows": rows[:3],
            "error": request.query_params.get("error"),
        },
    )


@router.post(
    "/{target_key}/preview/{upload_id}",
    response_class=HTMLResponse,
    response_model=None,
)
async def import_preview(request: Request, target_key: str, upload_id: str):
    target = bi.get_target(target_key)
    if target is None:
        return _redirect("/admin/import", error="Unknown import target")

    try:
        headers, raw_rows, meta = bi.load_upload_rows(upload_id)
    except FileNotFoundError:
        return _redirect(
            f"/admin/import/{target_key}",
            error="Upload expired or not found — please upload again",
        )

    form = await request.form()
    mapping = bi.parse_mapping_form(form, target.fields)

    missing_required = [
        f.label
        for f in target.fields
        if f.required and not (mapping.get(f.key) or "").strip()
    ]
    if missing_required:
        return _redirect(
            f"/admin/import/{target_key}/map/{upload_id}",
            error="Map required fields: " + ", ".join(missing_required),
        )

    mapped = bi.apply_mapping(raw_rows, mapping, target.fields)

    conn = connect()
    try:
        preview = target.validate(conn, mapped)
    finally:
        conn.close()

    return templates.TemplateResponse(
        request,
        "import/preview.html",
        {
            "title": f"Preview — {target.label}",
            "target": target,
            "upload_id": upload_id,
            "mapping": mapping,
            "headers": headers,
            "filename": meta.get("filename", "upload.csv"),
            "preview": preview,
            "total_rows": len(mapped),
        },
    )


@router.post("/{target_key}/commit/{upload_id}")
async def import_commit(
    request: Request, target_key: str, upload_id: str
) -> RedirectResponse:
    target = bi.get_target(target_key)
    if target is None:
        return _redirect("/admin/import", error="Unknown import target")

    try:
        _headers, raw_rows, _meta = bi.load_upload_rows(upload_id)
    except FileNotFoundError:
        return _redirect(
            f"/admin/import/{target_key}",
            error="Upload expired or not found — please upload again",
        )

    form = await request.form()
    mapping = bi.parse_mapping_form(form, target.fields)
    mapped = bi.apply_mapping(raw_rows, mapping, target.fields)

    conn = connect()
    try:
        preview = target.validate(conn, mapped)
        if not preview.valid_rows:
            return _redirect(
                f"/admin/import/{target_key}/map/{upload_id}",
                error="No valid rows to import — fix mapping or CSV data",
            )
        counts = target.commit(conn, preview.valid_rows)
    except Exception as exc:  # noqa: BLE001
        return _redirect(
            f"/admin/import/{target_key}",
            error=f"Import failed: {exc}",
        )
    finally:
        conn.close()

    bi.delete_upload(upload_id)
    invalid_rows = len({i.row_number for i in preview.issues})
    imported = counts.get(target.count_key, len(preview.valid_rows))
    extras = [
        f"{k}={v}"
        for k, v in counts.items()
        if k != target.count_key
    ]
    flash = (
        f"Imported {imported} {target.count_key} "
        f"({preview.insert_count} new, {preview.update_count} updated"
        + (f", {invalid_rows} row(s) skipped" if invalid_rows else "")
        + (f"; {', '.join(extras)}" if extras else "")
        + ")."
    )
    return _redirect(target.success_redirect, flash=flash)
