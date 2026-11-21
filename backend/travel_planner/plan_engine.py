"""Plan generator engine: pure functions over in-memory inputs (no database access).

Given the organization, the event catalog, the rules and the blackout periods, it proposes the trips of one plan
year. It is deterministic (same inputs, same plan) and explains what it could not do instead of guessing.

How it works, in short
1. Every event type with a yearly quota or a cadence is expanded into trips per unit (cluster, region, local
   office or nationwide): ``count = cadence per year``, clamped to the quota.
2. Trips are placed one by one, most important event types first (company events, then wider scope, then
   events with more participants), into calendar weeks. Each week gets a penalty (distance from the ideal week,
   blackout, traveler already away, trip limits per person and period, crowded cluster, rotation load) and the
   lowest penalty wins; ties go to the earlier week.
3. When a less important event meets a combinable one (merge rules) of the same place within a week, it is
   absorbed: the trip stays in the plan as "merged" and its participants join the surviving trip.
4. Positions with a yearly limit (for example the Head of Field "3x") are assigned afterwards, spread evenly.
5. The result is checked with the same ``evaluate`` function that later checks manual edits.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

# ---------------------------------------------------------------------------------------------- inputs

PER_YEAR = {"week": 52, "month": 12, "quarter": 4, "half_year": 2, "year": 1}
BREADTH = {"local_office": 0, "external": 0, "cluster": 1, "region": 2, "nationwide": 3}

# penalty weights (lower total wins)
W_DISTANCE = 1.0          # per week away from the ideal week
W_BLACKOUT = 200.0        # trip inside a "warn" blackout (a "block" blackout is never used)
W_WINDOW = 30.0           # outside the preferred months
W_SPACING = 100.0         # same event and place within MIN_GAP weeks
W_AWAY = 120.0           # per traveler already away that week
W_CAP = 80.0              # per traveler who would exceed a trip limit
W_CLUSTER_LOAD = 5.0      # per other trip in the same cluster that week
W_ROTATION = 25.0         # per trip above the rotation limit in a region and quarter
W_MERGE_BONUS = 40.0      # a combinable trip of the same place is nearby
MIN_GAP = 3


@dataclass(frozen=True)
class UnitRef:
    kind: str  # region | cluster | local_office | nationwide
    id: int | None = None


@dataclass
class UnitIn:
    kind: str
    id: int | None
    name: str
    region_id: int | None = None
    lead_person_id: int | None = None
    hub_office_id: int | None = None  # local office used as the trip location


@dataclass
class PersonIn:
    id: int
    name: str
    position: str  # position code
    level: int
    function_area: str = "field"
    region_id: int | None = None
    cluster_id: int | None = None
    office_id: int | None = None


@dataclass
class EventPos:
    position: str
    participation: str  # organizer | participant
    yearly_limit: int | None = None
    travels: bool = True


@dataclass
class ERule:
    id: int | None
    key: str
    rule_type: str
    scope_kind: str
    position: str | None = None
    period: str | None = None
    interval_n: int | None = None
    min_count: int | None = None
    max_count: int | None = None
    params: dict[str, Any] = field(default_factory=dict)
    severity: str = "warn"


@dataclass
class EventIn:
    id: int
    code: str
    name: str
    is_company: bool = False
    visited_kind: str = "cluster"
    typical_days: int | None = None
    typical_mode: str | None = None
    organizer_position: str | None = None
    positions: list[EventPos] = field(default_factory=list)
    rules: list[ERule] = field(default_factory=list)


@dataclass
class BlackoutIn:
    id: int
    name: str
    start: date
    end: date
    severity: str = "warn"
    event_ids: frozenset[int] = frozenset()  # empty = all events
    cause_event_id: int | None = None

    def affects(self, event_id: int) -> bool:
        return not self.event_ids or event_id in self.event_ids


@dataclass
class TripView:
    """A trip as the checks see it (generated here or loaded from the database)."""

    key: int
    event_id: int
    visited: UnitRef
    start: date
    end: date
    participants: dict[int, tuple[str, bool]]  # person id -> (role, travels)
    absorbed: bool = False
    status: str = "generated"


@dataclass
class Inputs:
    year: int
    regions: list[UnitIn]
    clusters: list[UnitIn]
    offices: list[UnitIn]
    people: list[PersonIn]
    events: list[EventIn]
    general_rules: list[ERule] = field(default_factory=list)
    merges: set[frozenset[int]] = field(default_factory=set)
    blackouts: list[BlackoutIn] = field(default_factory=list)
    positions: dict[str, tuple[int, str]] = field(default_factory=dict)  # code -> (level, function area)
    kept: list[TripView] = field(default_factory=list)  # existing trips that stay (manual, confirmed, ...)


# ---------------------------------------------------------------------------------------------- outputs


@dataclass
class TripOut:
    key: int
    event_id: int
    event_code: str
    title: str
    scope: UnitRef
    visited: UnitRef
    start: date
    end: date
    participants: dict[int, tuple[str, bool]]
    rule_id: int | None = None
    absorbed_into: int | None = None
    notes: list[str] = field(default_factory=list)
    hub_office_id: int | None = None
    transport_mode: str | None = None


@dataclass
class Warn:
    level: str
    code: str
    message: str


@dataclass
class Result:
    trips: list[TripOut] = field(default_factory=list)
    unplaced: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    warnings: list[Warn] = field(default_factory=list)


# ---------------------------------------------------------------------------------------------- calendar


def week_starts(year: int) -> list[date]:
    """Mondays whose Monday to Friday lies inside the year."""
    d = date(year, 1, 1)
    d += timedelta(days=(7 - d.weekday()) % 7)
    out: list[date] = []
    while d + timedelta(days=4) <= date(year, 12, 31):
        out.append(d)
        d += timedelta(days=7)
    return out


def trip_dates(monday: date, days: int) -> tuple[date, date]:
    start = monday + timedelta(days=1 if days <= 4 else 0)  # Tuesday for short trips
    return start, start + timedelta(days=days - 1)


def period_key(d: date, period: str) -> tuple:
    if period == "week":
        iso = d.isocalendar()
        return (iso[0], iso[1])
    if period == "month":
        return (d.year, d.month)
    if period == "quarter":
        return (d.year, (d.month - 1) // 3)
    if period == "half_year":
        return (d.year, (d.month - 1) // 6)
    return (d.year,)


def _overlaps(a1: date, a2: date, b1: date, b2: date) -> bool:
    return a1 <= b2 and b1 <= a2


# ---------------------------------------------------------------------------------------------- the world


class World:
    """Lookups over the inputs: units, people and who belongs where."""

    def __init__(self, inp: Inputs):
        self.inp = inp
        self.people = {p.id: p for p in inp.people}
        self.units: dict[UnitRef, UnitIn] = {}
        for u in (*inp.regions, *inp.clusters, *inp.offices):
            self.units[UnitRef(u.kind, u.id)] = u
        self.units[UnitRef("nationwide")] = UnitIn("nationwide", None, "Nationwide")
        self.members: dict[int, set[UnitRef]] = {}
        for p in inp.people:
            m: set[UnitRef] = set()
            if p.region_id:
                m.add(UnitRef("region", p.region_id))
            if p.cluster_id:
                m.add(UnitRef("cluster", p.cluster_id))
            if p.office_id:
                m.add(UnitRef("local_office", p.office_id))
            self.members[p.id] = m
        # a leader belongs to everything below the unit they lead
        for r in inp.regions:
            if r.lead_person_id in self.members:
                m = self.members[r.lead_person_id]
                m.add(UnitRef("region", r.id))
                m.update(UnitRef("cluster", c.id) for c in inp.clusters if c.region_id == r.id)
                m.update(UnitRef("local_office", o.id) for o in inp.offices if o.region_id == r.id)
        for c in inp.clusters:
            if c.lead_person_id in self.members:
                self.members[c.lead_person_id].add(UnitRef("cluster", c.id))
        self.region_of = {UnitRef("cluster", c.id): c.region_id for c in inp.clusters}
        self.region_of.update({UnitRef("local_office", o.id): o.region_id for o in inp.offices})
        self.region_of.update({UnitRef("region", r.id): r.id for r in inp.regions})

    def people_in(self, position: str, unit: UnitRef) -> list[PersonIn]:
        out = []
        for p in self.people.values():
            if p.position != position:
                continue
            if unit.kind == "nationwide" or p.level == 0 or unit in self.members[p.id]:  # level 0: the Head
                out.append(p)
        return sorted(out, key=lambda p: (p.name, p.id))

    def units_for(self, scope_kind: str) -> list[UnitIn]:
        if scope_kind == "nationwide":
            return [self.units[UnitRef("nationwide")]]
        pool = {"cluster": self.inp.clusters, "region": self.inp.regions, "local_office": self.inp.offices}.get(
            scope_kind, [])
        led = [u for u in pool if u.lead_person_id or scope_kind == "local_office"]
        return sorted(led, key=lambda u: (u.name, u.id))

    def region_id(self, ref: UnitRef) -> int | None:
        return self.region_of.get(ref)


def _event_rules(ev: EventIn, rtype: str) -> list[ERule]:
    return [r for r in ev.rules if r.rule_type == rtype]


def trips_per_unit(ev: EventIn) -> tuple[int | None, ERule | None, str | None]:
    """How many trips per unit a year, the rule responsible, and why not if none."""
    quota = next(iter(_event_rules(ev, "annual_quota")), None)
    cadence = next(iter(_event_rules(ev, "cadence")), None)
    if not quota and not cadence:
        return None, None, "no yearly quota or cadence rule"
    n = None
    if cadence and cadence.period:
        n = max(1, PER_YEAR[cadence.period] // max(1, cadence.interval_n or 1))
    if quota:
        lo, hi = quota.min_count, quota.max_count
        if n is None:
            n = lo if lo else hi
        else:
            n = max(lo or 0, min(n, hi if hi is not None else n))
    if not n:
        return None, quota or cadence, "the rules ask for no trips"
    return n, quota or cadence, None


def _is_above(world: World, pos: str, organizer: str | None) -> bool:
    """A field manager above the organizer joins only through a yearly limit or a merged event."""
    if not organizer:
        return False
    a, b = world.inp.positions.get(pos), world.inp.positions.get(organizer)
    return bool(a and b and a[1] == "field" == b[1] and a[0] < b[0])


# ---------------------------------------------------------------------------------------------- planner


@dataclass
class _Spec:
    event: EventIn
    rule: ERule | None
    scope: UnitRef
    visited: UnitRef
    k: int
    ideal: int
    pool: list[int]  # candidate weeks
    hard_pool: bool
    window_months: frozenset[int]
    days: int
    order: tuple


class Planner:
    def __init__(self, inp: Inputs):
        self.inp = inp
        self.w = World(inp)
        self.weeks = week_starts(inp.year)
        self.first = self.weeks[0]
        self.events = {e.id: e for e in inp.events}
        self.rank = {e.id: self._rank(e) for e in inp.events}
        self.partners: dict[int, set[int]] = defaultdict(set)
        for pair in inp.merges:
            a, b = tuple(pair)
            if a not in self.events or b not in self.events:
                continue
            self.partners[a].add(b)
            self.partners[b].add(a)
            if self.rank[a] == self.rank[b]:
                self.result_skipped_pairs = getattr(self, "result_skipped_pairs", [])
                self.result_skipped_pairs.append(
                    f"{self.events[a].name} and {self.events[b].name} are combinable, but neither is more "
                    "important (scope, company event, participants), so they are not combined. "
                    "Give one of them more participants.")
        self.caps = [r for r in inp.general_rules
                     if r.rule_type == "period_cap" and r.max_count is not None and r.period]
        self.result = Result(skipped=list(getattr(self, "result_skipped_pairs", [])))
        self.trips: list[TripOut] = []
        self.next_key = 1
        self.occ: dict[int, set[int]] = defaultdict(set)
        self.cap_count: dict[tuple, int] = defaultdict(int)
        self.cluster_week: dict[tuple[int, int], int] = defaultdict(int)
        self.event_unit_weeks: dict[tuple, list[int]] = defaultdict(list)
        self.rotation_load: dict[tuple, int] = defaultdict(int)
        self.by_visited: dict[UnitRef, list[TripOut]] = defaultdict(list)
        self.limited: list[tuple] = []
        self.absorbed_events: dict[int, set[int]] = defaultdict(set)
        for t in inp.kept:
            self._occupy_kept(t)

    # ----- ranks, weeks
    def _rank(self, e: EventIn) -> tuple:
        return (e.is_company, BREADTH.get(e.visited_kind, 0), len(e.positions))

    def week_of(self, d: date) -> int:
        return (d - self.first).days // 7

    def span(self, w: int, days: int) -> set[int]:
        s, e = trip_dates(self.weeks[w], days)
        return set(range(self.week_of(s), self.week_of(e) + 1))

    # ----- occupancy
    def _cap_applies(self, rule: ERule, p: PersonIn) -> bool:
        return rule.position is None or rule.position == p.position

    def _occupy(self, travelers: list[int], start: date, end: date) -> None:
        weeks = set(range(self.week_of(start), self.week_of(end) + 1))
        for pid in travelers:
            self.occ[pid] |= weeks
            p = self.w.people.get(pid)
            for rule in self.caps:
                if p and self._cap_applies(rule, p):
                    self.cap_count[(rule.key, pid, period_key(start, rule.period or "month"))] += 1

    def _occupy_kept(self, t: TripView) -> None:
        self._occupy([pid for pid, (_, tr) in t.participants.items() if tr], t.start, t.end)

    # ----- participants
    def build_participants(self, ev: EventIn, scope: UnitRef):
        """People who join by default, plus positions that join only up to a yearly limit."""
        parts: dict[int, tuple[str, bool]] = {}
        limited: list[tuple[int, str, int, bool]] = []
        for ep in ev.positions:
            people = self.w.people_in(ep.position, scope)
            if ep.participation == "organizer":
                if not people:  # nobody holds the position here: the unit's leader acts as organizer
                    lead = self.w.units[scope].lead_person_id
                    if lead in self.w.people:
                        people = [self.w.people[lead]]
                for p in people:
                    parts[p.id] = ("organizer", True)
            elif ep.yearly_limit is not None:
                for p in people:
                    limited.append((p.id, ev.code, ep.yearly_limit, ep.travels))
            elif _is_above(self.w, ep.position, ev.organizer_position):
                continue
            else:
                for p in people:
                    parts.setdefault(p.id, ("traveler" if ep.travels else "host", ep.travels))
        return parts, limited

    # ----- scoring
    def _score(self, s: _Spec, w: int, travelers: list[int]) -> float | None:
        start, end = trip_dates(self.weeks[w], s.days)
        if end > date(self.inp.year, 12, 31):
            return None
        pen = abs(w - s.ideal) * W_DISTANCE
        for b in self.inp.blackouts:
            if b.affects(s.event.id) and b.cause_event_id != s.event.id and _overlaps(start, end, b.start, b.end):
                if b.severity == "block":
                    return None
                pen += W_BLACKOUT
        if s.window_months and start.month not in s.window_months:
            pen += W_WINDOW
        for other in self.event_unit_weeks[(s.event.id, s.visited)]:
            if abs(other - w) < MIN_GAP:
                pen += W_SPACING
        span = self.span(w, s.days)
        away = sum(1 for pid in travelers if self.occ[pid] & span)
        pen += min(away, 10) * W_AWAY
        for pid in travelers:
            p = self.w.people.get(pid)
            for rule in self.caps:
                if p and self._cap_applies(rule, p):
                    key = (rule.key, pid, period_key(start, rule.period or "month"))
                    if self.cap_count[key] >= (rule.max_count or 0):
                        pen += W_CAP
        cluster = s.visited.id if s.visited.kind == "cluster" else None
        if cluster is not None:
            pen += W_CLUSTER_LOAD * self.cluster_week[(cluster, w)]
        rot = next(iter(_event_rules(s.event, "rotation")), None)
        if rot and rot.period == "quarter" and (rot.max_count or rot.min_count):
            region = self.w.region_id(s.visited)
            load = self.rotation_load[(s.event.id, region, period_key(start, "quarter"))]
            limit = rot.max_count or rot.min_count or 0
            pen += max(0, load + 1 - limit) * W_ROTATION
        if self._merge_target(s.event, s.visited, w, travelers):
            pen -= W_MERGE_BONUS
        return pen

    def _merge_target(self, ev: EventIn, visited: UnitRef, w: int, travelers: list[int]) -> TripOut | None:
        """A more important, combinable trip of the same place within a week, where nobody joining is away."""
        for t in self.by_visited.get(visited, []):
            if t.absorbed_into is None and t.event_id in self.partners[ev.id] \
                    and self.rank[t.event_id] > self.rank[ev.id] and ev.id not in self.absorbed_events[t.key] \
                    and abs(self.week_of(t.start) - w) <= 1:
                weeks = set(range(self.week_of(t.start), self.week_of(t.end) + 1))
                if all(pid in t.participants or not (self.occ[pid] & weeks) for pid in travelers):
                    return t
        return None

    # ----- placement
    def _place(self, s: _Spec) -> None:
        parts, limited = self.build_participants(s.event, s.scope)
        travelers = [pid for pid, (_, tr) in parts.items() if tr]
        best: tuple[float, int] | None = None
        for w in s.pool:
            sc = self._score(s, w, travelers)
            if sc is not None and (best is None or (sc, w) < best):
                best = (sc, w)
        name = self.w.units[s.visited].name
        if best is None:
            self.result.unplaced.append(f"{s.event.name}, {name}: no suitable week (blackouts or the year end).")
            return
        w = best[1]
        start, end = trip_dates(self.weeks[w], s.days)
        unit = self.w.units[s.visited]
        trip = TripOut(
            key=self.next_key, event_id=s.event.id, event_code=s.event.code,
            title=s.event.name if s.visited.kind == "nationwide" else f"{s.event.name}: {name}",
            scope=s.scope, visited=s.visited, start=start, end=end, participants=dict(parts),
            rule_id=s.rule.id if s.rule else None, hub_office_id=unit.hub_office_id,
            transport_mode=s.event.typical_mode,
        )
        self.next_key += 1
        target = self._merge_target(s.event, s.visited, w, travelers)
        if target is not None:
            self._absorb(trip, target)
        else:
            self._occupy(travelers, start, end)
            for wk in self.span(w, s.days):
                if s.visited.kind == "cluster":
                    self.cluster_week[(s.visited.id, wk)] += 1  # type: ignore[index]
            self.event_unit_weeks[(s.event.id, s.visited)].append(w)
            region = self.w.region_id(s.visited)
            self.rotation_load[(s.event.id, region, period_key(start, "quarter"))] += 1
            self.by_visited[s.visited].append(trip)
        # a yearly limit ("up to 3 times") is spent on the trip that actually takes place
        holder = target if target is not None else trip
        for pid, _code, limit, travels in limited:
            self.limited.append((s.event.id, pid, limit, travels, holder))
        self.trips.append(trip)

    def _absorb(self, trip: TripOut, target: TripOut) -> None:
        """The less important trip is held together with the surviving one."""
        trip.absorbed_into = target.key
        trip.start, trip.end = target.start, target.end
        self.absorbed_events[target.key].add(trip.event_id)
        self.event_unit_weeks[(trip.event_id, trip.visited)].append(self.week_of(target.start))
        added = []
        for pid, (role, travels) in trip.participants.items():
            if pid not in target.participants:
                target.participants[pid] = ("traveler" if role == "organizer" else role, travels)
                if travels:
                    added.append(pid)
        self._occupy(added, target.start, target.end)
        target.notes.append(f"Includes {self.events[trip.event_id].name}.")

    # ----- limited participants
    def _own_limit(self, event_id: int, pid: int) -> int | None:
        pos = self.w.people[pid].position
        ev = self.events[event_id]
        return next((ep.yearly_limit for ep in ev.positions if ep.position == pos), None)

    def _assign_limited(self) -> None:
        """Spend yearly limits ("up to 3 times") evenly over the year, avoiding clashes and monthly caps."""
        groups: dict[tuple[int, int], list[tuple]] = defaultdict(list)
        for event_id, pid, limit, travels, trip in self.limited:
            if trip.absorbed_into is None:
                groups[(event_id, pid)].append((limit, travels, trip))
        joined: dict[tuple[int, int], int] = defaultdict(int)  # (person, event of the trip) -> times
        for (_event_id, pid), items in sorted(groups.items()):
            limit, travels = items[0][0], items[0][1]
            unique = {t.key: t for _, _, t in items}
            trips = sorted(unique.values(), key=lambda t: (t.start, t.key))
            if limit <= 0:
                continue
            picks = list(range(len(trips))) if len(trips) <= limit else [
                int((i + 0.5) * len(trips) / limit) for i in range(limit)]
            used: set[int] = set()
            p = self.w.people[pid]
            for idx in picks:
                order = [j for j in [*range(idx, len(trips)), *range(idx - 1, -1, -1)] if j not in used]
                # the person may also be limited on the event of the surviving trip itself
                order = [j for j in order if (lim := self._own_limit(trips[j].event_id, pid)) is None
                         or joined[(pid, trips[j].event_id)] < lim or trips[j].event_id == _event_id]
                choice = next((j for j in order if self._within_caps(p, trips[j])), None)
                if choice is None:
                    choice = next((j for j in order if not self._busy(p, trips[j])), order[0] if order else None)
                if choice is None:
                    continue
                used.add(choice)
                t = trips[choice]
                joined[(pid, t.event_id)] += 1
                t.participants[pid] = ("traveler", travels)
                if travels:
                    self._occupy([pid], t.start, t.end)

    def _busy(self, p: PersonIn, t: TripOut) -> bool:
        return bool(self.occ[p.id] & set(range(self.week_of(t.start), self.week_of(t.end) + 1)))

    def _within_caps(self, p: PersonIn, t: TripOut) -> bool:
        if self._busy(p, t):
            return False
        for rule in self.caps:
            if self._cap_applies(rule, p) and self.cap_count[
                    (rule.key, p.id, period_key(t.start, rule.period or "month"))] >= (rule.max_count or 0):
                return False
        return True

    # ----- build the specs
    def specs(self) -> list[_Spec]:
        out: list[_Spec] = []
        kept = defaultdict(int)
        for t in self.inp.kept:
            if not t.absorbed and t.status != "cancelled":
                kept[(t.event_id, t.visited)] += 1
        taken_clusters: dict[tuple, set[int]] = defaultdict(set)
        for t in self.inp.kept:
            if t.visited.kind == "cluster" and not t.absorbed:
                taken_clusters[(t.event_id,)].add(t.visited.id or 0)
        for ev in sorted(self.inp.events, key=lambda e: (self.rank[e.id], e.code), reverse=True):
            n, rule, why = trips_per_unit(ev)
            if n is None:
                self.result.skipped.append(f"{ev.name}: {why}.")
                continue
            assert rule is not None
            quota = next(iter(_event_rules(ev, "annual_quota")), None)
            scope_kind = (quota or rule).scope_kind
            units = self.w.units_for(scope_kind)
            if not units:
                self.result.skipped.append(f"{ev.name}: no {scope_kind.replace('_', ' ')} to plan for.")
                continue
            days = ev.typical_days or 1
            window = next(iter(_event_rules(ev, "preferred_window")), None)
            months = frozenset(window.params.get("months", [])) if window else frozenset()
            cause = [b for b in self.inp.blackouts if b.cause_event_id == ev.id]
            pool, hard = list(range(len(self.weeks))), False
            if cause:
                pool = [i for i in pool if any(
                    b.start <= trip_dates(self.weeks[i], days)[0] and trip_dates(self.weeks[i], days)[1] <= b.end
                    for b in cause)]
                hard = True
            inside = [i for i in pool if trip_dates(self.weeks[i], days)[0].month in months] if months else []
            ideal_pool = pool if (cause or not months) else (inside or pool)
            if not pool:
                self.result.unplaced.append(f"{ev.name}: the blackout that holds it has no free week.")
                continue
            distinct = quota.params.get("distinct_units") if quota else None
            for i, u in enumerate(units):
                ref = UnitRef(u.kind, u.id)
                visited_list: list[UnitRef]
                if distinct == "cluster" and u.kind == "region":
                    region_clusters = [c for c in self.inp.clusters if c.region_id == u.id]
                    have = sum(kept[(ev.id, UnitRef("cluster", c.id))] for c in region_clusters)
                    count = max(0, n - have)
                    clusters = [c for c in region_clusters if (c.id or 0) not in taken_clusters[(ev.id,)]]
                    clusters.sort(key=lambda c: (c.name, c.id))
                    if len(clusters) < count:
                        self.result.unplaced.append(
                            f"{ev.name}, {u.name}: needs {count} different clusters but has {len(clusters)}.")
                        count = len(clusters)
                    picks = [clusters[int((j + 0.5) * len(clusters) / count)] for j in range(count)] if count else []
                    visited_list = [UnitRef("cluster", c.id) for c in picks]
                else:
                    count = max(0, n - kept[(ev.id, ref)])
                    visited_list = [ref] * count
                for k, vis in enumerate(visited_list):
                    frac = (k + (i + 0.5) / len(units)) / max(1, len(visited_list))
                    ideal = ideal_pool[min(len(ideal_pool) - 1, int(frac * len(ideal_pool)))]
                    out.append(_Spec(ev, rule, ref, vis, k, ideal, pool, hard, months, days,
                                     (tuple(-x for x in self._rank_key(ev)), k, i, ev.code)))
        return sorted(out, key=lambda s: s.order)

    def _rank_key(self, ev: EventIn) -> tuple:
        r = self.rank[ev.id]
        return (int(r[0]), r[1], r[2])

    def run(self) -> Result:
        for spec in self.specs():
            self._place(spec)
        self._assign_limited()
        self.result.trips = self.trips
        views = [_view(t) for t in self.trips] + self.inp.kept
        self.result.warnings = evaluate(views, self.inp)
        return self.result


def _view(t: TripOut) -> TripView:
    return TripView(t.key, t.event_id, t.visited, t.start, t.end, t.participants, absorbed=t.absorbed_into is not None)


def generate(inp: Inputs) -> Result:
    return Planner(inp).run()


# ---------------------------------------------------------------------------------------------- checks


def evaluate(trips: list[TripView], inp: Inputs) -> list[Warn]:
    """Check a set of trips against the rules. Used for generated plans and, later, manual edits."""
    world = World(inp)
    events = {e.id: e for e in inp.events}
    warns: list[Warn] = []
    # a trip combined into a bigger one is stored as "cancelled" with a link; it still counts toward the quotas
    live = [t for t in trips if t.status != "cancelled" or t.absorbed]
    surviving = [t for t in live if not t.absorbed]

    # trip limits per person and period (rules across event types)
    for rule in inp.general_rules:
        if rule.rule_type != "period_cap" or not rule.period:
            continue
        counts: dict[tuple, int] = defaultdict(int)
        for t in surviving:
            for pid, (_, travels) in t.participants.items():
                p = world.people.get(pid)
                if travels and p and (rule.position is None or rule.position == p.position):
                    counts[(pid, period_key(t.start, rule.period))] += 1
        for (pid, key), n in sorted(counts.items(), key=lambda x: (world.people[x[0][0]].name, x[0][1])):
            if rule.max_count is not None and n > rule.max_count:
                warns.append(Warn(rule.severity, "period_cap",
                                  f"{world.people[pid].name} has {n} trips in {_period_label(key, rule.period)} "
                                  f"(limit {rule.max_count})."))
            if rule.min_count is not None and n < rule.min_count:
                warns.append(Warn(rule.severity, "period_min",
                                  f"{world.people[pid].name} has {n} trips in {_period_label(key, rule.period)} "
                                  f"(at least {rule.min_count} expected)."))

    # yearly limits per person and event type
    per_person_event: dict[tuple[int, int], int] = defaultdict(int)
    for t in surviving:
        for pid, (_, travels) in t.participants.items():
            if travels:
                per_person_event[(pid, t.event_id)] += 1
    for ev in inp.events:
        for ep in ev.positions:
            if ep.yearly_limit is None:
                continue
            for p in sorted((p for p in inp.people if p.position == ep.position), key=lambda p: p.name):
                n = per_person_event.get((p.id, ev.id), 0)
                if n > ep.yearly_limit:
                    warns.append(Warn("warn", "yearly_limit",
                                      f"{p.name} joins {n} times {ev.name} (limit {ep.yearly_limit} a year)."))

    # quotas per place
    for ev in inp.events:
        for rule in _event_rules(ev, "annual_quota"):
            for u in world.units_for(rule.scope_kind):
                ref = UnitRef(u.kind, u.id)
                n = sum(1 for t in live
                        if t.event_id == ev.id and _quota_unit(world, t.visited, rule.scope_kind) == ref)
                if rule.min_count is not None and n < rule.min_count:
                    warns.append(Warn(rule.severity, "quota_short",
                                      f"{ev.name}, {u.name}: {n} planned, at least {rule.min_count} expected."))
                if rule.max_count is not None and n > rule.max_count:
                    warns.append(Warn(rule.severity, "quota_over",
                                      f"{ev.name}, {u.name}: {n} planned, at most {rule.max_count} expected."))

    # blackouts
    for t in surviving:
        for b in inp.blackouts:
            if b.affects(t.event_id) and b.cause_event_id != t.event_id and _overlaps(t.start, t.end, b.start, b.end):
                warns.append(Warn(b.severity, "blackout",
                                  f"{events[t.event_id].name} ({t.start:%b %d}) falls in '{b.name}'."))

    # a person in two trips at the same time
    by_person: dict[int, list[TripView]] = defaultdict(list)
    for t in surviving:
        for pid, (_, travels) in t.participants.items():
            if travels:
                by_person[pid].append(t)
    for pid, ts in sorted(by_person.items(), key=lambda x: world.people[x[0]].name if x[0] in world.people else ""):
        ts.sort(key=lambda t: (t.start, t.key))
        for a, b in zip(ts, ts[1:], strict=False):
            if _overlaps(a.start, a.end, b.start, b.end) and pid in world.people:
                warns.append(Warn("warn", "overlap",
                                  f"{world.people[pid].name} is in two trips at once: {events[a.event_id].name} and "
                                  f"{events[b.event_id].name} ({b.start:%b %d})."))
    return warns


def _quota_unit(world: World, visited: UnitRef, scope_kind: str) -> UnitRef | None:
    if scope_kind == "nationwide":
        return UnitRef("nationwide")
    if scope_kind == visited.kind:
        return visited
    if scope_kind == "region":
        rid = world.region_id(visited)
        return UnitRef("region", rid) if rid else None
    return None


def _period_label(key: tuple, period: str) -> str:
    if period == "month":
        return date(key[0], key[1], 1).strftime("%B %Y")
    if period == "week":
        return f"week {key[1]} of {key[0]}"
    if period == "quarter":
        return f"Q{key[1] + 1} {key[0]}"
    if period == "half_year":
        return f"H{key[1] + 1} {key[0]}"
    return str(key[0])


__all__ = ["generate", "evaluate", "Inputs", "Result"]
