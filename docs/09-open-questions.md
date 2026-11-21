# 9. Open Questions and Data Issues

Items are grouped by who can answer. "Blocking" means design or build cannot continue safely without it.

## 9.1 Platform and IT

| # | Question | Blocking? |
|---|----------|-----------|
| P1 | Is **Lakebase** enabled in the workspace? If not, which PostgreSQL can the app reach? | Yes |
| P2 | Can all several hundred planned users (supervisors included) be given access to the Databricks workspace/app via SSO? Who provisions them? | Yes |
| P3 | Which deployment method is allowed (Asset Bundles, CLI, CI)? Are there naming or tagging rules for apps? | No |
| P4 | Data protection review: is storing names and employee numbers in this app acceptable? (E-mail addresses are deliberately not stored; only a keyed hash is.) Who is the data owner? | Yes |
| P5 | After the author's contract ends this year, who maintains the app and its database? | Yes, for the handover plan |

## 9.2 Business rules (Head of Field, regional managers, travel desk)

| # | Question |
|---|----------|
| B1 | Planning granularity: weekly for H1 and monthly for H2, or weekly all year? |
| B2 | Head of Field: the *Position rules* sheet says "once a month", but the *Events description* grants the Head 2× region visits, 3× region management meetings, 3× Lakbay, 1× conference and 3× year-end parties, and the *Travel Plans* sheet lists 18 trips (area tour, quarterly meetings, party legs). Which caps are authoritative? |
| B3 | Are "Region Visit" (quarterly) and "Region Management Meeting" (every four months) both required, or is one merged into the other? |
| B4 | How are caps enforced: warning with a reason (proposed) or hard block for any rule? |
| B5 | Maximum area visits per week nationwide, per region, per person? Any minimums? (Asked at the meeting.) |
| B6 | Does attending the conference or year-end party count as the touchpoint for that week or month? (The "satisfaction" rule.) |
| B7 | How is a Lakbay region chosen each year? Which three areas rotate? |
| B8 | What exactly does "joint visit: partial" mean? Which of the listed functions join which trips? |
| B9 | Can an RM or the Head skip the AM and attend supervisor meetings directly? How is a visit selected (rotation, risk, request)? |
| B10 | The year-end party is "November, December or January": which of these falls in plan year 2027? |
| B11 | Which events are mandatory (compliance) and which are advisory? |
| B12 | Should travelers confirm that a trip happened ("done"), or should a planner? |
| B13 | Should trips carry outcomes (documents, notes)? (Raised at the meeting; proposed for Phase 3.) |
| B14 | Is the request priority (High/Medium/Low, from the sample data fields) needed? |
| B15 | Which functions (Training, Quality, Legal, HR) join in Phase 3, and who owns their calendars? |
| B16 | Policy topics left undecided in the standardization meeting: airfare, hotel, baggage, laundry, insurance, cash advance versus Grab codes. Leave out of the app for now? |

## 9.3 Data issues found in the source files

