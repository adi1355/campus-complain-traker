"""Pages shared by students and admins: complaint details, feedback, private image serving."""
from flask import (Blueprint, abort, current_app, flash, g, redirect, render_template,
                   request, send_from_directory, url_for)

from auth import login_required, student_required
from db import get_db
from queries import COMPLAINT_SELECT
from utils import PRIORITIES, STATUSES, clean_text

bp = Blueprint("complaints", __name__)


def load_complaint_or_404(cid):
    """Admins may open any complaint; a student only their own (others get 404)."""
    c = get_db().execute(COMPLAINT_SELECT + " WHERE c.id = ?", (cid,)).fetchone()
    if c is None or (g.user["role"] != "admin" and c["student_id"] != g.user["id"]):
        abort(404)
    return c


@bp.route("/complaints/<int:cid>")
@login_required
def detail(cid):
    db = get_db()
    c = load_complaint_or_404(cid)
    history = db.execute(
        "SELECT h.*, u.name AS updater_name, u.role AS updater_role FROM complaint_history h "
        "LEFT JOIN users u ON u.id = h.updated_by WHERE h.complaint_id = ? ORDER BY h.id",
        (cid,)).fetchall()
    feedback = db.execute("SELECT * FROM feedback WHERE complaint_id = ?", (cid,)).fetchone()
    can_give_feedback = (g.user["role"] == "student" and c["status"] == "Resolved"
                         and feedback is None)
    return render_template("complaint_details.html", c=c, history=history, feedback=feedback,
                           can_give_feedback=can_give_feedback, statuses=STATUSES,
                           priorities=PRIORITIES)


@bp.route("/complaints/<int:cid>/feedback", methods=["POST"])
@student_required
def feedback(cid):
    db = get_db()
    c = load_complaint_or_404(cid)
    if c["status"] != "Resolved":
        flash("You can give feedback only after the complaint is resolved.", "warning")
        return redirect(url_for("complaints.detail", cid=cid))
    if db.execute("SELECT 1 FROM feedback WHERE complaint_id = ?", (cid,)).fetchone():
        flash("Feedback was already submitted for this complaint.", "warning")
        return redirect(url_for("complaints.detail", cid=cid))

    rating = request.form.get("rating", "")
    comments = clean_text(request.form.get("comments"), multiline=True)
    if rating not in {"1", "2", "3", "4", "5"}:
        flash("Please choose a rating from 1 to 5.", "danger")
    elif len(comments) > 500:
        flash("Comments must be 500 characters or fewer.", "danger")
    else:
        db.execute(
            "INSERT INTO feedback (complaint_id, rating, comments, is_anonymous) VALUES (?, ?, ?, ?)",
            (cid, int(rating), comments or None, 1 if request.form.get("anonymous") else 0))
        db.commit()
        flash("Thank you for your feedback!", "success")
    return redirect(url_for("complaints.detail", cid=cid))


@bp.route("/uploads/<path:filename>")
@login_required
def upload(filename):
    """Complaint images are private: only the owner or an admin may fetch them."""
    c = get_db().execute(
        "SELECT student_id FROM complaints WHERE image_filename = ?", (filename,)).fetchone()
    if c is None or (g.user["role"] != "admin" and c["student_id"] != g.user["id"]):
        abort(404)
    return send_from_directory(current_app.config["UPLOAD_FOLDER"], filename)
