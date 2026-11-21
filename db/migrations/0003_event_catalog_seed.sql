-- 0003: starting event catalog, taken from the "Events description" and "Position rules" sheets of the
-- Traveling Calendar template, the 2027 Travel Plans, and the meeting notes. It is only a starting point:
-- administrators edit all of it in the app. See docs/04-travel-rules.md.

-- Supporting functions that join or run events (not part of the field hierarchy)
INSERT INTO travel.position (code, name, level, function_area, is_traveler) VALUES
  ('COORD', 'Field Coordinator',                    4, 'support',  true),
  ('LEGAL', 'Legal Collections',                    4, 'legal',    true),
  ('QA',    'Quality (Field QA)',                   4, 'quality',  true),
  ('TRAIN', 'Training',                             4, 'training', true),
  ('HR',    'HR',                                   4, 'hr',       true),
  ('HOC',   'Head of Collections / Support',        4, 'support',  true)
ON CONFLICT (code) DO NOTHING;

-- Event types ---------------------------------------------------------------------------------------------
INSERT INTO travel.event_type
  (code, name, description, organizer_position_id, visited_kind, joint_visit, is_company_event,
   typical_days, typical_mode, scheduling_notes)
SELECT v.code, v.name, v.descr, p.id, v.visited, v.joint, v.company, v.days::smallint, v.mode, v.notes
FROM (VALUES
 ('AM-FSV-VISIT','Area Visit','Area Manager visits the field supervisors of the cluster.','AM','cluster','no',false,2,NULL,
  '1 or 2 days for 1:1 meetings with each supervisor.'),
 ('AM-FSV-MEET','Area Management Meeting','Team meeting of the Area Manager with the supervisors of the cluster.','AM','cluster','partial',false,1,NULL,
  'Not in the month of the conference or the year-end party. Participants: Regional Manager, Quality, Training.'),
 ('RM-AM-VISIT','Region Visit','Regional Manager visits an Area Manager.','RM','cluster','no',false,2,NULL,
  '1 or 2 days for 1:1 with the Area Manager. The Head of Field may join to anchor on regional hubs; pair with 1 to 2 area spot checks.'),
 ('RM-AM-MEET','Region Management Meeting','Regional Manager meets the Area Managers of the region.','RM','cluster','partial',false,2,NULL,
  'Rotate through 4 to 5 areas per region each quarter (1 to 2 areas a month). Not in the month of the conference or the year-end party.'),
 ('LAKBAY','Collection Lakbay Regional Visit','Regional roadshow merged with the Area Meeting and the Region Management Meeting.','RM','region','yes',false,3,NULL,
  'Three times a year in three different areas of a region. For the Regional Manager and the Area Managers of that region, not nationwide.'),
 ('CONF','Collection Conference','Nationwide conference, merged with the Area Meeting.',NULL,'nationwide','yes',true,2,'air_land',
  'Once a year. Blocks area and region meetings in its month.'),
 ('YEAR-END','Year-End / Kick-Off Party','Year-end or kick-off party attended by Area Managers and supervisors.','AM','cluster','partial',true,2,NULL,
  'November, December or January. One per cluster. Blocks area and region meetings in its month.'),
 ('FLCU',E'Field Leader''s Collections University','Leadership training for Regional Managers, Area Managers and supervisors.','TRAIN','cluster','yes',false,2,NULL,
  'Twice a year (first and second half). Cluster by region where possible.'),
 ('TQACE-AWARE','TQACE Awareness Campaign','Local awareness campaign run with Quality and Training.','TRAIN','local_office','yes',false,1,NULL,NULL),
 ('NEGOTIATION-P3','Phase 3: Negotiation Skills Training','Local negotiation skills training.','TRAIN','local_office','yes',false,1,NULL,NULL),
 ('COURT-VISIT','Court Visit','Legal operations manager or head of legal visits a court.','LEGAL','external','no',false,1,NULL,NULL),
 ('COURT-HEARING','Court Filing / Hearing','Legal specialist and field supervisor attend a filing or hearing.','LEGAL','external','no',false,1,NULL,NULL),
 ('HEAD-AREA','Head of Field area tour','Head of Field meets the supervisors of each area once a year, grouped into multi-stop trips.','HEAD','local_office','no',false,3,'mixed',
  'From the 2027 Travel Plans: for example Mindanao in two legs of 3 days and 2 nights. Merged with the Area Management Meeting when it takes place in the same area.'),
 ('REGIONAL-FIELD-MEET','Regional Field Meeting','Head of Field with Regional Managers, Area Managers and coordinators of a region.','HEAD','region','no',false,3,'air_land',
  'From the 2027 budget and Travel Plans.'),
 ('LO-VISIT','Local office visit','Supervisor travels to the local office for business-trip-order (BTO) tasks.','FSV','local_office','no',false,1,'land',
  'Transportation cost, not a business trip.')
) AS v(code, name, descr, org, visited, joint, company, days, mode, notes)
LEFT JOIN travel.position p ON p.code = v.org
ON CONFLICT (code) DO NOTHING;