| # | Finding | Proposed handling |
|---|---------|-------------------|
| D1 | The *Reference* sheet shows a cluster named *Visayas East* and a cluster *Cebu*; the *Emp Tables* sheet shows *Cebu* and *Visayas West*. | Confirm the official cluster list. |
| D2 | Cluster *Cebu* has no AM; the row says "AM TEMP / Regional Manager". | Model as the RM acting as AM, with an end date. |
| D3 | Some clusters appear under a different region than their provinces (for example Bohol and Leyte under Mindanao clusters). | Confirm: cluster membership is by manager, not strictly by geography. |
| D4 | "Area" means a group of supervisors in the event catalog, but a city in the employee list (for example "Lipa City") and in *Travel Plans*. | App terms: cluster and local office. Confirm mapping. |
| D5 | The local office named "Mexico" is in Pampanga (North Luzon). | Display as *Mexico (Pampanga)* to avoid confusion. |
| D6 | Position names vary: *Senior Field Supervisor*, *Field Supervisor II*, *Collections Regional Manager*, *Regional Field Leaders*, *Collection Regional Manager - VisMin*. | Agree on one position list with codes and levels. |
| D7 | The *Events description* has typos ("Congerence", "Noveber", "Collecions") and several empty codes. | Fix at import; confirm codes. |
| D8 | The employee file with about 3,970 rows is mostly field collectors (FTEs) with many columns unrelated to travel; the supervisor list has 123 rows. | Import only supervisors, AMs and RMs, plus a head count per local office. Verify that every supervisor has an AM. |
| D9 | The *Position* list mixes individual names (for example specific people) with groups. | Replace names with positions or functions; assign people separately. |
| D10 | Travel Plans sheet leaves some cells empty (group, length, mode) and uses codes like T1 / L1 without definition. | Confirm that T = trip and L = leg; derive legs from them. |
| D11 | The budget uses hard-coded numbers in formulas (for example 20,000 + 2 × 3,000 + 2,500 + 3 × 600). | Replace with named rates in `cost_rate` once the meaning of each term is confirmed. |
| D12 | Source workbooks contain employee contact numbers and e-mails. | Not imported; keep out of the repository. |

## 9.3a Findings from the first import of the real workbook

The first run against the 2027 workbook produced 1 Head, 3 RMs, 11 AMs and 145 supervisors in 5 regions, 12 clusters and 20 local offices.
These points need a business decision:

| # | Finding | Handling now |
|---|---------|--------------|
| I1 | Six groups of supervisors (30 people in total) report to a different manager in the employee list than the cluster table names (for example, 11 supervisors in *North Luzon 2* list the *North Luzon 1* AM; 9 in *North Luzon 1* list the RM; 8 in *South Luzon 4*). The employee list seems older than the cluster table. | The **cluster table wins**; a grouped warning is shown. Confirm that it is right. |
| I2 | Cluster *Cebu* has no AM: the RM acts as AM. | The RM leads the cluster; the RM is the manager of its supervisors. Add an end date when an AM is appointed. |
| I3 | One supervisor is in the employee list but not in the FSV table. About 24 supervisors in the FSV table are not in the employee list, so they have **no employee number**. | They are matched by name. Provide employee numbers to make matching reliable. |
| I4 | The workbook contains digital mentors (5) and digital supervisors (2) among supervisors. | Imported as positions `DM` and `DSV` at supervisor level. Confirm whether they travel and with which rules. |
| I5 | The RM's own local office ("Mexico" for one RM) is a base, not a region. | Stored as the RM's base office (the office itself is taken from the AM and supervisor tables, which carry its region). |
| I6 | Provinces (the *Reference* sheet) are not imported yet: its "area" names (*West Visayas*, *East Visayas*) do not match the cluster names (*Visayas West*, *Cebu*). | Local offices are loaded as locations. Provinces follow once the cluster names are agreed (D1). |

## 9.4 Catalog assumptions

Decisions taken when the starting catalog was loaded. Each can be changed in the app, but the business should confirm them:

