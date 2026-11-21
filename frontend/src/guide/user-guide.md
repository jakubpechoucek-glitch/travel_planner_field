Plan field travel early, together, and at lower cost. This guide explains every function of the application, role by role: what you can see, what you can do, and how to do it.

# 1. What the application does

Travel Planner helps Field Collections teams meet in person without spending more than necessary. Instead of every manager planning trips alone, the application builds **one shared yearly plan** from clear rules, lets managers adjust it, and shows what it will cost.

## 1.1 The idea in five steps

1. **Rules are defined once.** Administrators describe event types (area visit, region meeting, conference and so on) with who takes part, how often, and when they must not happen.
2. **The plan is generated.** The application proposes trips for the whole year from the organization and the rules. Trips that can be combined are combined.
3. **Managers adjust it.** Every change to a generated trip needs a reason, and the application shows right away whether the change breaks a rule.
4. **The plan is published.** Everybody sees their own trips in My plan and can add them to their calendar.
5. **Cost follows the plan.** The estimate uses the budget's own formula and is compared with the budget.

![Figure 1. The Home page of a planner: next trip, key figures and setup progress.](home)

## 1.2 Words used in this guide

| Term | Meaning |
|---|---|
| **Event type** | A kind of trip or meeting, for example Area Visit or Region Management Meeting. The list is called the event catalog. |
| **Rule** | A limit or preference of an event type: how often, how many per person, preferred months, rotation and so on. Rules have a severity: info, warning or block. |
| **Trip** | One planned occurrence of an event: dates, place, organizer, travelers and hosts. |
| **Traveler / host** | A traveler leaves home for the trip and creates cost. A host is visited (for example a supervisor in a visited area) and creates no travel cost. |
| **Combined trip** | Two events of the same place that were joined into one bigger trip. The smaller one stays visible as a combined (cancelled) row with the reason. |
| **Blackout period** | Dates where certain event types should not take place, for example the conference month. |
| **Plan year status** | Draft, Review, Published or Closed (see section 5.2). |
| **Scope** | The part of the organization a role applies to: everything, a region or a cluster. |
| **Person-trip** | One person on one trip. Costs and budgets are counted in person-trips. |

# 2. Roles at a glance

Every person has a role in the application. Roles are assigned by an administrator and some have a scope. Most people only need **My plan**.

| Role | Typical person | Scope | Main pages |
|---|---|---|---|
| **Viewer** (no special role) | Field supervisor | Self | Home, My plan, Events and rules |
| **Area planner** | Area Manager | Own cluster(s) | Plan (own cluster), My plan, Events and rules |
| **Regional planner** | Regional Manager | Own region(s) | Plan (own region), Costs (own region), My plan, Events and rules |
| **National planner** | Head of Field | All Field Collections | All pages except Users; generate and publish the plan; budget |
| **Administrator** | Business owner of the tool | Everything | All pages including Users; rules, rates and imports |
| **Function planner / Coordinator** | Training, Quality, Legal leads; travel desk contact | Selected | Home, My plan, Events and rules (planning pages for these roles arrive in a later phase) |

## 2.1 Function matrix

**Yes** = can do, **own** = within the person's own scope, **view** = read only, **–** = not available.

| Function | Viewer | Area | Regional | National | Admin |
|---|---|---|---|---|---|
| See own trips (My plan), calendar file | Yes | Yes | Yes | Yes | Yes |
| Read events and rules | View | View | View | View | Edit |
| See plan (timeline, heatmap, trip list) | – | Own | Own | Yes | Yes |
| Change, cancel, confirm trips; add a trip | – | Own | Own | Yes | Yes |
| Change nationwide events | – | – | – | Yes | Yes |
| Run plan checks (rule warnings for the whole plan) | – | – | – | Yes | Yes |
| Generate the plan | – | – | – | Yes | Yes |
| Publish, withdraw, close the plan | – | – | – | Yes | Yes |
| Export the plan to Excel | – | Own | Own | Yes | Yes |
| See cost estimate | – | – | Own | Yes | Yes |
| See budget comparison | – | – | – | Yes | Yes |
| Edit rates, travel modes, early-booking tiers | – | – | – | – | Yes |
| Load the budget workbook | – | – | – | – | Yes |
| See Organization page | – | – | – | Yes | Yes |
| Import the organization | – | – | – | – | Yes |
| Edit event types, rules, blackouts | – | – | – | – | Yes |
| Manage users, roles and sign-ins | – | – | – | – | Yes |

