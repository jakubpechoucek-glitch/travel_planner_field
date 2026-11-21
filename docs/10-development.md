# 10. Development Guide

## 10.1 Prerequisites

Python 3.11+ (tested on 3.13), Node.js 20+ (tested on 22), and PostgreSQL 15+ (Docker is the easiest way).

## 10.2 First-time setup

```bash
make setup                 # virtualenv, Python and npm dependencies
cp .env.example .env       # local configuration (never committed)
make db                    # PostgreSQL 16 in Docker, creates tp_dev and tp_test
make run                   # API on http://localhost:8000 (applies migrations on start)
make web                   # in a second terminal: UI on http://localhost:5173
```

In local development the app trusts `DEV_USER_EMAIL` when no identity header arrives. Use a fictitious address.
To make yourself administrator locally:

```bash
IDENTITY_KEY=dev-only-change-me python tools/hash_email.py   # type the e-mail at the hidden prompt
# put the printed hash into BOOTSTRAP_ADMIN_HASHES in .env, then restart
```

## 10.3 Tests and checks

```bash
make test     # pytest against PostgreSQL (TEST_DATABASE_URL, default postgresql://tp:tp@localhost:5432/tp_test)
make lint     # ruff + TypeScript type check
```

CI (`.github/workflows/ci.yml`) runs both on every push with a PostgreSQL service container.
Tests drop and recreate the `travel` schema in the test database; never point `TEST_DATABASE_URL` at real data.

## 10.3a Importing the organization

```bash
cd backend
python -m travel_planner.orgimport /path/to/workbook.xlsx                  # preview: nothing is saved
python -m travel_planner.orgimport /path/to/workbook.xlsx --apply --effective 2027-01-01
```

