# 4. Travel Rules

Source: *Traveling Calendar template*, sheets **Events description** and **Position rules**,
plus the meeting transcript and the *Travel Plans* sheet of the 2027 workbook.
Everything below is the **starting configuration**; the administrator edits it in the app.

## 4.1 Concepts

An **event type** defines a kind of trip. Each has:

- **organizer position** (who typically travels or hosts) and **visited unit** (who is visited);
- **participation per position**: not involved / participates / participates with a yearly limit (for example "3x");
- **cadence**: a recurring rule such as "every 2 months per cluster";
- **limits**: minimum and maximum number of trips per period (week, month, quarter, half-year, year), per person or per organization unit;
- **scheduling strategy**: free-text guidance plus machine-readable constraints (blackouts, rotation, preferred months);
- **joint visit** mode: *none*, *partial*, or *yes* (other functions join the same trip);
- **typical length and transport mode**, used later for cost forecasting.

## 4.2 Event catalog (initial)

Codes are proposed; the source sheet defines only some of them.

| Code | Event | Organizer → visited | Cadence (from source) | Annual volume | Joint visit | Notes |
|------|-------|---------------------|-----------------------|---------------|-------------|-------|
| `AM-FSV-VISIT` | Area Visit | AM → FSV | Monthly or bi-monthly | 6–12× per cluster | No | 1–2 days of 1:1 meetings with supervisors |
| `AM-FSV-MEET` | Area Management Meeting | AM → FSV | Bi-monthly | 6× per cluster | Partial | Team meeting; **not** in the month of the conference or year-end party. Participants: AM, RM, Quality, Training |
| `RM-AM-VISIT` | Region Visit | RM → AM | Quarterly | — | — | 1–2 days 1:1 with AM; Head may join (2×/year); pair with 1–2 area spot checks |
| `RM-AM-MEET` | Region Management Meeting | RM → AM | Every 4 months | 3× per cluster (~12–15 per region) | Partial | Rotate through 4–5 areas per region each quarter (1–2 per month); **not** in conference or year-end party months. Head 3×/year, Legal participates |
| `LAKBAY` | Collection Lakbay Regional Visit | RM + AMs of one region | 3× per year | 3 unique areas per year | Yes | New; **merged** with Area Meeting and Region Management Meeting. Not for nationwide scope. Head 3×/year; all functions participate |
| `CONF` | Collection Conference | Nationwide | Yearly | 1 | Yes | Planned as 2-day event (1 night); participants: AM, RM, Head 1×, coordinators, Legal, Quality, Training, HR, HoC Support |
| `YEAR-END` | Year-End / Kick-Off Party | AM → supervisors | Yearly | 1× per cluster | Partial | In November, December or January. Head 3×/year, Training 1–2× |
| `FLCU` | Field Leader's Collections University | Training Manager, TQACE Manager → RM, AM, FSV | Semi-annual (H1, H2) | 2× per cluster (28 sessions) | Yes | Run in Q1/Q2 and Q3/Q4; cluster by region where possible |
| `TQACE-AWARE` | TQACE Awareness Campaign | Local training → FSV | — | — | Yes | Quality and Training |
| `NEGOTIATION-P3` | Phase 3: Negotiation Skills Training | Local training | — | — | Yes | Training |
| `COURT-VISIT` | Court Visit | Legal Ops Manager, Head of Legal → courts | — | — | — | Legal |
| `COURT-HEARING` | Court Filing / Hearing | Legal Specialist, FSV | — | — | — | Legal |
| `HEAD-AREA` | Head of Field area tour ("Meet with FSV") | Head → all areas | Annual, grouped into trips | Every local office once a year | — | From *Travel Plans*: grouped legs (for example Mindanao in two legs of 3D/2N, North Luzon in a 4D/3N trip) |
| `REGIONAL-FIELD-MEET` | Regional Field Meeting | Head, RMs, AMs, coordinators | Quarterly | 1 per region per quarter | — | From *Traveling Plan Budget 2027* and *Travel Plans* |
| `LO-VISIT` | Local office visit | FSV → local office | BTO schedule | — | — | Transportation cost, not a business trip (budget sheet) |

