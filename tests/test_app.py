"""Automated tests for the Smart Campus Complaint & Solution Tracker.

Run from the project folder with:   python -m unittest discover -s tests -v
Each test gets a brand-new temporary database and upload folder, so the real
database.db is never touched.
"""
import io
import os
import re
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app import create_app          # noqa: E402
from db import get_db               # noqa: E402
from utils import suggest_priority, validate_password   # noqa: E402

ADMIN_EMAIL, ADMIN_PASSWORD = "admin@test.local", "AdminPass123"
PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64      # tiny file with a valid PNG signature


class BaseCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.app = create_app({
            "TESTING": True,
            "DATABASE": os.path.join(self.tmp, "test.db"),
            "UPLOAD_FOLDER": os.path.join(self.tmp, "uploads"),
            "ADMIN_EMAIL": ADMIN_EMAIL,
            "ADMIN_PASSWORD": ADMIN_PASSWORD,
            "ADMIN_PASSWORD_FROM_ENV": True,
        })

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    # ---- helpers -----------------------------------------------------------
    def new_client(self):
        client = self.app.test_client()
        with client.session_transaction() as s:
            s["csrf_token"] = "test-token"
        return client

    def post(self, client, url, data=None, **kw):
        # Login deliberately resets the session, so we re-seed the known token each time.
        with client.session_transaction() as s:
            s["csrf_token"] = "test-token"
        data = dict(data or {})
        data["csrf_token"] = "test-token"
        return client.post(url, data=data, **kw)

    def register(self, client, name="Asha Rao", email="asha@test.com", password="Student123"):
        return self.post(client, "/register", {
            "name": name, "email": email, "password": password, "confirm_password": password},
            follow_redirects=True)

    def login(self, client, email, password):
        return self.post(client, "/login", {"email": email, "password": password},
                         follow_redirects=True)

    def student(self, email="asha@test.com", name="Asha Rao"):
        client = self.new_client()
        self.register(client, name=name, email=email)
        self.login(client, email, "Student123")
        return client

    def admin(self):
        client = self.new_client()
        self.login(client, ADMIN_EMAIL, ADMIN_PASSWORD)
        return client

    def category_id(self, name="Electricity"):
        with self.app.app_context():
            return get_db().execute("SELECT id FROM categories WHERE name = ?", (name,)).fetchone()[0]

    def submit(self, client, title="Ceiling fan not working", category="Electricity",
               description="The ceiling fan in room 204 has stopped working completely.",
               location="Block B, Room 204", image=None):
        data = {"title": title, "description": description, "location": location,
                "category": str(self.category_id(category))}
        if image:
            data["image"] = image
        return self.post(client, "/student/complaints/new", data,
                         content_type="multipart/form-data", follow_redirects=True)

    def complaint_row(self, cid=1):
        with self.app.app_context():
            return dict(get_db().execute("SELECT * FROM complaints WHERE id = ?", (cid,)).fetchone())

    def run_sql(self, sql, params=()):
        with self.app.app_context():
            db = get_db()
            db.execute(sql, params)
            db.commit()


# =============================================================================
class TestAuthentication(BaseCase):
    def test_registration_and_login(self):
        c = self.new_client()
        r = self.register(c)
        self.assertIn(b"Account created", r.data)
        r = self.login(c, "asha@test.com", "Student123")
        self.assertIn(b"Hello, Asha", r.data)

    def test_password_is_hashed(self):
        self.register(self.new_client())
        with self.app.app_context():
            row = get_db().execute("SELECT password_hash FROM users WHERE email='asha@test.com'").fetchone()
        self.assertNotIn("Student123", row[0])
        self.assertTrue(row[0].startswith(("scrypt:", "pbkdf2:")))

    def test_duplicate_email_rejected(self):
        self.register(self.new_client())
        r = self.register(self.new_client())
        self.assertIn(b"already exists", r.data)

    def test_weak_password_and_mismatch_rejected(self):
        c = self.new_client()
        r = self.register(c, password="short1")
        self.assertIn(b"at least 8 characters", r.data)
        r = self.post(c, "/register", {"name": "Bob Ray", "email": "bob@test.com",
                                       "password": "Student123", "confirm_password": "Different123"},
                      follow_redirects=True)
        self.assertIn(b"do not match", r.data)

    def test_invalid_login_attempts(self):
        c = self.new_client()
        self.register(c)
        r = self.login(c, "asha@test.com", "WrongPassword1")
        self.assertIn(b"Invalid email or password", r.data)
        r = self.login(c, "nobody@test.com", "Student123")
        self.assertIn(b"Invalid email or password", r.data)

    def test_cannot_self_register_as_admin(self):
        c = self.new_client()
        self.post(c, "/register", {"name": "Evil User", "email": "evil@test.com", "role": "admin",
                                   "password": "Student123", "confirm_password": "Student123"})
        with self.app.app_context():
            role = get_db().execute("SELECT role FROM users WHERE email='evil@test.com'").fetchone()[0]
        self.assertEqual(role, "student")

    def test_logout(self):
        c = self.student()
        self.post(c, "/logout")
        self.assertEqual(c.get("/student/dashboard").status_code, 302)

    def test_admin_login_goes_to_admin_dashboard(self):
        r = self.login(self.new_client(), ADMIN_EMAIL, ADMIN_PASSWORD)
        self.assertIn(b"Administrator dashboard", r.data)