# 3. Getting started

## 3.1 Signing in

In the company installation you sign in automatically through Databricks single sign-on: open the app from Databricks and you are in. In the trial installation you see a sign-in page: enter your work e-mail and the access code you were given.

> **Tip** Your e-mail address is never stored. The application keeps only a one-way code derived from it, and uses that code to recognize you.

If you see **You do not have access yet**, your sign-in worked but nobody has linked it to a person and a role. Ask the Field Collections travel administrator.

## 3.2 Finding your way

- The **sidebar** on the left lists the pages you may use. On a phone it becomes a bar at the top that you can scroll sideways.
- Your name and role are at the bottom of the sidebar; the arrow icon signs you out.
- Every page has a **Help** panel at the top (the question-mark bar). Open it for a short explanation of that page.
- The application follows your device's light or dark setting.

## 3.3 Home

Home is the landing page for planners and administrators (supervisors land on My plan). It shows:

- A **greeting** with the number of days to your next trip.
- **Key figures**: trips in the plan, estimated cost (and budget where you may see it) and the number of rule findings, each with a small chart by month.
- **Your next trips** with date, countdown and place.
- For administrators, **Setup progress**: organization loaded, events set, plan generated, plan published, costs estimated, with a button to jump to what is still open.
- **Quick links** to the pages you may use.

# 4. Guide by role

Each chapter lists what the role can do and walks through the typical tasks. Higher roles can do everything the roles before them can do, within their scope.

## 4.1 Field supervisor and other viewers

**Purpose:** know which trips you take part in, when, where, and why a trip changed.

![Figure 2. My plan: trips by month, a year strip and a card per trip.](myplan)

### What you can do

- See every trip you take part in: trips you **organize**, trips you **travel** on, and visits to your team where you are the **host**.
- See the **next trip** and the year at a glance on the colored **year strip**; the color shows the kind of event.
- Read the **status** of each trip: Proposed (planned by the rules, not yet confirmed), Confirmed, Done or Cancelled.
- See the **original date and the reason** whenever a trip was moved or changed.
- See **who else** is on a trip (button *Who is on this trip*).
- Download all your trips as a calendar file with **Add to my calendar** (Outlook, Google Calendar and phone calendars can open it).
- Read the event catalog on **Events and rules**.

### How to

1. Open **My plan**. Trips are grouped by month; earlier and cancelled trips are folded away under their own headings.
2. Select **Who is on this trip** on a card to see the people, their positions and who organizes.
3. Select **Add to my calendar**, open the downloaded file and confirm in your calendar program.
4. If you have several plan years, choose the year in the **Year** list.

> **Note** You see your trips once the plan is published. Until then the page says so. To change a trip, ask your area manager; supervisors cannot change the plan.

## 4.2 Area planner (Area Manager)

**Purpose:** plan and adjust the trips of your cluster, and keep them within the rules.

### What you can do

- Everything a supervisor can do (My plan, calendar file, Events and rules).
- Open **Plan** and see the timeline, the heatmap and the trip list of **your cluster** and its local offices. Nationwide events are visible but cannot be changed by you.
- **Change** a trip (dates, length, people, notes), **cancel** it, **confirm** it or mark it **done**. Every change needs a reason.
- **Add a trip** by hand in your cluster.
- Read the **history** of every trip: who changed what, when, and why.
- **Export** your part of the plan to Excel (without cost columns).

### Reading the plan

The **Plan** page has two views, switched at the top of the plan card:

- **Timeline**: one row per area, one bar per trip, colored by event family. Hatched bars are still proposed by the rules. Use **Year / Q1 to Q4** to zoom, click a legend entry to hide or show a family, hover a bar for details and click it to open the trip. A dashed red line marks today.
- **Heatmap by month**: rows are areas, columns are months and each cell is the number of trips. Darker blue means more trips. Click a cell to list its trips below.

![Figure 3. The timeline: each bar is a trip, colors are event families.](timeline)

![Figure 4. The heatmap by month; clicking a cell lists its trips.](heatmap)

### Changing a trip

