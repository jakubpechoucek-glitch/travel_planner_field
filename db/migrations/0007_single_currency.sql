-- 0007: one currency. All amounts in the application are Philippine pesos (PHP).
ALTER TABLE travel.cost_rate ADD CONSTRAINT cost_rate_currency_php CHECK (currency = 'PHP');
COMMENT ON COLUMN travel.cost_rate.currency IS 'Always PHP (Philippine peso): the application has a single currency';
COMMENT ON COLUMN travel.budget_line.unit_price IS 'Philippine pesos';
COMMENT ON COLUMN travel.budget_line.annual_cost IS 'Philippine pesos';
COMMENT ON COLUMN travel.cost_rate.amount IS 'Philippine pesos';
