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

Area managers join and leave. An administrator must be able to:

- add a person and **link their login** (the administrator types the sign-in e-mail once; the server stores only its keyed hash, never the address);
- assign a position, manager, region/cluster/local office and role;
- deactivate a person on their end date (history is kept; future generated trips are flagged for review);
- move a person to a new manager or cluster with an effective date;
- import people in bulk from a spreadsheet (needed for the first load of roughly 120 supervisors and managers).

Governance: at least two administrators, and every administrative change is written to the audit log.

## 2.4 Views per role

| View | Audience | Content |
|------|----------|---------|
| **My plan** | Everyone | My trips, upcoming first, with status and reason for any change |
| **Calendar heatmap** | Planners | Rows = region/cluster/area, columns = month or week, cells = number of trips; click to drill down |
| **Timeline** | Planners | Rows = people, columns = days; bars for trips; blackout periods shaded |
| **Compliance** | RM, Head | Trips versus minimum and maximum per event type, per unit; highlights under- and over-use |
| **Synergies** | Planners | Suggested merges or moves (same destination, nearby dates) |
| **Administration** | Administrator | Users, org structure, event types, rules, blackout periods, plan years |

## 2.5 Principle of least privilege

- Cost forecasts are visible to RM, Head and Administrator only.
- Comments and override reasons are visible to anyone who can see the trip.
- Contact data (phone numbers) is **not stored** at all.
