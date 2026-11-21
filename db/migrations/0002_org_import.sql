-- 0002: support for the organization import.
--  * org_unit.lead_person_id: the person leading a region (RM) or a cluster (AM, or the RM when acting)
--  * person.name_key: normalized name used to match people that have no employee number
--  * reference data: the field-hierarchy positions

ALTER TABLE travel.org_unit ADD COLUMN lead_person_id integer REFERENCES travel.person(id);
ALTER TABLE travel.person   ADD COLUMN name_key text;
CREATE INDEX person_name_key_idx ON travel.person(name_key);
CREATE INDEX org_unit_lead_idx   ON travel.org_unit(lead_person_id);

INSERT INTO travel.position (code, name, level, function_area, is_traveler) VALUES
  ('HEAD', 'Head of Nationwide Field',  0, 'field', true),
  ('RM',   'Regional Manager',          1, 'field', true),
  ('AM',   'Area Manager',              2, 'field', true),
  ('SFSV', 'Senior Field Supervisor',   3, 'field', true),
  ('FSV2', 'Field Supervisor II',       3, 'field', true),
  ('FSV',  'Field Supervisor',          3, 'field', true),
  ('DM',   'Digital Mentor',            3, 'field', true),
  ('DSV',  'Digital Supervisor',        3, 'field', true)
ON CONFLICT (code) DO NOTHING;