1. Open the trip: click a bar in the timeline, or click a cell in the heatmap and then the trip title in the list.
2. Select **Change this trip**. You can move the dates, change the length, add or remove people, and edit the notes.
3. The panel shows the **effect on the plan** live: rule warnings that would appear or disappear, and clashes such as a person being on two trips at once.
4. Choose a **type of reason** and write the **reason for the change** (required). Warnings you accept must be acknowledged with a reason.
5. Save. The change appears in the trip's **History** and, for the people on the trip, in My plan.

### Other trip actions

| Action | What it does |
|---|---|
| **Confirm** | Moves a proposed trip to Confirmed. |
| **Mark as done** | Records that the trip took place. |
| **Cancel this trip** | Cancels the trip; a reason is required and shown to the people on it. |
| **Add a trip** | Creates a trip by hand: choose the event type, place, dates and people, and give a reason. It is marked *by hand* and survives later regeneration. |

> **Note** If another user changed the same trip while you were editing, the application tells you and asks you to reload before saving, so nobody overwrites someone else's change.

Plan-wide **Checks** (rule warnings for the whole plan) and **Generate plan** are available to national planners and administrators.

## 4.3 Regional planner (Regional Manager)

**Purpose:** the same as the area planner, for a whole region, plus the cost view.

- Everything an area planner can do, for **all clusters of your region(s)**.
- Open **Costs** to see the estimate for your region: total, by month, by place, by position and by mode of transport.
- Use the **early-booking what-if** to see what fares would cost if booked a number of days ahead (once the discount tiers are known).
- Export your region to Excel; cost columns are included for your scope.

### Using the cost page

1. Open **Costs**. The large figure is the estimated cost; the tiles show trips, person-trips and share of air or sea travel.
2. Read **By month** to see when spending peaks. Hover a column for the exact amount and number of trips.
3. Read **Where the money goes** (land, air, sea) and the ranked lists of places and positions.
4. In **Early booking**, type a number of days ahead to see the saving.

![Figure 5. The cost estimate with the plan-against-budget comparison.](costs)

> **Note** The cost is an estimate for planning, not a booking or approval. It counts people who travel (hosts have no travel cost). Cost = air or sea fare (only if the person must fly or sail) + local transport + hotel nights × rate + days × per diem.

## 4.4 National planner (Head of Field)

**Purpose:** own the whole plan, publish it, and watch it against the budget.

- Everything a regional planner can do, for **all regions**, including nationwide events.
- **Generate the plan** from the organization and the rules, with a preview first.
- Run the plan-wide **Checks**.
- **Publish** the plan, withdraw the publication, or close the year.
- See the **budget comparison** on Costs.
- Open the **Organization** page to see regions, clusters, leaders and head counts.

### Generating the plan

1. Open **Plan** and the **Generate plan** card. Select **Preview**. Nothing is saved yet.
2. Read the preview: trips created, trips combined, trips per event, events that could not be placed, events skipped because they have no quota or cadence, and rule warnings.
3. If it looks right, select **Apply plan**. Trips nobody has changed are rebuilt; trips changed or added by hand stay.
4. Open **Checks** below the plan to review warnings by type (trip limits per person, yearly limits, quotas, blackouts, overlaps).

### Publishing

1. When the plan is reviewed, select **Publish plan** and confirm. Everyone with a trip now sees it in My plan, and the plan can no longer be generated again.
2. **Withdraw publication** brings the plan back to review. Manual changes after publication stay possible and are marked as changes after publication.
3. **Close the year** makes the plan read-only for reporting.

### Excel export

**Export to Excel** downloads the plan you may see as a workbook: summary, trips, people, days away, changes and checks. Tick *Include cancelled and combined trips* to add them. Every export is recorded in the audit log.

## 4.5 Administrator

**Purpose:** set the application up, keep people and rules current, and run the plan year. Administrators have all the functions above plus the following.

### Organization

![Figure 6. The Organization page: regions, clusters, leaders and head counts.](org)

1. Open **Organization** and choose the planning workbook (.xlsx).
2. Select **Check** (preview). The result lists what would be created, plus information, warnings and errors in plain language. Nothing is saved.
3. Fix problems in the workbook if needed, then select the button to load it. Regions, clusters, local offices, people, reporting lines and positions are created with a valid-from date.

> **Note** Phone numbers, user names and e-mail addresses in the workbook are ignored and never stored.

### Users, sign-ins and roles

![Figure 7. The Users page.](users)

Giving someone access takes two steps on the person's page:

