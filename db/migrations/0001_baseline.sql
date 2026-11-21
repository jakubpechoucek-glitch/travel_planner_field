-- =============================================================================
-- Travel Planner for Field Teams: baseline migration 0001
-- Target: PostgreSQL 15+ (Databricks Lakebase compatible). No extensions needed.
-- See docs/06-data-model.md for the explanation of every table.
-- E-mail addresses are NOT stored; users are matched by a keyed hash (sso_key_hash).
-- =============================================================================

CREATE SCHEMA IF NOT EXISTS travel;
SET search_path = travel, public;

-- -----------------------------------------------------------------------------
-- 1. Organization
-- -----------------------------------------------------------------------------

CREATE TABLE position (
    id            integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    code          text     NOT NULL UNIQUE,
    name          text     NOT NULL,
    level         smallint NOT NULL,                -- 0 = top of hierarchy; used by rules
    function_area text     NOT NULL DEFAULT 'field'
                  CHECK (function_area IN ('field','training','quality','legal','hr','support','other')),
    is_traveler   boolean  NOT NULL DEFAULT true,   -- false for field collectors (FTEs)
    active        boolean  NOT NULL DEFAULT true
);

-- Geography used for planning: region -> cluster, and local offices (travel hubs).
CREATE TABLE org_unit (
    id        integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    parent_id integer REFERENCES org_unit(id),
    kind      text NOT NULL CHECK (kind IN ('region','cluster','local_office')),
    code      text NOT NULL,
    name      text NOT NULL,
    active    boolean NOT NULL DEFAULT true,
    UNIQUE (kind, code)
);
CREATE INDEX org_unit_parent_idx ON org_unit(parent_id);

-- City or province where a trip physically happens.
CREATE TABLE location (
    id              integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name            text NOT NULL,
    province        text,
    region_id       integer REFERENCES org_unit(id),
    local_office_id integer REFERENCES org_unit(id),
    active          boolean NOT NULL DEFAULT true,
    UNIQUE (name, province)
);

-- Identity of an employee. Contact numbers and e-mail addresses are intentionally NOT stored.
CREATE TABLE person (
    id          integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    employee_no text UNIQUE,
    full_name   text NOT NULL,
    sso_key_hash text UNIQUE,                        -- HMAC-SHA256(lower(sso e-mail)); the e-mail itself is never stored
    active      boolean NOT NULL DEFAULT true,
    start_date  date,
    end_date    date,
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now(),
    CHECK (end_date IS NULL OR start_date IS NULL OR end_date >= start_date)
);

-- Effective-dated position, manager and unit of a person.
CREATE TABLE person_assignment (
    id              integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    person_id       integer NOT NULL REFERENCES person(id),
    position_id     integer NOT NULL REFERENCES position(id),
    manager_id      integer REFERENCES person(id),
    region_id       integer REFERENCES org_unit(id),
    cluster_id      integer REFERENCES org_unit(id),
    local_office_id integer REFERENCES org_unit(id),
    valid_from      date NOT NULL,
    valid_to        date,                            -- NULL = open ended
    CHECK (valid_to IS NULL OR valid_to >= valid_from),
    CHECK (manager_id IS NULL OR manager_id <> person_id),
    UNIQUE (person_id, valid_from)
);
CREATE INDEX person_assignment_person_idx  ON person_assignment(person_id, valid_from);
CREATE INDEX person_assignment_manager_idx ON person_assignment(manager_id);
CREATE INDEX person_assignment_cluster_idx ON person_assignment(cluster_id);

-- Supervisors that meet together (an AM can have several groups).
CREATE TABLE meeting_group (
    id              integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name            text NOT NULL,
    manager_id      integer NOT NULL REFERENCES person(id),
    cluster_id      integer REFERENCES org_unit(id),
    local_office_id integer REFERENCES org_unit(id),
    active          boolean NOT NULL DEFAULT true
);
CREATE TABLE meeting_group_member (
    meeting_group_id integer NOT NULL REFERENCES meeting_group(id) ON DELETE CASCADE,
    person_id        integer NOT NULL REFERENCES person(id),
    PRIMARY KEY (meeting_group_id, person_id)
);

