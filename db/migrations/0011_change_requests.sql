-- 0011: "suggest a change". A person on a trip asks the planner of that trip to move it or to take them off it.
-- The planner decides (accepted or declined, with a note). The request itself changes nothing in the plan: an accepted
-- request is carried out by the planner as a normal change with a reason.
CREATE TABLE travel.change_request (
    id             bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    trip_id        bigint  NOT NULL REFERENCES travel.trip(id) ON DELETE CASCADE,
    requested_by   integer NOT NULL REFERENCES travel.person(id),
    kind           text    NOT NULL CHECK (kind IN ('move', 'cannot_attend', 'other')),
    message        text    NOT NULL CHECK (length(message) BETWEEN 3 AND 500),
    proposed_start date,
    proposed_end   date,
    status         text    NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'accepted', 'declined', 'withdrawn')),
    decided_by     integer REFERENCES travel.person(id),
    decided_at     timestamptz,
    decision_note  text,
    created_at     timestamptz NOT NULL DEFAULT now(),
    CHECK (proposed_end IS NULL OR proposed_start IS NULL OR proposed_end >= proposed_start),
    CHECK (status <> 'declined' OR decision_note IS NOT NULL)
);
CREATE INDEX change_request_trip_idx ON travel.change_request(trip_id, status);
-- one open request per person and trip
CREATE UNIQUE INDEX change_request_one_open ON travel.change_request(trip_id, requested_by) WHERE status = 'open';