| # | Assumption | Source |
|---|------------|--------|
| K1 | Area visit: 6 to 12 per cluster a year, default spacing two months. Area meeting: exactly 6 per cluster, every two months. | Events description |
| K2 | Region visit: 4 per Area Manager a year (quarterly). Region management meeting: 3 per cluster, every four months, rotating through 4 to 5 clusters per region each quarter. | Events description |
| K3 | Lakbay: 3 a year per region in 3 different clusters. Conference: 1 a year. Year-end party: 1 per cluster, preferably November to January. | Events description |
| K4 | Field Leader's Collections University: 2 sessions per cluster a year (one per half). | Events description |
| K5 | Head of Field area tour: every local office once a year. Regional Field Meeting: once per region a year, rotating through the quarters (changed from "4 per region" after the first generation; the source says "quarterly" but lists one meeting per region). | Travel Plans |
| K6 | Regional Manager: at most 2 trips a month (warn). Head of Field: at most 1 trip a month (warn); this conflicts with the 18 trips in the Travel Plans (see B2). | Position rules |
| K7 | Conference in April and the year-end party in December 2027 are placeholders for the blackout periods. | Travel Plans (planned month) |
| K8 | All quota and cap rules default to *warn*, as asked in the meeting ("a prompt when you have exceeded the frequency"). Rotation, cadence and window rules default to *info*. | Meeting |
| K9 | "Joint visit: Partial" is stored as *Partly*; which functions join which trips is expressed in the participation table. | Events description |
| K10 | Supervisors attend the year-end party (added to its participants; the template lists only AM, RM, Head, Training). | Activity: Area Manager to Supervisors |
| K11 | The visited team does not travel for visits to them (supervisors at an area visit, the Area Manager at a region visit, supervisors at the Head's area tour). | Events description |

## 9.5 Generator findings

The first plan generated for 2027 from the real structure (255 trips plus 46 combined, about 0.2 seconds) shows where the rules and the numbers disagree. These are the
questions the business needs to answer before the plan can be taken as a proposal:

| # | Finding | Options |
|---|---------|---------|
| G1 | **Lakbay needs "3 different clusters" per region, but four regions have only 2 clusters** (NCR, North Luzon, Visayas, Mindanao). Only South Luzon (4 clusters) works. | Lower the number to 2 for those regions; allow a cluster to host Lakbay twice; or count local offices instead of clusters (the source says "3 unique areas") |
| G2 | **Trip limits and the catalog volumes contradict each other.** A Regional Manager is limited to 2 trips a month (24 a year), but the catalog gives each RM area meetings (4 per cluster through the merged region visits), region meetings (3 per cluster), Lakbay, the conference and regional meetings. The Head of Field is limited to 1 trip a month, but must meet every local office (20) plus regional meetings. About 40 "trip limit" warnings result. | Raise the limits; reduce the volumes (for example RM joins only some area meetings); or accept the warnings as a planning signal |
| G3 | **The Head's area tour is 20 separate trips** (one per local office). The Travel Plans group them into about 8 multi-stop trips (T1 / L1, T1 / L2 ...). | Build trip grouping (stops per trip) in the next iteration |
| G4 | Three overlaps remain where the Head is in two trips in the same week; they follow from G2 and G3. | Resolved with G2 and G3 |
| G5 | Region visit (4 per cluster) is mostly combined with the area meeting of the same cluster, which is the intent of the merge rule, but it makes the RM travel a lot. | Confirm that the region visit should not be a separate trip |
| G6 | Weeks start on Monday and trips are Tuesday to Friday. Public holidays and company non-working days are unknown. | Provide the holiday calendar |
| G7 | The generator treats a "participant" position above the organizer as optional (RM at an area meeting). | Confirm; otherwise set a yearly limit for it in the catalog |

## 9.6 Manual editing decisions

Decisions taken while building the editing; please confirm:

| # | Decision | Alternative |
|---|----------|-------------|
| E1 | A reason is required for **every** manual change, also for adding or cancelling a trip. Confirming a trip and marking it as done are not deviations, so the app writes the reason. | Allow adding a trip without a reason when it is inside the rules |
| E2 | **Warn** rules need an acknowledgement; **block** rules refuse the change. All quota and cap rules are seeded as *warn*, so nothing is blocked out of the box. | Make some rules *block* (for example the monthly trip limit) |
| E3 | Regional planners change trips under their region, area planners those of their cluster and its local offices. Nationwide events are changed only by administrators and national planners. | Let regional planners also change nationwide events they attend |
| E4 | A planner marks a trip as done once it has started. | Let the traveler confirm; require a short outcome note |
| E5 | A combined trip cannot yet be split back into two trips. The workaround is to cancel it with a reason and add the trips by hand. | Build "split" (restores the combined trip as its own trip) |
| E6 | After the plan is *published*, changes are allowed and marked "after publication" in the history. | Require approval by the Head of Field for changes after publication |
| E7 | The administrator that signs in through the bootstrap setting has no person record, so the history shows "Administrator". | Link every administrator to a person on the first sign-in |

## 9.7 User administration decisions

| # | Decision | Alternative |
|---|----------|-------------|
| A1 | The sign-in is linked by an administrator typing the person's e-mail, because addresses are not stored. A typo is only discovered when the person cannot sign in. | Let people claim their own account the first time they sign in, with an administrator approving the request (the app would see the address once, in the request) |
| A2 | The employee list does not contain sign-in addresses. They have to come from HR or the company directory as a list of `e-mail, employee number`. | Ask IT for an export from the directory |
| A3 | Roles are suggested from the organization, but *Viewer* (supervisors see their own trips) is not assigned automatically, since that view is not built yet. | Give every supervisor the viewer role when "My plan" exists |
| A4 | Deactivating a person blocks sign-in at once but keeps their history and trips. Their open trips are not changed automatically. | Flag a deactivated person's future trips for review |
| A5 | There is no self-service for planners to give access to others; only administrators manage users. | Let regional planners manage the area planners of their region |

## 9.8 My plan decisions

| # | Decision | Alternative |
|---|----------|-------------|
| M1 | Supervisors see their trips only after the plan is **published**; planners see their own trips while it is under review. | Show proposals to supervisors earlier, marked "proposed" |
| M2 | A trip generated by the rules shows as **Proposed** until a planner confirms it. | Treat every published trip as agreed |
| M3 | Everyone on a trip can see the **names** of the others on that trip (they attend together). They cannot see other people's other trips. | Show only the organizer and the number of people |
| M4 | A visited team is a **host**: the trip is shown to them, marked "you host this visit", and is exported as free time in the calendar. | Hide visits from the visited team |
| M5 | The calendar file is a download (all-day events, tentative for proposed trips). A live subscription that updates itself is not built. | A private feed link per person |
| M6 | Supervisors cannot change anything. To ask for a change they contact their manager. | A "suggest a change" button that notifies the planner |
| M7 | The plan has working days only and no public holidays, so a trip can fall on a holiday. | Add the holiday calendar (G6) |

## 9.9 Excel export decisions

| # | Decision | Alternative |
|---|----------|-------------|
| X1 | The workbook is a snapshot of values. It does not refresh and has no formulas. | Add live formulas for totals so that edits in Excel recalculate |
| X2 | It contains names of people. It is limited to the caller's scope and every export is in the audit log. Once downloaded, the file is outside the application's control. | Remove names from exports for regional and area planners; add a watermark with the exporter |
| X3 | There are no costs yet. Days away and nights per person and trip are included so that a budget can be built from them. | Add the cost forecast (Phase 2) and the layout of the *Traveling Plan Budget 2027* sheet (event, position, count, frequency, unit price) |
| X4 | The SAP request column is empty until request numbers are tracked. | Import SAP numbers from the travel desk |
| X5 | Days are calendar days (start to end inclusive); nights are days minus one. Public holidays are not considered. | Working days, or the company's own definition of days out of office |

## 9.10 Product and design

| # | Question |
|---|----------|
| U1 | One calendar per audience (Region managers, field, travel desk) or one view with filters? |
| U2 | Should planners edit with drag-and-drop on the timeline, a form, or both? (Proposed: both.) |
| U3 | Is a mobile view needed, or desktop only? |
| U4 | Corporate branding: logo, colors, fonts? |
| U5 | Notifications: e-mail only, or also Microsoft Teams? (Not in MVP.) |
| U6 | Time to retain trip history after the plan year closes? |

## 9.11 Next steps

1. Business owner reviews documents 1 to 5 and answers B1 to B12, P1 to P5.
2. Follow-up meeting (the Thursday session proposed at the kickoff) to walk through the calendar views.
3. Receive the user list and the prompt used in Copilot for the first calendar visualization (offered at the meeting).
4. After sign-off: start Phase 0.
