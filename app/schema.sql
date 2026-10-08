-- Software inventory schema (SQLite)
-- Each license product is its own software row (no software_pool nesting).

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS fund (
    code TEXT PRIMARY KEY,
    label TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS person (
    employee_id TEXT PRIMARY KEY,
    first_name TEXT NOT NULL,
    last_name TEXT NOT NULL,
    department_name TEXT,
    fund_code TEXT NOT NULL REFERENCES fund(code),
    email TEXT,
    status TEXT DEFAULT 'active',
    type TEXT DEFAULT 'employee'
);

CREATE TABLE IF NOT EXISTS software (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    software_key TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    publisher TEXT,
    license_type TEXT NOT NULL DEFAULT 'unknown'
        CHECK (license_type IN ('per-seat', 'concurrent', 'site', 'unknown')),
    seat_count INTEGER NOT NULL DEFAULT 0,
    yearly_cost REAL NOT NULL DEFAULT 0,
    primary_department TEXT,
    owner_employee_id TEXT REFERENCES person(employee_id),
    owner_name TEXT,
    is_contract INTEGER NOT NULL DEFAULT 0,
    status TEXT DEFAULT 'active',
    notes TEXT,
    -- Town inventory sheet fields (David export)
    users TEXT,
    external_use INTEGER NOT NULL DEFAULT 0,
    external_facing INTEGER NOT NULL DEFAULT 0,
    support_link TEXT,
    support_email TEXT,
    support_phone TEXT,
    support_hours TEXT,
    able_to_retire TEXT,
    able_to_replace TEXT,
    sensitive_data TEXT,
    sensitive_data_details TEXT
);

CREATE TABLE IF NOT EXISTS assignment (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    software_id INTEGER NOT NULL REFERENCES software(id) ON DELETE CASCADE,
    person_id TEXT NOT NULL REFERENCES person(employee_id),
    assigned_on TEXT,
    notes TEXT,
    UNIQUE (software_id, person_id)
);

CREATE INDEX IF NOT EXISTS idx_person_fund ON person(fund_code);
CREATE INDEX IF NOT EXISTS idx_software_key ON software(software_key);
CREATE INDEX IF NOT EXISTS idx_assignment_software ON assignment(software_id);
CREATE INDEX IF NOT EXISTS idx_assignment_person ON assignment(person_id);
