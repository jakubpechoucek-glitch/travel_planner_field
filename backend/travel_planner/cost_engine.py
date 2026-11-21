"""Cost forecast engine: pure functions over in-memory inputs (no database).

The model is the one of the 2027 budget: for every person who travels on a trip

    cost = fare (air or sea, if the person has to fly or sail) + local transport
           + nights x lodging per night + days x per diem

with rates by position (the Head's hotel is dearer). Whether a person flies depends on where they are based and
where the trip takes place (a region-to-region table with optional overrides for places that always need a flight).
Air and sea fares can be cheaper when booked early (tiers entered by the business); the forecast shows the effect.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date

FARE_KIND = {"air": "airfare", "sea": "sea_fare"}


@dataclass
class Rate:
    kind: str
    amount: float
    mode: str | None = None
    position: str | None = None  # position code; None = everybody
    valid_from: date = date(2000, 1, 1)
    valid_to: date | None = None


@dataclass
class CostPerson:
    person_id: int
    position: str
    home_region_id: int | None  # where the person is based (None when unknown)


@dataclass
class CostTrip:
    trip_id: int
    event_id: int
    start: date
    end: date
    dest_region_id: int | None  # region of the place (None = unknown)
    dest_unit_id: int | None  # the visited unit, for overrides
    travelers: list[CostPerson]


@dataclass
class ModeTable:
    matrix: dict[tuple[int, int], str] = field(default_factory=dict)  # (from region, to region) -> mode
    overrides: list[tuple[int | None, int, str]] = field(default_factory=list)  # (from region or None, to unit, mode)


@dataclass
class CostLine:
    trip_id: int
    event_id: int
    person_id: int
    position: str
    month: int
    mode: str
    fare: float
    local: float
    lodging: float
    per_diem: float
    fare_factor: float
    fare_full: float  # the fare before any early-booking factor
    assumed_mode: bool  # the mode was a guess (unknown home or place)

    @property
    def total(self) -> float:
        return self.fare + self.local + self.lodging + self.per_diem


@dataclass
class CostResult:
    lines: list[CostLine] = field(default_factory=list)
    missing_rates: set[str] = field(default_factory=set)


def find_rate(rates: list[Rate], kind: str, on: date, *, mode: str | None = None,
              position: str | None = None) -> Rate | None:
    """The valid rate that fits best: one for the position and mode beats a general one."""
    best: tuple[int, Rate] | None = None
    for r in rates:
        if r.kind != kind or r.valid_from > on or (r.valid_to is not None and r.valid_to < on):
            continue
        if r.position not in (None, position) or r.mode not in (None, mode):
            continue
        score = (2 if r.position else 0) + (1 if r.mode else 0)
        if best is None or (score, r.valid_from) > (best[0], best[1].valid_from):
            best = (score, r)
    return best[1] if best else None


def travel_mode(table: ModeTable, home: int | None, dest_region: int | None, dest_unit: int | None) -> tuple[str, bool]:
    """(mode, assumed). Overrides first (most specific), then the region table; unknown places count as land."""
    for from_region, to_unit, mode in table.overrides:
        if to_unit == dest_unit and from_region == home and home is not None:
            return mode, False
    for from_region, to_unit, mode in table.overrides:
        if to_unit == dest_unit and from_region is None:
            return mode, False
    if home is not None and dest_region is not None:
        if home == dest_region and (home, dest_region) not in table.matrix:
            return "land", False
        mode = table.matrix.get((home, dest_region))
        if mode:
            return mode, False
    return "land", True


def booking_factor(tiers: list[tuple[int, float]], lead_days: int) -> float:
    """The factor of the tier with the largest 'at least N days ahead' that the lead time reaches."""
    best = max((t for t in tiers if t[0] <= lead_days), default=None, key=lambda t: t[0])
    return best[1] if best else 1.0


def forecast(trips: list[CostTrip], rates: list[Rate], modes: ModeTable, tiers: list[tuple[int, float]],
             today: date, book_ahead_days: int | None = None) -> CostResult:
    """Cost of every traveler on every trip.

    ``book_ahead_days`` answers "what if all fares were booked N days ahead?"; without it the real lead time counts.
    """
    out = CostResult()

    def amount(kind: str, on: date, mode: str | None = None, position: str | None = None) -> float:
        r = find_rate(rates, kind, on, mode=mode, position=position)
        if r is None:
            out.missing_rates.add(kind if mode is None else f"{kind} ({mode})")
            return 0.0
        return r.amount

    for t in trips:
        days = (t.end - t.start).days + 1
        nights = days - 1
        lead = max(0, (t.start - today).days) if book_ahead_days is None else book_ahead_days
        factor = booking_factor(tiers, lead)
        for p in t.travelers:
            mode, assumed = travel_mode(modes, p.home_region_id, t.dest_region_id, t.dest_unit_id)
            fare_full = amount(FARE_KIND[mode], t.start, mode=mode, position=p.position) if mode in FARE_KIND else 0.0
            out.lines.append(CostLine(
                trip_id=t.trip_id, event_id=t.event_id, person_id=p.person_id, position=p.position,
                month=t.start.month, mode=mode, fare=round(fare_full * factor, 2),
                local=amount("local_transport", t.start, position=p.position),
                lodging=nights * amount("lodging_per_night", t.start, position=p.position) if nights else 0.0,
                per_diem=days * amount("per_diem", t.start, position=p.position),
                fare_factor=factor, fare_full=fare_full, assumed_mode=assumed))
    return out


def totals_by(lines: list[CostLine], key) -> dict:
    out: dict = defaultdict(lambda: {"cost": 0.0, "trips": set(), "person_trips": 0})
    for ln in lines:
        k = key(ln)
        out[k]["cost"] += ln.total
        out[k]["trips"].add(ln.trip_id)
        out[k]["person_trips"] += 1
    return out
