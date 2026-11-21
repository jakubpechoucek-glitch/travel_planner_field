# Project guide for coding assistants

Travel planner web app for Field Collections teams. Runs as a Databricks App on PostgreSQL (Lakebase).
Read `README.md` and `docs/` first; the design documents are the source of truth.

## Rules
- **All user-facing text, in-app help, code comments and documentation: American English.**
- **Never store e-mail addresses or phone numbers.** Users are matched by `person.sso_key_hash`
  (HMAC of the e-mail). Never log e-mails. Do not commit spreadsheets or personal data.
- Event types, rules, positions and the org structure are **data**, not code.
- Any change to a generated trip needs a **reason** (database enforces it in `trip_change`).
- Schema changes: add a numbered file in `db/migrations/`; never edit an applied migration.
- Update the relevant document in `docs/` in the same change as the feature.

## Commands
`make setup`, `make db`, `make test`, `make lint`, `make run`, `make web`, `make build` (see `docs/10-development.md`).

## Layout
`backend/travel_planner` FastAPI app · `backend/tests` pytest (needs PostgreSQL) · `db/migrations` SQL ·
`frontend` React + Vite · `app.yaml` Databricks App · `tools` helper scripts.
