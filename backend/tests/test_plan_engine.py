from datetime import date

import pytest

from travel_planner.plan_engine import (
    BlackoutIn,
    ERule,
    EventIn,
    EventPos,
    Inputs,
    PersonIn,
    TripView,
    UnitIn,
    UnitRef,
    evaluate,
    generate,
    week_starts,
)

YEAR = 2027
POSITIONS = {"HEAD": (0, "field"), "RM": (1, "field"), "AM": (2, "field"), "FSV": (3, "field"),
             "TRAIN": (4, "training")}


def world(**changes) -> Inputs:
    people = [
        PersonIn(1, "Hana Head", "HEAD", 0),
        PersonIn(2, "Rita Rivera", "RM", 1, region_id=1),
        PersonIn(3, "Amy Alvarez", "AM", 2, region_id=1, cluster_id=11, office_id=21),
        PersonIn(4, "Alan Abad", "AM", 2, region_id=1, cluster_id=12, office_id=22),
        PersonIn(5, "Sam Stone", "FSV", 3, region_id=1, cluster_id=11, office_id=21),
        PersonIn(6, "Sue Smith", "FSV", 3, region_id=1, cluster_id=11, office_id=21),
        PersonIn(7, "Bob Beta", "FSV", 3, region_id=1, cluster_id=12, office_id=22),
        PersonIn(8, "Bea Bell", "FSV", 3, region_id=1, cluster_id=12, office_id=22),
    ]
    meet = EventIn(
        1, "MEET", "Area Meeting", visited_kind="cluster", typical_days=1, organizer_position="AM",
        positions=[EventPos("AM", "organizer"), EventPos("FSV", "participant"), EventPos("RM", "participant"),
                   EventPos("TRAIN", "participant")],
        rules=[ERule(1, "Q-MEET", "annual_quota", "cluster", period="year", min_count=6, max_count=6),
               ERule(2, "C-MEET", "cadence", "cluster", period="month", interval_n=2)])
    visit = EventIn(
        2, "VISIT", "Region Visit", visited_kind="cluster", typical_days=2, organizer_position="RM",
        positions=[EventPos("RM", "organizer"), EventPos("AM", "participant", travels=False),
                   EventPos("HEAD", "participant", yearly_limit=2)],
        rules=[ERule(3, "Q-VISIT", "annual_quota", "cluster", period="year", min_count=4, max_count=4)])
    conf = EventIn(
        3, "CONF", "Conference", is_company=True, visited_kind="nationwide", typical_days=2,
        positions=[EventPos("AM", "participant"), EventPos("RM", "participant"),
                   EventPos("HEAD", "participant", yearly_limit=1)],
        rules=[ERule(4, "Q-CONF", "annual_quota", "nationwide", period="year", min_count=1, max_count=1)])
    lakbay = EventIn(
        4, "LAKBAY", "Lakbay", visited_kind="region", typical_days=3, organizer_position="RM",
        positions=[EventPos("RM", "organizer"), EventPos("AM", "participant")],
        rules=[ERule(5, "Q-LKB", "annual_quota", "region", period="year", min_count=3, max_count=3,
                     params={"distinct_units": "cluster"})])
    manual_only = EventIn(5, "COURT", "Court visit", visited_kind="external", organizer_position="TRAIN")
    inp = Inputs(
        year=YEAR,
        regions=[UnitIn("region", 1, "North", lead_person_id=2, hub_office_id=21)],
        clusters=[UnitIn("cluster", 11, "Alpha 1", region_id=1, lead_person_id=3, hub_office_id=21),
                  UnitIn("cluster", 12, "Alpha 2", region_id=1, lead_person_id=4, hub_office_id=22)],
        offices=[UnitIn("local_office", 21, "Port One", region_id=1), UnitIn("local_office", 22, "Port Two", region_id=1)],
        people=people, events=[meet, visit, conf, lakbay, manual_only],
        general_rules=[ERule(6, "RM-MONTH", "period_cap", "position", position="RM", period="month", max_count=2)],
        merges={frozenset({1, 2})},
        blackouts=[BlackoutIn(1, "Conference month", date(YEAR, 4, 1), date(YEAR, 4, 30),
                              event_ids=frozenset({1}), cause_event_id=3)],
        positions=POSITIONS,
    )
    for k, v in changes.items():
        setattr(inp, k, v)
    return inp