-- Who takes part (organizer / participant) and yearly limits (the "2x", "3x" cells) --------------------------
INSERT INTO travel.event_type_position (event_type_id, position_id, participation, yearly_limit)
SELECT e.id, p.id, v.participation, v.lim::smallint
FROM (VALUES
 ('AM-FSV-VISIT','AM','organizer',NULL),
 ('AM-FSV-VISIT','FSV','participant',NULL),
 ('AM-FSV-MEET','AM','organizer',NULL), ('AM-FSV-MEET','RM','participant',NULL),
 ('AM-FSV-MEET','QA','participant',NULL), ('AM-FSV-MEET','TRAIN','participant',NULL),
 ('AM-FSV-MEET','FSV','participant',NULL),
 ('RM-AM-VISIT','RM','organizer',NULL), ('RM-AM-VISIT','HEAD','participant',2),
 ('RM-AM-VISIT','AM','participant',NULL),
 ('RM-AM-MEET','RM','organizer',NULL), ('RM-AM-MEET','HEAD','participant',3),
 ('RM-AM-MEET','LEGAL','participant',NULL), ('RM-AM-MEET','AM','participant',NULL),
 ('LAKBAY','RM','organizer',NULL), ('LAKBAY','AM','participant',NULL), ('LAKBAY','HEAD','participant',3),
 ('LAKBAY','COORD','participant',NULL), ('LAKBAY','LEGAL','participant',NULL), ('LAKBAY','QA','participant',NULL),
 ('LAKBAY','TRAIN','participant',NULL), ('LAKBAY','HR','participant',NULL), ('LAKBAY','HOC','participant',NULL),
 ('CONF','AM','participant',NULL), ('CONF','RM','participant',NULL), ('CONF','HEAD','participant',1),
 ('CONF','COORD','participant',NULL), ('CONF','LEGAL','participant',NULL), ('CONF','QA','participant',NULL),
 ('CONF','TRAIN','participant',NULL), ('CONF','HR','participant',NULL), ('CONF','HOC','participant',NULL),
 ('YEAR-END','AM','organizer',NULL), ('YEAR-END','RM','participant',NULL), ('YEAR-END','HEAD','participant',3),
 ('YEAR-END','TRAIN','participant',2),
 ('FLCU','TRAIN','organizer',NULL), ('FLCU','HR','participant',NULL), ('FLCU','RM','participant',NULL),
 ('FLCU','AM','participant',NULL), ('FLCU','FSV','participant',NULL),
 ('TQACE-AWARE','TRAIN','organizer',NULL), ('TQACE-AWARE','QA','participant',NULL), ('TQACE-AWARE','FSV','participant',NULL),
 ('NEGOTIATION-P3','TRAIN','organizer',NULL),
 ('COURT-VISIT','LEGAL','organizer',NULL),
 ('COURT-HEARING','LEGAL','organizer',NULL), ('COURT-HEARING','FSV','participant',NULL),
 ('HEAD-AREA','HEAD','organizer',NULL), ('HEAD-AREA','FSV','participant',NULL),
 ('REGIONAL-FIELD-MEET','HEAD','organizer',NULL), ('REGIONAL-FIELD-MEET','RM','participant',NULL),
 ('REGIONAL-FIELD-MEET','AM','participant',NULL), ('REGIONAL-FIELD-MEET','COORD','participant',NULL),
 ('LO-VISIT','FSV','organizer',NULL)
) AS v(ev, pos, participation, lim)
JOIN travel.event_type e ON e.code = v.ev
JOIN travel.position p ON p.code = v.pos
ON CONFLICT DO NOTHING;