## 4.3 Position rules

From the *Position rules* sheet:

| Function | Primary cadence | Synchronization |
|----------|-----------------|-----------------|
| Area Managers | Every month | Occasionally with Quality or Legal |
| Quality Specialists | Every 6–8 weeks | Join new-supervisor coaching or audits |
| Legal Operations Manager | Monthly for high-volume regions | Join Operations for legal strategy reviews |
| Training Manager | Quarterly or during major process changes | Combine with Operations and Quality |
| WFM / Planning Manager | As needed for launches or staffing reviews | Usually independent |
| Senior Operations Director | Quarterly strategic visits | Meet all local managers together for regional reviews |
| Head of Nationwide Field | Once a month (see also *Open questions*) | — |

Per-person caps and special rules:

1. **A Regional Manager can have two business trips a month.**
2. **The Head of Field travels about once a month, ideally never more than once**, with exceptions.
3. **If an RM or the Head visits an area, the visit is merged with the "Area Management Meeting".** (Merge rule.)
4. **If a Lakbay visit is organized, it is merged with the Area Meeting and the Region Management Meeting.** (Merge rule.)

## 4.4 Rule types the application must support

| Rule type | Meaning | Example |
|-----------|---------|---------|
| **Cadence** | Generate one trip every *N* months/weeks per unit or person | AM-FSV-MEET every 2 months per cluster |
| **Annual quota** | Exactly/at least/at most *N* trips per year per unit | LAKBAY: 3 per year per region, in 3 different clusters |
| **Participation cap** | Maximum trips per year for a position in an event type | Head at RM-AM-MEET: max 3 per year |
| **Period cap** | Maximum trips per week, month or quarter per person or unit | RM: max 2 trips per month; Head: max 1 per month |
| **Blackout** | Event type not allowed in given dates | No AM-FSV-MEET or RM-AM-MEET in the conference month or year-end party month |
| **Preferred window** | Generator prefers these months or weeks | YEAR-END in Nov, Dec or Jan; FLCU in Q1/Q2 and Q3/Q4 |
| **Rotation** | Spread over units with no repetition until all are covered | RM-AM-MEET rotates 4–5 areas per quarter |
| **Merge** | Two event types on one trip | RM visit to an area merges with that area's meeting |
| **Satisfaction** | One event counts as another for quota purposes | The conference counts as the weekly Head–RM touchpoint that week |
| **Concurrency cap** | At most *N* trips in the same unit/week (to avoid overload) | Maximum 2 area visits per week nationally *(to be confirmed)* |