1. **Link the sign-in.** Type the person's work e-mail once. The server turns it into a one-way code, stores only that, and forgets the address. A typo means the person cannot sign in; link again to correct it.
2. **Add a role.** Choose the role and, for regional and area planners, the region or cluster it applies to.

### Faster for hundreds of people

- **Link many sign-ins at once:** paste lines of `e-mail, employee number` (or the full name). **Check** shows problems by line number; nothing is saved until every line is fine; **Link** saves. Addresses are not echoed back.
- **Suggested roles:** **Show suggestions** proposes national planner for the Head of Field, regional planner for each Regional Manager and area planner for each Area Manager. Existing roles stay.

### Changes over time

- **Add a person** who is not in the import (for example a new Training lead).
- Change **position, manager and place** with a *valid from* date. The previous assignment is kept as history.
- **Deactivate** a person who leaves (they can no longer sign in; history stays) and **Reactivate** if they return.
- Search and filter the list by name, employee number, role and sign-in status.

> **Note** The application always keeps at least one administrator who can sign in. Removing the last one, or deactivating yourself, is refused. We recommend at least two administrators.

### Events and rules

![Figure 8. Events and rules: the event list, participation and rules.](catalog)

Event types, rules, positions and blackout periods are data, not program code, so you change them here without a new release.

| Task | How |
|---|---|
| Add or edit an **event type** | Select **Add event type** or an event in the list, then *Edit*. Set name, short code, who organizes, which unit kind is visited, typical length and transport, and notes. |
| Define **who takes part** | In the event's participation list choose each position, whether it joins by default, whether it travels or is a host, and an optional yearly limit (for example Head of Field up to 3 times). |
| Add a **rule** | Select **Add rule**: kind of rule (cadence, annual quota, participation cap, period cap, preferred window, rotation, concurrency cap), scope, period, minimum and maximum, and what happens if it is broken (info, warning or block). Rules are versioned: saving creates a new version. |
| Set **merge rules** | Choose which smaller event is combined into which bigger one. |
| Add a **blackout period** | Select **Add blackout period**: dates, the event types it applies to (none = all), what happens if a trip falls in it, and optionally the event that is held in this period (for example the conference). |
| **Remove** a rule or blackout | Use **Remove**; the change is written to the audit log. |

### Costs: rates, modes and budget

Open **Costs → Rates and travel modes** (administrators only):

- **Rates:** unit prices by position (air fare, sea fare, hotel per night, per diem, local transport) with a valid-from date. Use **Set a rate** to enter a new rate, **End this rate** to stop one.
- **Where people are based** and **where nationwide events are held**: needed to decide who flies.
- **Travel modes between regions:** land, air or sea for each pair of regions; **Show suggestions** proposes them.
- **Places that need another mode:** exceptions from anywhere or from one region.
- **Early booking discounts:** tiers of *at least (days ahead)* and *cheaper by (%)*. Empty until the business enters real tiers; the application assumes none.
- **Budget:** upload the budget workbook, **Check**, then load it. Lines are matched to events; unmatched lines are listed.

### Plan year

Administrators can do everything a national planner does with the plan: generate, publish, withdraw, close.

## 4.6 Function planner and coordinator

These roles are meant for Training, Quality, Legal and travel-desk colleagues. In this version they can sign in, read **Events and rules**, and see **My plan** for trips they take part in. Planning pages for function trips, statuses, SAP references and itineraries are planned for later phases.

# 5. Feature reference

## 5.1 Pages and who sees them

| Page | Who | What it is for |
|---|---|---|
| **Home** | Everyone | Overview, next trips, key figures, setup progress, quick links |
| **My plan** | Everyone with a linked sign-in | Own trips, reasons for changes, calendar file |
| **Plan** | Area, regional, national planners, administrators | Timeline, heatmap, trip list, trip changes, checks, export; generate and publish for national planners and administrators |
| **Costs** | Regional, national planners, administrators | Estimate, budget comparison, early booking; rates and budget for administrators |
| **Events and rules** | Everyone (read), administrators (edit) | Event catalog, participation, rules, merge rules, blackouts |
| **Organization** | National planners, administrators | Regions, clusters, leaders, head counts; import for administrators |
| **Users** | Administrators | People, sign-in links, roles, assignments |

## 5.2 The life of a plan year

