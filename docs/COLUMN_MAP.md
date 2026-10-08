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
| `fund_label`       | `fund.label`           | Optional; defaults to fund_code |
| `status`           | `person.status`        | e.g. active (normalized lowercase on bulk import) |
| `email`            | `person.email`         | |
| `type`             | `person.type`          | e.g. employee, contractor (from RelationshipToOrganization) |

**HR export aliases (bulk import auto-map):** `Employee` → employee_id, `Name.GivenName` / `Name.FamilyName`, `Employee.APEXDepartment`, `ExpenseAccount.FinanceDimension3`, `Employee.EmployeeWorkEmailAddress`, `Employee.APEXEmployeeStatus`, `Employee.RelationshipToOrganization` → type.

Billing fund for any assignment always comes from `person.fund_code` — never from the assignment row.

## `software.csv` → `software`

| CSV column (app / seed) | Table.column | Notes |
|-------------------------|--------------|-------|
| `software_key` | `software.software_key` | Unique; auto-slugged from Application on bulk import when blank |
| `name` / **Application** | `software.name` | |
| `primary_department` / **Department** | `software.primary_department` | |
| `owner_name` / **Owner** | `software.owner_name` | Free-text owner (often a dept/team) |
| `users` / **Users** | `software.users` | Who uses the app |
| `external_use` / **External Use** (sheet typo: Exernal Use) | `software.external_use` | yes → 1 |
| `external_facing` / **External Facing** | `software.external_facing` | yes → 1 |
| `notes` / **Notes** | `software.notes` | |
| `support_link` / **Support Link for tickets/info** | `software.support_link` | |
| `support_email` / **Email** | `software.support_email` | Vendor support email |
| `support_phone` / **Phone** | `software.support_phone` | |
| `support_hours` / **Support Hours** | `software.support_hours` | |
| `able_to_retire` / **Able to Retire** | `software.able_to_retire` | Free text |
| `able_to_replace` / **Able to Replace** | `software.able_to_replace` | Free text |
| `yearly_cost` / **Cost or Maintenance** | `software.yearly_cost` | Commas/currency stripped on import |
| `sensitive_data` / **Sensitive Data** | `software.sensitive_data` | e.g. Yes, Investigate |
| `sensitive_data_details` / **Sensitive Data Details** | `software.sensitive_data_details` | |
| `publisher` | `software.publisher` | Optional / legacy |
| `license_type` | `software.license_type` | `per-seat` \| `concurrent` \| `site` \| `unknown` |
| `seat_count` | `software.seat_count` | Optional / legacy |
| `is_contract` | `software.is_contract` | Optional / legacy |
| `owner_employee_id` | `software.owner_employee_id` | FK → person (optional) |
| `status` | `software.status` | Default `active` |

**Bulk import:** Admin → Import software. Duplicate Application names (e.g. two SiteImprove rows) get `siteimprove` and `siteimprove-2` keys. Upserts on `software_key`.

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
