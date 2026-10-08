"""Reusable SQL queries: complaint searching and all analytics.
Every value coming from a user is passed as a ? parameter (never pasted into the SQL)."""
import re
from datetime import datetime, timedelta, timezone

from utils import PRIORITIES, STATUSES

COMPLAINT_SELECT = """
    SELECT c.*, cat.name AS category_name, u.name AS student_name, u.email AS student_email
    FROM complaints c
    JOIN categories cat ON cat.id = c.category_id
    JOIN users u ON u.id = c.student_id
"""

# Urgent first, resolved complaints last
ADMIN_ORDER = (
    "(c.status = 'Resolved'), "
    "CASE c.priority WHEN 'Urgent' THEN 0 WHEN 'High' THEN 1 WHEN 'Medium' THEN 2 ELSE 3 END, "
    "c.created_at DESC"
)


def offset_modifier(minutes):
    """SQLite date modifier such as '+330 minutes' (UTC -> local time)."""
    return f"{int(minutes):+d} minutes"


def _escape_like(text):
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _valid_date(text):
    try:
        return datetime.strptime(text or "", "%Y-%m-%d").date().isoformat()
    except ValueError:
        return None


def search_complaints(db, mod, student_id=None, q="", status="", priority="",
                      category_id="", date_from="", date_to="", admin_order=False):
    """Filter complaints. Only fixed SQL fragments are joined; values go in `params`."""
    where, params = [], []
    if student_id is not None:
        where.append("c.student_id = ?")
        params.append(student_id)
    if q:
        like = f"%{_escape_like(q)}%"
        where.append(
            "(c.complaint_code LIKE ? ESCAPE '\\' OR c.title LIKE ? ESCAPE '\\' "
            "OR c.description LIKE ? ESCAPE '\\' OR c.location LIKE ? ESCAPE '\\' "
            "OR u.name LIKE ? ESCAPE '\\')"
        )
        params += [like] * 5
    if status in STATUSES:
        where.append("c.status = ?")
        params.append(status)
    if priority in PRIORITIES:
        where.append("c.priority = ?")
        params.append(priority)
    if str(category_id).isdigit():
        where.append("c.category_id = ?")
        params.append(int(category_id))
    if _valid_date(date_from):
        where.append("date(c.created_at, ?) >= ?")
        params += [mod, date_from]
    if _valid_date(date_to):
        where.append("date(c.created_at, ?) <= ?")
        params += [mod, date_to]

    sql = COMPLAINT_SELECT
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY " + (ADMIN_ORDER if admin_order else "c.created_at DESC, c.id DESC")
    return db.execute(sql, params).fetchall()


# --------------------------------------------------------------------------- analytics
def status_counts(db, student_id=None):
    sql = ("SELECT COUNT(*) AS total, "
           "COALESCE(SUM(status = 'Pending'), 0) AS pending, "
           "COALESCE(SUM(status = 'In Progress'), 0) AS in_progress, "
           "COALESCE(SUM(status = 'Resolved'), 0) AS resolved FROM complaints")
    params = []
    if student_id is not None:
        sql += " WHERE student_id = ?"
        params.append(student_id)
    return dict(db.execute(sql, params).fetchone())


def by_category(db, student_id=None):
    sql = ("SELECT cat.name AS name, COUNT(*) AS count FROM complaints c "
           "JOIN categories cat ON cat.id = c.category_id")
    params = []
    if student_id is not None:
        sql += " WHERE c.student_id = ?"
        params.append(student_id)
    sql += " GROUP BY cat.name ORDER BY count DESC, cat.name"
    return [dict(r) for r in db.execute(sql, params).fetchall()]


def by_priority(db):
    rows = {r["priority"]: r["n"] for r in db.execute(
        "SELECT priority, COUNT(*) AS n FROM complaints GROUP BY priority")}
    return [{"name": p, "count": rows.get(p, 0)} for p in PRIORITIES]


def _last_months(count, offset_minutes):
    now = datetime.now(timezone.utc) + timedelta(minutes=offset_minutes)
    year, month, out = now.year, now.month, []
    for _ in range(count):
        out.append(f"{year:04d}-{month:02d}")
        month -= 1
        if month == 0:
            year, month = year - 1, 12
    return list(reversed(out))


