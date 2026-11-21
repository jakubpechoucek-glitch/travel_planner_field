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

## 10.4 Configuration

| Variable | Used in | Meaning |
|----------|---------|---------|
| `APP_ENV` | all | `dev`, `test` or `prod` |
| `DATABASE_URL` | dev, test | Full PostgreSQL URL |
| `PGHOST`, `PGDATABASE`, `PGUSER`, `PGPORT`, `PGSSLMODE` | prod | Lakebase connection; the password is a short-lived OAuth token fetched at connect time |
| `IDENTITY_KEY` | all | Secret for the e-mail hash. **Changing it unlinks every user**, so treat it as permanent |
| `BOOTSTRAP_ADMIN_HASHES` | all | Comma-separated key hashes of the first administrators |
| `IDENTITY_HEADER` | all | Header with the signed-in user's e-mail (default `X-Forwarded-Email`; verify on Databricks) |
| `DEV_USER_EMAIL` | dev, test | Fallback identity. The app refuses to start in prod if this is set |
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

## 10.7 Conventions

- American English in code, comments, UI text and documentation.
- No e-mail addresses or phone numbers in the database, logs, test data or repository. Use `@example.test` addresses in tests.
- Backend: type hints, `ruff` clean. Frontend: TypeScript `strict`.
- One pull request per feature; documentation and in-app help updated in the same change.