def by_event(res, code):
    return [t for t in res.trips if t.event_code == code]


def test_weeks_are_whole_work_weeks_in_the_year():
    weeks = week_starts(YEAR)
    assert weeks[0] == date(2027, 1, 4) and weeks[0].weekday() == 0
    assert weeks[-1] == date(2027, 12, 27)          # Monday to Friday still inside the year
    assert len(weeks) == 52


def test_deterministic():
    a, b = generate(world()), generate(world())
    sig = lambda r: [(t.event_code, t.visited, t.start, t.end, sorted(t.participants)) for t in r.trips]  # noqa: E731
    assert sig(a) == sig(b) and len(a.trips) > 0


def test_counts_per_unit_follow_the_rules():
    res = generate(world())
    for cluster in (11, 12):
        assert len([t for t in by_event(res, "MEET") if t.visited == UnitRef("cluster", cluster)]) == 6
        assert len([t for t in by_event(res, "VISIT") if t.visited == UnitRef("cluster", cluster)]) == 4
    assert len(by_event(res, "CONF")) == 1
    assert "COURT" not in {t.event_code for t in res.trips}
    assert any("Court visit" in s for s in res.skipped)


def test_nothing_outside_the_year_or_on_weekends():
    for t in generate(world()).trips:
        assert t.start.year == YEAR and t.end.year == YEAR
        assert t.start.weekday() < 5


def test_conference_sits_in_its_blackout_and_meetings_stay_out():
    res = generate(world())
    conf = by_event(res, "CONF")[0]
    assert date(YEAR, 4, 1) <= conf.start <= conf.end <= date(YEAR, 4, 30)
    for t in by_event(res, "MEET"):
        assert not (t.start <= date(YEAR, 4, 30) and date(YEAR, 4, 1) <= t.end)
    assert not [w for w in res.warnings if w.code == "blackout"]


def test_block_blackout_is_never_used():
    inp = world(blackouts=[BlackoutIn(1, "No travel in June", date(YEAR, 6, 1), date(YEAR, 6, 30), severity="block")])
    res = generate(inp)
    assert res.trips and all(not (t.start <= date(YEAR, 6, 30) and date(YEAR, 6, 1) <= t.end) for t in res.trips)


def test_region_visit_merges_into_area_meeting():
    res = generate(world())
    meetings = {t.key: t for t in by_event(res, "MEET")}
    merged = [t for t in by_event(res, "VISIT") if t.absorbed_into]
    assert merged, "at least some visits should be combined with an area meeting"
    for v in merged:
        m = meetings[v.absorbed_into]
        assert (v.start, v.end) == (m.start, m.end) and v.visited == m.visited
        assert m.participants[2][0] == "traveler"          # the RM joined the meeting
        assert any("Region Visit" in note for note in m.notes)
    # each meeting absorbs at most one visit
    assert len({v.absorbed_into for v in merged}) == len(merged)


def test_visited_team_are_hosts_who_do_not_travel():
    res = generate(world(merges=set()))
    visit = by_event(res, "VISIT")[0]
    assert visit.participants[2] == ("organizer", True)
    assert visit.participants[3][1] is False or visit.participants[4][1] is False


def test_head_joins_only_up_to_the_yearly_limit_and_spread_out():
    res = generate(world(merges=set()))
    head_visits = [t for t in by_event(res, "VISIT") if 1 in t.participants]
    assert len(head_visits) == 2
    assert abs((head_visits[0].start - head_visits[1].start).days) > 60
    assert sum(1 for t in by_event(res, "CONF") if 1 in t.participants) == 1


def test_limit_is_spent_on_the_surviving_trip_when_the_event_is_merged():
    res = generate(world())          # every region visit is combined with an area meeting here
    surviving_with_head = [t for t in by_event(res, "MEET") if 1 in t.participants]
    assert len(surviving_with_head) == 2


def test_managers_above_the_organizer_do_not_join_by_default():
    res = generate(world())
    plain = [t for t in by_event(res, "MEET") if not any("Region Visit" in n for n in t.notes)]
    assert plain and all(2 not in t.participants for t in plain)   # the RM is not at every area meeting


