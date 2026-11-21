# 2. Users, Roles and Access

Several hundred employees can open the app. Only a small group edits plans; most
users view their own plan and trips that involve them.

## 2.1 Application roles

Roles are assigned in the app (not derived from Databricks groups) so that business
administrators can manage them without IT. A person has one **role** and, where
relevant, a **scope** (the part of the organization the role applies to).

| Role | Typical person | Scope | Can view | Can edit |
|------|----------------|-------|----------|----------|
| **Viewer** | Field supervisor | Self | Own trips and trips they are invited to | Mark own trip as done; comment |
| **Area planner** | Area manager | Own cluster | Cluster calendar, supervisors' trips | Trips organized by the AM and the AM's supervisors; reasons required for overrides |
| **Regional planner** | Regional manager | Own region(s) | Region calendar, all AMs and clusters | Trips of the RM and AMs in the region |
| **National planner** | Head of Field | All Field Collections | Everything; compliance and cost dashboards | All trips; approve plan publication |
| **Function planner** | Training, Quality, Legal leads | Own function, any region | Own function's trips plus a read-only view of field trips (to find synergies) | Own function's trips |
| **Coordinator** | Field coordinator, travel desk contact | Selected scope | Trips and statuses | Status, SAP reference, itinerary details (later phases) |
| **Administrator** | Designated business owner(s) | Global | Everything, including audit log | Users and roles, org structure, event types, rules, blackout periods, plan year lifecycle |

Open point: should functions outside Field Collections see field trips by default?
The transcript says regional managers should "see all those travels and plotted events
so that we can synergize with training, QA and other teams", so the default proposal is
**read-only visibility of trip dates, locations and organizer across all planners**, while
cost and comments stay within the owning scope.

## 2.2 Authentication

- Users sign in through Databricks (SSO). The app receives the user's identity in the
  request headers set by the Databricks Apps proxy; the app never handles passwords.
- **E-mail addresses are not stored.** The app computes a keyed hash (HMAC-SHA256 of the lower-cased e-mail) in memory and matches it to `person.sso_key_hash`. The hash is filled when an administrator links a person to a login (see below). If no match exists, the user sees a
  "You do not have access yet" page that explains how to request access.
- Roles and scopes are looked up in the database on each request (cached briefly).

See [Architecture](07-architecture.md#73-authentication-and-authorization).

## 2.3 User lifecycle

Implemented on the **Users** page (administrators only; `backend/travel_planner/users.py`).

**Getting people in.** People come from the [organization import](03-organization-model.md#35-the-organization-import-phase-1); *Add a person* covers people who are not in the import
(for example a future Training or Legal lead).

**Giving access** takes two steps, both on the person's page:

1. **Link the sign-in.** The administrator types the person's work e-mail once. The server turns it into a keyed hash, stores only the hash and forgets the address; it is never shown again,
   never logged and never in the audit log. A typo means the person cannot sign in; linking again replaces it. The same sign-in cannot be linked to two people.
2. **Give a role** (with a scope for regional and area planners: the region or the cluster).

**Faster for hundreds of people**

- *Link many sign-ins at once*: paste lines of `e-mail, employee number` (or the full name, either order; comma, semicolon or tab). A check shows what would happen, with problems by line number
  (unknown person, invalid address, address used twice, address already linked to someone else). Nothing is saved until every line is fine. The addresses are not echoed back.
- *Suggested roles*: the Head of Field becomes a national planner, each Regional Manager the regional planner of their region, each Area Manager the area planner of their cluster. Existing roles stay.

**Changes over time**

- *Deactivate* a person who leaves: they can no longer sign in at once, the history stays; *Reactivate* if they return.
- *Position, manager and place* change with a *valid from* date; the previous assignment is kept as history, as in the import.
- Roles can be added and removed at any time; every change is in the audit log (who and what, no addresses).

**Safeguards**

- The application always keeps at least one **administrator who can sign in**: removing the last administrator role, deactivating or unlinking the last administrator is refused
  (unless a bootstrap administrator is configured). The Users page recommends at least two.
- You cannot deactivate yourself.
- A global role (administrator, national planner, ...) is held once per person; a scoped role once per scope.
- The first administrator is set through configuration (`BOOTSTRAP_ADMIN_HASHES`); see the [development guide](10-development.md).

## 2.4 Views per role

| View | Audience | Content |
|------|----------|---------|
| **Export to Excel** | Administrators, national, regional and area planners | The plan they can see as a workbook (see [Planning workflow](05-planning-workflow.md#59-excel-export)); every export is written to the audit log |
| **My plan** | Everyone with a linked sign-in (supervisors land here) | The trips the person takes part in, as organizer, traveler or host, grouped by month; the next trip; status (proposed, confirmed, done, cancelled); the original date and the reason when a trip was moved or changed; who else is on the trip; calendar export (.ics). Supervisors see it once the plan is published; planners see their own trips while it is under review. Cancelled and earlier trips are folded away |
| **Plan (own scope)** | Regional and area planners | The heatmap, trips and history of their own units; they can change those trips (see [Planning workflow](05-planning-workflow.md#53-manual-changes-and-reasons)). Plan-wide checks and plan generation stay with administrators and national planners |
| **Calendar heatmap** | Planners | Rows = region/cluster/area, columns = month or week, cells = number of trips; click to drill down |
| **Timeline** | Planners | Rows = people, columns = days; bars for trips; blackout periods shaded |
| **Compliance** | RM, Head | Trips versus minimum and maximum per event type, per unit; highlights under- and over-use |
| **Synergies** | Planners | Suggested merges or moves (same destination, nearby dates) |
| **Events and rules** | Everyone with access (read), Administrator (edit) | The event catalog, rules and blackout periods |
| **Organization** | Administrator, National planner | Regions, clusters, leaders, supervisor counts. Administrators also import the structure here |
| **Administration** | Administrator | Users, org structure, event types, rules, blackout periods, plan years |

## 2.5 Principle of least privilege

- Cost forecasts are visible to RM, Head and Administrator only.
- Comments and override reasons are visible to anyone who can see the trip.
- Contact data (phone numbers) is **not stored** at all.
