# Travel Planner for Field Teams

A web application for planning business travel across Field Collections teams (and,
in later phases, Training, Quality, Legal and other functions), so that people who
need to meet in person can plan those meetings **in advance**, **together**, and
**at a lower cost**.

The application is built to run as a **Databricks App** and stores its data in
**PostgreSQL** (Databricks Lakebase, or any PostgreSQL 15+ for local development).

> Status: **Phase 0 (foundations)**. Design documents are drafted; the project skeleton
> (API, migrations, authentication, empty UI, CI) is in place. No planning features yet.

## Quick start

```bash
make setup && cp .env.example .env && make db
make run      # http://localhost:8000   (make web for the UI dev server on :5173)
make test
```

See the [development guide](docs/10-development.md).

## The idea in one paragraph

Administrators define *event types* (area visit, region meeting, conference, ...)
together with their rules: who takes part, how often, yearly/monthly limits and
blackout periods. The application **generates a yearly travel plan** from those
rules and the organization structure. Planners then **adjust the plan manually**,
and every deviation from the rule-based plan requires a **reason**. The calendar
view makes overlaps, over-use and chances to combine trips visible, so trips can
be booked earlier and cheaper. The goal is **not to cut travel** but to plan it
early, combine it, and keep control of spend.

## Documentation

| # | Document | Purpose |
|---|----------|---------|
| 1 | [Product overview](docs/01-product-overview.md) | Goals, principles, scope, glossary |
| 2 | [Users, roles and access](docs/02-users-roles-access.md) | Who uses the app and what each role can see and do |
| 3 | [Organization model](docs/03-organization-model.md) | Regions, clusters, offices and reporting lines (from the source files) |
| 4 | [Travel rules](docs/04-travel-rules.md) | Event catalog, participation, frequency, limits, blackouts, merge rules |
| 5 | [Planning workflow](docs/05-planning-workflow.md) | Plan generation, manual overrides, warnings, synergies, statuses |
| 6 | [Data model](docs/06-data-model.md) | PostgreSQL schema design (DDL in [`db/migrations/`](db/migrations/0001_baseline.sql)) |
| 7 | [Architecture](docs/07-architecture.md) | Databricks Apps, Lakebase, authentication, tech stack |
| 8 | [MVP and roadmap](docs/08-mvp-roadmap.md) | Phased delivery plan |
| 9 | [Open questions and data issues](docs/09-open-questions.md) | What must be decided or cleaned before building |
| 10 | [Development guide](docs/10-development.md) | Local setup, tests, configuration, migrations, deployment |
| – | [User guide](frontend/src/guide/user-guide.md) | How every page works, by role (also shown in the app under *User guide*) |

## Source material

The design is derived from four documents provided by the business:

- *Discussion on Travel Planning Standardization* (meeting minutes: travel guidelines)
- *Traveling web app for Field teams* (meeting transcript, Nov 20, 2026)
- *Traveling Calendar template* (event catalog, position rules, 2027 budget, sample data fields)
- *Travel Calendar 2027 Field Collections* (employee lists, org tables, 2027 travel plans, calendar plot)

These files contain personal data (names, phone numbers, e-mail addresses) and are
**not stored in this repository**.

## Language and currency

All user-facing text, in-app help and documentation are written in **American English**.
All amounts are in **Philippine pesos (PHP, ₱)**; the application has a single currency.