class TestSecurity(BaseCase):
    def test_anonymous_users_are_redirected_to_login(self):
        c = self.new_client()
        for url in ("/student/dashboard", "/admin/dashboard", "/complaints/1", "/admin/reports"):
            r = c.get(url)
            self.assertEqual(r.status_code, 302, url)
            self.assertIn("/login", r.headers["Location"])

    def test_student_blocked_from_admin_pages(self):
        c = self.student()
        for url in ("/admin/dashboard", "/admin/complaints", "/admin/students",
                    "/admin/categories", "/admin/reports", "/admin/export.csv",
                    "/admin/feedback", "/admin/api/stats"):
            self.assertEqual(c.get(url).status_code, 403, url)

    def test_student_cannot_post_admin_actions(self):
        c = self.student()
        self.submit(c)
        r = self.post(c, "/admin/complaints/1/update", {"status": "Resolved", "priority": "Low", "remarks": "x"})
        self.assertEqual(r.status_code, 403)
        self.assertEqual(self.complaint_row()["status"], "Pending")
        self.assertEqual(self.post(c, "/admin/categories/add", {"name": "Hack"}).status_code, 403)

    def test_admin_cannot_open_student_only_pages(self):
        self.assertEqual(self.admin().get("/student/dashboard").status_code, 403)

    def test_csrf_token_required(self):
        c = self.new_client()
        r = c.post("/login", data={"email": "a@b.com", "password": "x"})       # no token
        self.assertEqual(r.status_code, 400)
        with c.session_transaction() as s:
            s["csrf_token"] = "real"
        r = c.post("/login", data={"email": "a@b.com", "password": "x", "csrf_token": "forged"})
        self.assertEqual(r.status_code, 400)

    def test_xss_is_escaped(self):
        c = self.student()
        self.submit(c, title="<script>alert(1)</script> broken", location="Room <b>1</b>")
        page = c.get("/complaints/1").data
        self.assertNotIn(b"<script>alert(1)</script>", page)
        self.assertIn(b"&lt;script&gt;alert(1)&lt;/script&gt;", page)

    def test_sql_injection_in_search_is_harmless(self):
        a = self.admin()
        s = self.student()
        self.submit(s)
        r = a.get("/admin/complaints?q=' OR '1'='1")
        self.assertEqual(r.status_code, 200)
        self.assertNotIn(b"CMP-", r.data)       # injection text matched nothing
        self.assertEqual(self.admin().get("/admin/complaints?q=fan").data.count(b"CMP-"), 1)

    def test_security_headers_present(self):
        r = self.new_client().get("/login")
        self.assertEqual(r.headers["X-Content-Type-Options"], "nosniff")
        self.assertIn("default-src 'self'", r.headers["Content-Security-Policy"])


