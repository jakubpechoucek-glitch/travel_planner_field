# 6. Data Model

The database is **PostgreSQL 15+**. The DDL is in [`db/migrations/0001_baseline.sql`](../db/migrations/0001_baseline.sql); it
loads cleanly on PostgreSQL 16 and uses no extensions, so it is compatible with Databricks Lakebase.
All objects live in the `travel` schema.

## 6.1 Overview

```
position ──< person_assignment >── person ──< user_role
                 │  │  │              │
          org_unit (region / cluster / local_office)       meeting_group ──< meeting_group_member
                 │
              location

event_type ──< event_type_position >── position
    │  └──< rule  (versioned)
    │  └──< merge_rule
    │
plan_year ──< blackout_period ──< blackout_event_type
    │
    └──< trip ──< trip_participant >── person
           │  └──< trip_leg                (Phase 2)
           │  └──< trip_change             (history + reasons)
           │  └──< warning_ack
cost_rate (Phase 2)        audit_log
```

## 6.2 Tables

### Organization

| Table | Purpose | Key points |
|-------|---------|-----------|
| `position` | Job positions and groups (Head of Field, RM, AM, FSV, Legal Specialist, ...) | `level` is used by rules; `is_traveler` is false for field collectors |
| `org_unit` | Regions, clusters and local offices | Generic tree (`kind`, `parent_id`); a new layer is a new row, not a schema change. `lead_person_id` is the RM of a region or the AM (or acting RM) of a cluster |
| `location` | Cities and provinces where trips happen | Linked to region and local office; filled from the *Reference* sheet |
| `person` | Identity of an employee | Name, `name_key` (normalized name for matching), employee number, active flag, `sso_key_hash` (keyed hash used to match the SSO login). **No e-mail address, no phone number.** |
| `person_assignment` | Effective-dated position, manager and unit | Plans use the assignment valid on the trip date; supports restructuring |
| `meeting_group` / `_member` | Supervisors that meet together | An AM may have several groups |

### Access

| Table | Purpose |
|-------|---------|
| `user_role` | Application role with an optional scope (an `org_unit`). Roles: viewer, area planner, regional planner, national planner, function planner, coordinator, administrator |

### Events and rules

| Table | Purpose |
|-------|---------|
| `event_type` | The event catalog: organizer position, visited unit kind, joint-visit mode, typical length and transport |
| `event_type_position` | Participation per position and optional **yearly limit** (the "2x", "3x" cells of the template) |
| `rule` | Versioned rule: type, scope, period, min/max, severity, parameters as JSON. `UNIQUE (rule_key, version)` |
| `merge_rule` | "Event A merges into event B" |

`rule.params` holds type-specific details that would otherwise need many nullable columns, for example
`{"months": [11, 12, 1]}` for a preferred window or `{"distinct_units": true, "per_quarter": [4, 5]}` for rotation.
The application validates `params` per `rule_type` (JSON schema) before saving.

### Plan and trips

| Table | Purpose |
|-------|---------|
| `plan_year` | Lifecycle: draft, review, published, closed |
| `blackout_period` / `blackout_event_type` | Dates where event types are not allowed (no event types listed = all) |
| `trip` | One planned occurrence. Keeps **both** the current dates and the original generated dates (`generated_start_date`, `generated_end_date`) so the UI can show the deviation |
| `trip_participant` | Who is involved; `travels = false` for local hosts, so that cost and overlap logic ignore them |
| `trip_leg` | Itinerary legs for multi-stop trips (the source plan's "T1 / L1" notation); Phase 2 |
| `trip_change` | History. A reason is **mandatory** for every change except `created` and `generated` (enforced by a `CHECK`) |
| `warning_ack` | Which rule warning was acknowledged, by whom, with which reason |

### Cost and audit

| Table | Purpose |
|-------|---------|
| `cost_rate` | Unit prices by kind, transport mode and position (Phase 2). Default currency PHP |
| `audit_log` | Administrative actions: role changes, rule edits, publication, imports |

## 6.3 Views

| View | Purpose |
|------|---------|
| `v_person_current` | The assignment that is valid today for every active person |
| `v_trip_calendar` | One row per traveling person per non-cancelled trip; feeds the timeline and heatmap |
| `v_person_trips_per_month` | Trip counts per person per month, for period caps |

## 6.4 Integrity rules enforced by the database

- `trip.end_date >= trip.start_date`.
- A cancelled trip must have a `cancel_reason`.
- A change other than creation or generation must have a `reason`.
- A person cannot be their own manager; assignment periods are valid (`valid_to >= valid_from`).
- Rule `max_count >= min_count`; severities and statuses come from fixed lists.
- Cascade deletes only for owned child rows (participants, legs, change history). Master data is deactivated, not deleted.

Rules that need more than a `CHECK` (for example, "no overlapping assignment periods per person",
"one RM at most per region") are validated in the application service layer and by import checks.

## 6.5 Generated versus current

A trip generated by a rule has `source = 'generated'`, `rule_id` pointing to the rule version, and
`generated_*` dates equal to the current dates. When a planner edits it, the current dates change, the
`generated_*` dates stay, and a `trip_change` row records the reason. Regeneration only replaces trips that
are still `generated` and unedited.

## 6.6 Personal data

- Stored: employee number, full name, position, reporting line, office, and a keyed hash of the SSO e-mail (`sso_key_hash`, HMAC-SHA256 with a secret held in a Databricks secret). **E-mail addresses are never stored**, in the database, logs or the audit log.
- **Not stored:** phone numbers, hire dates, salary, collection capacity, anything from the field-collector (FTE) list beyond a head count per office.
- The source workbooks contain personal data and stay outside the repository and outside the database.
- Access to `person` data follows the role scopes in [Users, roles and access](02-users-roles-access.md).
- The audit log records who changed what, not what they viewed.
- Retention: trips and history are kept for the life of the plan year plus the period required by company policy *(to be confirmed)*.

## 6.7 Migrations

Migration `0002_org_import.sql` adds `org_unit.lead_person_id`, `person.name_key` and seeds the field-hierarchy positions (`HEAD`, `RM`, `AM`, `SFSV`, `FSV2`, `FSV`, `DM`, `DSV`).

Schema changes are versioned SQL migrations applied by the application at deployment (Alembic or a similar
tool, to be chosen with the application framework). The baseline is `db/migrations/0001_baseline.sql`; further changes are added as numbered files and applied in order by `backend/travel_planner/migrate.py`, which records them in `travel.schema_migration`.
