"""Reusable CSV bulk-import engine with field mapping.

Targets (people now; software/assignments later) declare app fields, aliases
for auto-mapping headers, and a commit function. The wizard stores uploaded
CSV bytes under data/uploads/ and reuses the same parse → map → preview →
commit flow for each target.
"""

from __future__ import annotations

import csv
import json
import re
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from app.db import REPO_ROOT, connect
from app.queries import allocate_software_key

UPLOAD_DIR = REPO_ROOT / "data" / "uploads"


# ---------------------------------------------------------------------------
# Transforms
# ---------------------------------------------------------------------------


def title_case(value: str) -> str:
    return value.strip().title() if value.strip() else ""


def lower_case(value: str) -> str:
    return value.strip().lower() if value.strip() else ""


def normalize_type(value: str) -> str:
    """Map RelationshipToOrganization-style values to a short type slug."""
    raw = value.strip()
    if not raw:
        return "employee"
    # Collapse spaces/underscores; keep alphanumeric + hyphen
    slug = re.sub(r"[\s_]+", "-", raw.lower())
    slug = re.sub(r"[^a-z0-9\-]", "", slug)
    return slug or "employee"


def normalize_license_type(value: str) -> str:
    lt = value.strip().lower() or "unknown"
    if lt in {"per-seat", "perseat", "per_seat"}:
        return "per-seat"
    if lt in {"concurrent", "floating"}:
        return "concurrent"
    if lt in {"site", "site-license", "site_license"}:
        return "site"
    if lt == "unknown":
        return "unknown"
    return "unknown"


def boolish(value: str) -> str:
    """Normalize yes/true/1 → '1', else '0'."""
    return "1" if value.strip().lower() in {"yes", "true", "1", "y"} else "0"


def money(value: str) -> str:
    """Strip currency symbols/commas; return cleaned numeric string (or '')."""
    raw = (value or "").strip()
    if not raw:
        return ""
    cleaned = re.sub(r"[^\d.\-]", "", raw)
    return cleaned


TRANSFORMS: dict[str, Callable[[str], str]] = {
    "title_case": title_case,
    "lower": lower_case,
    "type": normalize_type,
    "license_type": normalize_license_type,
    "boolish": boolish,
    "money": money,
}


# ---------------------------------------------------------------------------
# Target field definitions
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FieldDef:
    key: str
    label: str
    required: bool = False
    transform: str | None = None
    aliases: tuple[str, ...] = ()
    default: str | None = None


@dataclass
class ImportTarget:
    key: str
    label: str
    description: str
    fields: list[FieldDef]
    validate: Callable[[sqlite3.Connection, list[dict[str, str]]], "PreviewResult"]
    commit: Callable[[sqlite3.Connection, list[dict[str, str]]], dict[str, int]]
    success_redirect: str
    count_key: str


def _norm_header(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (name or "").strip().lower())


def suggest_mapping(headers: list[str], fields: list[FieldDef]) -> dict[str, str]:
    """Return {app_field_key: csv_header_or_empty} using aliases + exact key."""
    by_norm: dict[str, str] = {}
    for h in headers:
        n = _norm_header(h)
        if n and n not in by_norm:
            by_norm[n] = h

    mapping: dict[str, str] = {}
    used: set[str] = set()
    for f in fields:
        candidates = (f.key,) + f.aliases
        chosen = ""
        for c in candidates:
            hit = by_norm.get(_norm_header(c))
            if hit and hit not in used:
                chosen = hit
                break
        mapping[f.key] = chosen
        if chosen:
            used.add(chosen)
    return mapping


# ---------------------------------------------------------------------------
# Upload session persistence
# ---------------------------------------------------------------------------


def _ensure_upload_dir() -> Path:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    return UPLOAD_DIR