class TestComplaints(BaseCase):
    def test_submit_complaint_generates_unique_id(self):
        c = self.student()
        r1 = self.submit(c)
        r2 = self.submit(c, title="Projector is broken")
        self.assertRegex(r1.data.decode(), r"CMP-\d{4}-00001")
        self.assertRegex(r2.data.decode(), r"CMP-\d{4}-00002")
        self.assertNotEqual(self.complaint_row(1)["complaint_code"], self.complaint_row(2)["complaint_code"])

    def test_validation_errors(self):
        c = self.student()
        r = self.post(c, "/student/complaints/new",
                      {"title": "x", "description": "short", "location": "", "category": "999"},
                      content_type="multipart/form-data")
        self.assertIn(b"Title must be", r.data)
        self.assertIn(b"Description must be", r.data)
        self.assertIn(b"Location must be", r.data)
        self.assertIn(b"valid category", r.data)

    def test_initial_history_entry_created(self):
        self.submit(self.student())
        with self.app.app_context():
            rows = get_db().execute("SELECT * FROM complaint_history WHERE complaint_id=1").fetchall()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["new_status"], "Pending")
        self.assertIsNone(rows[0]["previous_status"])

    def test_student_cannot_view_other_students_complaint(self):
        a = self.student("asha@test.com", "Asha Rao")
        b = self.student("ben@test.com", "Ben Thomas")
        self.submit(a)
        self.assertEqual(a.get("/complaints/1").status_code, 200)
        self.assertEqual(b.get("/complaints/1").status_code, 404)
        self.assertNotIn(b"CMP-", b.get("/student/complaints").data)
        self.assertEqual(self.post(b, "/complaints/1/feedback", {"rating": "5"}).status_code, 404)

    def test_admin_can_view_any_complaint(self):
        self.submit(self.student())
        self.assertEqual(self.admin().get("/complaints/1").status_code, 200)

    def test_student_filters(self):
        c = self.student()
        self.submit(c, title="Fan not working", category="Electricity")
        self.submit(c, title="Dirty corridor floor", category="Cleanliness",
                    description="The corridor floor near the canteen is very dirty.")
        electricity = self.category_id("Electricity")
        r = c.get(f"/student/complaints?category={electricity}")
        self.assertIn(b"Fan not working", r.data)
        self.assertNotIn(b"Dirty corridor", r.data)
        self.assertIn(b"Dirty corridor", c.get("/student/complaints?q=corridor").data)
        self.assertNotIn(b"Fan not working", c.get("/student/complaints?status=Resolved").data)
        self.assertIn(b"Fan not working", c.get("/student/complaints?date_from=2000-01-01").data)
        self.assertNotIn(b"Fan not working", c.get("/student/complaints?date_from=2999-01-01").data)


class TestPriorityRecommendation(unittest.TestCase):
    def test_rules(self):
        self.assertEqual(suggest_priority(0, "Dusty desk", "Desk is dusty")[0], "Low")
        self.assertEqual(suggest_priority(2, "Light", "Tube light flickers")[0], "Medium")
        self.assertEqual(suggest_priority(2, "Fan", "Ceiling fan not working")[0], "High")
        self.assertEqual(suggest_priority(2, "Sparks", "Sparks from the socket, fire risk")[0], "Urgent")
        self.assertEqual(suggest_priority(1, "Wi-Fi down", "Wi-Fi is down before the exam")[0], "High")
        self.assertEqual(suggest_priority(0, "Minor", "A small stain on the wall")[0], "Low")

    def test_reason_is_explained(self):
        _p, reason = suggest_priority(2, "Fire", "There is smoke and fire")
        self.assertIn("critical", reason)

    def test_word_boundaries(self):
        # "shutdown" must not match the keyword "down"
        self.assertEqual(suggest_priority(0, "Shutdown", "Computer shutdown schedule")[0], "Low")

    def test_stored_on_submission(self):
        pass  # covered in TestAdminWorkflow.test_priority_recommendation_saved