def test_lakbay_needs_distinct_clusters_and_says_so():
    res = generate(world())
    lakbay = by_event(res, "LAKBAY")
    assert len(lakbay) == 2 and {t.visited for t in lakbay} == {UnitRef("cluster", 11), UnitRef("cluster", 12)}
    assert any("3 different clusters" in u for u in res.unplaced)


def test_no_traveler_is_in_two_trips_at_once():
    res = generate(world())
    assert not [w for w in res.warnings if w.code == "overlap"]


def test_existing_trips_count_toward_the_quota():
    kept = TripView(900, 1, UnitRef("cluster", 11), date(YEAR, 9, 14), date(YEAR, 9, 14), {3: ("organizer", True)},
                    status="planned")
    res = generate(world(kept=[kept]))
    assert len([t for t in by_event(res, "MEET") if t.visited == UnitRef("cluster", 11)]) == 5
    assert len([t for t in by_event(res, "MEET") if t.visited == UnitRef("cluster", 12)]) == 6
    assert not [w for w in res.warnings if w.code == "quota_short" and "Area Meeting" in w.message]


def test_evaluate_finds_limit_overlap_and_blackout_problems():
    inp = world()
    d = lambda m, day: date(YEAR, m, day)  # noqa: E731
    trips = [
        TripView(1, 2, UnitRef("cluster", 11), d(5, 4), d(5, 5), {2: ("organizer", True)}),
        TripView(2, 2, UnitRef("cluster", 12), d(5, 11), d(5, 12), {2: ("organizer", True)}),
        TripView(3, 2, UnitRef("cluster", 11), d(5, 18), d(5, 19), {2: ("organizer", True)}),   # third RM trip in May
        TripView(4, 1, UnitRef("cluster", 11), d(4, 13), d(4, 13), {3: ("organizer", True)}),   # meeting in the blackout
        TripView(5, 1, UnitRef("cluster", 12), d(6, 8), d(6, 8), {4: ("organizer", True)}),
        TripView(6, 3, UnitRef("nationwide"), d(6, 8), d(6, 9), {4: ("traveler", True)}),        # Alan twice on June 8
    ]
    codes = {w.code for w in evaluate(trips, inp)}
    assert {"period_cap", "blackout", "overlap", "quota_short"} <= codes
    msg = next(w.message for w in evaluate(trips, inp) if w.code == "period_cap")
    assert "Rita Rivera has 3 trips in May 2027 (limit 2)" in msg


def test_absorbed_and_cancelled_trips_do_not_count_as_travel():
    inp = world()
    trips = [
        TripView(1, 2, UnitRef("cluster", 11), date(YEAR, 5, 4), date(YEAR, 5, 5), {2: ("organizer", True)}),
        TripView(2, 2, UnitRef("cluster", 11), date(YEAR, 5, 11), date(YEAR, 5, 12), {2: ("organizer", True)}, absorbed=True),
        TripView(3, 2, UnitRef("cluster", 11), date(YEAR, 5, 18), date(YEAR, 5, 19), {2: ("organizer", True)},
                 status="cancelled"),
    ]
    assert not [w for w in evaluate(trips, inp) if w.code in ("period_cap", "overlap")]


@pytest.mark.parametrize("severity", ["info", "warn"])
def test_rules_with_other_severity_still_generate(severity):
    inp = world()
    inp.events[0].rules[0].severity = severity
    assert generate(inp).trips


def test_equal_rank_events_are_not_combined_and_it_is_reported():
    inp = world()
    inp.events[0].positions = inp.events[0].positions[:3]       # same number of participants as the visit
    res = generate(inp)
    assert not [t for t in res.trips if t.absorbed_into]
    assert any("neither is more important" in s for s in res.skipped)


def test_rules_held_every_second_year():
    from travel_planner.plan_engine import held_in, schedule_phrase

    biennial = {"every_n_years": 2, "first_year": 2027}
    assert [held_in(biennial, y) for y in (2026, 2027, 2028, 2029, 2030)] == [False, True, False, True, False]
    assert held_in({}, 2028) and held_in({"every_n_years": 1, "first_year": 2027}, 2028)
    assert schedule_phrase(biennial) == "every 2 years, starting in 2027" and schedule_phrase({}) == ""