-- -----------------------------------------------------------------------------
-- 2. Application access
-- -----------------------------------------------------------------------------

CREATE TABLE user_role (
    id                integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    person_id         integer NOT NULL REFERENCES person(id),
    role              text NOT NULL CHECK (role IN
                      ('viewer','area_planner','regional_planner','national_planner',
                       'function_planner','coordinator','administrator')),
    scope_org_unit_id integer REFERENCES org_unit(id),   -- NULL = global / own function
    created_at        timestamptz NOT NULL DEFAULT now(),
    UNIQUE (person_id, role, scope_org_unit_id)
);

-- -----------------------------------------------------------------------------
-- 3. Event types and rules
-- -----------------------------------------------------------------------------

CREATE TABLE event_type (
    id                    integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    code                  text NOT NULL UNIQUE,
    name                  text NOT NULL,
    description           text,
    organizer_position_id integer REFERENCES position(id),
    visited_kind          text NOT NULL DEFAULT 'cluster'
                          CHECK (visited_kind IN ('local_office','cluster','region','nationwide','external')),
    joint_visit           text NOT NULL DEFAULT 'no' CHECK (joint_visit IN ('no','partial','yes')),
    is_company_event      boolean NOT NULL DEFAULT false,   -- conference, year-end party
    typical_days          smallint,
    typical_mode          text CHECK (typical_mode IN ('land','air','sea','air_land','air_sea','mixed')),
    scheduling_notes      text,
    active                boolean NOT NULL DEFAULT true
);

-- Who takes part in an event type; optional yearly limit (the "3x" cells).
CREATE TABLE event_type_position (
    event_type_id integer NOT NULL REFERENCES event_type(id) ON DELETE CASCADE,
    position_id   integer NOT NULL REFERENCES position(id),
    participation text NOT NULL DEFAULT 'participant' CHECK (participation IN ('organizer','participant')),
    yearly_limit  smallint CHECK (yearly_limit IS NULL OR yearly_limit >= 0),
    PRIMARY KEY (event_type_id, position_id)
);

-- Versioned rules: one row per version of a rule_key.
CREATE TABLE rule (
    id            integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    rule_key      text NOT NULL,
    version       integer NOT NULL DEFAULT 1,
    event_type_id integer REFERENCES event_type(id),       -- NULL = applies across event types
    rule_type     text NOT NULL CHECK (rule_type IN
                  ('cadence','annual_quota','participation_cap','period_cap',
                   'preferred_window','rotation','concurrency_cap')),
    scope_kind    text NOT NULL CHECK (scope_kind IN
                  ('person','position','local_office','cluster','region','nationwide')),
    position_id   integer REFERENCES position(id),         -- for person/position-scoped caps
    period        text CHECK (period IN ('week','month','quarter','half_year','year')),
    interval_n    smallint,                                -- cadence: every N periods
    min_count     smallint,
    max_count     smallint,
    params        jsonb NOT NULL DEFAULT '{}'::jsonb,      -- e.g. {"months":[11,12,1],"rotate_per_quarter":[4,5]}
    severity      text NOT NULL DEFAULT 'warn' CHECK (severity IN ('block','warn','info')),
    description   text,
    valid_from    date NOT NULL,
    valid_to      date,
    active        boolean NOT NULL DEFAULT true,
    UNIQUE (rule_key, version),
    CHECK (min_count IS NULL OR max_count IS NULL OR max_count >= min_count),
    CHECK (valid_to IS NULL OR valid_to >= valid_from)
);
CREATE INDEX rule_event_type_idx ON rule(event_type_id);

-- "Event A is merged into event B when ..." (RM visit merges with area meeting).
CREATE TABLE merge_rule (
    id                  integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    event_type_id       integer NOT NULL REFERENCES event_type(id),
    merges_into_id      integer NOT NULL REFERENCES event_type(id),
    condition_text      text,
    severity            text NOT NULL DEFAULT 'info' CHECK (severity IN ('block','warn','info')),
    active              boolean NOT NULL DEFAULT true,
    CHECK (event_type_id <> merges_into_id),
    UNIQUE (event_type_id, merges_into_id)
);

