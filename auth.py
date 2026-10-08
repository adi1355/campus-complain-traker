"""Authentication: register, login, logout and the access-control decorators."""
import sqlite3
from functools import wraps

from flask import (Blueprint, abort, flash, g, redirect, render_template, request,
                   session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

from db import get_db
from utils import EMAIL_RE, clean_text, validate_password

bp = Blueprint("auth", __name__)

# Used so a login attempt for an unknown email takes about as long as a real one.
_DUMMY_HASH = generate_password_hash("dummy-password-for-timing")


def home_for(user):
    return url_for("admin.dashboard") if user["role"] == "admin" else url_for("student.dashboard")


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if g.user is None:
            flash("Please log in to continue.", "warning")
            return redirect(url_for("auth.login"))
        return view(*args, **kwargs)
    return wrapped


def role_required(role):
    """Allow only users with the given role. Others get a 403 page."""
    def decorator(view):
        @wraps(view)
        @login_required
        def wrapped(*args, **kwargs):
            if g.user["role"] != role:
                abort(403)
            return view(*args, **kwargs)
        return wrapped
    return decorator


student_required = role_required("student")
admin_required = role_required("admin")


def _authenticate_user(email, password):
    user = get_db().execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
    if not user:
        return None
    valid = check_password_hash(user["password_hash"], password)
    if not valid:
        return None
    return user


@bp.route("/register", methods=["GET", "POST"])
def register():
    if g.user:
        return redirect(home_for(g.user))
    form = {"name": "", "email": ""}
    if request.method == "POST":
        name = clean_text(request.form.get("name"))
        email = clean_text(request.form.get("email")).lower()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")
        form = {"name": name, "email": email}

        errors = []
        if not 2 <= len(name) <= 80:
            errors.append("Name must be between 2 and 80 characters.")
        if not EMAIL_RE.match(email) or len(email) > 120:
            errors.append("Please enter a valid email address.")
        pw_error = validate_password(password)
        if pw_error:
            errors.append(pw_error)
        if password != confirm:
            errors.append("Passwords do not match.")

        if not errors:
            db = get_db()
            try:
                # Role is ALWAYS 'student' here - nobody can self-register as admin.
                db.execute(
                    "INSERT INTO users (name, email, password_hash, role) VALUES (?, ?, ?, 'student')",
                    (name, email, generate_password_hash(password)),
                )
                db.commit()
                flash("Account created. You can log in now.", "success")
                return redirect(url_for("auth.student_login"))
            except sqlite3.IntegrityError:
                errors.append("An account with this email already exists.")
        for e in errors:
            flash(e, "danger")
    return render_template("register.html", form=form)


@bp.route("/login", methods=["GET"])
def login():
    if g.user:
        return redirect(home_for(g.user))
    return render_template("login.html")


@bp.route("/student/login", methods=["GET", "POST"])
def student_login():
    if g.user:
        return redirect(home_for(g.user))

    email = ""
    if request.method == "POST":
        email = clean_text(request.form.get("email")).lower()
        password = request.form.get("password", "")
        user = _authenticate_user(email, password)

        if user and user["role"] == "student":
            session.clear()
            session["user_id"] = user["id"]
            flash(f"Welcome, {user['name']}!", "success")
            return redirect(url_for("student.dashboard"))

        if user and user["role"] != "student":
            flash("This account is for the administrator. Use the admin login page.", "warning")
        else:
            flash("Invalid student email or password.", "danger")

    return render_template("student_login.html", email=email)


@bp.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if g.user:
        return redirect(home_for(g.user))

    email = ""
    if request.method == "POST":
        email = clean_text(request.form.get("email")).lower()
        password = request.form.get("password", "")
        user = _authenticate_user(email, password)

        if user and user["role"] == "admin":
            session.clear()
            session["user_id"] = user["id"]
            flash(f"Welcome, {user['name']}!", "success")
            return redirect(url_for("admin.dashboard"))

        if user and user["role"] != "admin":
            flash("This account is for a student. Use the student login page.", "warning")
        else:
            flash("Invalid admin email or password.", "danger")

    return render_template("admin_login.html", email=email)


@bp.route("/logout", methods=["POST"])
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("auth.login"))
