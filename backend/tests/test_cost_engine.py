from datetime import date

from travel_planner.cost_engine import (
    CostPerson,
    CostTrip,
    ModeTable,
    Rate,
    booking_factor,
    find_rate,
    forecast,
    totals_by,
    travel_mode,
)

# the starting rate card, as in migration 0006 (taken from the 2027 budget)
RATES = [
    Rate("airfare", 20000, mode="air"), Rate("local_transport", 2500), Rate("lodging_per_night", 3000),
    Rate("lodging_per_night", 5000, position="HEAD"), Rate("per_diem", 600),
]
NCR, NL, VIS, MIN = 1, 2, 3, 4
LUZON = {(a, b): "land" for a in (NCR, NL) for b in (NCR, NL)}
MODES = ModeTable(matrix={**LUZON, (NCR, VIS): "air", (VIS, NCR): "air", (NCR, MIN): "air", (MIN, NCR): "air",
                          (VIS, MIN): "air", (MIN, VIS): "air", (NL, VIS): "air", (VIS, NL): "air"})
TODAY = date(2026, 11, 21)


def trip(person, days, dest_region, start=date(2027, 3, 2), unit=10):
    return CostTrip(1, 1, start, date(2027, 3, 2 + days - 1) if start == date(2027, 3, 2) else start, dest_region, unit,
                    [person])


def cost(position, home, dest, days):
    res = forecast([trip(CostPerson(1, position, home), days, dest)], RATES, MODES, [], TODAY)
    return res.lines[0].total, res


def test_unit_prices_reproduce_the_2027_budget():
    # Area Manager by plane, 3 days / 2 nights: 20000 + 2 x 3000 + 2500 + 3 x 600
    assert cost("AM", NCR, VIS, 3)[0] == 30300
    # Head of Field by plane, 3 days: hotel is 5000 a night
    assert cost("HEAD", NCR, VIS, 3)[0] == 34300
    # Area Manager by land, 3 days: 2 x 3000 + 2500 + 3 x 600
    assert cost("AM", NCR, NL, 3)[0] == 10300
    # Year-end party, Head, 2 days / 1 night by plane: 20000 + 3000... with the Head's rate 5000
    assert cost("HEAD", NCR, VIS, 2)[0] == 20000 + 5000 + 2500 + 2 * 600
    # a one-day trip has no hotel
    assert cost("FSV", NCR, NCR, 1)[0] == 2500 + 600


def test_components_and_mode():
    total, res = cost("AM", NCR, VIS, 3)
    ln = res.lines[0]
    assert (ln.mode, ln.fare, ln.local, ln.lodging, ln.per_diem) == ("air", 20000, 2500, 6000, 1800)
    assert not ln.assumed_mode and not res.missing_rates
    assert cost("AM", VIS, VIS, 2)[1].lines[0].mode == "land"             # inside a region: land unless the table says so


def test_unknown_places_are_assumed_to_be_land_and_marked():
    assert travel_mode(MODES, None, VIS, 5) == ("land", True)
    assert travel_mode(MODES, NCR, None, 5) == ("land", True)
    _, res = cost("AM", None, VIS, 2)
    assert res.lines[0].assumed_mode and res.lines[0].fare == 0


def test_overrides_beat_the_region_table():
    modes = ModeTable(matrix=MODES.matrix, overrides=[(None, 99, "air"), (NL, 99, "land")])
    assert travel_mode(modes, NCR, NL, 99) == ("air", False)             # an island: everybody flies
    assert travel_mode(modes, NL, NL, 99) == ("land", False)             # except people from this region
    assert travel_mode(modes, NCR, NL, 98) == ("land", False)            # another place in the same region


def test_rates_pick_the_most_specific_valid_row():
    rates = [Rate("per_diem", 600, valid_from=date(2027, 1, 1), valid_to=date(2027, 12, 31)),
             Rate("per_diem", 700, valid_from=date(2028, 1, 1)),
             Rate("per_diem", 900, position="HEAD", valid_from=date(2027, 1, 1)),
             Rate("per_diem", 100, valid_to=date(2026, 12, 31))]
    assert find_rate(rates, "per_diem", date(2027, 5, 1)).amount == 600
    assert find_rate(rates, "per_diem", date(2028, 5, 1)).amount == 700
    assert find_rate(rates, "per_diem", date(2027, 5, 1), position="HEAD").amount == 900
    assert find_rate(rates, "per_diem", date(2026, 5, 1)).amount == 100       # an older rate that has ended
    assert find_rate(rates, "airfare", date(2027, 5, 1)) is None


def test_missing_rates_are_reported_not_hidden():
    res = forecast([trip(CostPerson(1, "AM", NCR), 3, VIS)], [Rate("per_diem", 600)], MODES, [], TODAY)
    assert {"airfare (air)", "local_transport", "lodging_per_night"} <= res.missing_rates
    assert res.lines[0].total == 1800                                      # only what is known


def test_booking_early_makes_air_fares_cheaper():
    tiers = [(30, 0.9), (60, 0.8)]
    assert [booking_factor(tiers, d) for d in (0, 29, 30, 59, 60, 400)] == [1.0, 1.0, 0.9, 0.9, 0.8, 0.8]
    far = CostTrip(1, 1, date(2027, 6, 8), date(2027, 6, 10), VIS, 10, [CostPerson(1, "AM", NCR)])
    near = CostTrip(2, 1, date(2026, 12, 8), date(2026, 12, 10), VIS, 10, [CostPerson(2, "AM", NCR)])
    res = forecast([far, near], RATES, MODES, tiers, TODAY)
    by_trip = {ln.trip_id: ln for ln in res.lines}
    assert by_trip[1].fare == 16000 and by_trip[1].fare_factor == 0.8      # 198 days ahead
    assert by_trip[2].fare == 20000 and by_trip[2].fare_factor == 1.0      # 17 days ahead: below the first tier
    # the what-if: book everything 60 days ahead
    what_if = forecast([far, near], RATES, MODES, tiers, TODAY, book_ahead_days=60)
    assert all(ln.fare == 16000 for ln in what_if.lines)
    # land trips are not affected
    land = forecast([CostTrip(3, 1, date(2027, 6, 8), date(2027, 6, 10), NL, 10, [CostPerson(3, "AM", NCR)])],
                    RATES, MODES, tiers, TODAY)
    assert land.lines[0].fare == 0 and land.lines[0].total == 6000 + 2500 + 1800


def test_totals_by_groups_people_and_trips():
    t1 = CostTrip(1, 7, date(2027, 3, 2), date(2027, 3, 3), NL, 10, [CostPerson(1, "AM", NCR), CostPerson(2, "FSV", NCR)])
    t2 = CostTrip(2, 8, date(2027, 4, 6), date(2027, 4, 7), NL, 10, [CostPerson(1, "AM", NCR)])
    lines = forecast([t1, t2], RATES, MODES, [], TODAY).lines
    by_event = totals_by(lines, lambda ln: ln.event_id)
    assert by_event[7]["person_trips"] == 2 and by_event[8]["person_trips"] == 1
    assert round(sum(v["cost"] for v in by_event.values()), 2) == round(sum(ln.total for ln in lines), 2)
    assert totals_by(lines, lambda ln: ln.month).keys() == {3, 4}
