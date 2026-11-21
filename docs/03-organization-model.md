# 3. Organization Model

This chapter describes the structure found in the source spreadsheets
(sheets *EMP LIST FC upload*, *Emp Tables*, *Reference*, *Position*). Names of
individuals are deliberately omitted; they are loaded from the employee file at import time.

## 3.1 Reporting line (who visits whom)

```
Head of Nationwide Field
 └─ Regional Manager (RM)            3 people
     └─ Area Manager (AM)            11 people + 1 acting (Cebu)
         └─ Field Supervisor (FSV)   ~123 people (FSV, Senior FSV, FSV II)
             └─ Field collectors (FTEs, ~3,900)   — not travelers; counted for capacity only
```

Supporting functions sit next to this line and visit it: Training (TQACE), Quality,
Legal Collections, Field Coordination, HR. See the *Position* sheet for the full list
of 24 position/group values (including groups such as "Agency Trainers" and "Field QA team").

## 3.2 Geography

The structure used for travel planning is **region → cluster → local office**:

| Region | RM scope | Clusters | Local offices (supervisor hubs) |
|--------|----------|----------|---------------------------------|
| NCR | RM 1 | NCR Central, NCR South | Cubao |
| North Luzon | RM 1 | North Luzon 1, North Luzon 2 | Mexico, Cabanatuan, Cauayan, Urdaneta, Benguet, Vigan |
| South Luzon | RM 3 | South Luzon 1, 2, 3, 4 | Dasmarinas City, Lipa City, Legaspi City, Puerto Prinsesa |
| Visayas | RM 2 | Cebu, Visayas West | Cebu, Mandaue, Iloilo City, Bacolod City, Leyte |
| Mindanao | RM 2 | Mindanao 1, Mindanao 2 | Davao City, Cagayan De Oro, General Santos, Zamboanga |

Notes:

- One **AM manages one cluster**. An AM's supervisors are spread over several provinces
  that report to one local office (for example, cluster *South Luzon 2* covers Batangas,
  Cavite, Mindoro and Palawan, supervised from *Lipa City*).
- One RM can manage **two regions** (RM 1: NCR and North Luzon; RM 2: Visayas and Mindanao).
- **Local offices are travel hubs.** "Area" in the event catalog (for example "6 area meetings per area")
  refers to an AM's group of supervisors. Where the planning files say "area" for a city, they mean the local office.
  The app uses the explicit terms **cluster** and **local office** to avoid confusion.
- Some AMs run two groups of supervisors that do not meet together because of distance or size; the model
  therefore allows **more than one meeting group per AM** (see `meeting_group` in the [data model](06-data-model.md)).
- A **location** (city or province) is where a trip physically takes place. The *Reference* sheet maps provinces to local offices.

## 3.3 How the model handles change

The next year is expected to bring changes: a new layer between Head and Area, new events,
new frequencies, people leaving and joining. Therefore:

- Positions and organization units are **data**, not code; each has a *level* number used by rules.
- Reporting lines (`person.manager_id`) and unit assignments carry **effective dates**, so
  a plan for 2027 is generated from the structure valid in 2027.
- Rules refer to positions (and optionally to levels), never to named individuals.
- Restructuring is done by an administrator in the UI, not in the database.

## 3.4 Source-to-model mapping

| Source sheet / field | Target |
|----------------------|--------|
| EMP LIST FC upload: EMP NO, EMP NAME, USERNAME, POSITION | `person` (employee number, name, position); the login link is set later by an administrator |
| EMP LIST FC upload: AM | `person.manager_id` (supervisor → AM) |
| EMP LIST FC upload: REGION, AREA | `person.region_id`, `person.local_office_id` |
| EMP LIST FC upload: CRM | RM of the person's region (check against `manager_id` chain) |
| Emp Tables: RM TABLE / AM_TABLE / FSV TABLE | RM → cluster → AM assignments, `org_unit` rows of kind `cluster` |
| Reference LO from Sir Cy: Area, Province | `location` rows (province/city) with `local_office_id` |
| Position | `position` rows (code, name, level, whether the position travels) |
| FC Employee List: PRIMARY AREA, CAPACITY, COLLECTION TYPE, CONTACT NUMBER, EMAIL, ... | **Not imported** except a head count per local office (capacity). Contact numbers are never stored. |

The import is a one-time, repeatable admin action with a preview step and an error report
(unmatched managers, duplicate employee numbers, unknown positions).

## 3.5 The organization import (Phase 1)

Administrators load the structure from the planning workbook, in the app (**Organization → Import organization**) or with
`python -m travel_planner.orgimport workbook.xlsx [--apply] [--effective YYYY-MM-DD]` (see the [development guide](10-development.md)).

**What the workbook must contain**

- Sheet **Emp Tables** with side-by-side tables, each starting with an `EMP NAME` column and found by header names (not by cell address):
  1) Regional Managers (name, position, region, cluster, local office), 2) Area Managers (same columns), 3) Supervisors (same columns),
  4) optionally the Head of Field (name, position). Rows in table 1 whose position is "Head of ..." are also taken as the Head.
- Sheet **EMP LIST FC upload** (optional): employee number, name, position, manager (column `AM`), region, local office (column `AREA`).
  Other columns (user name, phone number, e-mail, and so on) are ignored and never read into the database.

**How rules are applied**

| Situation | Result |
|-----------|--------|
| Each cluster has one leader | The Area Manager. If the AM table names a Regional Manager or a "temp" AM, the **RM acts as leader** (info message) |
| A supervisor's manager | The **leader of the supervisor's cluster**. The cluster tables are the authority; if the employee list names someone else, one grouped warning per cluster and manager is shown |
| A supervisor is only in the employee list | Cluster is derived from the local office when it is unambiguous; otherwise a warning |
| A Regional Manager's manager | The Head of Field, when found |
| An RM covers two regions | The RM leads both regions; the RM's own assignment has no single region |
| Positions | Matched by text to `HEAD`, `RM`, `AM`, `SFSV`, `FSV2`, `FSV`, `DM` (Digital Mentor), `DSV` (Digital Supervisor). Anything else is an **error** |
| People | Matched by employee number, otherwise by normalized name; names are converted from ALL CAPS to normal case |
| Local offices | Created as org units and as travel locations |

**Safety properties**

- **Preview first.** A preview performs the full write inside a transaction and rolls it back, so the counts are exact.
- **Errors block saving.** Warnings do not. Nothing is partly imported.
- **Idempotent.** Importing the same file again reports everything as unchanged.
- **History.** A change with a later *Valid from* date closes the old assignment (the day before) and opens a new one.
- **Nothing is deleted.** People missing from a later file are reported and left unchanged.
- **No contact data.** E-mail addresses and phone numbers are not read; employee numbers and names are stored. Logins are linked later by an administrator.
- Every applied import is written to the audit log (counts only, no names).
