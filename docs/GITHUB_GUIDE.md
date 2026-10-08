# Publishing to GitHub & preparing the college submission

> Nobody else can create the repository for you – it must be created from **your** GitHub account.
> It takes about five minutes.

## A. Create the repository

1. Sign in at <https://github.com> → **New repository**.
2. Name: `smart-campus-complaint-tracker` · Visibility: Public (or Private) ·
   **do not** tick "Add a README / .gitignore" (the project already has them) → **Create repository**.

## B. Push the code (VS Code terminal, inside the project folder)

```powershell
git config --global user.name  "Your Name"
git config --global user.email "you@example.com"

git init
git add .
git status          # check: .env, database.db, venv and uploads must NOT be listed
git commit -m "Initial commit: Smart Campus Complaint & Solution Tracker"
git branch -M main
git remote add origin https://github.com/<your-username>/smart-campus-complaint-tracker.git
git push -u origin main
```
If asked to sign in, use the browser prompt, or a Personal Access Token as the password.

**Important:** `.gitignore` keeps `.env` (your secrets) and `database.db` out of GitHub. Never upload them.

## C. Good commit habits (examiners like a visible history)

```powershell
git add .
git commit -m "Add feedback feature"
git push
```
Use short messages such as `Add priority recommendation`, `Fix CSV export bug`, `Write tests for uploads`.

## D. Submission checklist

- [ ] `python -m unittest discover -s tests -v` shows **OK**
- [ ] `python app.py` starts and you can log in as admin and as a student
- [ ] Demo data loaded (`python seed_demo.py`) so charts are populated for the demo
- [ ] Screenshots taken: login, student dashboard, submit form, complaint timeline,
      admin dashboard (with urgent alert), manage complaints, reports, test run output
- [ ] Report (`docs/PROJECT_REPORT.md`) exported to Word/PDF with your name, roll number, guide, college
      (VS Code: install the "Markdown PDF" extension → right-click the file → *Export (pdf)*; Mermaid diagrams render on
      GitHub, or paste the Mermaid code at <https://mermaid.live> and export PNGs for Word)
- [ ] GitHub link written on the title page of the report
- [ ] ZIP of the project (without `venv/`, `.env`, `database.db`) on a pen drive as backup
- [ ] You can explain every file – practise with `docs/VIVA_QA.md`

## E. Demo script (5 minutes)

1. Register a student → log in → submit "Sparks from switch board" in *Electricity* with a photo → show the generated ID and the automatic **Urgent** priority.
2. Log out → log in as admin → point at the **urgent alert banner** → open the complaint → change status to *In Progress* with a remark.
3. Mark it *Resolved* (note: a resolution note is mandatory).
4. Back as student → show the timeline and remarks → give anonymous feedback.
5. Admin → *Reports*: resolution time, monthly trend, CSV export.
6. Show `python -m unittest discover -s tests -v` passing.
