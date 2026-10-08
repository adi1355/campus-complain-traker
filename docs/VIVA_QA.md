# Viva Questions and Simple Answers

**1. What is your project about?**
A web app where students submit campus complaints and track their progress, and administrators prioritise, resolve and analyse them.

**2. Why Flask?**
It is small, easy to learn, and lets us see every part of the application (routes, templates, database access) without hidden magic – ideal for explaining in a viva.

**3. Why SQLite?**
It needs no server, the database is a single file, and it is bundled with Python. It is enough for a college-sized system. For thousands of simultaneous users we would move to MySQL/PostgreSQL.

**4. How do you keep passwords safe?**
We never store passwords. `generate_password_hash` (Werkzeug) stores a salted, slow hash; at login `check_password_hash` compares the typed password with it.

**5. How do sessions and login work?**
After a correct login the user's id is stored in Flask's signed session cookie. A `before_request` function loads that user for every request. The signing uses `SECRET_KEY`, so the cookie cannot be forged.

**6. How do you separate students and admins?**
The `users.role` column. Decorators `student_required` and `admin_required` check the role before a view runs; wrong role → 403. Registration always creates `student`; the first admin is created from `.env`.

**7. Can student A see student B's complaint?**
No. Complaint pages check `student_id`; for another student's complaint the server answers 404. Images are also served through a permission check.

**8. What is SQL injection? How do you prevent it?**
Attacker text inside a query, e.g. `' OR '1'='1`. We always pass user values as `?` parameters, so they are treated as data, never as SQL.

**9. What is XSS? How do you prevent it?**
Injecting a `<script>` through a form. Jinja2 auto-escapes output, so `<script>` is displayed as text.

**10. What is CSRF?**
Another website tricking a logged-in user's browser into sending a request. Each form carries a secret token stored in the session; `before_request` rejects POSTs whose token is missing or wrong.

**11. How is the complaint ID generated?**
After inserting the row we take its unique database id and build `CMP-<year>-<id padded to 5 digits>`, e.g. `CMP-2026-00012`. Because the row id is unique, the code is unique.

**12. Explain the smart priority recommendation.**
It is a rule-based score: category base score + points for danger words (fire, spark, gas leak) + points for "problem" words (not working, broken, exam) − points for minor words. Score ≥5 Urgent, ≥3 High, ≥1 Medium, else Low. It only *suggests*; the admin can change it. It is not machine learning.

**13. How is average resolution time calculated?**
`AVG((resolved_at − created_at) in hours)` over resolved complaints, using SQLite's `julianday()`.

**14. What is stored in complaint history?**
For every submission or update: old status, new status, remarks, who changed it and when. The student sees it as a timeline – this is the "transparent tracking" feature.

**15. How are image uploads made safe?**
Only png/jpg/jpeg/webp; the first bytes (magic number) must match the type; maximum 2 MB; the file is saved under a random name (the user's file name is never used); the folder is outside `static`, so files are served only to the owner or admin.

**16. How is anonymous feedback implemented?**
`feedback.is_anonymous`. For anonymous feedback the admin page hides the student's name and the complaint ID. Honest limitation: the database still links feedback to its complaint.

**17. How do the charts work?**
The page contains `<canvas>` elements. `dashboard.js` calls a JSON route (`/admin/api/stats`) with `fetch`, then Chart.js draws doughnut, bar and line charts from that data.

**18. Why store time in UTC?**
So the data is consistent whatever the server's time zone. We convert to local time (default IST, +330 minutes) only when displaying.

**19. What does `PRAGMA foreign_keys = ON` do?**
SQLite does not enforce foreign keys unless asked; this makes the database reject, for example, a complaint with a non-existent student.

**20. What is a Blueprint?**
A way to split routes into modules (auth, student, complaints, admin) and register them on the app.

**21. How did you test the project?**
55 automated `unittest` tests (registration, login, access control, CSRF, complaint creation, history, uploads, feedback, analytics, injection attempts) plus a manual run through the browser. Run with `python -m unittest discover -s tests -v`.

**22. What are the limitations and future scope?**
No e-mail/SMS, no password reset, no rate limiting, keyword-based priority. Future: notifications, staff assignment, SLA deadlines, ML classification, production database.

**23. Does the system send e-mail or SMS?**
No. Updates are visible inside the app only; sending messages is listed as future scope.

**24. How would you deploy it for real?**
Use a production server (e.g. waitress/gunicorn) behind HTTPS, set `SESSION_COOKIE_SECURE=1`, a strong `SECRET_KEY`, back up `database.db`, and consider a bigger database.

**25. Why do you never delete a category?**
Old complaints refer to it. Deactivating keeps history intact while hiding it from new complaints.
