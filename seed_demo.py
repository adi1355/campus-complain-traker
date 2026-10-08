"""OPTIONAL: fills the database with DEMO data so the charts look good in a presentation.

    python seed_demo.py

Creates 3 demo students (password: Student@123) and about 40 complaints spread over the
last 6 months, with status history and some feedback. Safe to run twice (it skips if
the demo students already exist). Do NOT use demo data in a real deployment.
"""
import random
from datetime import datetime, timedelta, timezone

from werkzeug.security import generate_password_hash

from app import create_app
from db import get_db
from utils import suggest_priority

DEMO_PASSWORD = "Student@123"
STUDENTS = [("Aarav Sharma", "aarav@demo.edu"), ("Diya Patel", "diya@demo.edu"),
            ("Rohan Mehta", "rohan@demo.edu")]

# (category, title, description, location)
TEMPLATES = [
    ("Electricity", "Ceiling fan not working", "The ceiling fan has stopped working and the room is very hot.", "Block A, Room 101"),
    ("Electricity", "Sparks from switch board", "There are sparks coming from the switch board near the door. Dangerous for students.", "Block B, Room 204"),
    ("Electricity", "Tube lights flickering", "Two tube lights keep flickering during lectures.", "Block C, Room 12"),
    ("Wi-Fi / Network", "Wi-Fi down in library", "Wi-Fi has been down since morning and we cannot access journals.", "Central Library"),
    ("Wi-Fi / Network", "Slow internet in hostel", "Internet speed is very slow in the evening.", "Boys Hostel"),
    ("Classroom", "Projector is broken", "The projector shows no display, lectures are affected.", "Block A, Room 105"),
    ("Classroom", "Broken benches", "Three benches are broken and unsafe to sit on.", "Block D, Room 301"),
    ("Laboratory", "Computers not booting", "Five computers in the lab are not working at all.", "Computer Lab 2"),
    ("Laboratory", "Chemical smell in lab", "A strong chemical smell and smoke from the storage cupboard. Emergency.", "Chemistry Lab"),
    ("Cleanliness", "Washroom not cleaned", "The washroom has not been cleaned for two days.", "Block B, Ground Floor"),
    ("Cleanliness", "Overflowing dustbins", "Dustbins near the canteen are overflowing.", "Canteen"),
    ("Water Supply", "No water in drinking tap", "There is no water in the drinking water taps.", "Block C, 1st Floor"),
    ("Water Supply", "Water leakage in corridor", "A pipe is leaking and the corridor is slippery.", "Block A, 2nd Floor"),
    ("Safety & Security", "Broken gate lock", "The side gate lock is broken, anyone can enter at night.", "Side Gate"),
    ("Other", "Notice board damaged", "A small notice board glass is cracked.", "Admin Block"),
]
REMARKS_PROGRESS = ["Work order sent to the maintenance team.", "Technician has inspected the problem.",
                    "Parts have been ordered.", "Assigned to the electrical department."]
REMARKS_DONE = ["Issue fixed and verified.", "Replaced the faulty part.", "Cleaned and inspected.", "Problem resolved by the maintenance team."]


def ts(dt):
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def main():
    app = create_app()
    with app.app_context():
        db = get_db()
        if db.execute("SELECT 1 FROM users WHERE email = ?", (STUDENTS[0][1],)).fetchone():
            print("Demo data already present - nothing to do.")
            return
        random.seed(7)
        admin_id = db.execute("SELECT id FROM users WHERE role = 'admin' LIMIT 1").fetchone()[0]
        student_ids = []
        for name, email in STUDENTS:
            cur = db.execute("INSERT INTO users (name, email, password_hash, role) VALUES (?, ?, ?, 'student')",
                             (name, email, generate_password_hash(DEMO_PASSWORD)))
            student_ids.append(cur.lastrowid)
        cats = {r["name"]: (r["id"], r["base_score"]) for r in db.execute("SELECT * FROM categories")}
        now = datetime.now(timezone.utc)

        for i in range(40):
            cat, title, desc, loc = random.choice(TEMPLATES)
            cat_id, base = cats[cat]
            created = now - timedelta(days=random.uniform(0.2, 180), hours=random.uniform(0, 12))
            priority, reason = suggest_priority(base, title, desc)
            age_days = (now - created).days
            roll = random.random()
            if age_days > 14:                      # old complaints are mostly resolved
                status = "Resolved" if roll < 0.7 else ("In Progress" if roll < 0.85 else "Pending")
            elif age_days > 2:
                status = "Resolved" if roll < 0.2 else ("In Progress" if roll < 0.6 else "Pending")
            else:
                status = "Pending"
            student = random.choice(student_ids)
            cur = db.execute(
                "INSERT INTO complaints (complaint_code, student_id, title, description, category_id, location, "
                "priority, suggested_priority, priority_reason, status, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (f"TMP-{i}", student, title, desc, cat_id, loc, priority, priority, reason, status, ts(created), ts(created)))
            cid = cur.lastrowid
            db.execute("UPDATE complaints SET complaint_code = ? WHERE id = ?",
                       (f"CMP-{created.year}-{cid:05d}", cid))
            db.execute("INSERT INTO complaint_history (complaint_id, previous_status, new_status, remarks, updated_by, created_at) "
                       "VALUES (?, NULL, 'Pending', 'Complaint submitted.', ?, ?)", (cid, student, ts(created)))
            last = created
            if status in ("In Progress", "Resolved"):
                last = created + timedelta(hours=random.uniform(1, 20))
                db.execute("INSERT INTO complaint_history (complaint_id, previous_status, new_status, remarks, updated_by, created_at) "
                           "VALUES (?, 'Pending', 'In Progress', ?, ?, ?)",
                           (cid, random.choice(REMARKS_PROGRESS), admin_id, ts(last)))
            resolved_at = None
            if status == "Resolved":
                resolved = last + timedelta(hours=random.uniform(2, 90))
                resolved_at = ts(resolved)
                last = resolved
                db.execute("INSERT INTO complaint_history (complaint_id, previous_status, new_status, remarks, updated_by, created_at) "
                           "VALUES (?, 'In Progress', 'Resolved', ?, ?, ?)",
                           (cid, random.choice(REMARKS_DONE), admin_id, resolved_at))
                if random.random() < 0.6:
                    db.execute("INSERT INTO feedback (complaint_id, rating, comments, is_anonymous, created_at) VALUES (?, ?, ?, ?, ?)",
                               (cid, random.choice([3, 4, 4, 5, 5]),
                                random.choice(["Quick response, thank you.", "Fixed, but took a while.", "Very helpful.", None]),
                                random.choice([0, 1, 1]), ts(resolved + timedelta(hours=3))))
            db.execute("UPDATE complaints SET updated_at = ?, resolved_at = ? WHERE id = ?", (ts(last), resolved_at, cid))
        db.commit()
        print("Demo data created. Student logins: aarav@demo.edu / diya@demo.edu / rohan@demo.edu  (password: Student@123)")


if __name__ == "__main__":
    main()
