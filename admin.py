"""Administrator pages: dashboard, complaint management, students, categories, reports."""
import csv
import io
import sqlite3
from datetime import datetime, timedelta, timezone

from flask import (Blueprint, Response, abort, current_app, flash, g, jsonify, redirect,
                   render_template, request, url_for)

import queries
from auth import admin_required
from db import get_db
from utils import PRIORITIES, STATUSES, clean_text, format_dt

bp = Blueprint("admin", __name__, url_prefix="/admin")


def _offset():
    return current_app.config["DISPLAY_UTC_OFFSET_MINUTES"]


def _mod():
    return queries.offset_modifier(_offset())


def _filters_from_request():
    return {k: clean_text(request.args.get(k)) for k in
            ("q", "status", "priority", "category", "date_from", "date_to")}


@bp.route("/dashboard")
@admin_required
def dashboard():
    db = get_db()
    return render_template(
        "admin_dashboard.html",
        counts=queries.status_counts(db),
        avg_hours=queries.avg_resolution_hours(db),
        avg_rating=queries.average_rating(db),
        urgent=queries.urgent_open(db),
        recent=queries.search_complaints(db, _mod(), admin_order=False)[:6],
        student_count=db.execute("SELECT COUNT(*) FROM users WHERE role = 'student'").fetchone()[0],
    )


@bp.route("/api/stats")
@admin_required
def stats_api():
    return jsonify(queries.build_stats(get_db(), _offset()))


@bp.route("/complaints")
@admin_required
def complaints():
    db = get_db()
    f = _filters_from_request()
    rows = queries.search_complaints(
        db, _mod(), q=f["q"], status=f["status"], priority=f["priority"],
        category_id=f["category"], date_from=f["date_from"], date_to=f["date_to"],
        admin_order=True)
    categories = db.execute("SELECT id, name FROM categories ORDER BY name").fetchall()
    return render_template("manage_complaints.html", complaints=rows, filters=f,
                           categories=categories, statuses=STATUSES, priorities=PRIORITIES)


@bp.route("/complaints/<int:cid>/update", methods=["POST"])
@admin_required
def update_complaint(cid):
    db = get_db()
    c = db.execute("SELECT * FROM complaints WHERE id = ?", (cid,)).fetchone()
    if c is None:
        abort(404)
    back = redirect(url_for("complaints.detail", cid=cid))

    new_status = request.form.get("status", "")
    new_priority = request.form.get("priority", "")
    remarks = clean_text(request.form.get("remarks"), multiline=True)

    if new_status not in STATUSES or new_priority not in PRIORITIES:
        flash("Invalid status or priority.", "danger")
        return back
    if len(remarks) > 1000:
        flash("Remarks must be 1000 characters or fewer.", "danger")
        return back
    if new_status == "Resolved" and c["status"] != "Resolved" and not remarks:
        flash("Please add a resolution note before marking a complaint as Resolved.", "danger")
        return back

    status_changed = new_status != c["status"]
    priority_changed = new_priority != c["priority"]
    if not (status_changed or priority_changed or remarks):
        flash("Nothing was changed.", "info")
        return back

    # resolved_at is set when the complaint becomes Resolved and cleared if it is re-opened
    if new_status == "Resolved":
        resolved_sql = "resolved_at = COALESCE(resolved_at, datetime('now'))"
    else:
        resolved_sql = "resolved_at = NULL"

    notes = []
    if priority_changed:
        notes.append(f"Priority changed from {c['priority']} to {new_priority}.")
    if remarks:
        notes.append(remarks)

    db.execute(
        f"UPDATE complaints SET status = ?, priority = ?, {resolved_sql}, "
        "updated_at = datetime('now') WHERE id = ?", (new_status, new_priority, cid))
    db.execute(
        "INSERT INTO complaint_history (complaint_id, previous_status, new_status, remarks, "
        "updated_by) VALUES (?, ?, ?, ?, ?)",
        (cid, c["status"], new_status, " ".join(notes) or None, g.user["id"]))
    db.commit()
    flash("Complaint updated. The student can see this update on their tracking page.", "success")
    return back


@bp.route("/students")
@admin_required
def students():
    rows = get_db().execute(
        "SELECT u.id, u.name, u.email, u.created_at, COUNT(c.id) AS complaint_count "
        "FROM users u LEFT JOIN complaints c ON c.student_id = u.id "
        "WHERE u.role = 'student' GROUP BY u.id ORDER BY u.created_at DESC").fetchall()
    return render_template("students.html", students=rows)


