-- Smart Campus Complaint & Solution Tracker : database schema (SQLite)
-- All timestamps are stored in UTC as 'YYYY-MM-DD HH:MM:SS'.

CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT NOT NULL,
    email         TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role          TEXT NOT NULL DEFAULT 'student' CHECK (role IN ('student', 'admin')),
    created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Admin-managed list of complaint categories.
-- base_score (0-3) tells the priority recommender how serious the category is by default.
CREATE TABLE IF NOT EXISTS categories (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL UNIQUE,
    base_score INTEGER NOT NULL DEFAULT 0 CHECK (base_score BETWEEN 0 AND 3),
    is_active  INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1))
);

CREATE TABLE IF NOT EXISTS complaints (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    complaint_code     TEXT NOT NULL UNIQUE,            -- e.g. CMP-2026-00012
    student_id         INTEGER NOT NULL REFERENCES users(id),
    title              TEXT NOT NULL,
    description        TEXT NOT NULL,
    category_id        INTEGER NOT NULL REFERENCES categories(id),
    location           TEXT NOT NULL,
    priority           TEXT NOT NULL DEFAULT 'Medium'
                       CHECK (priority IN ('Low', 'Medium', 'High', 'Urgent')),
    suggested_priority TEXT,                            -- what the recommender suggested
    priority_reason    TEXT,                            -- why (shown to the admin)
    status             TEXT NOT NULL DEFAULT 'Pending'
                       CHECK (status IN ('Pending', 'In Progress', 'Resolved')),
    image_filename     TEXT,
    created_at         TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at         TEXT NOT NULL DEFAULT (datetime('now')),
    resolved_at        TEXT
);

CREATE TABLE IF NOT EXISTS complaint_history (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    complaint_id    INTEGER NOT NULL REFERENCES complaints(id) ON DELETE CASCADE,
    previous_status TEXT,                               -- NULL for the first entry
    new_status      TEXT NOT NULL,
    remarks         TEXT,
    updated_by      INTEGER REFERENCES users(id),
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS feedback (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    complaint_id INTEGER NOT NULL UNIQUE REFERENCES complaints(id) ON DELETE CASCADE,
    rating       INTEGER NOT NULL CHECK (rating BETWEEN 1 AND 5),
    comments     TEXT,
    is_anonymous INTEGER NOT NULL DEFAULT 1 CHECK (is_anonymous IN (0, 1)),
    created_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_complaints_student  ON complaints(student_id);
CREATE INDEX IF NOT EXISTS idx_complaints_status   ON complaints(status);
CREATE INDEX IF NOT EXISTS idx_complaints_category ON complaints(category_id);
CREATE INDEX IF NOT EXISTS idx_history_complaint   ON complaint_history(complaint_id);
