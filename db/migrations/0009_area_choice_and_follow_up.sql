-- 0009: two things the Head of Field asked for (see docs/04-travel-rules.md 4.9 and 4.10).
--  1. Choose the area later: a trip can hold a region slot first; the area is chosen shortly before the trip
--     (event_type.area_choice_days) and may be labelled diagnostic or benchmark (the "2 + 1" mix).
--  2. Follow-up of actions: up to three actions per trip with a due date, closed after the visit
--     (event_type.follow_up_days says when the follow-up is due after the trip ends).

ALTER TABLE travel.event_type
  ADD COLUMN area_choice_days smallint CHECK (area_choice_days IS NULL OR area_choice_days BETWEEN 1 AND 365),
  ADD COLUMN follow_up_days   smallint CHECK (follow_up_days   IS NULL OR follow_up_days   BETWEEN 1 AND 365);

ALTER TABLE travel.trip
  ADD COLUMN area_pending   boolean NOT NULL DEFAULT false,
  ADD COLUMN area_decide_by date,
  ADD COLUMN area_focus     text CHECK (area_focus IS NULL OR area_focus IN ('diagnostic', 'benchmark'));

CREATE TABLE travel.trip_action (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    trip_id     bigint NOT NULL REFERENCES travel.trip(id) ON DELETE CASCADE,
    title       text   NOT NULL CHECK (length(title) BETWEEN 3 AND 300),
    due_date    date   NOT NULL,
    status      text   NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'done', 'dropped')),
    close_note  text,
    created_by  integer REFERENCES travel.person(id),
    created_at  timestamptz NOT NULL DEFAULT now(),
    closed_by   integer REFERENCES travel.person(id),
    closed_at   timestamptz
);
CREATE INDEX trip_action_trip_idx ON travel.trip_action(trip_id);

-- Starting configuration
UPDATE travel.event_type SET area_choice_days = 60 WHERE code = 'SPECIAL-AREA';
UPDATE travel.event_type SET follow_up_days = 30 WHERE code IN ('SPECIAL-AREA', 'REGIONAL-FIELD-MEET', 'HEAD-AREA');

-- The "2 + 1" rule: of the Special Area visits of a year, at most two are diagnostic and one is a benchmark
UPDATE travel.rule SET params = params || '{"area_mix": {"diagnostic": 2, "benchmark": 1}}'::jsonb
WHERE rule_key = 'SA-QUOTA' AND active;
