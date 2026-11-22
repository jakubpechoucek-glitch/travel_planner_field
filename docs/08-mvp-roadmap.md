# 8. MVP and Roadmap

Guiding statement from the kickoff meeting: *"Let's focus on a small POC or MVP that lets us test the primary
intention of this tool, then add features step by step."* Expect **four to five versions** before the model is tuned.

## 8.1 Phase 0: Foundations (1 to 2 weeks)

- Confirm the open questions (see [document 9](09-open-questions.md)), above all workspace access and Lakebase availability.
- Receive and clean the user list and org chart; agree on position names and codes.
- Business owner reviews this documentation.
- Set up repository, CI, local PostgreSQL, a first empty Databricks App deployment.

Status (Lakebase confirmed as available):

- [x] Repository, CI (GitHub Actions), local PostgreSQL (Docker), `Makefile`
- [x] API skeleton (FastAPI), versioned SQL migrations, baseline schema
- [x] Authentication by keyed hash of the SSO identity (no e-mail stored), bootstrap administrator
- [x] Empty web UI (React + Vite) that shows sign-in status; served by the API
- [x] Tests: health, identity, roles, migrations, database constraints
- [ ] First deployment of the skeleton to a Databricks App (needs workspace owner)
- [ ] Verify identity header and Lakebase credential flow on the real workspace
- [ ] Data protection sign-off; user list and org chart received

**Exit criteria:** an empty authenticated app is reachable by test users; data owner confirmed.

## 8.2 Phase 1: MVP (about 6 weeks)

| Capability | Included |
|------------|----------|
| Authentication and role-based visibility | Yes: viewer, area, regional, national planner, administrator |
| Org structure and people | Import from spreadsheet with preview and error report; admin editing |
| Event catalog and rules | Admin screens for event types, participation, cadence, caps, blackouts |
| Plan generation for 2027 | Field Collections events only; regeneration keeps manual edits |
| Calendar views | Heatmap (region/cluster × month/week), people timeline, "My plan" |
| Manual editing | Move, resize, add, cancel, merge; **mandatory reason** for overrides |
| Warnings | Period caps, quotas, blackouts, overlap, merge hint, with acknowledgment |
| Status | generated, planned, completed, cancelled |
| In-app help | Help panel, tooltips, getting-started tour (English) |
| Admin | Users and roles, plan year lifecycle, audit log |

Progress:

- [x] **Organization import** (workbook → regions, clusters, local offices, people, reporting lines, effective dating, preview, audit)
- [x] Organization page with structure view and in-app help
- [x] **Event catalog and rules**: starting catalog loaded, admin screens for event types, participation, rules (versioned), merge rules and blackouts, in-app help
- [ ] Admin screens for users, roles and login linking
- [x] **Plan generator**: rules to trips (weeks, blackouts, limits, combining, yearly limits), preview and regeneration that keeps edits, checks, heatmap and trip list
- [x] **Manual editing with mandatory reasons**: change dates, people and notes, cancel, confirm, mark as done, add a trip by hand; live effect on the rules, acknowledgement of warnings, history, role scope
- [x] Scoped plan view and editing for regional and area planners
- [x] **Admin screens for users**: people, sign-in linking (hashed), roles with scope, bulk linking, suggested roles, deactivation, last-administrator safeguard
- [x] **My plan** for everyone with a sign-in (own trips, reasons for changes, who is on the trip) and **calendar export (.ics)**; **publishing** of the plan
- [x] **Excel export** of the plan (summary, trips, people, days away, changes, checks), scoped by role
- [x] **Cost estimate** from the plan with the budget's own formula, plan against budget, early-booking effect, rates and travel modes, and cost columns in the Excel export
- [x] **Events held every N years** (for example a biennial conference or an off-year meeting): *Which years* setting on quota and cadence rules, plan years opened from the Plan page, year selector
- [x] **Choosing the area later** (Special Area visits hold a region slot) and **follow-up of actions** (up to three per trip, closed within 30 days), with the *Follow-ups* view
- [x] **Synergy suggestions** (same place, close dates; dismissable)
- [x] **"Suggest a change"** from a supervisor to the manager (My plan → Plan → Suggestions)
- [x] **People timeline** (Plan → People: rows are people, columns are days, days away, clashes, blackout periods)

**Not in MVP:** costs, lead-time checks, approval states, itineraries, outcome documents, other functions' event catalogs, integrations, notifications.

**Exit criteria:** the Head of Field and three regional managers can generate and adjust the 2027 plan, see all overlaps, and export it; every override has a reason.

## 8.3 Phase 2: Control (4 to 6 weeks)

- ~~Cost forecast per trip, month, region; budget comparison~~ **Done** (see below). ~~"Book earlier" insights~~ **Done**: the effect of early booking once the discount tiers are known. Urgent request path: open.
- Itinerary legs, same-day return hint, baggage need.
- Request/approval statuses with the SAP request number.
- Compliance dashboard with under- and over-use per region and person.
- ~~Synergy suggestions (same destination within N days)~~ **Done** (Plan → Synergies).
- Export to Excel and calendar (ICS) for individuals.

## 8.4 Phase 3: Other functions and outcomes

- Training, Quality, Legal, HR event catalogs and role scopes.
- Joint trips across functions; shared visibility.
- Trip outcomes (notes, links to documents) and completion tracking.
- E-mail notifications and reminders.
- Optional: reporting through Unity Catalog / Databricks dashboards.

## 8.5 Later ideas

- Integration with SAP or the travel desk once policies are standardized.
- Travel entitlement rules (airfare, hotel, laundry, insurance) when agreed.
- Cash advance vs. Grab codes choice.
- What-if scenarios: compare two plan versions and their cost.

## 8.6 Delivery approach

- Short iterations with a demo every one to two weeks; first demo with seeded data.
- A pilot group (Head of Field, three RMs, a few AMs) uses the tool for several weeks before wider rollout.
- Feedback captured in the app (a "Send feedback" link) and reviewed weekly.
- Documentation and in-app help are updated in the same change as the feature.

## 8.7 Success measures

- Share of trips in the plan that are entered at least 30 days before departure.
- Number of merged or avoided trips through synergy suggestions.
- Forecast versus actual cost per region (Phase 2).
- Share of overrides with a reason (target 100%).
- Weekly active planners; time to build a plan year.
