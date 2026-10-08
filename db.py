"""Database helpers: connection handling, initialisation and first-run seed data."""
import sqlite3

from flask import current_app, g
from werkzeug.security import generate_password_hash

# (name, base_score)  - base_score feeds the priority recommender (0 = low ... 3 = serious)
DEFAULT_CATEGORIES = [
    ("Classroom", 0),
    ("Electricity", 2),
    ("Wi-Fi / Network", 1),
    ("Laboratory", 1),
    ("Cleanliness", 0),
    ("Water Supply", 2),
    ("Safety & Security", 3),
    ("Other", 0),
]


def get_db():
    """One connection per request, stored on Flask's `g` object."""
    if "db" not in g:
        g.db = sqlite3.connect(current_app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row            # rows behave like dictionaries
        g.db.execute("PRAGMA foreign_keys = ON")  # SQLite needs this to enforce FKs
    return g.db


def close_db(_error=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db(app):
    """Create tables (if missing) and insert default categories + first admin."""
    with app.app_context():
        db = get_db()
        with app.open_resource("schema.sql") as f:
            db.executescript(f.read().decode("utf-8"))

        if db.execute("SELECT COUNT(*) FROM categories").fetchone()[0] == 0:
            db.executemany(
                "INSERT INTO categories (name, base_score) VALUES (?, ?)", DEFAULT_CATEGORIES
            )

        has_admin = db.execute("SELECT 1 FROM users WHERE role = 'admin' LIMIT 1").fetchone()
        if not has_admin:
            cfg = app.config
            db.execute(
                "INSERT INTO users (name, email, password_hash, role) VALUES (?, ?, ?, 'admin')",
                (
                    cfg["ADMIN_NAME"],
                    cfg["ADMIN_EMAIL"].lower(),
                    generate_password_hash(cfg["ADMIN_PASSWORD"]),
                ),
            )
            if not cfg.get("ADMIN_PASSWORD_FROM_ENV"):
                print("WARNING: using the DEFAULT admin password. Set ADMIN_PASSWORD in .env!")
        db.commit()
        close_db()
