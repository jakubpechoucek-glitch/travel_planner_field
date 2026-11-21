-- 0006: cost forecast.
--  * rates: starting rate card taken from the formulas of the 2027 budget ("Per Budget Travelling (FC)"):
--      unit price = air fare + nights x lodging + local transport + days x per diem
--      e.g. Area Manager by plane, 3 days: 20,000 + 2 x 3,000 + 2,500 + 3 x 600 = 30,300 (the budget's unit price)
--  * travel_mode: how people travel between regions (air or land); loaded by the application (suggested, editable)
--  * travel_mode_override: a destination that always needs another mode (an island), optionally from one region only
--  * app_setting: where the Head is based and where nationwide events are held
--  * booking_discount: cheaper air fares when booked early (tiers are entered by the business, none are assumed)
--  * budget_line: the budget lines of a plan year, to compare with the forecast

INSERT INTO travel.cost_rate (rate_kind, mode, position_id, amount, currency, valid_from, note)
VALUES
  ('airfare',           'air', NULL, 20000, 'PHP', DATE '2027-01-01', 'Round-trip air ticket (2027 budget)'),
  ('local_transport',   NULL,  NULL,  2500, 'PHP', DATE '2027-01-01', 'Local transport per trip (2027 budget)'),
  ('lodging_per_night', NULL,  NULL,  3000, 'PHP', DATE '2027-01-01', 'Hotel per night (2027 budget)'),
  ('per_diem',          NULL,  NULL,   600, 'PHP', DATE '2027-01-01', 'Per diem per day (2027 budget)');
INSERT INTO travel.cost_rate (rate_kind, mode, position_id, amount, currency, valid_from, note)
SELECT 'lodging_per_night', NULL, p.id, 5000, 'PHP', DATE '2027-01-01', 'Hotel per night for the Head of Field (2027 budget)'
FROM travel.position p WHERE p.code = 'HEAD';

CREATE TABLE travel.travel_mode (
    id             integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    from_region_id integer NOT NULL REFERENCES travel.org_unit(id),
    to_region_id   integer NOT NULL REFERENCES travel.org_unit(id),
    mode           text NOT NULL CHECK (mode IN ('land', 'air', 'sea')),
    UNIQUE (from_region_id, to_region_id)
);

CREATE TABLE travel.travel_mode_override (
    id             integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    from_region_id integer REFERENCES travel.org_unit(id),           -- NULL = from anywhere
    to_unit_id     integer NOT NULL REFERENCES travel.org_unit(id),  -- a cluster, local office or region
    mode           text NOT NULL CHECK (mode IN ('land', 'air', 'sea')),
    note           text
);
CREATE UNIQUE INDEX travel_mode_override_uidx
    ON travel.travel_mode_override (COALESCE(from_region_id, 0), to_unit_id);

CREATE TABLE travel.app_setting (
    key   text PRIMARY KEY,
    value text
);

CREATE TABLE travel.booking_discount (
    id             integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    min_days_ahead integer NOT NULL CHECK (min_days_ahead >= 1) UNIQUE,
    factor         numeric(4, 3) NOT NULL CHECK (factor > 0 AND factor <= 1),   -- applied to the air or sea fare
    note           text
);

CREATE TABLE travel.budget_line (
    id            integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    plan_year     smallint NOT NULL REFERENCES travel.plan_year(year),
    cost_center   text,
    cost_item     text,                         -- Business Trips, Transportation cost
    event_name    text NOT NULL,
    position_name text,
    remarks       text,
    persons       numeric(10, 2),               -- the "Count" column
    frequency     numeric(10, 2),
    unit_price    numeric(14, 2),
    annual_cost   numeric(16, 2) NOT NULL,
    event_type_id integer REFERENCES travel.event_type(id),   -- which event of the catalog the line belongs to
    justification text,
    source_row    integer
);
CREATE INDEX budget_line_year_idx ON travel.budget_line(plan_year);
