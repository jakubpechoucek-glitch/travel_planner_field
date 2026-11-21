# 1. Product Overview

## 1.1 Problem

Field leaders (area managers, regional managers, the head of field) and supporting
functions (training, quality, legal) must regularly meet field supervisors in person.
Today, trips are planned in spreadsheets and an MS Forms tracker, then filed
individually in SAP for approval. As a result:

- there is no single, visual view of who travels where and when;
- trips to the same area are not combined, even when one overnight stay would be
  cheaper than two separate trips;
- requests arrive close to the travel date, so airfare is more expensive and approvals are late;
- it is hard to see which teams under-use or over-use their travel allowance.

## 1.2 Goals

1. **Plan early.** One yearly plan, generated from rules, supports advance approval and earlier booking.
2. **Find synergies.** Make overlaps visible so trips can be merged, moved or skipped.
3. **Control spend.** Forecast the cost of the plan and compare it with the annual travel budget.
4. **Stay compliant.** Track each trip type against its minimum and maximum frequency and warn when a limit is exceeded.
5. **Stay flexible.** Plans follow the rules but can be changed; every change records a reason.

**Non-goal:** limiting travel as such. The tool exists to make travel earlier, combined and transparent.

## 1.3 Design principles

- **Simple for hundreds of users.** Most users open the app, see their own plan, and do very little. Defaults over configuration.
- **Visual first.** Managers need to *see* the plan (heatmap and timeline) to decide whether to merge or move a trip.
- **Rules generate, humans decide.** Generated trips are proposals; manual edits always win, but must be explained.
- **Configurable, not hard-coded.** Event types, rules, positions and the organization structure are data that an administrator edits. The structure will change (new layer between head and area, new events, new frequencies).
- **Small steps.** Deliver a minimal viable product, learn from real use over several weeks, then extend. Expect four to five versions before the model is fully tuned.
- **No integrations in the MVP.** SAP stays the system of record for expense approval. The app stores a reference to the SAP request but does not integrate with it at first.
- **Privacy by design.** Store only the personal data the app needs (see [Data model](06-data-model.md#66-personal-data)).

## 1.4 Scope

**In scope (MVP):** Field Collections organization; event catalog and rule management;
generated yearly plan; manual editing with reasons; calendar views by region, area and person;
rule-compliance warnings; role-based visibility; in-app help; administration of users and rules.

**Later phases:** cost forecast, lead-time warnings, itinerary details, approval status,
other functions (Training, Quality, Legal, HR), reporting, outcomes and documents per trip,
SAP reference tracking, optional integrations. See [MVP and roadmap](08-mvp-roadmap.md).

**Out of scope for now:** replacing SAP, booking tickets or hotels, expense claims,
cash advances and Grab codes (policy not yet decided).

## 1.5 Glossary

| Term | Meaning |
|------|---------|
| Head of Field | Head of Nationwide Field. Top of the field hierarchy. |
| RM | Regional Manager (Collection Regional Manager). Manages several clusters. |
| AM | Area Manager. Manages one cluster and its field supervisors. |
| FSV | Field Supervisor (including senior and level II). |
| FTE | A field collector counted for capacity; not a traveler in the MVP. |
| Region | Geographic grouping: NCR, North Luzon, South Luzon, Visayas, Mindanao. |
| Cluster | A group of provinces managed by one AM (for example *South Luzon 2*). |
| Local office (LO) | The physical office where supervisors meet (for example *Lipa City*). In the source files this is also called "area". |
| Event type | A kind of trip or gathering with its own rules (for example *Area Visit*). |
| Trip | One planned occurrence of an event type: dates, destination, organizer, participants. |
| Plan year | The calendar year being planned (the first is 2027). |
| Override | A manual change to a generated trip. Requires a reason. |
| Blackout period | Dates when certain event types must not happen (conference month, year-end party). |
| Synergy | Two or more trips that can be merged or placed next to each other to save cost. |
| Lakbay | "Collection Lakbay Regional Visit": a regional roadshow combined with area and regional meetings. |
| TQACE | Training, Quality Assurance and Compliance function. |
| Lakebase | Databricks' managed PostgreSQL service. |