class TestAdminWorkflow(BaseCase):
    def setUp(self):
        super().setUp()
        self.s = self.student()
        self.a = self.admin()
        self.submit(self.s)

    def update(self, status, priority="High", remarks=""):
        return self.post(self.a, "/admin/complaints/1/update",
                         {"status": status, "priority": priority, "remarks": remarks},
                         follow_redirects=True)

    def test_priority_recommendation_saved(self):
        row = self.complaint_row()
        self.assertEqual(row["priority"], "High")           # Electricity(2) + "not working"(1)
        self.assertEqual(row["suggested_priority"], "High")
        self.assertIn("Score 3", row["priority_reason"])

    def test_status_update_and_history(self):
        self.update("In Progress", "High", "Electrician has been informed.")
        self.update("Resolved", "High", "Fan capacitor replaced.")
        row = self.complaint_row()
        self.assertEqual(row["status"], "Resolved")
        self.assertIsNotNone(row["resolved_at"])
        with self.app.app_context():
            hist = get_db().execute(
                "SELECT previous_status, new_status, remarks FROM complaint_history "
                "WHERE complaint_id=1 ORDER BY id").fetchall()
        self.assertEqual([(h[0], h[1]) for h in hist],
                         [(None, "Pending"), ("Pending", "In Progress"), ("In Progress", "Resolved")])
        # the student sees the remarks on the tracking page
        page = self.s.get("/complaints/1").data
        self.assertIn(b"Electrician has been informed.", page)
        self.assertIn(b"Fan capacitor replaced.", page)

    def test_resolution_requires_note(self):
        r = self.update("Resolved", "High", "")
        self.assertIn(b"resolution note", r.data)
        self.assertEqual(self.complaint_row()["status"], "Pending")

    def test_admin_can_change_priority(self):
        self.update("Pending", "Urgent", "Escalating.")
        self.assertEqual(self.complaint_row()["priority"], "Urgent")
        self.assertEqual(self.complaint_row()["suggested_priority"], "High")   # recommendation kept
        self.assertIn(b"Priority changed from High to Urgent", self.s.get("/complaints/1").data)

    def test_reopen_clears_resolved_date(self):
        self.update("Resolved", "High", "Done.")
        self.update("In Progress", "High", "Problem came back.")
        self.assertIsNone(self.complaint_row()["resolved_at"])

    def test_invalid_values_rejected(self):
        r = self.update("Hacked", "High", "x")
        self.assertIn(b"Invalid status", r.data)

    def test_admin_search_and_filter(self):
        self.submit(self.s, title="Projector bulb fused", category="Classroom",
                    description="The projector bulb in the seminar hall has fused.")
        self.assertEqual(self.a.get("/admin/complaints?q=projector").data.count(b"CMP-"), 1)
        self.assertEqual(self.a.get("/admin/complaints?priority=High").data.count(b"CMP-"), 1)   # the fan
        self.assertEqual(self.a.get("/admin/complaints?priority=Medium").data.count(b"CMP-"), 1)  # the projector
        self.assertEqual(self.a.get("/admin/complaints?status=Resolved").data.count(b"CMP-"), 0)
        self.assertEqual(self.a.get("/admin/complaints?q=Asha").data.count(b"CMP-"), 2)  # by student name

    def test_urgent_alert_on_dashboard(self):
        self.assertNotIn(b"urgent complaint", self.a.get("/admin/dashboard").data)
        self.update("Pending", "Urgent", "Escalated.")
        self.assertIn(b"1 urgent complaint need attention", self.a.get("/admin/dashboard").data)
        self.update("Resolved", "Urgent", "Fixed.")
        self.assertNotIn(b"urgent complaint", self.a.get("/admin/dashboard").data)

    def test_students_page_hides_password_hash(self):
        page = self.a.get("/admin/students").data
        self.assertIn(b"asha@test.com", page)
        self.assertNotIn(b"scrypt", page)
        self.assertNotIn(b"pbkdf2", page)

    def test_category_management(self):
        r = self.post(self.a, "/admin/categories/add", {"name": "Parking", "base_score": "1"},
                      follow_redirects=True)
        self.assertIn(b"Parking", r.data)
        r = self.post(self.a, "/admin/categories/add", {"name": "Parking", "base_score": "1"},
                      follow_redirects=True)
        self.assertIn(b"already exists", r.data)
        cid = self.category_id("Parking")
        self.post(self.a, f"/admin/categories/{cid}/toggle")
        self.assertNotIn(b"Parking</option>", self.s.get("/student/complaints/new").data)

    def test_csv_export_and_formula_injection_guard(self):
        self.submit(self.s, title="=HYPERLINK(1) bad title", description="A malicious looking title.")
        r = self.a.get("/admin/export.csv")
        self.assertEqual(r.mimetype, "text/csv")
        body = r.data.decode()
        self.assertIn("Complaint ID", body)
        self.assertIn("'=HYPERLINK(1) bad title", body)
        self.assertNotIn("'-", body)            # empty "resolved" dates must stay empty