The same function runs behind **Organization → Import organization** in the app (administrator only; files up to 10 MB).
The workbook contains personal data: keep it outside the repository (`*.xlsx` is git-ignored) and never use it in tests.
Tests build a small fictitious workbook (`backend/tests/orgfixture.py`). Details: [Organization model](03-organization-model.md#35-the-organization-import-phase-1).

## 10.3b Generating a plan

In the app: **Plan → Generate plan** (administrators, national planners), preview first. The engine is plain Python (`backend/travel_planner/plan_engine.py`) and can be run
without a database for experiments; `backend/tests/test_plan_engine.py` shows how to build the inputs. `plan_store.py` loads the inputs from PostgreSQL and saves the result.

```bash
curl -X POST "http://localhost:8000/api/admin/plan/2027/generate?commit=false"   # preview (nothing saved)
```

| Endpoint | Who | Purpose |
|----------|-----|---------|
| `GET /api/plan-years` | any planner | The plan years with status and number of trips |
| `POST /api/admin/plan-years` `{"year": 2028}` | administrator, national planner | Open the next plan year as a draft (it must be the year after the last one) |

A rule is held every N years with `params.every_n_years` and `params.first_year` (quota and cadence rules only); the generator skips the event in the other years and reports it under *skipped*.

## 10.3c Changing trips (API)

All under `/api/plan` and limited by role scope (`backend/travel_planner/access.py`):

| Call | Purpose |
|------|---------|
| `POST /trips/{id}/edit?commit=false` | Preview (default) or save a change of dates, notes, title or people. Returns the new warnings; `commit=true` needs `acknowledge` when there are *warn* warnings |
| `POST /trips/{id}/cancel?commit=` | Cancel with a reason |
| `POST /trips/{id}/status` | Confirm a generated trip or mark it as done |
| `POST /{year}/trips?commit=` | Add a trip by hand (default people come from the catalog) |
| `GET /trips/{id}`, `GET /trips/{id}/history` | Detail with an `updated_at` token, and the change history |
| `GET /places`, `GET /people?q=` | Places and people the caller may use |

Every change body has `reason` (3 to 500 characters), `category` and optionally `expected_updated_at` (the token from the detail).

## 10.3d User administration (API)

Under `/api/admin/users` (administrators only):

| Call | Purpose |
|------|---------|
| `GET /meta` | Positions, org units, roles and their scope kind, the number of administrators who can sign in |
| `GET ?q=&role=&login=&active=&limit=&offset=` | People with position, place, roles and whether a sign-in is linked |
| `POST`, `PUT /{id}` | Add a person; change name, employee number, active flag, or the effective-dated assignment |
| `POST /{id}/login` `{email}`, `DELETE /{id}/login` | Link (or replace) and unlink a sign-in. The address is hashed and discarded |
| `POST /{id}/roles`, `DELETE /{id}/roles/{role_id}` | Add and remove a role (scope required for regional and area planners) |
| `POST /bulk-login?commit=` `{text}` | Link many sign-ins from pasted lines; preview by default |
| `POST /suggest-roles?commit=` | Roles that follow from the organization; preview by default |

To become the first administrator without a person record: `IDENTITY_KEY=... python tools/hash_email.py` and put the printed hash into `BOOTSTRAP_ADMIN_HASHES`.
Once real administrators have a linked sign-in and the role, remove that setting.

## 10.3e My plan and publishing (API)

| Call | Who | Purpose |
|------|-----|---------|
| `GET /api/my/trips?year=` | any signed-in person with a role | The caller's own trips with role, status, original dates, last change and participants. Empty until the plan is published (planners see theirs earlier) |
| `GET /api/my/trips.ics?year=` | the same | iCalendar file of the caller's trips (cancelled trips are left out; 404 until published) |
| `POST /api/admin/plan/{year}/status` `{status}` | administrators, national planners | `published` (from review), `review` (withdraw), `closed` (from published) |

## 10.3f Excel export (API)

`GET /api/plan/{year}/export.xlsx[?include=cancelled]` for anyone with plan access (administrator, national, regional and area planner); scoped as the plan page is,
`Checks` only for the whole-plan roles. The workbook is built with openpyxl in `backend/travel_planner/plan_export.py` and tested in `backend/tests/test_plan_export.py`
(structure, agreement with the plan, real dates, no formulas from text, scope, audit).

## 10.3g Cost estimate (API)

| Call | Who | Purpose |
|------|-----|---------|
| `GET /api/cost/{year}/forecast?book_ahead_days=` | administrator, national, regional planner (scoped) | Totals, by month, place, event and position, by mode, the budget comparison (whole-plan roles), the early-booking effect and the assumptions |
| `GET /api/cost/config` | the same | Rates, travel modes, place overrides, settings, discount tiers |
| `GET /api/cost/{year}/budget` | administrator, national planner | The budget lines and their event |
| `POST /api/admin/cost/rates`, `DELETE /api/admin/cost/rates/{id}` | administrator | Set a rate from a date (closes the previous one) or end it |
| `PUT /api/admin/cost/modes`, `POST /api/admin/cost/modes/suggest` | administrator | Set one cell of the region table, or load the suggested defaults |
| `POST /api/admin/cost/overrides`, `DELETE .../{id}` | administrator | A place that needs another mode |
| `PUT /api/admin/cost/settings`, `PUT /api/admin/cost/booking-tiers` | administrator | Head office and venue regions; early-booking tiers (the factor must not rise with the days) |
| `POST /api/admin/budget/import?year=&commit=`, `PUT /api/admin/budget/lines/{id}` | administrator | Load the budget workbook (preview by default) and match a line to an event |

The engine (`cost_engine.py`) is tested without a database in `backend/tests/test_cost_engine.py`, including the budget's unit prices; `test_costs.py` covers the database side.

## 10.3h Visual design

The interface uses one design system in `frontend/src/styles.css` (tokens for light and dark mode, chosen by the browser setting):

- **Shell:** a dark sidebar with icons and the signed-in user (a scrolling top bar on phones), a dashboard on **Home** (greeting, days to the next trip, key figures, rule checks, setup progress for administrators), and a split sign-in page.
- **Event families:** `frontend/src/theme.ts` groups event codes into seven families, each with one color of the validated categorical palette (area, region, Lakbay, company, Head of Field, training, other). The same colors are used on the plan timeline, in My plan and in the events list. Color never carries meaning alone: every use has a legend, a tooltip or a label.
- **Plan timeline:** one row per area, a bar per trip (hatched = still proposed), filters by family, zoom by quarter, click to open the trip. It reads `GET /api/plan/{year}/trips`, which returns `event_code`, `place` and `row_unit_id` for this purpose. The monthly heatmap stays as a second view and uses one blue ramp.
- **Charts** (`frontend/src/charts.tsx`): columns, ranked bars, paired bars (budget against estimate), a segmented bar, meters, sparklines and a progress ring, all with tooltips and text alternatives. Status colors always come with an icon and a label.
- `GET /api/my/trips` also returns `event_code` per trip.

## 10.3i User guide in the application

Every signed-in user can open **User guide** in the sidebar. The text is a single Markdown file, `frontend/src/guide/user-guide.md` (screenshots next to it as `.jpg`), rendered by `frontend/src/Guide.tsx` with a table of contents, a "Go to my chapter" shortcut for the user's role, and print or save as PDF. It lives under `frontend/` so that the container build includes it. Supported Markdown: headings (`#`, `##`, `###`), paragraphs, bullet and numbered lists, pipe tables, `**bold**`, `*italic*`, `code`, images `![caption](name)` (file `name.jpg` in the same folder) and notes `> **Tip** text` or `> **Note** text`. Update the guide in the same change as a feature that users can see; screenshots must use fictitious data only.

## 10.4 Configuration

| Variable | Used in | Meaning |
|----------|---------|---------|
| `APP_ENV` | all | `dev`, `test`, `demo` (trial hosting) or `prod` (Databricks) |
| `DATABASE_URL` | dev, test | Full PostgreSQL URL |
| `PGHOST`, `PGDATABASE`, `PGUSER`, `PGPORT`, `PGSSLMODE` | prod | Lakebase connection; the password is a short-lived OAuth token fetched at connect time |
| `IDENTITY_KEY` | all | Secret for the e-mail hash. **Changing it unlinks every user**, so treat it as permanent |
| `BOOTSTRAP_ADMIN_HASHES` | all | Comma-separated key hashes of the first administrators |
| `IDENTITY_HEADER` | all | Header with the signed-in user's e-mail (default `X-Forwarded-Email`; verify on Databricks) |
| `DEV_USER_EMAIL` | dev, test | Fallback identity. The app refuses to start in prod if this is set |
| `DEMO_PASSCODE`, `DEMO_FIRST_LOGIN_ADMIN`, `SESSION_HOURS` | demo | Trial hosting only (see 10.7) |
| `RUN_MIGRATIONS` | all | Apply pending migrations on start (default true) |

The app refuses to start in `prod` without `IDENTITY_KEY` and the three Lakebase variables.

## 10.5 Database migrations

- Files `db/migrations/NNNN_name.sql`, applied in order, once each, recorded in `travel.schema_migration`.
- A migration runs in one transaction; a failure rolls it back and stops the start-up.
- Applying is serialized with an advisory lock, so several app instances can start at once.
- **Never edit an applied migration**; add a new one.

## 10.6 Deploying to Databricks (to be completed with the workspace owner)

1. Build the UI: `make build` (output in `frontend/dist`, which is not in git).
2. Create secrets for `IDENTITY_KEY` and the bootstrap administrator hash; bind the Lakebase instance as an app resource; fill the names in `app.yaml`.
3. Deploy the folder containing `app.yaml`, `requirements.txt`, `backend/`, `db/` and `frontend/dist/` with the Databricks CLI or Asset Bundles.
4. Open the app, check `/api/health`, then sign in as the bootstrap administrator.

Open points to verify on the real workspace: the identity header name, how the Lakebase credential is issued to the app's service
principal (`backend/travel_planner/db.py`), the port and command conventions in `app.yaml`, and whether the sync step honors `.gitignore`
(`frontend/dist` must be included in the deployed files).

## 10.7 Trial hosting outside Databricks (demo mode)

For trials before the Databricks deployment, the app can run on any container host (the first trial runs on Render:
one web service built from the `Dockerfile`, plus a managed PostgreSQL 16 database).

- `APP_ENV=demo` replaces SSO with a sign-in form: work e-mail plus a shared **access code** (`DEMO_PASSCODE`).
  The e-mail is hashed immediately and never stored; the session cookie holds only the hash, expiry and signature.
- `DEMO_FIRST_LOGIN_ADMIN=true` makes the first person who signs in the administrator while no administrator exists.
  Turn it off (or set `BOOTSTRAP_ADMIN_HASHES`) once the right person is in.
- Failed sign-ins are throttled (10 per minute, in memory).
- Required variables: `DATABASE_URL`, `IDENTITY_KEY`, `DEMO_PASSCODE`. Use **fictitious data only** in a trial; it is not
  the production environment and has not been through the data protection review.
- Demo mode is not a substitute for SSO: do not load real employee data into a trial installation.

## 10.8 Conventions

- American English in code, comments, UI text and documentation.
- Money: one currency, the Philippine peso (PHP, ₱). Use `backend/travel_planner/currency.py` and `frontend/src/money.ts`; never hard-code another symbol or format.
- No e-mail addresses or phone numbers in the database, logs, test data or repository. Use `@example.test` addresses in tests.
- Backend: type hints, `ruff` clean. Frontend: TypeScript `strict`.
- One pull request per feature; documentation and in-app help updated in the same change.
