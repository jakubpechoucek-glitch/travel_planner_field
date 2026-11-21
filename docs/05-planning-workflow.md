# 5. Planning Workflow

## 5.1 Lifecycle of a plan year

```
Draft ──generate──▶ Review ──publish──▶ Published ──close──▶ Closed
  ▲                    │                     │
  └──── regenerate ────┘                     └── manual edits continue, with reasons
```

| State | Who | What happens |
|-------|-----|--------------|
| **Draft** | Administrator | Org structure and rules are loaded; blackout periods defined |
| **Review** | Planners | The generator creates proposed trips; planners review, move, merge, add, delete |
| **Published** | Head of Field | The plan becomes the baseline; submitting travel requests is based on it. Edits remain possible but are flagged as *changes after publication* |
| **Closed** | Administrator | The year is read-only; used for reporting |

**Opening a plan year.** The first plan year is **2027**. Administrators and national planners open the next one with **Plan → Open plan year** (always the year after the last one, as an empty draft).
The year selector at the top of Home, Plan and Costs switches between plan years. Events held only every second year (see [Travel rules](04-travel-rules.md#44-rule-types-the-application-must-support)) are planned only in their years;
in the other years the generator lists them as *not held in that year* and raises no quota warning for them.

The first plan year is **2027**. Source: "Use travel plans submitted with the annual budget as the baseline reference."

**Publishing.** Administrators and national planners publish a reviewed plan (**Plan → Publish plan**, asks for confirmation). From then on everybody sees their own trips in
[My plan](02-users-roles-access.md#24-views-per-role) and the plan cannot be generated again; manual changes remain possible and are marked "after publication". The publication can be
withdrawn (back to review) and the year can be closed (read-only). A plan without trips cannot be published; a draft must be generated first. Every status change is in the audit log.

## 5.2 Generating the plan

Implemented in `backend/travel_planner/plan_engine.py` (pure logic, no database) and `plan_store.py` (loading and saving).
Who can run it: administrators and national planners (**Plan → Generate plan**, or `POST /api/admin/plan/{year}/generate`).

**Input:** the organization (regions, clusters, leaders, people), the active event types with their participation and rules, the merge
rules, and the blackout periods of the plan year. **Output:** trips with dates, a visited place, travelers and hosts.

**Steps**

1. **How many trips.** For each event type with a yearly quota or a cadence: `trips per place = cadence per year`
   (for example every 2 months gives 6), limited to the quota's minimum and maximum. Places are the clusters, regions, local offices or the
   whole country, depending on the rule's scope. Events without a quota or cadence (for example Court Visit) are listed as *not planned*.
2. **Order.** Company events first, then wider scope (nationwide, region, cluster, local office), then events with more participants.
3. **Placing.** Each trip goes into a calendar week (Monday to Friday, inside the year). Every week gets a penalty and the lowest wins; ties go to the
   earlier week, so the same inputs always give the same plan.

   | Penalty | Meaning |
   |---------|---------|
   | Distance | Weeks away from the ideal slot (places are staggered so they do not all fall in the same week) |
   | Blackout | Inside a *warn* blackout: very high. Inside a *block* blackout: never used |
   | Preferred months | Outside the months of a "preferred months" rule |
   | Spacing | Same event and place within 3 weeks of another |
   | Traveler away | A traveler is already on another trip that week (the heaviest everyday penalty) |
   | Trip limits | A traveler would exceed a trip limit per person and period (for example 2 per month for a Regional Manager) |
   | Crowded cluster | Other trips in the same cluster that week |
   | Rotation | More trips of the event in a region and quarter than the rotation rule allows |
   | Combining | A bonus when a combinable bigger trip of the same place is within a week |

   An event that is *caused by* a blackout (the conference in its month) is placed only inside that period.
4. **Who takes part.** The organizer is whoever holds the organizer position in the place; when nobody does, the place's leader acts
   (the Regional Manager in a cluster without an Area Manager). Other positions join by default, except:
   - positions with a **yearly limit** ("Head of Field up to 3 times") are assigned afterwards, spread evenly over the year, preferring weeks without a clash and months within the trip limits;
   - a **field manager above the organizer** (for example the Regional Manager at an area meeting) does not join by default; they join only through a yearly limit or when another event is combined into the trip.
   Positions marked *does not travel* are hosts (for example the supervisors at an area visit).
5. **Combining.** If a trip meets a combinable event (merge rule) of the same place within a week, and nobody joining is already away, the *less important* one is
   absorbed: it stays in the plan as a *merged* row (status cancelled, with a link and the reason "Combined with ...") and its people join the bigger trip.
   The bigger trip is chosen by importance (company event, then scope, then number of participating positions); if two events are equally important they are not combined and the
   result says so.
6. **Checks.** The same `evaluate` function that checks manual edits reports: trip limits per person, yearly limits, quotas per place (too few or too many),
   blackouts, and a person in two trips at once. Merged trips still count toward the quotas.

**Preview and saving.** A preview runs the whole generation inside a transaction and rolls it back, so the numbers are exact.
Saving replaces **untouched generated trips** (and the merged rows they absorbed) and keeps everything else: trips that were edited (any change except
`created`/`generated` in the history), added by hand, requested, approved or completed. Kept trips are counted toward the quotas and keep their people
and weeks busy, so regenerating never duplicates them. The plan year must be in *draft* or *review*; generating moves *draft* to *review*.

**Known limits** (see [open questions](09-open-questions.md#95-generator-findings))

- Working days only; public holidays are not known yet.
- One trip has one visited place. Multi-stop tours (the "T1 / L1" legs of the Head's area tour) are not grouped yet.
- Concurrency limits ("at most N at once") are stored but not yet used by the generator or the checks.
- Training, Quality and Legal people are not in the organization import yet, so those positions appear in rules but not on trips.
- Visibility of the plan is limited to administrators and national planners until scoped views for regional and area managers are built.

## 5.3 Manual changes and reasons

Implemented in `backend/travel_planner/trip_edit.py` and the **Plan** page (open a trip, then *Change this trip*, *Cancel this trip*, *Confirm*, *Mark as done*; *Add a trip* for a trip the rules did not plan).

**What can be changed:** dates (a move keeps the length, otherwise it is recorded as a resize), notes and title, the people (add or remove), cancelling, adding a trip by hand.
Confirming a generated trip ("this is going to happen") and marking a trip as done are status changes; they are not deviations, so the app supplies the reason ("Confirmed by planner.", "Marked as done.").
A trip can be marked as done once it has started.

**The rules of a change**

1. **A reason is mandatory** (at least 3 characters) for every change, including cancelling and adding a trip, plus a type: business request, conflict with a company event, combined with another trip, capacity, budget, other.
   The database refuses a history row without a reason.
2. **The effect is shown before saving.** The change is applied inside a transaction, the whole plan is checked again, and the *new* warnings are returned (and how many existing warnings the change resolves). A preview rolls back.
3. **Warnings need an acknowledgement.** A rule with severity *warn* must be confirmed ("I understand these warnings and want to continue"); the acknowledgement is stored (`warning_ack`) with the reason. A rule with severity *block* refuses the change.
4. **No lost updates.** Each trip carries an `updated_at` token. If someone else changed the trip in the meantime, the change is refused with a clear message.
5. **History.** Every change is a `trip_change` row: who, when, kind (moved, resized, reassigned, edited, status, cancelled, created), reason, type, and before and after values. The rule-based dates are kept (`generated_start_date`, `generated_end_date`) so the app can show "Planned by the rules for ...".
6. **Scope.** Administrators and national planners change everything. A regional planner changes trips in the units under their region; an area planner those of their cluster and its local offices. Nationwide trips are visible to every planner but changed only by administrators and national planners. A trip outside your scope appears as not found.
7. **States.** Generated, confirmed (`planned`), requested and approved trips can be changed; done, cancelled and trips of a closed plan year cannot. A change after the plan was published is marked "after publication" in the history.
8. **Regeneration respects it.** Any trip with a history row other than *created* or *generated*, every confirmed trip and every trip added by hand is kept when the plan is generated again, and it counts toward the quotas.

Cancelling or adding a trip changes the quota of its place, so the app tells you ("Area Management Meeting, Alpha 2: 5 planned, at least 6 expected."). Cancelling a trip that includes a combined trip means the combined trip no longer takes place, and its quota effect is shown too.

**Not yet built:** splitting a combined trip back into two trips, undoing a change, approval of a change by a manager, notifications, and changes made by travelers themselves.

## 5.4 Warnings and compliance

The app evaluates rules whenever a trip is created or changed, and in the compliance dashboard.

| Warning | Example message |
|---------|-----------------|
| Period cap exceeded | "This is Alex's third trip in March. The limit for Regional Managers is 2 per month." |
| Quota exceeded or missed | "Cluster South Luzon 2 has 5 of 6 planned area meetings." |
| Blackout | "Area meetings should not take place in the conference month." |
| Overlap | "Maria is also scheduled for a trip from March 3 to 5." |
| Merge available | "An RM visit to this cluster is planned the same week. Merge with the area meeting?" |
| Lead time (Phase 2) | "Travel starts in 2 days; requests should be submitted at least 3 days in advance." |

For a `warn` rule the planner must tick **"I understand"** and enter a reason before saving; the acknowledgment
is stored with the trip. Compliance views show both *under-use* (below minimum) and *over-use* (above maximum)
per region, cluster and person, so management can see "which teams are not using the travel and which are over-using it".

## 5.5 Synergy suggestions

The app proposes, but never forces:

- **Same destination, close dates.** Two trips to the same local office within 14 days (configurable): suggest combining or extending one stay instead of a second trip.
- **Same traveler, back-to-back.** Suggest one itinerary with several legs.
- **Joint trips.** Training, Quality or Legal trips to a cluster where an AM already travels: suggest joining.
- **Conflict with company events.** A trip scheduled in a conference or party week.

Suggestions appear in the *Synergies* view and as hints on the trip form. Accepting a suggestion is a normal
manual change and records its reason automatically.

## 5.6 Trip status

| Status | Meaning |
|--------|---------|
| `generated` | Proposed by the rules; untouched |
| `planned` | Confirmed by a planner (manually created or accepted) |
| `requested` | Submitted by the traveler in SAP; the SAP request number is stored (Phase 2) |
| `approved` | Approved (Phase 2) |
| `completed` | The traveler or planner marked the trip as done; optional outcome notes (Phase 2: documents) |
| `cancelled` | Not happening; reason required |

In the MVP, planners work with `generated`, `planned`, `completed` and `cancelled`. The request and
approval states are included in the model so Phase 2 does not need a migration of existing data.

## 5.7 Cost forecast

Implemented in `backend/travel_planner/cost_engine.py` (pure logic), `cost_store.py` (database) and the **Costs** page. Visible to administrators, national planners and regional planners
(for their own region); administrators maintain the rates.

**Currency.** Every amount in the application is in **Philippine pesos (PHP, ₱)**. There is no second currency and no conversion; the database refuses any other currency code and the API refuses a currency field on a rate.
Excel shows amounts with the peso sign.

**The model is the budget's own formula.** For every person who *travels* on a planned trip (hosts, who are visited, cost nothing):

> cost = fare (air or sea, only if the person has to fly or sail) + local transport + nights × hotel per night + days × per diem

with *days* from the start to the end date and *nights* = days − 1. The starting rates come from the formulas of the 2027 budget ("Per Budget Travelling (FC)"):
air fare ₱20,000 (round trip), local transport ₱2,500, hotel ₱3,000 a night (₱5,000 for the Head of Field), per diem ₱600. They reproduce the budget's unit prices, for example
an Area Manager flying for three days: 20,000 + 2 × 3,000 + 2,500 + 3 × 600 = ₱30,300; by land: 6,000 + 2,500 + 1,800 = ₱10,300; the Head of Field flying for three days: ₱34,300.

**Does the person fly?** It depends on where they are based and where the trip takes place:

1. A *place override* (an island or a remote place that needs a flight, from anywhere or from one region) wins.
2. Otherwise the *travel modes between regions* table decides (rows: where the person is based; columns: the region of the trip). Inside a region people go by land unless the table says otherwise.
3. A person is based in the region of their assignment, or of their local office; the Head of Field in the configured *head office region*. Nationwide events are held in the configured *venue region*.
4. Anything unknown is counted as by land and **reported** ("for N person-trips the home or the place is unknown").

The application loads *suggested* modes (land inside a region and between NCR, North Luzon and South Luzon, air otherwise) on request; the business must confirm them.

**Rates** have valid-from dates: a new rate from a date ends the one it replaces, so earlier trips keep their price. A rate for a position beats the general one. A missing rate is counted as zero and
reported, never hidden.

**What the page shows:** the total, trips and person-trips, the average per person-trip and the share by air or sea; cost by month; cost by event, place and position; the assumptions and what is missing.

**Plan against the budget.** The budget workbook is loaded on the same page (administrators): each line (event, position, count, frequency, unit price, annual cost) is matched to an event of the catalog
(automatically by name, and by hand where it cannot be matched) and compared per event: budget cost and person-trips (count × frequency) against the estimate and the person-trips of the plan.

**Early booking.** Booking early makes air and sea fares cheaper, but the discounts are **not assumed**: the business enters tiers ("booked at least 60 days ahead: 20% off"). With tiers the page shows
today's fares, the fares if every one were booked N days ahead, and the saving. Without tiers the saving is zero and the page asks for the numbers.

**Not included:** baggage fees, travel insurance, laundry, cash advances, incentive trips and anything outside field collections; fares by route or date; changes after booking. These can be added as rates or lines.

## 5.8 In-app help

Every screen has a **Help** panel and contextual tooltips in American English, covering:

- what the screen shows and who sees it;
- how to add, move, merge or cancel a trip, and why a reason is required;
- what each warning means and what to do about it;
- a short glossary and a "Getting started" tour on first sign-in.

Help content is stored as Markdown in the repository (`docs/user-guide/`, later) and rendered inside the app.

## 5.9 Excel export

**Plan → Export to Excel** (or `GET /api/plan/{year}/export.xlsx`) downloads the plan as a workbook for planning meetings, budget work and approvals
(`backend/travel_planner/plan_export.py`). It is a snapshot with values, not formulas.

| Sheet | Content |
|-------|---------|
| About | What the file contains, plan status, export time, and what is left out |
| Summary | Trips per month by place (a heatmap) with totals; trips by event with the number merged into bigger trips and the days away |
| Trips | One row per trip: event, region, cluster, local office, start, end, days, nights, status, source (rules or by hand), organizer, number of travelers and hosts, transport, the dates by the rules and whether the trip was moved, last reason, combined events, notes, SAP request |
| People on trips | One row per person per trip: role (organizer, traveler, host), whether they travel, days away and nights |
| Per person | Trips, days away, nights and trips per month for every person who travels, with a heat scale |
| Changes | Every manual change: when, who, kind, type of reason and the reason |
| Checks | The rule warnings of the saved plan (only for people who see the whole plan) |

**Rules of the export**

- It follows your **scope**: a regional or area planner gets the trips of their own area plus the nationwide events. People outside the area are named only on trips in the area, never on nationwide trips, and are left out of *Per person*.
- *Include cancelled and combined trips* adds those rows, with the status "Cancelled" or "Combined into another trip" and the reason.
- All text is written as text, so a note that starts with "=" can never run as a formula. No e-mail addresses or phone numbers are in the file (the database does not have them).
- Dates are real Excel dates; days are calendar days from start to end, nights are days minus one.
- Every export is recorded in the audit log (who, how many trips, whole plan or an area). The file contains names, so please treat it as internal.

