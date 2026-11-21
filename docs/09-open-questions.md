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

## 9.4 Product and design

| # | Question |
|---|----------|
| U1 | One calendar per audience (Region managers, field, travel desk) or one view with filters? |
| U2 | Should planners edit with drag-and-drop on the timeline, a form, or both? (Proposed: both.) |
| U3 | Is a mobile view needed, or desktop only? |
| U4 | Corporate branding: logo, colors, fonts? |
| U5 | Notifications: e-mail only, or also Microsoft Teams? (Not in MVP.) |
| U6 | Time to retain trip history after the plan year closes? |

## 9.5 Next steps

1. Business owner reviews documents 1 to 5 and answers B1 to B12, P1 to P5.
2. Follow-up meeting (the Thursday session proposed at the kickoff) to walk through the calendar views.
3. Receive the user list and the prompt used in Copilot for the first calendar visualization (offered at the meeting).
4. After sign-off: start Phase 0.