-- -----------------------------------------------------------------------------
-- 4. Plan years, blackouts, trips
-- -----------------------------------------------------------------------------

CREATE TABLE plan_year (
    year         smallint PRIMARY KEY,
    status       text NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','review','published','closed')),
    published_at timestamptz,
    published_by integer REFERENCES person(id)
);

CREATE TABLE blackout_period (
    id         integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    plan_year  smallint NOT NULL REFERENCES plan_year(year),
    name       text NOT NULL,
    start_date date NOT NULL,
    end_date   date NOT NULL,
    reason     text,
    severity   text NOT NULL DEFAULT 'warn' CHECK (severity IN ('block','warn','info')),
    CHECK (end_date >= start_date)
);
-- Event types affected by a blackout. No rows = all event types.
CREATE TABLE blackout_event_type (
    blackout_id   integer NOT NULL REFERENCES blackout_period(id) ON DELETE CASCADE,
    event_type_id integer NOT NULL REFERENCES event_type(id),
    PRIMARY KEY (blackout_id, event_type_id)
);

CREATE TABLE trip (
    id                   bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    plan_year            smallint NOT NULL REFERENCES plan_year(year),
    event_type_id        integer NOT NULL REFERENCES event_type(id),
    title                text NOT NULL,
    visited_org_unit_id  integer REFERENCES org_unit(id),
    location_id          integer REFERENCES location(id),
    start_date           date NOT NULL,
    end_date             date NOT NULL,
    status               text NOT NULL DEFAULT 'generated'
                         CHECK (status IN ('generated','planned','requested','approved','completed','cancelled')),
    source               text NOT NULL DEFAULT 'manual' CHECK (source IN ('generated','manual')),
    rule_id              integer REFERENCES rule(id),            -- rule version that generated it
    generated_start_date date,                                   -- original rule-based values
    generated_end_date   date,
    merged_into_trip_id  bigint REFERENCES trip(id),
    transport_mode       text CHECK (transport_mode IN ('land','air','sea','air_land','air_sea','mixed')),
    purpose              text,
    notes                text,
    sap_request_no       text,                                   -- Phase 2
    completed_at         timestamptz,
    completion_note      text,
    cancel_reason        text,
    created_by           integer REFERENCES person(id),
    created_at           timestamptz NOT NULL DEFAULT now(),
    updated_by           integer REFERENCES person(id),
    updated_at           timestamptz NOT NULL DEFAULT now(),
    CHECK (end_date >= start_date),
    CHECK (status <> 'cancelled' OR cancel_reason IS NOT NULL),
    CHECK (merged_into_trip_id IS NULL OR merged_into_trip_id <> id)
);
CREATE INDEX trip_dates_idx       ON trip(start_date, end_date);
CREATE INDEX trip_year_event_idx  ON trip(plan_year, event_type_id);
CREATE INDEX trip_unit_idx        ON trip(visited_org_unit_id);
CREATE INDEX trip_location_idx    ON trip(location_id, start_date);

CREATE TABLE trip_participant (
    trip_id   bigint  NOT NULL REFERENCES trip(id) ON DELETE CASCADE,
    person_id integer NOT NULL REFERENCES person(id),
    role      text    NOT NULL DEFAULT 'traveler' CHECK (role IN ('organizer','traveler','host')),
    travels   boolean NOT NULL DEFAULT true,           -- false for local hosts/attendees
    PRIMARY KEY (trip_id, person_id)
);
CREATE INDEX trip_participant_person_idx ON trip_participant(person_id);

-- Itinerary legs (Phase 2), e.g. "T1 / L1" in the source plan.
CREATE TABLE trip_leg (
    id               bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    trip_id          bigint NOT NULL REFERENCES trip(id) ON DELETE CASCADE,
    seq              smallint NOT NULL,
    from_location_id integer REFERENCES location(id),
    to_location_id   integer REFERENCES location(id),
    mode             text CHECK (mode IN ('land','air','sea')),
    leg_date         date,
    UNIQUE (trip_id, seq)
);

