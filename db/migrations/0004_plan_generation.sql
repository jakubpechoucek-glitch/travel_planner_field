-- 0004: what the plan generator needs to know in addition to the catalog.
--  * event_type_position.travels: whether this position travels for the event (a visited team is a host)
--  * blackout_period.caused_by_event_type_id: the event that creates the blackout (the conference month holds the conference)

ALTER TABLE travel.event_type_position ADD COLUMN travels boolean NOT NULL DEFAULT true;
ALTER TABLE travel.blackout_period     ADD COLUMN caused_by_event_type_id integer REFERENCES travel.event_type(id);

-- Visited teams are hosts: they do not travel for visits to them.
UPDATE travel.event_type_position etp SET travels = false
FROM travel.event_type e, travel.position p
WHERE etp.event_type_id = e.id AND etp.position_id = p.id
  AND ((e.code = 'AM-FSV-VISIT' AND p.code = 'FSV')
    OR (e.code = 'RM-AM-VISIT'  AND p.code = 'AM')
    OR (e.code = 'HEAD-AREA'    AND p.code = 'FSV'));

-- The tentative 2027 blackouts belong to the conference (April) and the year-end party (December).
UPDATE travel.blackout_period b SET caused_by_event_type_id = e.id
FROM travel.event_type e
WHERE b.plan_year = 2027 AND b.name LIKE 'Collection Conference month%' AND e.code = 'CONF';
UPDATE travel.blackout_period b SET caused_by_event_type_id = e.id
FROM travel.event_type e
WHERE b.plan_year = 2027 AND b.name LIKE 'Year-end party month%' AND e.code = 'YEAR-END';

CREATE INDEX trip_source_status_idx ON travel.trip(plan_year, source, status);

-- Corrections to the starting catalog found while generating the first plan ------------------------------------
-- 1. The Regional Field Meeting is held once per region a year, rotating through the quarters (Travel Plans:
--    Mindanao in February, Visayas in May, North Luzon in September). It is not 4 per region.
UPDATE travel.rule SET active = false, valid_to = GREATEST(valid_from, CURRENT_DATE - 1)
WHERE rule_key = 'RFM-CADENCE' AND version = 1 AND active;
INSERT INTO travel.rule (rule_key, version, event_type_id, rule_type, scope_kind, period, min_count, max_count,
                         severity, description, valid_from)
SELECT 'RFM-QUOTA', 1, e.id, 'annual_quota', 'region', 'year', 1, 1, 'warn',
       'One Regional Field Meeting per region a year; the regions rotate through the quarters.', DATE '2027-01-01'
FROM travel.event_type e
WHERE e.code = 'REGIONAL-FIELD-MEET'
  AND NOT EXISTS (SELECT 1 FROM travel.rule r WHERE r.rule_key = 'RFM-QUOTA');

-- 2. The year-end party is attended by the supervisors of the cluster (activity: Area Manager -> Supervisors).
INSERT INTO travel.event_type_position (event_type_id, position_id, participation, yearly_limit, travels)
SELECT e.id, p.id, 'participant', NULL, true
FROM travel.event_type e, travel.position p
WHERE e.code = 'YEAR-END' AND p.code = 'FSV'
ON CONFLICT DO NOTHING;
