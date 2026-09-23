# Software Inventory (prototype)

Internal Town of Apex tool for license seats, assignments, and fund-aware cost exploration.

**Stack:** FastAPI + SQLite + Jinja2 (server-rendered HTML). No React, no auth/SSO, no Power BI.

**Model:** each license product is its own software row (seats + yearly cost on the title). No nested pools. Assignments link person ↔ software only.

See [docs/PLAN.md](docs/PLAN.md) for product goals and [docs/COLUMN_MAP.md](docs/COLUMN_MAP.md) for CSV → table mapping.

## Quick start (Docker — preferred)

```bash
cd /Users/connormckinnis/Developer/software-inventory
docker compose up --build
```

Then open http://localhost:8000/

- On first start, if `data/inventory.db` is empty, seed CSVs are imported automatically.
- SQLite file is persisted via the `./data` volume.

### Re-import seed (force rebuild — prototype OK)

```bash
# Inside the running container (clears tables, rebuilds schema, re-imports)
docker compose exec web python -m app.seed --force

# Or via HTTP
curl -X POST http://localhost:8000/admin/import-seed
```

### Useful endpoints

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/` | Home page (counts) |
| GET | `/software` | Software explorer (filter/sort) |
| GET/POST | `/software/new` | Create software (seats + yearly cost) |
| GET | `/software/{id or key}` | Software detail + assignments |
| GET/POST | `/software/{key}/edit` | Edit metadata including seats/cost (`software_key` locked) |
| GET/POST | `/software/{key}/delete` | Delete (blocked if assignments exist) |
| GET | `/people` | People explorer (filter/sort) |
| GET | `/people/{employee_id}` | Person detail + assignments |
| GET | `/assignments` | Assignments list (filter) |
| GET/POST | `/assignments/new` | Create assignment (person ↔ software) |
| GET/POST | `/assignments/{id}/edit` | Edit notes |
| GET/POST | `/assignments/{id}/delete` | Delete with confirm |
| GET | `/reports` | KPIs, cost by fund/dept, seats used vs purchased |
| GET | `/admin` | Admin UI (backup + export links) |
| GET | `/admin/backup` | Download `inventory.db` |
| GET | `/admin/export` or `/admin/export.csv.zip` | Zip of CSV dumps (no pools file) |
| GET | `/health` | Liveness `{status: ok}` |
| GET | `/admin/stats` | JSON row counts |
| POST | `/admin/import-seed` | Force clear/rebuild + re-import `data/seed/*.csv` |

## Click-through (David)

1. **Software CRUD** — Home → Software → **New software** → fill key/name/license + seats/cost → Create. Open the title → **Edit** (key stays locked). Delete software only after unassigning everyone.
2. **Assignments** — Software detail → Assign person, or Assignments → New (no pool picker).
3. **Reports** — Nav **Reports**: KPIs, cost by fund, cost by department, seats used vs purchased.
4. **Backup / export** — Nav **Admin** → Download `inventory.db` or CSV zip. Or: `curl -OJ http://localhost:8000/admin/backup` and `curl -OJ http://localhost:8000/admin/export`.

## Cost allocation (reports)

- Billing fund/department always from the **person** record (never overridden on the assignment).
- **Per-seat** with `seat_count > 0`: each assignment on that software is charged `yearly_cost / seat_count`. Unused seats are unallocated; over-assignment can exceed the software yearly cost.
- **Concurrent / site / unknown**, or `seat_count == 0`: even-split `yearly_cost` across assignments on that software, then sum by person fund or department.
- KPI **Total yearly cost** is the sum of all `software.yearly_cost` values (not the allocated sum).

## Local run (venv, no Docker)

```bash
cd /Users/connormckinnis/Developer/software-inventory
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m app.seed --force
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Environment: `INVENTORY_DB` defaults to `data/inventory.db`.

## Seed files

Place/replace CSVs under `data/seed/`:

- `employees.csv` — people + funds
- `software.csv` — one row per license product (includes `seat_count`, `yearly_cost`)
- `assignments.csv` — software ↔ person links (no `pool_label`)

Column details: [docs/COLUMN_MAP.md](docs/COLUMN_MAP.md).

Expected dummy seed counts (approx): **5 funds, 5 people, 6 software** (Adobe split: `SW-002` Creative Cloud + `SW-006` Temp contractor), **9 assignments**. No pools.

## Backup & export

**SQLite file (full DB):**

- Browser: [Admin → Download inventory.db](http://localhost:8000/admin/backup)
- CLI: `curl -OJ http://localhost:8000/admin/backup`
- Or copy: `cp data/inventory.db data/inventory-backup-$(date +%Y%m%d).db`

**CSV zip** (`funds`, `people`, `software`, `assignments` — COLUMN_MAP-aligned; **no pools.csv**):

- Browser: [Admin → Download CSV zip](http://localhost:8000/admin/export)
- CLI: `curl -OJ http://localhost:8000/admin/export`

Keep seed CSVs under version control; do not commit `inventory.db` (see `.gitignore`).

## Project layout

```
app/
  main.py          # FastAPI app + auto-seed on empty DB
  db.py            # SQLite helpers (INVENTORY_DB)
  schema.sql       # Tables (no software_pool)
  seed.py          # CSV import; --force clears/rebuilds
  queries.py       # Explorers, CRUD, reports
  routers/         # health/admin, pages, software, people, assignments, reports
  templates/       # Jinja + Tailwind CDN (Apex tokens)
data/
  seed/            # Source CSVs
  inventory.db     # Runtime DB (volume / gitignored)
docs/
  PLAN.md
  COLUMN_MAP.md
Dockerfile
docker-compose.yml
requirements.txt
```