@bp.route("/categories")
@admin_required
def categories():
    rows = get_db().execute(
        "SELECT cat.*, COUNT(c.id) AS complaint_count FROM categories cat "
        "LEFT JOIN complaints c ON c.category_id = cat.id GROUP BY cat.id ORDER BY cat.name"
    ).fetchall()
    return render_template("categories.html", categories=rows)


@bp.route("/categories/add", methods=["POST"])
@admin_required
def add_category():
    name = clean_text(request.form.get("name"))
    score = request.form.get("base_score", "0")
    if not 2 <= len(name) <= 50:
        flash("Category name must be between 2 and 50 characters.", "danger")
    elif score not in {"0", "1", "2", "3"}:
        flash("Default urgency must be between 0 and 3.", "danger")
    else:
        try:
            get_db().execute("INSERT INTO categories (name, base_score) VALUES (?, ?)",
                             (name, int(score)))
            get_db().commit()
            flash(f"Category '{name}' added.", "success")
        except sqlite3.IntegrityError:
            flash("A category with this name already exists.", "danger")
    return redirect(url_for("admin.categories"))


@bp.route("/categories/<int:cat_id>/toggle", methods=["POST"])
@admin_required
def toggle_category(cat_id):
    db = get_db()
    cat = db.execute("SELECT * FROM categories WHERE id = ?", (cat_id,)).fetchone()
    if cat is None:
        abort(404)
    # Categories are deactivated, never deleted, so old complaints keep their category.
    db.execute("UPDATE categories SET is_active = ? WHERE id = ?", (0 if cat["is_active"] else 1, cat_id))
    db.commit()
    flash(f"Category '{cat['name']}' {'deactivated' if cat['is_active'] else 'activated'}.", "success")
    return redirect(url_for("admin.categories"))


@bp.route("/reports")
@admin_required
def reports():
    db = get_db()
    months = queries.available_months(db, _offset())
    selected = request.args.get("month") or months[0]
    report = queries.month_report(db, selected, _offset())
    if report is None:
        flash("Invalid month selected.", "danger")
        selected = months[0]
        report = queries.month_report(db, selected, _offset())
    return render_template(
        "reports.html", months=months, selected=selected, report=report,
        counts=queries.status_counts(db), avg_hours=queries.avg_resolution_hours(db),
        by_category_time=queries.resolution_by_category(db))


def _csv_safe(value):
    """Stop spreadsheet formula injection: cells starting with = + - @ are prefixed with '."""
    text = "" if value is None else str(value)
    return "'" + text if text[:1] in ("=", "+", "-", "@") else text


@bp.route("/export.csv")
@admin_required
def export_csv():
    f = _filters_from_request()
    rows = queries.search_complaints(
        get_db(), _mod(), q=f["q"], status=f["status"], priority=f["priority"],
        category_id=f["category"], date_from=f["date_from"], date_to=f["date_to"],
        admin_order=True)
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["Complaint ID", "Title", "Category", "Location", "Priority", "Status",
                     "Student", "Created", "Resolved"])
    off = _offset()
    for r in rows:
        writer.writerow([_csv_safe(x) for x in (
            r["complaint_code"], r["title"], r["category_name"], r["location"], r["priority"],
            r["status"], r["student_name"], format_dt(r["created_at"], off),
            format_dt(r["resolved_at"], off) if r["resolved_at"] else "")])
    stamp = (datetime.now(timezone.utc) + timedelta(minutes=off)).strftime("%Y%m%d")
    return Response(buf.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": f"attachment; filename=complaints_{stamp}.csv"})


@bp.route("/feedback")
@admin_required
def feedback_list():
    db = get_db()
    rows = db.execute(
        "SELECT f.*, c.complaint_code, c.title, cat.name AS category_name, u.name AS student_name "
        "FROM feedback f JOIN complaints c ON c.id = f.complaint_id "
        "JOIN categories cat ON cat.id = c.category_id JOIN users u ON u.id = c.student_id "
        "ORDER BY f.created_at DESC").fetchall()
    return render_template("feedback_list.html", feedback=rows, avg_rating=queries.average_rating(db))
