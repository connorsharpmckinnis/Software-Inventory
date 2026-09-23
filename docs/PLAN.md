# Software inventory prototype — plan (updated 2026-09-10)

## Context
David Epley needs a relational inventory because ServiceDesk Plus does not fit license assignment + fund-aware cost exploration. Internal-only tool on the Town network (Docker). No auth/SSO required for v1 (network access is the gate). David prefers self-hosted over Power BI.

## Product goals (v1)
1. Explorer: filter/sort/click software, people, assignments (dept, fund, contract Y/N, etc.)
2. Input: add/edit software titles (seats + yearly cost on the software row)
3. Assign: link a person to a software; billing fund always from `person.fund`
4. Reports: yearly cost rollups, seats used vs purchased, cost by fund/dept; derived per-seat cost
5. Seed from CSV; easy backup/export of SQLite + CSV dumps

## Non-goals (v1)
Auth/SSO/roles (maybe later), Infor live sync, device/install inventory, replacing SDP entirely, **contract/payment bundling across titles**, nested license “pools”

## Data model
- **fund**: code (e.g. 4055), label; legacy numbering — do not assume tidy hierarchy
- **person**: employee_id, name, department_name, fund_code → fund, email, status
- **software**: key/name/publisher, license_type (per-seat|concurrent|site|unknown), **seat_count**, **yearly_cost**, primary_department, owner, is_contract, status, notes
  - Each license product is its own row (e.g. Acrobat ≠ Creative Cloud All Access; temp contractor Adobe seats = separate row)
  - Derived: per_seat_cost = yearly_cost / seat_count when seat_count > 0 and license_type is per-seat
- **assignment**: software_id, person_id, assigned_on, notes (UNIQUE software_id + person_id)
  - Billing fund = person.fund always (no override in v1)
- **Removed:** `software_pool` table and `assignment.pool_id`

## Stack decision (prefer simple)
**FastAPI + SQLite + server-rendered HTML (Jinja) + small vanilla JS (or HTMX)** — not React/Vite for v1.

Why: David-facing internal CRUD/explorer does not need a SPA; less build tooling, easier Docker, faster to demo. Tailwind via CDN is fine. Revisit React only if UI complexity explodes.

Docker Compose: app + volume for `data/inventory.db`; scripts for `export` (CSV zip) and DB file copy backup.

## Seed files (dummy — replace later)
- `data/seed/software.csv`
- `data/seed/employees.csv`
- `data/seed/assignments.csv` (optional starter links)

Import command rebuilds/merges into SQLite. Document column map so official sheets drop in.
**Force re-seed clears and rebuilds** (prototype OK; no in-place schema migrations).

## Screens
1. Software list + filters → detail (seats/cost, assignments, add assignment)
2. People list + filters → detail (assignments, add software)
3. Software create/edit (includes seats + yearly cost)
4. Reports (KPIs + tables)
5. Admin: import CSV, download backup/export

## Cost allocation (reports)
- Billing fund/dept from person
- Per-seat + seat_count > 0: each assignment gets yearly_cost / seat_count
- Else: even-split software yearly_cost across its assignments
- KPI total = sum of software.yearly_cost

## Repo location
`/Users/connormckinnis/Developer/software-inventory`

## Build order
1. Scaffold Docker + FastAPI + SQLite schema + seed import ✅
2. Read-only explorers ✅
3. Assignments CRUD ✅
4. Software CRUD ✅
5. Reports + backup/export ✅
6. README for David ✅
7. Remove pools — flatten seats/cost onto software ✅
