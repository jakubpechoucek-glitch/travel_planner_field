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

Input: the organization structure valid in the plan year, event types, rules, blackout periods.

Steps:

1. **Expand** each cadence/quota rule into candidate trips per unit or person (for example, 6 area meetings for each of 12 clusters).
2. **Place blackouts** (conference month, year-end party month) and fixed events first (conference, year-end party).
3. **Place regional events** (Lakbay, region meetings) with rotation.
4. **Place recurring events** (area visits and meetings) on preferred weeks, spreading load so that no unit or person exceeds its caps.
5. **Merge** trips according to merge rules (visit by RM → area meeting).
6. **Choose destinations:** local office of the visited unit, or the location named in the rule.
7. **Mark each trip** as `source = generated`, store the rule version, and compute rule warnings.

The generator is **deterministic** for a given input and seed, and idempotent: regenerating keeps trips that
were manually edited, confirmed, requested or approved, and replaces only untouched generated trips.

Granularity: trips have exact dates, but the generator plans by **week** (for example, "week 14") for the first six months and by
**month** for the second half. The planner can fix exact dates at any time. *(To be confirmed with the business.)*

## 5.3 Manual changes and reasons

Every trip can be moved, resized, reassigned, merged, split, cancelled, or added from scratch.

- **Edits to a generated trip require a reason** (free text, plus an optional category such as *business request*, *conference conflict*, *merged with another trip*, *capacity*, *other*).
- **Manually added trips** require a purpose (event type) and recommend a reason when they fall outside the rule plan.
- The original generated values are kept, so the UI can show *planned by rule* versus *current*.
- The change history (who, when, what, why) is visible on the trip and written to the audit log.

This directly implements the requirement that "anyone who is not aware of this exception would know and understand why this is happening".

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