-- Rules (version 1) ---------------------------------------------------------------------------------------
INSERT INTO travel.rule
  (rule_key, version, event_type_id, rule_type, scope_kind, position_id, period, interval_n,
   min_count, max_count, params, severity, description, valid_from)
SELECT v.rule_key, 1, e.id, v.rule_type, v.scope_kind, p.id, v.period, v.interval_n::smallint,
       v.min_count::smallint, v.max_count::smallint, v.params::jsonb, v.severity, v.descr, DATE '2027-01-01'
FROM (VALUES
 ('AMV-QUOTA',  'AM-FSV-VISIT','annual_quota','cluster',NULL,'year',NULL,6,12,'{}','warn','Six to twelve area visits per cluster a year (monthly or bi-monthly).'),
 ('AMV-CADENCE','AM-FSV-VISIT','cadence','cluster',NULL,'month',2,NULL,NULL,'{}','info','Default spacing used by the generator: bi-monthly.'),
 ('AMM-QUOTA',  'AM-FSV-MEET','annual_quota','cluster',NULL,'year',NULL,6,6,'{}','warn','Six area meetings per cluster a year.'),
 ('AMM-CADENCE','AM-FSV-MEET','cadence','cluster',NULL,'month',2,NULL,NULL,'{}','info','Bi-monthly.'),
 ('RMV-QUOTA',  'RM-AM-VISIT','annual_quota','cluster',NULL,'year',NULL,4,4,'{}','warn','Quarterly: four region visits per Area Manager a year.'),
 ('RMV-CADENCE','RM-AM-VISIT','cadence','cluster',NULL,'quarter',1,NULL,NULL,'{}','info','Quarterly.'),
 ('RMM-QUOTA',  'RM-AM-MEET','annual_quota','cluster',NULL,'year',NULL,3,3,'{}','warn','Three region management meetings per cluster a year (about 12 to 15 per region).'),
 ('RMM-CADENCE','RM-AM-MEET','cadence','cluster',NULL,'month',4,NULL,NULL,'{}','info','Every four months.'),
 ('RMM-ROTATION','RM-AM-MEET','rotation','region',NULL,'quarter',NULL,4,5,'{"unit":"cluster","unit_count_min":4,"unit_count_max":5}','info','Rotate through 4 to 5 clusters per region each quarter (1 to 2 a month), without repeating until all are covered.'),
 ('LKB-QUOTA',  'LAKBAY','annual_quota','region',NULL,'year',NULL,3,3,'{"distinct_units":"cluster"}','warn','Three Lakbay visits a year, in three different clusters of the region.'),
 ('CONF-QUOTA', 'CONF','annual_quota','nationwide',NULL,'year',NULL,1,1,'{}','warn','One conference a year.'),
 ('YEP-QUOTA',  'YEAR-END','annual_quota','cluster',NULL,'year',NULL,1,1,'{}','warn','One year-end or kick-off party per cluster.'),
 ('YEP-WINDOW', 'YEAR-END','preferred_window','nationwide',NULL,NULL,NULL,NULL,NULL,'{"months":[11,12,1]}','info','November, December or January.'),
 ('FLCU-CADENCE','FLCU','cadence','cluster',NULL,'half_year',1,NULL,NULL,'{"cluster_by":"region"}','info','Once in each half of the year; group clusters of the same region.'),
 ('FLCU-QUOTA', 'FLCU','annual_quota','cluster',NULL,'year',NULL,2,2,'{}','warn','Two sessions per cluster a year (about 28 sessions in total).'),
 ('HDA-QUOTA',  'HEAD-AREA','annual_quota','local_office',NULL,'year',NULL,1,1,'{}','warn','The Head of Field meets every local office once a year.'),
 ('RFM-CADENCE','REGIONAL-FIELD-MEET','cadence','region',NULL,'quarter',1,NULL,NULL,'{}','info','Labelled quarterly in the source; confirm whether it is per region.'),
 (NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL)
) AS v(rule_key, ev, rule_type, scope_kind, pos, period, interval_n, min_count, max_count, params, severity, descr)
LEFT JOIN travel.event_type e ON e.code = v.ev
LEFT JOIN travel.position p ON p.code = v.pos
WHERE v.rule_key IS NOT NULL;

