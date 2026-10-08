"""Application configuration. Secrets come from environment variables (.env)."""
import os
import secrets

from dotenv import load_dotenv

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))


class Config:
    # If SECRET_KEY is missing we make a temporary one. Everyone is logged out
    # whenever the server restarts, which is safe but inconvenient.
    SECRET_KEY = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
    SECRET_KEY_FROM_ENV = bool(os.environ.get("SECRET_KEY"))

    DATABASE = os.path.join(BASE_DIR, os.environ.get("DATABASE", "database.db"))
    UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")

    # Whole request limit (image limit is checked separately, see MAX_IMAGE_BYTES)
    MAX_CONTENT_LENGTH = 3 * 1024 * 1024
    MAX_IMAGE_BYTES = 2 * 1024 * 1024

    # Session cookie hardening
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = os.environ.get("SESSION_COOKIE_SECURE") == "1"

    # First admin account (created only if no admin exists yet)
    ADMIN_NAME = os.environ.get("ADMIN_NAME", "Campus Admin")
    ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@campus.local")
    ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "Admin@12345")
    ADMIN_PASSWORD_FROM_ENV = bool(os.environ.get("ADMIN_PASSWORD"))

    # Timestamps are stored in UTC; this offset is used only for display/reports.
    DISPLAY_UTC_OFFSET_MINUTES = int(os.environ.get("DISPLAY_UTC_OFFSET_MINUTES", "330"))
