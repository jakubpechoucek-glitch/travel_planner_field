-- 0005: user administration.
-- A person can hold a global role (no scope) only once. The baseline UNIQUE constraint does not catch this,
-- because NULL scopes are all different from each other in PostgreSQL.
DELETE FROM travel.user_role a USING travel.user_role b
WHERE a.scope_org_unit_id IS NULL AND b.scope_org_unit_id IS NULL
  AND a.person_id = b.person_id AND a.role = b.role AND a.id > b.id;

CREATE UNIQUE INDEX user_role_global_uidx ON travel.user_role (person_id, role) WHERE scope_org_unit_id IS NULL;