class TestImageUpload(BaseCase):
    def setUp(self):
        super().setUp()
        self.s = self.student()

    def count_files(self):
        folder = self.app.config["UPLOAD_FOLDER"]
        return len(os.listdir(folder)) if os.path.isdir(folder) else 0

    def test_valid_png_is_saved_and_served_to_owner(self):
        r = self.submit(self.s, image=(io.BytesIO(PNG_BYTES), "photo.png"))
        self.assertIn(b"Complaint submitted", r.data)
        stored = self.complaint_row()["image_filename"]
        self.assertTrue(stored.endswith(".png"))
        self.assertNotIn("photo", stored)                       # user filename is never reused
        self.assertEqual(self.s.get(f"/uploads/{stored}").status_code, 200)

    def test_uploads_are_private(self):
        self.submit(self.s, image=(io.BytesIO(PNG_BYTES), "photo.png"))
        stored = self.complaint_row()["image_filename"]
        other = self.student("ben@test.com", "Ben Thomas")
        self.assertEqual(other.get(f"/uploads/{stored}").status_code, 404)
        self.assertEqual(self.new_client().get(f"/uploads/{stored}").status_code, 302)
        self.assertEqual(self.admin().get(f"/uploads/{stored}").status_code, 200)

    def test_wrong_extension_rejected(self):
        r = self.submit(self.s, image=(io.BytesIO(b"MZ fake exe"), "virus.exe"))
        self.assertIn(b"PNG, JPG, JPEG or WEBP", r.data)
        self.assertEqual(self.count_files(), 0)

    def test_fake_image_content_rejected(self):
        r = self.submit(self.s, image=(io.BytesIO(b"<?php echo 1; ?>"), "shell.png"))
        self.assertIn(b"does not match", r.data)
        self.assertEqual(self.count_files(), 0)

    def test_oversized_image_rejected(self):
        big = PNG_BYTES + b"\x00" * (2 * 1024 * 1024 + 10)
        r = self.submit(self.s, image=(io.BytesIO(big), "big.png"))
        self.assertIn(b"too large", r.data)
        self.assertEqual(self.count_files(), 0)

    def test_empty_file_rejected(self):
        r = self.submit(self.s, image=(io.BytesIO(b""), "empty.png"))
        self.assertIn(b"empty", r.data)

    def test_path_traversal_blocked(self):
        self.assertEqual(self.s.get("/uploads/../config.py").status_code, 404)
        self.assertEqual(self.s.get("/uploads/..%2Fconfig.py").status_code, 404)


class TestFeedback(BaseCase):
    def setUp(self):
        super().setUp()
        self.s = self.student()
        self.a = self.admin()
        self.submit(self.s)

    def resolve(self):
        self.post(self.a, "/admin/complaints/1/update",
                  {"status": "Resolved", "priority": "High", "remarks": "Fixed."})

    def test_feedback_not_allowed_before_resolution(self):
        r = self.post(self.s, "/complaints/1/feedback", {"rating": "5"}, follow_redirects=True)
        self.assertIn(b"only after the complaint is resolved", r.data)
        self.assertNotIn(b"Submit feedback", self.s.get("/complaints/1").data)

    def test_feedback_after_resolution_and_only_once(self):
        self.resolve()
        self.assertIn(b"Submit feedback", self.s.get("/complaints/1").data)
        r = self.post(self.s, "/complaints/1/feedback",
                      {"rating": "4", "comments": "Quick fix, thanks", "anonymous": "1"},
                      follow_redirects=True)
        self.assertIn(b"Thank you for your feedback", r.data)
        r = self.post(self.s, "/complaints/1/feedback", {"rating": "1"}, follow_redirects=True)
        self.assertIn(b"already submitted", r.data)
        with self.app.app_context():
            self.assertEqual(get_db().execute("SELECT COUNT(*) FROM feedback").fetchone()[0], 1)

    def test_invalid_rating_rejected(self):
        self.resolve()
        for bad in ("0", "6", "abc", ""):
            r = self.post(self.s, "/complaints/1/feedback", {"rating": bad}, follow_redirects=True)
            self.assertIn(b"rating from 1 to 5", r.data)

    def test_anonymous_feedback_hides_identity_from_admin_list(self):
        self.resolve()
        self.post(self.s, "/complaints/1/feedback",
                  {"rating": "5", "comments": "Great", "anonymous": "1"})
        page = self.a.get("/admin/feedback").data
        self.assertIn(b"Great", page)
        self.assertIn(b"Anonymous", page)
        self.assertNotIn(b"Asha Rao", page)
        self.assertNotIn(b"CMP-", page)

    def test_named_feedback_shows_student(self):
        self.resolve()
        self.post(self.s, "/complaints/1/feedback", {"rating": "3"})     # checkbox not ticked
        page = self.a.get("/admin/feedback").data
        self.assertIn(b"Asha Rao", page)