**Events that are not held every year.** A yearly quota or a cadence can carry a year schedule: *held every N years, first in year Y* (stored in the rule's `params` as `every_n_years` and `first_year`).
With *every 2 years, first in 2027* the event is planned in 2027, 2029, 2031 and so on, and left out of 2028 and 2030 (the plan report says "not held in 2028"). The quota or cadence then describes
one held year, and the quota checks are not applied in the other years. Use it for the biennial conference, or for an off-year strategic meeting by starting it one year later
(for example every 2 years, first in 2028). A blackout period that belongs to such an event is simply defined only in the years it is held. Year schedules need the plan years to exist (see [Planning workflow](05-planning-workflow.md#51-lifecycle-of-a-plan-year)).

Each rule has a **severity**: `block` (cannot be saved), `warn` (needs acknowledgment and a reason), or `info`.
The transcript asks explicitly for a pop-up when a user exceeds a frequency limit, so the default for period
and quota caps is `warn`; blackouts default to `warn` too, because the business wants flexibility with a
recorded reason rather than a rigid platform.

**How the generator reads the catalog** (details in [Planning workflow](05-planning-workflow.md#52-generating-the-plan)): the number of trips per place comes from the cadence,
limited by the quota; a position with a yearly limit joins only that often; a field manager above the organizer joins only through a limit or a combined event; a position marked
*does not travel* is a host; an event combined with another is held together with the more important one.

## 4.5 Rule versioning

- Rules are versioned and valid from a date; editing a rule creates a new version.
- Plans reference the rule version that generated each trip, so past plans stay explainable.
- Changing a rule never silently rewrites trips that were manually edited or already requested.

## 4.6 Travel guidelines (from the standardization meeting)

These apply to every trip and drive the data we collect and the warnings we show.
No final entitlement rules were agreed, so they stay *informational* in the MVP.

| Guideline | Effect in the app |
|-----------|-------------------|
| Every request needs a detailed itinerary | Trip has itinerary legs; "itinerary complete" flag (Phase 2) |
| Return on the same day where practical | Warning when a trip has nights but the destination is within a configurable same-day radius (Phase 2) |
| Requests at least 3 days before travel | Lead-time warning, with an "urgent request" path (Phase 2) |
| Approve as early as possible | The yearly plan supports advance approval; approval status tracked (Phase 2) |
| Baggage based on actual need | Trip attribute "baggage needed" (Phase 2) |
| Entitlements (airfare, hotel, laundry, insurance, cash advance) undecided | Out of scope; cost rates are configurable placeholders |
| Cash advance vs. Grab codes undecided | Out of scope |

## 4.7 The catalog in the application (Phase 1)

The catalog described in this chapter is loaded as the **starting configuration** by migration `0003_event_catalog_seed.sql`:
15 event types, who takes part in each (with the "2x" and "3x" limits), 19 rules, 5 merge rules, and tentative 2027 blackout periods.
Everything is editable in the app (**Events and rules**, administrators only; everyone with access can read it).

**What an administrator can change**

- *Event type:* name, description, organizer, who is visited, whether others join, typical length and transport, planning notes, company event, active.
- *Who takes part:* a table of positions with *takes part*, *organizer* and *yearly limit*.
- *Combined with:* which other events it is merged into when both happen in the same place.
- *Rules per event* and *limits for all events* (for example the number of trips per month for a position).
- *Blackout periods* per plan year, for all events or selected ones.

**Rule kinds in the editor:** yearly quota, cadence (both with an optional *Which years* setting: every N years from a first year), preferred months, rotation, limit for a position (yearly limit), trip limit per person or
position, and a limit on events at the same time. Each rule is shown as one readable sentence (for example "6 to 12 per year for each cluster.")
and carries a **severity**: *Info* (a note), *Warn* (confirmation and a reason), *Block* (cannot be saved).

**Versioning.** Editing a rule never rewrites it: the old version is retired (kept for history) and a new version is created. Removing a rule retires it.
Every change to the catalog is written to the audit log (event type or rule key and counts, no personal data).

**Checks.** The server refuses incomplete or contradictory rules with a plain-English message (for example "Enter a minimum, a maximum, or both.").
Blackout dates must fall in the plan year, and a closed plan year cannot be changed. Codes of event types are unique.

**Decisions made while loading the starting catalog** (please confirm; see [open questions](09-open-questions.md#94-catalog-assumptions)):

- The two blackout months (April and December 2027) are placeholders taken from the 2027 Travel Plans. The rule "not in the month of the conference or year-end party" is expressed as blackout periods rather than as a rule that depends on other events.
- The Head of Field limit of one trip a month is seeded as a *warning*, although the source also lists many more trips for the Head.
- No weekly cap on area visits was seeded: the meeting asked for one but nobody gave a number.
- Functions outside field collections (Coordinator, Legal, Quality, Training, HR, Head of Collections/Support) exist as positions so they can be listed as participants. Their own cadence rules (for example Quality every 6 to 8 weeks) come in Phase 3.
