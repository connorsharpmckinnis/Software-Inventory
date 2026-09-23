# Seed CSV → database column map

Dummy seed files live in `data/seed/`. Replace them with official sheets that use the same headers (or update this map).

**Product rule:** each license product is its own `software` row. There is no `software_pool` table. Do not nest seats/cost under a parent title (e.g. Acrobat and Creative Cloud All Access are two software rows, not pools).

## `employees.csv` → `fund` + `person`

| CSV column         | Table.column           | Notes |
|--------------------|------------------------|-------|
| `employee_id`      | `person.employee_id`   | PK |
| `first_name`       | `person.first_name`    | |
| `last_name`        | `person.last_name`     | |
| `department_name`  | `person.department_name` | Free-text dept name |
| `fund_code`        | `person.fund_code` + `fund.code` | Upserts fund first |
| `fund_label`       | `fund.label`           | |
| `status`           | `person.status`        | e.g. active |
| `email`            | `person.email`         | |

Billing fund for any assignment always comes from `person.fund_code` — never from the assignment row.

## `software.csv` → `software`

| CSV column            | Table.column | Notes |
|-----------------------|--------------|-------|
| `software_key`        | `software.software_key` | Unique business key |
| `name`                | `software.name`         | |
| `publisher`           | `software.publisher`    | |
| `license_type`        | `software.license_type` | `per-seat` | `concurrent` | `site` | `unknown` |
| `seat_count`          | `software.seat_count`   | Purchased seats for this product |
| `yearly_cost`         | `software.yearly_cost`  | Yearly cost for this product |
| `is_contract`         | `software.is_contract`  | `yes`/`true`/`1` → true |
| `primary_department`  | `software.primary_department` | |
| `owner_employee_id`   | `software.owner_employee_id` | FK → person (optional) |
| `owner_name`          | `software.owner_name`   | Display name snapshot |
| `status`              | `software.status`       | |
| `notes`               | `software.notes`        | |

**Removed (was pool nesting):** `pool_2_label`, `pool_2_seat_count`, `pool_2_yearly_cost`. Former Adobe `pool_2` (“Temp contractor pool”) is now its own software row `SW-006`.

**Derived (not stored):** `per_seat_cost = yearly_cost / seat_count` when `seat_count > 0` and `license_type` is `per-seat` — compute in queries/templates.

## `assignments.csv` → `assignment`

| CSV column      | Table.column / behavior | Notes |
|-----------------|-------------------------|-------|
| `software_key`  | resolve → `assignment.software_id` | Must exist in software |
| `employee_id`   | `assignment.person_id`  | Must exist in person |
| `notes`         | `assignment.notes`      | |

**Removed:** `pool_label` / `pool_id`. Assignments link person ↔ software only. If a former seed assignment pointed at `pool_2`, retarget it to the new software_key (e.g. `SW-006`).

No fund column on assignments — fund is always from the person.

## Force re-seed

Prototype: `python -m app.seed --force` (or `POST /admin/import-seed`) **drops all tables** (including legacy `software_pool` if present), recreates schema from `app/schema.sql`, and re-imports CSVs. Empty DB on app startup still auto-seeds.
