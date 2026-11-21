import { useCallback, useEffect, useState } from "react";
import { api } from "./api";
import CostSettings from "./CostSettings";
import { money, signed } from "./money";
import { ColumnChart, HBars, Meter, PairedBars, SegBar, Sparkline } from "./charts";
import { Icon } from "./icons";

type Row = { cost: number; trips: number; person_trips: number };
type Forecast = {
  year: number; currency: string; currency_symbol: string;
  totals: { cost: number; trips: number; person_trips: number; avg_per_person_trip: number; air_or_sea_person_trips: number };
  by_month: { month: string; cost: number; trips: number }[];
  by_place: (Row & { place: string })[];
  by_event: (Row & { event_id: number; event: string })[];
  by_position: { position: string; cost: number; person_trips: number }[];
  by_mode: Record<string, { person_trips: number; cost: number }>;
  budget: {
    budget_total: number; forecast_total: number; difference: number; unmatched: number;
    rows: { event_id: number | null; event: string; budget_cost: number; budget_person_trips: number; forecast_cost: number; forecast_person_trips: number; difference: number }[];
  } | null;
  early_booking: { has_tiers: boolean; fares: number; fares_without_discount: number; target_days: number | null; fares_if_booked_ahead?: number; saving: number; factor_at_target?: number };
  assumptions: { missing_rates: string[]; assumed_mode_person_trips: number; modes_loaded: boolean; settings: Record<string, number | null>; tiers: { min_days_ahead: number; factor: number }[] };
};

