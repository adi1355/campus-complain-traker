"""Validation helpers, smart priority recommendation and image upload checks."""
import os
import re
import uuid
from datetime import datetime, timedelta

STATUSES = ["Pending", "In Progress", "Resolved"]
PRIORITIES = ["Low", "Medium", "High", "Urgent"]

EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")


# --------------------------------------------------------------------------- input cleaning
def clean_text(value, multiline=False):
    """Trim, remove control characters and (for single-line fields) collapse whitespace.
    Output escaping against XSS is done by Jinja2 auto-escaping in the templates."""
    value = (value or "").replace("\x00", "")
    value = re.sub(r"[\x01-\x08\x0b\x0c\x0e-\x1f\x7f]", "", value)
    value = value.replace("\r\n", "\n").replace("\r", "\n")
    if not multiline:
        value = re.sub(r"\s+", " ", value)
    return value.strip()


def validate_password(password):
    """Return an error message, or None when the password is acceptable."""
    if len(password) < 8:
        return "Password must be at least 8 characters long."
    if len(password) > 128:
        return "Password is too long (maximum 128 characters)."
    if not re.search(r"[A-Za-z]", password) or not re.search(r"\d", password):
        return "Password must contain at least one letter and one number."
    return None


# --------------------------------------------------------------------------- smart priority
# Words that suggest danger  -> +3 (counted once)
CRITICAL_WORDS = [
    "fire", "spark", "sparks", "sparking", "short circuit", "electric shock", "shock",
    "gas leak", "flood", "flooding", "smoke", "injury", "injured", "collapse", "collapsed",
    "exposed wire", "live wire", "danger", "dangerous", "emergency", "harassment", "theft",
]
# Words that suggest something is broken / blocking work -> +1 each (max +2)
HIGH_WORDS = [
    "not working", "not work", "broken", "leak", "leaking", "no water", "power cut",
    "power outage", "outage", "no power", "down", "exam", "dead", "fused", "blackout",
    "unsafe", "stuck",
]
# Words that suggest a small issue -> -1 (counted once)
MINOR_WORDS = ["minor", "small", "slight", "suggestion"]


def _find(words, text):
    return [w for w in words if re.search(r"\b" + re.escape(w) + r"\b", text)]


def suggest_priority(base_score, title, description):
    """Rule-based recommendation. Returns (priority, human-readable reason).

    score = category base score (0-3)
          + 3 if a critical word appears
          + 1 per 'high' word (max +2)
          - 1 if a 'minor' word appears
    score >= 5 Urgent | >= 3 High | >= 1 Medium | otherwise Low
    """
    text = f"{title} {description}".lower()
    crit, high, minor = _find(CRITICAL_WORDS, text), _find(HIGH_WORDS, text), _find(MINOR_WORDS, text)

    score = int(base_score)
    reasons = [f"category base score {int(base_score)}"]
    if crit:
        score += 3
        reasons.append("critical word(s): " + ", ".join(crit[:3]))
    if high:
        score += min(2, len(high))
        reasons.append("keyword(s): " + ", ".join(high[:3]))
    if minor:
        score -= 1
        reasons.append("minor-issue word(s): " + ", ".join(minor[:2]))

    if score >= 5:
        priority = "Urgent"
    elif score >= 3:
        priority = "High"
    elif score >= 1:
        priority = "Medium"
    else:
        priority = "Low"
    return priority, f"Score {score} ({'; '.join(reasons)})"


# --------------------------------------------------------------------------- image upload
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}


def _signature_ok(ext, head):
    """Check the first bytes of the file really look like the claimed image type."""
    if ext == "png":
        return head.startswith(b"\x89PNG\r\n\x1a\n")
    if ext in ("jpg", "jpeg"):
        return head.startswith(b"\xff\xd8\xff")
    if ext == "webp":
        return head[:4] == b"RIFF" and head[8:12] == b"WEBP"
    return False


def save_image(file_storage, upload_folder, max_bytes):
    """Validate and store an uploaded image.
    Returns (stored_filename_or_None, error_message_or_None). No file chosen -> (None, None)."""
    if file_storage is None or not file_storage.filename:
        return None, None

    ext = file_storage.filename.rsplit(".", 1)[-1].lower() if "." in file_storage.filename else ""
    if ext not in ALLOWED_EXTENSIONS:
        return None, "Image must be a PNG, JPG, JPEG or WEBP file."

    head = file_storage.stream.read(16)
    file_storage.stream.seek(0, os.SEEK_END)
    size = file_storage.stream.tell()
    file_storage.stream.seek(0)

    if size == 0:
        return None, "The uploaded image is empty."
    if size > max_bytes:
        return None, f"Image is too large (maximum {max_bytes // (1024 * 1024)} MB)."
    if not _signature_ok(ext, head):
        return None, "The file content does not match an image of that type."

    stored = f"{uuid.uuid4().hex}.{'jpg' if ext == 'jpeg' else ext}"  # never trust user filenames
    os.makedirs(upload_folder, exist_ok=True)
    file_storage.save(os.path.join(upload_folder, stored))
    return stored, None


# --------------------------------------------------------------------------- display helpers
def format_dt(value, offset_minutes=330, with_time=True):
    """Convert a stored UTC string to a friendly local string."""
    if not value:
        return "-"
    try:
        dt = datetime.strptime(value, "%Y-%m-%d %H:%M:%S") + timedelta(minutes=offset_minutes)
    except ValueError:
        return value
    return dt.strftime("%d %b %Y, %I:%M %p" if with_time else "%d %b %Y")


def format_duration(hours):
    """Turn a number of hours into '25 min', '6.5 hrs' or '3.2 days'."""
    if hours is None:
        return "-"
    if hours < 1:
        return f"{max(1, round(hours * 60))} min"
    if hours < 48:
        return f"{hours:.1f} hrs"
    return f"{hours / 24:.1f} days"
