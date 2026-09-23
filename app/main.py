"""FastAPI entrypoint for the software inventory prototype."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.db import connect, init_schema, is_db_empty
from app.routers import assignments, health, pages, people, reports, software
from app.seed import import_seed


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Ensure schema exists; auto-seed when the DB is empty.
    init_schema()
    conn = connect()
    try:
        empty = is_db_empty(conn)
    finally:
        conn.close()
    if empty:
        print("Database empty — importing seed CSVs…")
        import_seed(force=True)
    yield


app = FastAPI(
    title="Software Inventory",
    description="Town of Apex internal software license inventory (prototype)",
    lifespan=lifespan,
)

app.include_router(health.router)
app.include_router(pages.router)
app.include_router(reports.router)
app.include_router(software.router)
app.include_router(people.router)
app.include_router(assignments.router)

# Optional static dir (create if missing so mount does not fail)
static_dir = Path("app/static")
static_dir.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
