-- 0008: events asked for by the Head of Field: Special Area visits with analysts, skip-level sessions,
-- cross-region peer shadowing and an off-year leadership alignment offsite; plus a yearly travel-load guardrail.
-- A starting configuration like 0003: administrators edit all of it in the app (Events and rules).
-- See docs/04-travel-rules.md (4.8) and docs/09-open-questions.md (K12 to K17).

INSERT INTO travel.position (code, name, level, function_area, is_traveler) VALUES
  ('ANALYST', 'Analyst', 4, 'other', true)
ON CONFLICT (code) DO NOTHING;

INSERT INTO travel.event_type
  (code, name, description, organizer_position_id, visited_kind, joint_visit, is_company_event,
   typical_days, typical_mode, scheduling_notes)
SELECT v.code, v.name, v.descr, p.id, v.visited, v.joint, v.company, v.days::smallint, v.mode, v.notes
FROM (VALUES
 ('SPECIAL-AREA','Special Area visit (with Analysts)',
  'The Head of Field and the Analysts spend time in one area to compare what the dashboards say with what happens on the floor.',
  'HEAD','region','partial',false,2,'mixed',
  'One per region a year, in open months (May, July, November). It counts as that region''s Head-to-region visit for the month, so it is combined with the Regional Field Meeting. Pick two diagnostic or turnaround areas and one benchmark area a year. Lock the region slot a year ahead and choose the area about 60 days before (the area is chosen by the planner; the slot lock is not in the application yet).'),
 ('SKIP-LEVEL','Skip-level session',
  'A 60 to 90 minute block of the Head of Field with supervisors and Area Managers without their direct manager in the room.',
  'HEAD','region','no',false,1,NULL,
  'Held during the Head of Field''s regional trips, so it is combined with the Regional Field Meeting. Twice a year per region.'),
 ('PEER-SHADOW','Cross-region peer shadow',
  'A Regional Manager joins a peer''s region visit in another region to borrow ideas and calibrate standards.',
  'RM','cluster','no',false,2,NULL,
  'One per Regional Manager a year. Added by hand: the application does not yet pick a place in "another region" automatically.'),
 ('STRAT','Leadership alignment offsite',
  'Two-day offsite of the Head of Field, the Regional Managers and the Analysts to reset annual KPIs and budgets.',
  'HEAD','nationwide','no',false,2,'air_land',
  'Held in the years without the conference: every 2 years, the first one in 2028. Preferably November. Does not pull the Area Managers off the floor.')
) AS v(code, name, descr, org, visited, joint, company, days, mode, notes)
LEFT JOIN travel.position p ON p.code = v.org
ON CONFLICT (code) DO NOTHING;

INSERT INTO travel.event_type_position (event_type_id, position_id, participation, yearly_limit, travels)
SELECT e.id, p.id, v.participation, NULL, v.travels
FROM (VALUES
 ('SPECIAL-AREA','HEAD','organizer',true),   ('SPECIAL-AREA','ANALYST','participant',true),
 ('SPECIAL-AREA','RM','participant',true),   ('SPECIAL-AREA','AM','participant',false),
 ('SKIP-LEVEL','HEAD','organizer',true),     ('SKIP-LEVEL','AM','participant',false),
 ('SKIP-LEVEL','FSV','participant',false),
 ('PEER-SHADOW','RM','organizer',true),      ('PEER-SHADOW','AM','participant',false),
 ('STRAT','HEAD','organizer',true),          ('STRAT','RM','participant',true),
 ('STRAT','ANALYST','participant',true)
) AS v(ev, pos, participation, travels)
JOIN travel.event_type e ON e.code = v.ev
JOIN travel.position p ON p.code = v.pos
ON CONFLICT DO NOTHING;

INSERT INTO travel.rule
  (rule_key, version, event_type_id, rule_type, scope_kind, position_id, period, interval_n,
   min_count, max_count, params, severity, description, valid_from)
SELECT v.rule_key, 1, e.id, v.rule_type, v.scope_kind, NULL, v.period, NULL,
       v.min_count::smallint, v.max_count::smallint, v.params::jsonb, v.severity, v.descr, DATE '2027-01-01'
FROM (VALUES
 ('SA-QUOTA',   'SPECIAL-AREA','annual_quota','region','year',1,1,'{}','warn','One Special Area visit per region a year.'),
 ('SA-WINDOW',  'SPECIAL-AREA','preferred_window','nationwide',NULL,NULL,NULL,'{"months":[5,7,11]}','info','Open months: May, July and November.'),
 ('SKIP-QUOTA', 'SKIP-LEVEL','annual_quota','region','year',2,2,'{}','info','Two skip-level sessions per region a year.'),
 ('STRAT-QUOTA','STRAT','annual_quota','nationwide','year',1,1,'{"every_n_years":2,"first_year":2028}','warn','One offsite in each year without the conference, starting in 2028.'),
 ('STRAT-WINDOW','STRAT','preferred_window','nationwide',NULL,NULL,NULL,'{"months":[11]}','info','Preferably November.')
) AS v(rule_key, ev, rule_type, scope_kind, period, min_count, max_count, params, severity, descr)
JOIN travel.event_type e ON e.code = v.ev;

-- Travel-load guardrail: the Head of Field's trips a year. New major events must replace or absorb a routine visit.
INSERT INTO travel.rule
  (rule_key, version, event_type_id, rule_type, scope_kind, position_id, period, max_count, severity, description, valid_from)
SELECT 'HEAD-TRIPS-YEAR', 1, NULL, 'period_cap', 'position', p.id, 'year', 16, 'warn',
       'The Head of Field travels at most 16 times a year. A new major event should replace or absorb a routine visit.',
       DATE '2027-01-01'
FROM travel.position p WHERE p.code = 'HEAD';

-- Merge rules: a Special Area visit counts as the region's Head visit; skip-level sessions happen on those trips
INSERT INTO travel.merge_rule (event_type_id, merges_into_id, condition_text, severity)
SELECT a.id, b.id, v.cond, 'info'
FROM (VALUES
 ('SPECIAL-AREA','REGIONAL-FIELD-MEET','A Special Area visit counts as the region''s Head visit for that month.'),
 ('SKIP-LEVEL','REGIONAL-FIELD-MEET','Skip-level sessions are held during the Head of Field''s regional trip.')
) AS v(a, b, cond)
JOIN travel.event_type a ON a.code = v.a
JOIN travel.event_type b ON b.code = v.b;