def monthly_trend(db, offset_minutes, student_id=None, months=12):
    mod = offset_modifier(offset_minutes)
    extra, params_extra = ("", [])
    if student_id is not None:
        extra, params_extra = (" AND student_id = ?", [student_id])
    created = dict(db.execute(
        "SELECT strftime('%Y-%m', created_at, ?) AS m, COUNT(*) FROM complaints "
        "WHERE 1 = 1" + extra + " GROUP BY m", [mod] + params_extra).fetchall())
    resolved = dict(db.execute(
        "SELECT strftime('%Y-%m', resolved_at, ?) AS m, COUNT(*) FROM complaints "
        "WHERE resolved_at IS NOT NULL" + extra + " GROUP BY m", [mod] + params_extra).fetchall())
    labels = _last_months(months, offset_minutes)
    return {
        "labels": labels,
        "submitted": [created.get(m, 0) for m in labels],
        "resolved": [resolved.get(m, 0) for m in labels],
    }


def avg_resolution_hours(db, student_id=None):
    sql = ("SELECT AVG((julianday(resolved_at) - julianday(created_at)) * 24.0) "
           "FROM complaints WHERE resolved_at IS NOT NULL")
    params = []
    if student_id is not None:
        sql += " AND student_id = ?"
        params.append(student_id)
    return db.execute(sql, params).fetchone()[0]


def resolution_by_category(db):
    rows = db.execute(
        "SELECT cat.name AS name, COUNT(*) AS resolved, "
        "AVG((julianday(c.resolved_at) - julianday(c.created_at)) * 24.0) AS avg_hours "
        "FROM complaints c JOIN categories cat ON cat.id = c.category_id "
        "WHERE c.resolved_at IS NOT NULL GROUP BY cat.name ORDER BY avg_hours DESC").fetchall()
    return [dict(r) for r in rows]


def urgent_open(db):
    return db.execute(
        COMPLAINT_SELECT + " WHERE c.priority = 'Urgent' AND c.status != 'Resolved' "
        "ORDER BY c.created_at ASC").fetchall()


def average_rating(db):
    return db.execute("SELECT AVG(rating) FROM feedback").fetchone()[0]


def available_months(db, offset_minutes):
    mod = offset_modifier(offset_minutes)
    months = {r[0] for r in db.execute(
        "SELECT DISTINCT strftime('%Y-%m', created_at, ?) FROM complaints", (mod,))}
    months.update(_last_months(1, offset_minutes))
    return sorted(months, reverse=True)


def month_report(db, ym, offset_minutes):
    """Numbers for one month (ym like '2026-10'), using local (offset) time."""
    if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", ym or ""):
        return None
    mod = offset_modifier(offset_minutes)
    submitted = db.execute(
        "SELECT COUNT(*) FROM complaints WHERE strftime('%Y-%m', created_at, ?) = ?",
        (mod, ym)).fetchone()[0]
    resolved_row = db.execute(
        "SELECT COUNT(*), AVG((julianday(resolved_at) - julianday(created_at)) * 24.0) "
        "FROM complaints WHERE resolved_at IS NOT NULL "
        "AND strftime('%Y-%m', resolved_at, ?) = ?", (mod, ym)).fetchone()
    categories = db.execute(
        "SELECT cat.name AS name, COUNT(*) AS total, "
        "COALESCE(SUM(c.status = 'Resolved'), 0) AS resolved FROM complaints c "
        "JOIN categories cat ON cat.id = c.category_id "
        "WHERE strftime('%Y-%m', c.created_at, ?) = ? GROUP BY cat.name ORDER BY total DESC",
        (mod, ym)).fetchall()
    priorities = {r["priority"]: r["n"] for r in db.execute(
        "SELECT priority, COUNT(*) AS n FROM complaints "
        "WHERE strftime('%Y-%m', created_at, ?) = ? GROUP BY priority", (mod, ym))}
    return {
        "month": ym,
        "submitted": submitted,
        "resolved": resolved_row[0],
        "avg_hours": resolved_row[1],
        "categories": [dict(r) for r in categories],
        "priorities": [(p, priorities.get(p, 0)) for p in PRIORITIES],
    }


def build_stats(db, offset_minutes, student_id=None):
    """Everything the dashboards' charts need, as one JSON-friendly dict."""
    data = {
        "status": status_counts(db, student_id),
        "by_category": by_category(db, student_id),
        "monthly": monthly_trend(db, offset_minutes, student_id),
        "avg_resolution_hours": avg_resolution_hours(db, student_id),
    }
    if student_id is None:
        data["priority"] = by_priority(db)
    return data