export default function Costs({ isAdmin, whole }: { isAdmin: boolean; whole: boolean }) {
  const year = 2027;
  const [f, setF] = useState<Forecast | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [ahead, setAhead] = useState<number | "">("");

  const load = useCallback(async () => {
    const r = await api<Forecast>(`/api/cost/${year}/forecast${ahead ? `?book_ahead_days=${ahead}` : ""}`);
    if (r.ok) { setF(r.data); setError(null); } else setError(r.error);
  }, [ahead]);
  useEffect(() => { const t = setTimeout(() => void load(), ahead ? 400 : 0); return () => clearTimeout(t); }, [load, ahead]);

  if (error) return <section className="card"><p className="problem">{error}</p></section>;
  if (!f) return <section className="card"><p>Loading…</p></section>;

  const max = Math.max(1, ...f.by_month.map((m) => m.cost));
  const a = f.assumptions;
  const noCost = f.totals.person_trips === 0;

  return (
    <>
      <details className="card help">
        <summary>Help: the cost estimate</summary>
        <p>
          The estimate takes everybody who <strong>travels</strong> on a trip in the plan and adds up: the <strong>air or sea fare</strong> (only if the person has to fly or sail),
          <strong> local transport</strong>, <strong>hotel nights</strong> and <strong>per diem days</strong>. It uses the same formula as the budget:
          for example an Area Manager flying for three days costs 20,000 + 2 × 3,000 + 2,500 + 3 × 600 = ₱30,300.
        </p>
        <p>
          Whether someone flies depends on where they are based and where the trip takes place (see <em>Travel modes</em> below). Hosts, who are visited, have no travel cost.
          <strong> Early booking</strong> shows what cheaper fares would save, once the travel desk has told us the discounts.
        </p>
        <p>
          This is an <strong>estimate for planning</strong>, not a booking and not an approval. Hotel, per diem and fare rates are set by the company; they are shown under Rates.
          All amounts are in <strong>Philippine pesos (₱)</strong>.
        </p>
      </details>

      {noCost && <section className="card"><h2>Cost estimate {f.year}</h2><p className="muted">There are no trips with travelers in the plan yet. Generate the plan first.</p></section>}
      {!noCost && (
        <>
          <section className="hero">
            <div className="hero-grid">
              <div>
                <h1>Cost estimate {f.year}</h1>
                <p>{f.totals.trips.toLocaleString("en-US")} trips · {f.totals.person_trips.toLocaleString("en-US")} person-trips · {money(f.totals.avg_per_person_trip)} on average</p>
                {f.budget && (
                  <p style={{ marginTop: 10 }}>
                    <span className="pill"><Icon name={f.budget.difference > 0 ? "up" : "down"} size={14} />
                      {money(Math.abs(f.budget.difference))} {f.budget.difference > 0 ? "above" : "below"} the budget of {money(f.budget.budget_total)}</span>
                  </p>
                )}
              </div>
              <div className="big"><span className="figure">{money(f.totals.cost)}</span><span className="cap">estimated travel cost</span></div>
            </div>
          </section>
          <div className="stats">
            <div className="stat"><span className="label"><Icon name="send" size={16} />Trips</span><span className="value">{f.totals.trips.toLocaleString("en-US")}</span>
              <span className="foot"><span>by month</span><Sparkline values={f.by_month.map((m) => m.trips)} /></span></div>
            <div className="stat"><span className="label"><Icon name="users" size={16} />Person-trips</span><span className="value">{f.totals.person_trips.toLocaleString("en-US")}</span>
              <span className="foot"><span>people × trips</span></span></div>
            <div className="stat"><span className="label"><Icon name="plane" size={16} />By air or sea</span><span className="value">{Math.round((100 * f.totals.air_or_sea_person_trips) / f.totals.person_trips)}%</span>
              <span className="foot"><span>of person-trips</span></span></div>
            {f.budget && <div className={`stat ${f.budget.difference > 0 ? "bad" : "good"}`}><span className="label"><Icon name={f.budget.difference > 0 ? "alert" : "ok"} size={16} />Against the budget</span>
              <span className="value">{signed(f.budget.difference)}</span><span className="foot"><span>{f.budget.difference > 0 ? "over budget" : "under budget"}</span></span></div>}
          </div>
          <section className="card">
            {(a.missing_rates.length > 0 || a.assumed_mode_person_trips > 0 || !a.modes_loaded) && (
              <div className="note" role="status" style={{ marginBottom: 14 }}>
                <strong>Check the assumptions.</strong>
                {!a.modes_loaded && <> No travel modes are loaded, so every trip between regions is counted as travel by land. </>}
                {a.assumed_mode_person_trips > 0 && <> For {a.assumed_mode_person_trips} person-trips the home or the place is unknown, so they are counted as by land. </>}
                {a.missing_rates.length > 0 && <> No rate is set for: {a.missing_rates.join(", ")}; these are counted as zero. </>}
                {isAdmin && <>Fix them under <em>Rates and travel modes</em> below.</>}
              </div>
            )}
            <h3>By month</h3>
            <ColumnChart ariaLabel={`Estimated cost by month, from ${money(Math.min(...f.by_month.map((m) => m.cost)))} to ${money(max)}`} format={money}
              data={f.by_month.map((m) => ({ label: m.month.slice(0, 3), value: m.cost, tip: <><b>{m.month}</b><div>{money(m.cost)}</div><div className="t-muted">{m.trips} trips</div></> }))} />
          </section>
          <div className="home-grid" style={{ marginTop: 16 }}>
            <section className="card">
              <h3>Where the money goes</h3>
              <SegBar format={money} parts={Object.entries(f.by_mode).map(([mode, v], i) => ({
                label: `By ${mode}`, value: v.cost, color: ["var(--c1)", "var(--c2)", "var(--c3)"][i % 3],
              }))} />
              <h4>Top places</h4>
              <HBars format={money} rows={f.by_place.map((p) => ({ label: p.place, value: p.cost, note: `${p.trips} ${p.trips === 1 ? "trip" : "trips"}` }))} limit={6} />
            </section>
            <section className="card">
              <h3>By position</h3>
              <HBars format={money} rows={f.by_position.map((p) => ({ label: p.position, value: p.cost, note: `${p.person_trips} person-trips` }))} limit={8} />
            </section>
          </div>
        </>
      )}

      {!noCost && f.budget && (
        <section className="card">
          <h3>Plan against the budget</h3>
          <p className="muted">
            The budget counts <strong>person-trips</strong> (people × frequency) and prices each with its own formula. The estimate counts the people who travel on the planned trips.
            Differences show where the plan and the budget assume different things (number of trips, length of a trip, who travels).
          </p>
          <PairedBars format={money} aLabel="Budget" bLabel="Estimate"
            rows={f.budget.rows.filter((r) => r.budget_cost || r.forecast_cost).sort((x, y) => Math.max(y.budget_cost, y.forecast_cost) - Math.max(x.budget_cost, x.forecast_cost)).slice(0, 8)
              .map((r) => ({ label: r.event, a: r.budget_cost, b: r.forecast_cost, delta: r.forecast_cost - r.budget_cost }))} />
          <details style={{ marginTop: 14 }}><summary>Show all lines as a table</summary>
          <div className="heatwrap">
            <table className="trips money">
              <thead><tr><th>Event</th><th>Budget</th><th>Person-trips</th><th>Estimate</th><th>Person-trips</th><th>Estimate vs budget</th></tr></thead>
              <tbody>
                {f.budget.rows.map((r) => (
                  <tr key={r.event}>
                    <td>{r.event}</td>
                    <td>{money(r.budget_cost)}</td><td>{r.budget_person_trips || ""}</td>
                    <td>{money(r.forecast_cost)}</td><td>{r.forecast_person_trips || ""}</td>
                    <td className={r.difference > 0 ? "problem" : "good"}>{signed(r.difference)}</td>
                  </tr>
                ))}
                <tr className="total"><td>Total</td><td>{money(f.budget.budget_total)}</td><td></td><td>{money(f.budget.forecast_total)}</td><td></td><td>{signed(f.budget.difference)}</td></tr>
              </tbody>
            </table>
          </div></details>
          {f.budget.unmatched > 0 && <p className="note">{money(f.budget.unmatched)} of the budget is on lines that are not matched to an event (listed in the budget section below).</p>}
        </section>
      )}
      {!noCost && !f.budget && whole && (
        <section className="card"><h3>Plan against the budget</h3>
          <p className="muted">No budget lines are loaded yet.{isAdmin ? " Upload the budget workbook under Budget below." : " An administrator can load them."}</p></section>
      )}

      {!noCost && (
        <section className="card">
          <h3>Early booking</h3>
          {!f.early_booking.has_tiers ? (
            <p className="muted">
              Air and sea fares are {money(f.early_booking.fares)} of the estimate. Booking early usually makes fares cheaper, but the discounts are not known yet:
              ask the travel desk how much cheaper a fare is when it is booked 30, 60 or 90 days ahead, and enter the tiers{isAdmin ? " below" : ""}. Then this shows what early approval is worth.
            </p>
          ) : (
            <>
              <p>
                Fares are <strong>{money(f.early_booking.fares)}</strong> with today's lead times. If every fare were booked at least{" "}
                <input className="inline" type="number" min={1} max={730} value={ahead === "" ? f.early_booking.target_days ?? "" : ahead}
                  onChange={(e) => setAhead(e.target.value === "" ? "" : Number(e.target.value))} aria-label="Days ahead" /> days ahead, they would be{" "}
                <strong>{money(f.early_booking.fares_if_booked_ahead ?? 0)}</strong>
                {f.early_booking.saving > 0 ? <>: a saving of <strong className="good">{money(f.early_booking.saving)}</strong>.</> : <>: no saving.</>}
              </p>
              <div style={{ margin: "6px 0 10px" }}><Meter value={f.early_booking.fares_if_booked_ahead ?? 0} max={f.early_booking.fares_without_discount || 1} label="Fares if booked early, as a share of fares without discount" /></div>
              <p className="muted">Without any discount the fares would be {money(f.early_booking.fares_without_discount)}. Discount tiers: {a.tiers.map((t) => `${t.min_days_ahead}+ days: ${Math.round((1 - t.factor) * 100)}% off`).join(", ")}.</p>
            </>
          )}
        </section>
      )}

      {whole && <CostSettings year={year} isAdmin={isAdmin} onChanged={load} />}
    </>
  );
}
