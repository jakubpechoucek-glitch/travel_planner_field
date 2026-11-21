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

The first plan year is **2027**. Source: "Use travel plans submitted with the annual budget as the baseline reference."

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

## 5.7 Cost forecast (Phase 2)

The Budget sheet shows the logic to reproduce: *trips × (airfare + hotel nights × rate + local transport + per diem × days)*,
with different unit prices for land versus air or sea. The model stores **cost rates** by position and transport mode,
and the app forecasts cost per trip, per month and per region, comparing it with the annual budget lines. The forecast also
shows the effect of **booking earlier** (a configurable lead-time discount factor) to help justify early approval.

## 5.8 In-app help

Every screen has a **Help** panel and contextual tooltips in American English, covering:

- what the screen shows and who sees it;
- how to add, move, merge or cancel a trip, and why a reason is required;
- what each warning means and what to do about it;
- a short glossary and a "Getting started" tour on first sign-in.

Help content is stored as Markdown in the repository (`docs/user-guide/`, later) and rendered inside the app.