| Status | Who acts | What happens |
|---|---|---|
| **Draft** | Administrator | Organization and rules are loaded; blackout periods are defined. |
| **Review** | Planners | The generator creates proposed trips. Planners review, move, combine, add and cancel. |
| **Published** | National planner, administrator | The plan is the baseline. Everyone sees their trips. Later edits are flagged as changes after publication. |
| **Closed** | Administrator | The year is read-only and used for reporting. |

## 5.3 Trip statuses

| Status | Meaning |
|---|---|
| Proposed | Planned by the rules; nobody has confirmed it yet. |
| Confirmed | Agreed by a manager. |
| Requested / Approved | Used when travel requests are added in a later phase. |
| Done | The trip took place. |
| Cancelled | The trip will not take place, or it was combined into another trip. A reason is always shown. |

## 5.4 How the generator decides

The generator is deterministic: the same organization and rules always give the same plan.

- **How many trips:** from the event's cadence or yearly quota, per place (cluster, region, local office or nationwide). Events without quota or cadence are listed as not planned.
- **Order:** company events first, then wider scopes, then events with more participants.
- **When:** each trip goes into a Monday-to-Friday week. Weeks get penalties for being far from the ideal slot, inside a blackout, outside preferred months, too close to a similar trip, when a traveler is already away, when a person would exceed a trip limit, when the cluster is crowded, and for breaking rotation. Combining nearby trips earns a bonus. Blocked blackout weeks are never used.
- **Who:** the organizer holds the organizer position in the place (the leader acts if nobody does). Positions with a yearly limit are spread evenly over the year. A manager above the organizer joins only through a yearly limit or a combined event.
- **Combining:** if a combinable event of the same place is within a week and nobody is already away, the smaller one is absorbed into the bigger one and stays visible as a combined row.

## 5.5 Rule warnings

| Warning | Meaning |
|---|---|
| Trip limits per person | A person has more trips in a period than the limit allows. |
| Too few trips | A person has fewer trips than the minimum. |
| Yearly limit of an event | An event happens more or less often than its yearly limit for a position. |
| Too few / too many trips for a place | The place has fewer or more trips of an event than its quota. |
| Trips in blackout periods | A trip lies in a period where that event should not be held. |
| A person in two trips at once | Overlapping trips for one traveler. |

Severity levels: **info** (for your attention), **warning** (the plan may stay as it is when there is a reason) and **block** (the change is not allowed).

## 5.6 How cost is estimated

- Cost of a person-trip = fare (air or sea only) + local transport + nights × hotel rate + days × per diem.
- Rates depend on the traveler's position and have valid dates. The example in the help panel: an Area Manager flying for three days costs 20,000 + 2 × 3,000 + 2,500 + 3 × 600 = ₱30,300.
- Whether a person flies depends on where they are based and where the trip takes place (travel modes and exceptions).
- Hosts have no travel cost. If a base or place is unknown, the trip is counted as travel by land, and the page tells you how many person-trips are affected.
- The budget counts person-trips (people × frequency); the estimate counts the people who travel on the planned trips. Differences show where the plan and the budget assume different things.

# 6. Privacy and security

- **No e-mail addresses and no phone numbers are stored.** Users are matched by a one-way code derived from the e-mail with a secret key.
- E-mail addresses are never written to logs or to the audit log.
- Every change to a generated trip needs a reason and is kept in the trip history.
- Administrative actions (roles, rules, publication, imports, exports) are written to the audit log: who and what, not what was viewed.
- People see only what their role and scope allow. Cost is visible to administrators, national planners and regional planners (own region); the budget only to administrators and national planners.

# 7. Questions and answers

| Question | Answer |
|---|---|
| I cannot see my trips. | The plan is probably not published yet. My plan fills as soon as it is. |
| I see “You do not have access yet”. | Your sign-in is not linked to a person or has no role. Ask the administrator. |
| A trip was moved. Where is the reason? | On the trip's card in My plan, under *Originally planned for*, and in the trip history for planners. |
| Why can I not change a trip? | It is outside your cluster or region, or it is a nationwide event. Ask the planner responsible. |
| Why does the cost page not show a budget? | Only administrators and national planners see the budget, and it must be loaded first. |
| Why is an event missing from the generated plan? | It has no yearly quota or cadence rule, or the place does not have enough clusters for its rotation rule. The Generate preview lists these cases. |
| Can I undo a change? | Open the trip, change it back and give a reason. The history keeps every step. |
| How do I get the plan into Excel? | On Plan, select Export to Excel. |

For questions about access, contact the Field Collections travel administrator.