def save_upload(filename: str, content: bytes) -> str:
    """Persist CSV bytes; return upload_id."""
    _ensure_upload_dir()
    upload_id = uuid.uuid4().hex
    # Normalize to utf-8 text for later DictReader
    text = content.decode("utf-8-sig", errors="replace")
    path = UPLOAD_DIR / f"{upload_id}.csv"
    path.write_text(text, encoding="utf-8")
    meta = {
        "upload_id": upload_id,
        "filename": filename,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    (UPLOAD_DIR / f"{upload_id}.meta.json").write_text(
        json.dumps(meta), encoding="utf-8"
    )
    return upload_id


def load_upload_rows(upload_id: str) -> tuple[list[str], list[dict[str, str]], dict]:
    """Return (headers, rows, meta). Raises FileNotFoundError if missing."""
    if not re.fullmatch(r"[a-f0-9]{32}", upload_id):
        raise FileNotFoundError("Invalid upload id")
    csv_path = UPLOAD_DIR / f"{upload_id}.csv"
    meta_path = UPLOAD_DIR / f"{upload_id}.meta.json"
    if not csv_path.exists():
        raise FileNotFoundError(f"Upload not found: {upload_id}")
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
    with csv_path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        headers = list(reader.fieldnames or [])
        rows = [dict(r) for r in reader]
    return headers, rows, meta


def delete_upload(upload_id: str) -> None:
    if not re.fullmatch(r"[a-f0-9]{32}", upload_id):
        return
    for suffix in (".csv", ".meta.json"):
        path = UPLOAD_DIR / f"{upload_id}{suffix}"
        if path.exists():
            path.unlink()


# ---------------------------------------------------------------------------
# Mapping / preview / apply
# ---------------------------------------------------------------------------


def apply_mapping(
    raw_rows: list[dict[str, str]],
    mapping: dict[str, str],
    fields: list[FieldDef],
) -> list[dict[str, str]]:
    """Map CSV rows → canonical app-field dicts with transforms applied."""
    field_by_key = {f.key: f for f in fields}
    out: list[dict[str, str]] = []
    for raw in raw_rows:
        mapped: dict[str, str] = {}
        for key, fdef in field_by_key.items():
            csv_col = (mapping.get(key) or "").strip()
            if csv_col:
                value = (raw.get(csv_col) or "").strip()
            else:
                value = ""
            if not value and fdef.default is not None:
                value = fdef.default
            if value and fdef.transform:
                fn = TRANSFORMS.get(fdef.transform)
                if fn:
                    value = fn(value)
            mapped[key] = value
        out.append(mapped)
    return out


@dataclass
class RowIssue:
    row_number: int  # 1-based data row (header is row 0)
    message: str


@dataclass
class PreviewResult:
    mapped_rows: list[dict[str, str]]
    valid_rows: list[dict[str, str]]
    issues: list[RowIssue]  # rows skipped
    insert_count: int
    update_count: int
    sample: list[dict[str, str]] = field(default_factory=list)
    warnings: list[RowIssue] = field(default_factory=list)  # imported with fixes


def validate_people_rows(
    conn: sqlite3.Connection, mapped_rows: list[dict[str, str]]
) -> PreviewResult:
    issues: list[RowIssue] = []
    valid: list[dict[str, str]] = []
    existing_ids = {
        r[0]
        for r in conn.execute("SELECT employee_id FROM person").fetchall()
    }
    insert_n = 0
    update_n = 0

    for i, row in enumerate(mapped_rows, start=1):
        eid = row.get("employee_id", "").strip()
        first = row.get("first_name", "").strip()
        last = row.get("last_name", "").strip()
        fund = row.get("fund_code", "").strip()
        row_issues: list[str] = []
        if not eid:
            row_issues.append("missing employee_id")
        if not first:
            row_issues.append("missing first_name")
        if not last:
            row_issues.append("missing last_name")
        if not fund:
            row_issues.append("missing fund_code")
        if row_issues:
            for msg in row_issues:
                issues.append(RowIssue(i, msg))
            continue
        valid.append(row)
        if eid in existing_ids:
            update_n += 1
        else:
            insert_n += 1

    return PreviewResult(
        mapped_rows=mapped_rows,
        valid_rows=valid,
        issues=issues,
        insert_count=insert_n,
        update_count=update_n,
        sample=valid[:5],
    )


def commit_people(
    conn: sqlite3.Connection, rows: list[dict[str, str]]
) -> dict[str, int]:
    """Upsert funds + people from canonical mapped rows."""
    # Funds first (label = fund_label or fund_code)
    seen_funds: dict[str, str] = {}
    for row in rows:
        code = (row.get("fund_code") or "").strip()
        if not code:
            continue
        label = (row.get("fund_label") or "").strip() or code
        seen_funds[code] = label
    for code, label in seen_funds.items():
        conn.execute(
            """
            INSERT INTO fund (code, label) VALUES (?, ?)
            ON CONFLICT(code) DO UPDATE SET
                label = CASE
                    WHEN excluded.label != excluded.code THEN excluded.label
                    ELSE fund.label
                END
            """,
            (code, label),
        )

    people_n = 0
    for row in rows:
        employee_id = (row.get("employee_id") or "").strip()
        if not employee_id:
            continue
        person_type = (row.get("type") or "employee").strip() or "employee"
        status = (row.get("status") or "active").strip() or "active"
        conn.execute(
            """
            INSERT INTO person (
                employee_id, first_name, last_name, department_name,
                fund_code, email, status, type
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(employee_id) DO UPDATE SET
                first_name = excluded.first_name,
                last_name = excluded.last_name,
                department_name = excluded.department_name,
                fund_code = excluded.fund_code,
                email = excluded.email,
                status = excluded.status,
                type = excluded.type
            """,
            (
                employee_id,
                (row.get("first_name") or "").strip(),
                (row.get("last_name") or "").strip(),
                (row.get("department_name") or "").strip() or None,
                (row.get("fund_code") or "").strip(),
                (row.get("email") or "").strip() or None,
                status,
                person_type,
            ),
        )
        people_n += 1
    conn.commit()
    return {"funds": len(seen_funds), "people": people_n}


PEOPLE_FIELDS: list[FieldDef] = [
    FieldDef(
        key="employee_id",
        label="Employee ID",
        required=True,
        aliases=("Employee", "EmpID", "Emp Id", "ID"),
    ),
    FieldDef(
        key="first_name",
        label="First name",
        required=True,
        transform="title_case",
        aliases=("Name.GivenName", "GivenName", "FirstName", "First Name"),
    ),
    FieldDef(
        key="last_name",
        label="Last name",
        required=True,
        transform="title_case",
        aliases=("Name.FamilyName", "FamilyName", "LastName", "Last Name"),
    ),
    FieldDef(
        key="department_name",
        label="Department",
        aliases=(
            "Employee.APEXDepartment",
            "APEXDepartment",
            "Department",
            "Dept",
        ),
    ),
    FieldDef(
        key="fund_code",
        label="Fund code",
        required=True,
        aliases=(
            "ExpenseAccount.FinanceDimension3",
            "FinanceDimension3",
            "FundCode",
            "Fund Code",
            "Fund",
        ),
    ),
    FieldDef(
        key="fund_label",
        label="Fund label (optional)",
        aliases=("FundLabel", "Fund Label", "FundName", "Fund Name"),
    ),
    FieldDef(
        key="email",
        label="Email",
        aliases=(
            "Employee.EmployeeWorkEmailAddress",
            "EmployeeWorkEmailAddress",
            "WorkEmail",
            "EmailAddress",
            "Email",
        ),
    ),
    FieldDef(
        key="status",
        label="Status",
        transform="lower",
        default="active",
        aliases=(
            "Employee.APEXEmployeeStatus",
            "APEXEmployeeStatus",
            "EmployeeStatus",
            "Status",
        ),
    ),
    FieldDef(
        key="type",
        label="Type (relationship)",
        transform="type",
        default="employee",
        aliases=(
            "Employee.RelationshipToOrganization",
            "RelationshipToOrganization",
            "Relationship",
            "Type",
        ),
    ),
]


def validate_software_rows(
    conn: sqlite3.Connection, mapped_rows: list[dict[str, str]]
) -> PreviewResult:
    issues: list[RowIssue] = []
    all_warnings: list[RowIssue] = []
    valid: list[dict[str, str]] = []
    existing_keys = {
        r[0]
        for r in conn.execute("SELECT software_key FROM software").fetchall()
    }
    known_people = {
        r[0]
        for r in conn.execute("SELECT employee_id FROM person").fetchall()
    }
    reserved_keys: set[str] = set()
    insert_n = 0
    update_n = 0

    for i, row in enumerate(mapped_rows, start=1):
        name = row.get("name", "").strip()
        if not name:
            issues.append(RowIssue(i, "missing name (Application)"))
            continue

        key = row.get("software_key", "").strip()
        if not key:
            key = allocate_software_key(conn, name, reserved=reserved_keys)
            all_warnings.append(
                RowIssue(i, f"generated software_key {key!r} from Application")
            )
            row = {**row, "software_key": key}
        reserved_keys.add(key)

        owner = row.get("owner_employee_id", "").strip()
        if owner and owner not in known_people:
            all_warnings.append(
                RowIssue(i, f"unknown owner_employee_id {owner!r} — cleared")
            )
            row = {**row, "owner_employee_id": ""}

        seat = row.get("seat_count", "").strip()
        cost = money(row.get("yearly_cost", "") or "")
        row = {**row, "yearly_cost": cost}
        try:
            if seat:
                float(seat)
        except ValueError:
            all_warnings.append(
                RowIssue(i, f"invalid seat_count {seat!r} — using 0")
            )
            row = {**row, "seat_count": "0"}
        try:
            if cost:
                float(cost)
        except ValueError:
            all_warnings.append(
                RowIssue(i, f"invalid yearly_cost {cost!r} — using 0")
            )
            row = {**row, "yearly_cost": "0"}

        valid.append(row)
        if key in existing_keys:
            update_n += 1
        else:
            insert_n += 1

    return PreviewResult(
        mapped_rows=mapped_rows,
        valid_rows=valid,
        issues=issues,
        insert_count=insert_n,
        update_count=update_n,
        sample=valid[:5],
        warnings=all_warnings,
    )


def _parse_int(value: str | None) -> int:
    if value is None or str(value).strip() == "":
        return 0
    try:
        return int(float(str(value).strip()))
    except ValueError:
        return 0


def _parse_float(value: str | None) -> float:
    if value is None or str(value).strip() == "":
        return 0.0
    try:
        return float(money(str(value)))
    except ValueError:
        return 0.0


def _opt(value: str | None) -> str | None:
    return (value or "").strip() or None


def commit_software(
    conn: sqlite3.Connection, rows: list[dict[str, str]]
) -> dict[str, int]:
    """Upsert software by software_key."""
    n = 0
    for row in rows:
        key = (row.get("software_key") or "").strip()
        if not key:
            continue
        name = (row.get("name") or "").strip() or key
        license_type = (row.get("license_type") or "unknown").strip() or "unknown"
        if license_type not in {"per-seat", "concurrent", "site", "unknown"}:
            license_type = "unknown"
        is_contract = (row.get("is_contract") or "0").strip() in {"1", "yes", "true"}
        status = (row.get("status") or "active").strip() or "active"
        owner_id = (row.get("owner_employee_id") or "").strip() or None
        external_use = (row.get("external_use") or "0").strip() in {"1", "yes", "true"}
        external_facing = (row.get("external_facing") or "0").strip() in {
            "1",
            "yes",
            "true",
        }

        conn.execute(
            """
            INSERT INTO software (
                software_key, name, publisher, license_type,
                seat_count, yearly_cost,
                primary_department, owner_employee_id, owner_name,
                is_contract, status, notes,
                users, external_use, external_facing,
                support_link, support_email, support_phone, support_hours,
                able_to_retire, able_to_replace,
                sensitive_data, sensitive_data_details
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(software_key) DO UPDATE SET
                name = excluded.name,
                publisher = excluded.publisher,
                license_type = excluded.license_type,
                seat_count = excluded.seat_count,
                yearly_cost = excluded.yearly_cost,
                primary_department = excluded.primary_department,
                owner_employee_id = excluded.owner_employee_id,
                owner_name = excluded.owner_name,
                is_contract = excluded.is_contract,
                status = excluded.status,
                notes = excluded.notes,
                users = excluded.users,
                external_use = excluded.external_use,
                external_facing = excluded.external_facing,
                support_link = excluded.support_link,
                support_email = excluded.support_email,
                support_phone = excluded.support_phone,
                support_hours = excluded.support_hours,
                able_to_retire = excluded.able_to_retire,
                able_to_replace = excluded.able_to_replace,
                sensitive_data = excluded.sensitive_data,
                sensitive_data_details = excluded.sensitive_data_details
            """,
            (
                key,
                name,
                _opt(row.get("publisher")),
                license_type,
                _parse_int(row.get("seat_count")),
                _parse_float(row.get("yearly_cost")),
                _opt(row.get("primary_department")),
                owner_id,
                _opt(row.get("owner_name")),
                1 if is_contract else 0,
                status,
                _opt(row.get("notes")),
                _opt(row.get("users")),
                1 if external_use else 0,
                1 if external_facing else 0,
                _opt(row.get("support_link")),
                _opt(row.get("support_email")),
                _opt(row.get("support_phone")),
                _opt(row.get("support_hours")),
                _opt(row.get("able_to_retire")),
                _opt(row.get("able_to_replace")),
                _opt(row.get("sensitive_data")),
                _opt(row.get("sensitive_data_details")),
            ),
        )
        n += 1
    conn.commit()
    return {"software": n}


SOFTWARE_FIELDS: list[FieldDef] = [
    FieldDef(
        key="name",
        label="Application / name",
        required=True,
        aliases=(
            "Application",
            "SoftwareName",
            "Software Name",
            "Product",
            "ProductName",
            "Title",
            "Name",
        ),
    ),
    FieldDef(
        key="software_key",
        label="Software key (optional — auto from Application)",
        required=False,
        aliases=("SoftwareKey", "Software Key", "Key", "ProductKey", "SKU"),
    ),
    FieldDef(
        key="primary_department",
        label="Department",
        aliases=("Department", "PrimaryDepartment", "Primary Department", "Dept"),
    ),
    FieldDef(
        key="owner_name",
        label="Owner",
        aliases=("Owner", "OwnerName", "Owner Name"),
    ),
    FieldDef(
        key="users",
        label="Users",
        aliases=("Users", "User Group", "UserGroup"),
    ),
    FieldDef(
        key="external_use",
        label="External use",
        transform="boolish",
        default="0",
        aliases=("External Use", "Exernal Use", "ExternalUse"),
    ),
    FieldDef(
        key="external_facing",
        label="External facing",
        transform="boolish",
        default="0",
        aliases=("External Facing", "ExternalFacing", "Public Facing"),
    ),
    FieldDef(
        key="notes",
        label="Notes",
        aliases=("Notes", "Note", "Comments", "Comment"),
    ),
    FieldDef(
        key="support_link",
        label="Support link",
        aliases=(
            "Support Link for tickets/info",
            "Support Link",
            "SupportLink",
            "Support URL",
        ),
    ),
    FieldDef(
        key="support_email",
        label="Support email",
        aliases=("Email", "Support Email", "SupportEmail"),
    ),
    FieldDef(
        key="support_phone",
        label="Support phone",
        aliases=("Phone", "Support Phone", "SupportPhone"),
    ),
    FieldDef(
        key="support_hours",
        label="Support hours",
        aliases=("Support Hours", "SupportHours", "Hours"),
    ),
    FieldDef(
        key="able_to_retire",
        label="Able to retire",
        aliases=("Able to Retire", "AbleToRetire", "Retire"),
    ),
    FieldDef(
        key="able_to_replace",
        label="Able to replace",
        aliases=("Able to Replace", "AbleToReplace", "Replace"),
    ),
    FieldDef(
        key="yearly_cost",
        label="Cost or maintenance",
        transform="money",
        default="0",
        aliases=(
            "Cost or Maintenance",
            "Cost or maintenance",
            "YearlyCost",
            "AnnualCost",
            "Cost",
            "Price",
        ),
    ),
    FieldDef(
        key="sensitive_data",
        label="Sensitive data",
        aliases=("Sensitive Data", "SensitiveData"),
    ),
    FieldDef(
        key="sensitive_data_details",
        label="Sensitive data details",
        aliases=(
            "Sensitive Data Details",
            "SensitiveDataDetails",
            "Sensitive Details",
        ),
    ),
    # Legacy / optional inventory fields (kept for seed + older sheets)
    FieldDef(
        key="publisher",
        label="Publisher",
        aliases=("Vendor", "PublisherName", "Manufacturer", "Publisher"),
    ),
    FieldDef(
        key="license_type",
        label="License type",
        transform="license_type",
        default="unknown",
        aliases=("LicenseType", "License Type", "Licensing"),
    ),
    FieldDef(
        key="seat_count",
        label="Seat count",
        default="0",
        aliases=("SeatCount", "Seats", "Quantity", "Qty"),
    ),
    FieldDef(
        key="is_contract",
        label="Is contract",
        transform="boolish",
        default="0",
        aliases=("IsContract", "Contract", "HasContract"),
    ),
    FieldDef(
        key="owner_employee_id",
        label="Owner employee ID",
        aliases=("OwnerEmployeeId", "OwnerEmployeeID", "Owner ID"),
    ),
    FieldDef(
        key="status",
        label="Status",
        transform="lower",
        default="active",
        aliases=("SoftwareStatus", "Status"),
    ),
]


IMPORT_TARGETS: dict[str, ImportTarget] = {
    "people": ImportTarget(
        key="people",
        label="People (employees)",
        description=(
            "Upsert people by employee ID. Creates fund codes when missing "
            "(label defaults to the code). Names are title-cased; status is "
            "lowercased; type comes from RelationshipToOrganization."
        ),
        fields=PEOPLE_FIELDS,
        validate=validate_people_rows,
        commit=commit_people,
        success_redirect="/people",
        count_key="people",
    ),
    "software": ImportTarget(
        key="software",
        label="Software",
        description=(
            "Upsert software by software_key (auto-generated from Application "
            "when missing). Maps Town inventory columns: Department, Owner, "
            "Users, External Use/Facing, support contact fields, cost, "
            "sensitive data, etc. Duplicate Application names get -2, -3 keys."
        ),
        fields=SOFTWARE_FIELDS,
        validate=validate_software_rows,
        commit=commit_software,
        success_redirect="/software",
        count_key="software",
    ),
}


def get_target(key: str) -> ImportTarget | None:
    return IMPORT_TARGETS.get(key)


def parse_mapping_form(form: Any, fields: list[FieldDef]) -> dict[str, str]:
    """Extract map[<field>] values from a Starlette/FastAPI Form data dict."""
    mapping: dict[str, str] = {}
    for f in fields:
        mapping[f.key] = (form.get(f"map_{f.key}") or "").strip()
    return mapping
