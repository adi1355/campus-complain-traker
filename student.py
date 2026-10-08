"""Student pages: dashboard, my complaints list, submit complaint."""
import os
import uuid
from datetime import datetime, timezone

from flask import (Blueprint, current_app, flash, g, jsonify, redirect, render_template,
                   request, url_for)

import queries
from auth import student_required
from db import get_db
from utils import PRIORITIES, STATUSES, clean_text, save_image, suggest_priority

bp = Blueprint("student", __name__, url_prefix="/student")


def _mod():
    return queries.offset_modifier(current_app.config["DISPLAY_UTC_OFFSET_MINUTES"])


@bp.route("/dashboard")
@student_required
def dashboard():
    db, uid = get_db(), g.user["id"]
    recent = queries.search_complaints(db, _mod(), student_id=uid)[:5]
    return render_template(
        "student_dashboard.html",
        counts=queries.status_counts(db, uid),
        avg_hours=queries.avg_resolution_hours(db, uid),
        recent=recent,
    )


@bp.route("/api/stats")
@student_required
def stats_api():
    return jsonify(queries.build_stats(
        get_db(), current_app.config["DISPLAY_UTC_OFFSET_MINUTES"], g.user["id"]))


@bp.route("/complaints")
@student_required
def my_complaints():
    db = get_db()
    filters = {k: clean_text(request.args.get(k)) for k in
               ("status", "category", "date_from", "date_to", "q")}
    complaints = queries.search_complaints(
        db, _mod(), student_id=g.user["id"], q=filters["q"], status=filters["status"],
        category_id=filters["category"], date_from=filters["date_from"], date_to=filters["date_to"])
    categories = db.execute("SELECT id, name FROM categories ORDER BY name").fetchall()
    return render_template("my_complaints.html", complaints=complaints, filters=filters,
                           categories=categories, statuses=STATUSES)


@bp.route("/complaints/new", methods=["GET", "POST"])
@student_required
def new_complaint():
    db = get_db()
    categories = db.execute(
        "SELECT id, name FROM categories WHERE is_active = 1 ORDER BY name").fetchall()
    form = {"title": "", "description": "", "category": "", "location": ""}

    if request.method == "POST":
        form = {
            "title": clean_text(request.form.get("title")),
            "description": clean_text(request.form.get("description"), multiline=True),
            "category": clean_text(request.form.get("category")),
            "location": clean_text(request.form.get("location")),
        }
        errors = []
        if not 5 <= len(form["title"]) <= 120:
            errors.append("Title must be between 5 and 120 characters.")
        if not 10 <= len(form["description"]) <= 2000:
            errors.append("Description must be between 10 and 2000 characters.")
        if not 2 <= len(form["location"]) <= 100:
            errors.append("Location must be between 2 and 100 characters.")
        category = None
        if form["category"].isdigit():
            category = db.execute(
                "SELECT * FROM categories WHERE id = ? AND is_active = 1",
                (int(form["category"]),)).fetchone()
        if category is None:
            errors.append("Please choose a valid category.")

        image_name = None
        if not errors:       # only touch the disk once everything else is valid
            image_name, image_error = save_image(
                request.files.get("image"), current_app.config["UPLOAD_FOLDER"],
                current_app.config["MAX_IMAGE_BYTES"])
            if image_error:
                errors.append(image_error)

        if not errors:
            priority, reason = suggest_priority(
                category["base_score"], form["title"], form["description"])
            try:
                cur = db.execute(
                    "INSERT INTO complaints (complaint_code, student_id, title, description, "
                    "category_id, location, priority, suggested_priority, priority_reason, "
                    "status, image_filename) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'Pending', ?)",
                    ("TMP-" + uuid.uuid4().hex, g.user["id"], form["title"], form["description"],
                     category["id"], form["location"], priority, priority, reason, image_name))
                cid = cur.lastrowid
                year = datetime.now(timezone.utc).year
                code = f"CMP-{year}-{cid:05d}"          # unique because the row id is unique
                db.execute("UPDATE complaints SET complaint_code = ? WHERE id = ?", (code, cid))
                db.execute(
                    "INSERT INTO complaint_history (complaint_id, previous_status, new_status, "
                    "remarks, updated_by) VALUES (?, NULL, 'Pending', 'Complaint submitted.', ?)",
                    (cid, g.user["id"]))
                db.commit()
            except Exception:
                db.rollback()
                if image_name:       # do not leave an orphan file behind
                    try:
                        os.remove(os.path.join(current_app.config["UPLOAD_FOLDER"], image_name))
                    except OSError:
                        pass
                raise
            flash(f"Complaint submitted. Your complaint ID is {code}.", "success")
            return redirect(url_for("complaints.detail", cid=cid))
        for e in errors:
            flash(e, "danger")

    return render_template("submit_complaint.html", form=form, categories=categories)
