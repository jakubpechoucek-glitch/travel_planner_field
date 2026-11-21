-- 0010: synergy suggestions (two trips to the same place close in time). A planner can dismiss a suggestion,
-- so it does not come back. The pair is stored with the smaller trip id first.
CREATE TABLE travel.synergy_dismissal (
    trip_a_id    bigint NOT NULL REFERENCES travel.trip(id) ON DELETE CASCADE,
    trip_b_id    bigint NOT NULL REFERENCES travel.trip(id) ON DELETE CASCADE,
    reason       text,
    dismissed_by integer REFERENCES travel.person(id),
    dismissed_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (trip_a_id, trip_b_id),
    CHECK (trip_a_id < trip_b_id)
);