-- Rules across event types: caps per traveler
INSERT INTO travel.rule
  (rule_key, version, event_type_id, rule_type, scope_kind, position_id, period, max_count, severity, description, valid_from)
SELECT 'RM-TRIPS-MONTH', 1, NULL, 'period_cap', 'position', p.id, 'month', 2, 'warn',
       'A Regional Manager can have two business trips a month.', DATE '2027-01-01'
FROM travel.position p WHERE p.code = 'RM';
INSERT INTO travel.rule
  (rule_key, version, event_type_id, rule_type, scope_kind, position_id, period, max_count, severity, description, valid_from)
SELECT 'HEAD-TRIPS-MONTH', 1, NULL, 'period_cap', 'position', p.id, 'month', 1, 'warn',
       'The Head of Field ideally travels once a month, with exceptions.', DATE '2027-01-01'
FROM travel.position p WHERE p.code = 'HEAD';

-- Merge rules ("A is combined with B") ------------------------------------------------------------------------
INSERT INTO travel.merge_rule (event_type_id, merges_into_id, condition_text, severity)
SELECT a.id, b.id, v.cond, 'info'
FROM (VALUES
 ('RM-AM-VISIT','AM-FSV-MEET','When a Regional Manager visits an area, combine it with the Area Management Meeting.'),
 ('HEAD-AREA','AM-FSV-MEET','When the Head of Field visits an area, combine it with the Area Management Meeting.'),
 ('LAKBAY','AM-FSV-MEET','A Lakbay visit is combined with the Area Management Meeting.'),
 ('LAKBAY','RM-AM-MEET','A Lakbay visit is combined with the Region Management Meeting.'),
 ('CONF','AM-FSV-MEET','The conference is combined with the Area Meeting.')
) AS v(a, b, cond)
JOIN travel.event_type a ON a.code = v.a
JOIN travel.event_type b ON b.code = v.b
ON CONFLICT DO NOTHING;

-- Plan year 2027 and tentative blackouts (months are placeholders from the 2027 Travel Plans) ---------------------
INSERT INTO travel.plan_year (year) VALUES (2027) ON CONFLICT DO NOTHING;

INSERT INTO travel.blackout_period (plan_year, name, start_date, end_date, reason, severity)
VALUES
 (2027, 'Collection Conference month (tentative)', DATE '2027-04-01', DATE '2027-04-30',
  'Tentative: the Travel Plans put the conference in April 2027. Confirm the dates.', 'warn'),
 (2027, 'Year-end party month (tentative)', DATE '2027-12-01', DATE '2027-12-31',
  'Tentative: the Travel Plans put the party in December 2027. Confirm the dates.', 'warn');

INSERT INTO travel.blackout_event_type (blackout_id, event_type_id)
SELECT b.id, e.id
FROM travel.blackout_period b
JOIN travel.event_type e ON e.code IN ('AM-FSV-MEET', 'RM-AM-MEET')
WHERE b.plan_year = 2027;
