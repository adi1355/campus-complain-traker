# Smart Campus Complaint & Solution Tracker

A Flask + SQLite web application where students submit and track campus complaints
(classroom, electricity, Wi-Fi, laboratory, cleanliness, water, safety ...) and
administrators prioritise, resolve and analyse them.

**Stack:** Python 3 · Flask · SQLite · Bootstrap 5 · Chart.js · plain JavaScript

## Features

| Area | What it does |
|------|--------------|
| Student | Register/login, dashboard with statistics & charts, submit complaints (title, description, category, location, optional image), unique complaint ID (`CMP-2026-00012`), filter by category/date/status, see progress timeline and admin remarks, feedback after resolution |
| Administrator | Role-based login, view/search/filter all complaints, set priority (Low/Medium/High/Urgent), update status (Pending/In Progress/Resolved), remarks & resolution notes, student list, category management, feedback overview, monthly reports, CSV export |
| Analytics | Totals, pending / in progress / resolved, complaints by category, 12-month trend, priority mix, **average resolution time** (overall and per category) |
| Original ideas | Smart priority recommendation (rule based, explained, admin can override) · full status history · anonymous feedback · urgent-complaint alert banner · validated image attachments |

> **Notifications:** updates are shown **inside the app** (tracking page). The project does **not**
> send e-mail or SMS.

## 1. Prerequisites (Windows)

* Python 3.10 or newer – <https://www.python.org/downloads/> (tick **"Add python.exe to PATH"** in the installer)
* VS Code – <https://code.visualstudio.com/> with the *Python* extension
* Git – <https://git-scm.com/download/win>
* An internet connection when you open the site (Bootstrap and Chart.js load from a CDN)

## 2. Run it in VS Code (Windows)

1. Unzip the project, then in VS Code choose **File → Open Folder…** and pick `CampusComplaintTracker`.
2. Open a terminal: **Terminal → New Terminal** (PowerShell).
3. Create and activate a virtual environment:
   ```powershell
   python -m venv venv
   venv\Scripts\activate
   ```
   If PowerShell refuses to run the script, run this once and try again:
   `Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned`
4. Install the dependencies:
   ```powershell
   pip install -r requirements.txt
   ```
5. Create your configuration file and **edit it**:
   ```powershell
   copy .env.example .env
   ```
   Open `.env` and set:
   * `SECRET_KEY` – generate with `python -c "import secrets; print(secrets.token_hex(32))"`
   * `ADMIN_EMAIL` and `ADMIN_PASSWORD` – the first administrator account (**you choose these**)
6. *(Optional)* load demo data so the charts look full: `python seed_demo.py`
7. Start the server:
   ```powershell
   python app.py
   ```
8. Open <http://127.0.0.1:5000> in your browser.

The database (`database.db`) and its tables are created automatically on first start.

**Logins:** administrator = the email/password from your `.env`.
Students register themselves, or use the demo ones after step 6:
`aarav@demo.edu`, `diya@demo.edu`, `rohan@demo.edu` – password `Student@123`.

## 3. Run the automated tests

```powershell
python -m unittest discover -s tests -v
```
55 tests; they use a temporary database, so your real data is never touched.
(They take ~20 s because password hashing is deliberately slow.)

## 4. Project structure

```
CampusComplaintTracker/
├── app.py            application factory, CSRF, security headers, error pages
├── config.py         settings read from environment variables (.env)
├── db.py             database connection + first-run initialisation
├── schema.sql        all tables, constraints, indexes
├── auth.py           register / login / logout + role decorators
├── student.py        student dashboard, my complaints, submit complaint
├── complaints.py     complaint details, feedback, private image serving
├── admin.py          admin dashboard, management, categories, reports, CSV
├── queries.py        all reusable SQL (search + analytics)
├── utils.py          validation, priority recommendation, image checks
├── seed_demo.py      optional demo data
├── requirements.txt  Flask, python-dotenv
├── .env.example      template for your private .env
├── templates/        Jinja2 HTML pages (Bootstrap 5)
├── static/css|js/    style.css, dashboard.js (Chart.js code)
├── uploads/          uploaded images (private - served only through a permission check)
├── tests/test_app.py automated tests
└── docs/             project report, viva questions, GitHub guide
```

Difference from the brief: uploads live in `uploads/` instead of `static/uploads/`
because anything inside `static/` is public. Here only the complaint's owner and
administrators can open an image.

## 5. Configuration values you must supply

| Setting | Where | Notes |
|---------|-------|-------|
| `SECRET_KEY` | `.env` | long random string; without it logins reset on every restart |
| `ADMIN_EMAIL`, `ADMIN_PASSWORD` | `.env` | first admin, created once when the database is new |
| `DISPLAY_UTC_OFFSET_MINUTES` | `.env` (optional) | default `330` (India). Times are stored in UTC |

To reset everything: stop the server, delete `database.db` and the files in `uploads/`, start again.

## 6. Security summary

Werkzeug password hashing · session cookies (HttpOnly, SameSite) · session reset on login ·
role-based route protection · CSRF token on every POST · parameterised SQL everywhere ·
Jinja2 auto-escaping (XSS) · image extension + magic-byte + size checks, random file names ·
students can only open their own complaints (404 otherwise) · security headers incl. CSP ·
CSV export guards against spreadsheet-formula injection.

## 7. Known limitations

No e-mail/SMS notifications · no password reset · no login rate-limiting · no pagination
(fine for a college-sized dataset) · built-in Flask server is for demos – use a production
server (e.g. `waitress`) and HTTPS for real deployment.

See `docs/PROJECT_REPORT.md` for the full college report and `docs/GITHUB_GUIDE.md` to publish the code.
