"""Smart Campus Complaint & Solution Tracker - application entry point.

Run with:  python app.py
"""
import hmac
import os
import secrets

from flask import Flask, abort, g, redirect, render_template, request, session, url_for

import admin
import auth
import complaints
import student
from config import Config
from db import close_db, get_db, init_db
from utils import format_dt, format_duration


def create_app(test_config=None):
    app = Flask(__name__)
    app.config.from_object(Config)
    if test_config:
        app.config.update(test_config)

    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
    app.teardown_appcontext(close_db)
    init_db(app)

    for module in (auth, student, complaints, admin):
        app.register_blueprint(module.bp)

    # ------------------------------------------------------------ per-request hooks
    @app.before_request
    def load_logged_in_user():
        user_id = session.get("user_id")
        g.user = None
        if user_id is not None:
            g.user = get_db().execute(
                "SELECT id, name, email, role FROM users WHERE id = ?", (user_id,)).fetchone()
            if g.user is None:       # account no longer exists
                session.clear()

    @app.before_request
    def csrf_protect():
        """Every state-changing request must carry the secret token from the user's session."""
        if request.method in ("POST", "PUT", "PATCH", "DELETE"):
            sent = request.form.get("csrf_token") or request.headers.get("X-CSRFToken") or ""
            expected = session.get("csrf_token", "")
            if not expected or not hmac.compare_digest(sent, expected):
                abort(400, "Your form has expired or is invalid. Please go back and try again.")

    @app.context_processor
    def inject_helpers():
        def csrf_token():
            if "csrf_token" not in session:
                session["csrf_token"] = secrets.token_hex(16)
            return session["csrf_token"]
        return {"csrf_token": csrf_token}

    @app.after_request
    def security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self' https://cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "img-src 'self' data:; font-src 'self' https://cdn.jsdelivr.net; "
            "frame-ancestors 'none'; form-action 'self'")
        return response

    # ------------------------------------------------------------ template filters
    offset = app.config["DISPLAY_UTC_OFFSET_MINUTES"]
    app.jinja_env.filters["dt"] = lambda v, with_time=True: format_dt(v, offset, with_time)
    app.jinja_env.filters["duration"] = format_duration

    # ------------------------------------------------------------ routes + errors
    @app.route("/")
    def index():
        if g.user:
            return redirect(auth.home_for(g.user))
        return render_template("index.html")

    def error_page(code, title, message):
        return render_template("error.html", code=code, title=title, message=message), code

    @app.errorhandler(400)
    def bad_request(e):
        return error_page(400, "Request not accepted", getattr(e, "description", "Bad request."))

    @app.errorhandler(403)
    def forbidden(_e):
        return error_page(403, "Access denied", "You do not have permission to open this page.")

    @app.errorhandler(404)
    def not_found(_e):
        return error_page(404, "Page not found", "The page you asked for does not exist.")

    @app.errorhandler(413)
    def too_large(_e):
        return error_page(413, "Upload too large", "The uploaded file is too big (maximum 2 MB for images).")

    @app.errorhandler(500)
    def server_error(_e):
        return error_page(500, "Something went wrong", "An unexpected error occurred. Please try again.")

    if not app.config.get("SECRET_KEY_FROM_ENV") and not app.config.get("TESTING"):
        print("NOTE: SECRET_KEY is not set in .env - using a temporary key (logins reset on restart).")
    return app


if __name__ == "__main__":
    create_app().run(debug=os.environ.get("FLASK_DEBUG") == "1")