-- Every change to a trip, with the mandatory reason for overrides.
CREATE TABLE trip_change (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    trip_id     bigint NOT NULL REFERENCES trip(id) ON DELETE CASCADE,
    changed_by  integer REFERENCES person(id),
    changed_at  timestamptz NOT NULL DEFAULT now(),
    change_type text NOT NULL CHECK (change_type IN
                ('created','generated','moved','resized','reassigned','merged','split','status','cancelled','edited')),
    category    text CHECK (category IN
                ('business_request','company_event_conflict','merged','capacity','budget','other')),
    reason      text,
    before_data jsonb,
    after_data  jsonb,
    CHECK (change_type IN ('created','generated') OR reason IS NOT NULL)
);
CREATE INDEX trip_change_trip_idx ON trip_change(trip_id, changed_at);

-- A planner acknowledged a rule warning when saving a trip.
CREATE TABLE warning_ack (
    id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    trip_id         bigint NOT NULL REFERENCES trip(id) ON DELETE CASCADE,
    rule_id         integer REFERENCES rule(id),
    warning_code    text NOT NULL,
    acknowledged_by integer REFERENCES person(id),
    acknowledged_at timestamptz NOT NULL DEFAULT now(),
    reason          text NOT NULL
);

-- -----------------------------------------------------------------------------
-- 5. Cost model (Phase 2) and audit
-- -----------------------------------------------------------------------------

CREATE TABLE cost_rate (
    id          integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    rate_kind   text NOT NULL CHECK (rate_kind IN
                ('airfare','sea_fare','land_transport','lodging_per_night','per_diem','local_transport','other')),
    mode        text CHECK (mode IN ('land','air','sea')),
    position_id integer REFERENCES position(id),
    amount      numeric(12,2) NOT NULL CHECK (amount >= 0),
    currency    char(3) NOT NULL DEFAULT 'PHP',
    valid_from  date NOT NULL,
    valid_to    date,
    note        text,
    CHECK (valid_to IS NULL OR valid_to >= valid_from)
);

CREATE TABLE audit_log (
    id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    at              timestamptz NOT NULL DEFAULT now(),
    actor_person_id integer REFERENCES person(id),
    action          text NOT NULL,          -- e.g. 'rule.update', 'user.role.add', 'plan.publish'
    entity          text NOT NULL,
    entity_id       text,
    details         jsonb
);
CREATE INDEX audit_log_at_idx ON audit_log(at DESC);

-- -----------------------------------------------------------------------------
-- 6. Views
-- -----------------------------------------------------------------------------

-- The assignment valid today for each active person.
CREATE VIEW v_person_current AS
SELECT p.id AS person_id, p.employee_no, p.full_name, p.active,
       a.position_id, pos.code AS position_code, pos.name AS position_name, pos.level,
       a.manager_id, a.region_id, a.cluster_id, a.local_office_id
FROM person p
JOIN person_assignment a
  ON a.person_id = p.id
 AND a.valid_from <= CURRENT_DATE
 AND (a.valid_to IS NULL OR a.valid_to >= CURRENT_DATE)
JOIN position pos ON pos.id = a.position_id
WHERE p.active;

-- Calendar feed: one row per traveling person per trip.
CREATE VIEW v_trip_calendar AS
SELECT t.id AS trip_id, t.plan_year, t.event_type_id, et.code AS event_code, et.name AS event_name,
       t.title, t.status, t.source, t.start_date, t.end_date,
       t.location_id, t.visited_org_unit_id,
       tp.person_id, tp.role
FROM trip t
JOIN event_type et ON et.id = t.event_type_id
JOIN trip_participant tp ON tp.trip_id = t.id AND tp.travels
WHERE t.status <> 'cancelled';

-- Trips per person and month (spreading multi-month trips by start month), for period caps.
CREATE VIEW v_person_trips_per_month AS
SELECT tp.person_id,
       date_trunc('month', t.start_date)::date AS month,
       count(*) AS trips,
       count(*) FILTER (WHERE t.source = 'manual') AS manual_trips
FROM trip t
JOIN trip_participant tp ON tp.trip_id = t.id AND tp.travels
WHERE t.status <> 'cancelled'
GROUP BY tp.person_id, date_trunc('month', t.start_date);