class TestAnalytics(BaseCase):
    def test_dashboard_statistics_and_resolution_time(self):
        s = self.student()
        a = self.admin()
        self.submit(s, title="Fan not working")
        self.submit(s, title="Projector broken", category="Classroom",
                    description="The projector in room 3 is broken and shows nothing.")
        self.submit(s, title="Dirty washroom", category="Cleanliness",
                    description="The washroom on floor 2 has not been cleaned today.")
        self.post(a, "/admin/complaints/2/update", {"status": "In Progress", "priority": "Medium", "remarks": "On it"})
        self.post(a, "/admin/complaints/1/update", {"status": "Resolved", "priority": "High", "remarks": "Fixed"})
        # make complaint 1 look like it took exactly 6 hours
        self.run_sql("UPDATE complaints SET resolved_at = datetime(created_at, '+6 hours') WHERE id = 1")

        stats = a.get("/admin/api/stats").get_json()
        self.assertEqual(stats["status"], {"total": 3, "pending": 1, "in_progress": 1, "resolved": 1})
        self.assertAlmostEqual(stats["avg_resolution_hours"], 6.0, places=1)
        by_cat = {c["name"]: c["count"] for c in stats["by_category"]}
        self.assertEqual(by_cat, {"Electricity": 1, "Classroom": 1, "Cleanliness": 1})
        self.assertEqual(len(stats["monthly"]["labels"]), 12)
        self.assertEqual(sum(stats["monthly"]["submitted"]), 3)
        self.assertEqual(sum(stats["monthly"]["resolved"]), 1)
        self.assertEqual(sum(p["count"] for p in stats["priority"]), 3)

        page = a.get("/admin/dashboard").data
        self.assertIn(b"6.0 hrs", page)
        self.assertIn(b"id=\"categoryChart\"", page)
        self.assertIn(b"id=\"monthlyChart\"", page)

    def test_student_stats_only_include_own_complaints(self):
        a_client = self.student("asha@test.com", "Asha Rao")
        b_client = self.student("ben@test.com", "Ben Thomas")
        self.submit(a_client)
        self.submit(a_client, title="Another fan fault")
        self.submit(b_client, title="Ben's complaint here")
        self.assertEqual(a_client.get("/student/api/stats").get_json()["status"]["total"], 2)
        self.assertEqual(b_client.get("/student/api/stats").get_json()["status"]["total"], 1)

    def test_empty_database_stats(self):
        stats = self.admin().get("/admin/api/stats").get_json()
        self.assertEqual(stats["status"]["total"], 0)
        self.assertIsNone(stats["avg_resolution_hours"])

    def test_monthly_report(self):
        s, a = self.student(), self.admin()
        self.submit(s)
        month = re.search(r"\d{4}-\d{2}", a.get("/admin/reports").get_data(as_text=True)).group(0)
        page = a.get(f"/admin/reports?month={month}").get_data(as_text=True)
        self.assertIn("Report for " + month, page)
        self.assertIn("Electricity", page)
        self.assertIn("Invalid month", a.get("/admin/reports?month=garbage").get_data(as_text=True))


class TestMisc(BaseCase):
    def test_pages_render(self):
        c = self.new_client()
        for url in ("/", "/login", "/register"):
            self.assertEqual(c.get(url).status_code, 200, url)
        self.assertEqual(c.get("/does-not-exist").status_code, 404)

    def test_password_validator(self):
        self.assertIsNotNone(validate_password("abc"))
        self.assertIsNotNone(validate_password("onlyletters"))
        self.assertIsNotNone(validate_password("12345678"))
        self.assertIsNone(validate_password("abcd1234"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
