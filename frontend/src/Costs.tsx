import { useCallback, useEffect, useState } from "react";
import { api } from "./api";
import CostSettings from "./CostSettings";
import { money, signed } from "./money";

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

const compact = (n: number) => (n >= 1e6 ? `${(n / 1e6).toFixed(1)}M` : n >= 1e3 ? `${Math.round(n / 1e3)}k` : String(Math.round(n)));

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

      <section className="card">
        <h2>Cost estimate {f.year}</h2>
        {noCost && <p className="muted">There are no trips with travelers in the plan yet. Generate the plan first.</p>}
        {!noCost && (
          <>
            <div className="cards">
              <div className="stat"><span className="muted">Estimated cost</span><strong>{money(f.totals.cost)}</strong></div>
              <div className="stat"><span className="muted">Trips · person-trips</span><strong>{f.totals.trips} · {f.totals.person_trips}</strong></div>
              <div className="stat"><span className="muted">Average per person-trip</span><strong>{money(f.totals.avg_per_person_trip)}</strong></div>
              <div className="stat"><span className="muted">By air or sea</span><strong>{Math.round((100 * f.totals.air_or_sea_person_trips) / f.totals.person_trips)}%</strong></div>
              {f.budget && (
                <div className="stat"><span className="muted">Budget (Field Collections)</span><strong>{money(f.budget.budget_total)}</strong>
                  <span className={f.budget.difference > 0 ? "problem" : "good"}>
                    The estimate is {money(Math.abs(f.budget.difference))} {f.budget.difference > 0 ? "above" : "below"} the budget
                  </span></div>
              )}
            </div>
            {(a.missing_rates.length > 0 || a.assumed_mode_person_trips > 0 || !a.modes_loaded) && (
              <div className="note" role="status">
                <strong>Check the assumptions.</strong>
                {!a.modes_loaded && <> No travel modes are loaded, so every trip between regions is counted as travel by land. </>}
                {a.assumed_mode_person_trips > 0 && <> For {a.assumed_mode_person_trips} person-trips the home or the place is unknown, so they are counted as by land. </>}
                {a.missing_rates.length > 0 && <> No rate is set for: {a.missing_rates.join(", ")}; these are counted as zero. </>}
                {isAdmin && <>Fix them under <em>Rates and travel modes</em> below.</>}
              </div>
            )}

            <h3>By month</h3>
            <div className="bars" role="img" aria-label={`Estimated cost by month, from ${money(Math.min(...f.by_month.map((m) => m.cost)))} to ${money(max)}`}>
              {f.by_month.map((m) => (
                <div key={m.month} className="bar" title={`${m.month}: ${money(m.cost)} (${m.trips} trips)`}>
                  <span className="value">{m.cost ? compact(m.cost) : ""}</span>
                  <div className="fill" style={{ height: `${Math.round((m.cost / max) * 100)}%` }} />
                  <span className="label">{m.month}</span>
                </div>
              ))}
            </div>
          </>
        )}
      </section>

      {!noCost && f.budget && (
        <section className="card">
          <h3>Plan against the budget</h3>
          <p className="muted">
            The budget counts <strong>person-trips</strong> (people × frequency) and prices each with its own formula. The estimate counts the people who travel on the planned trips.
            Differences show where the plan and the budget assume different things (number of trips, length of a trip, who travels).
          </p>
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
          </div>
          {f.budget.unmatched > 0 && <p className="note">{money(f.budget.unmatched)} of the budget is on lines that are not matched to an event (listed in the budget section below).</p>}
        </section>
      )}
      {!noCost && !f.budget && whole && (
        <section className="card"><h3>Plan against the budget</h3>
          <p className="muted">No budget lines are loaded yet.{isAdmin ? " Upload the budget workbook under Budget below." : " An administrator can load them."}</p></section>
      )}

      {!noCost && (
        <details className="card">
          <summary>Cost by place and by position</summary>
          <div className="row top">
            <table className="trips money">
              <thead><tr><th>Place</th><th>Estimate</th><th>Trips</th></tr></thead>
              <tbody>{f.by_place.map((p) => <tr key={p.place}><td>{p.place}</td><td>{money(p.cost)}</td><td>{p.trips}</td></tr>)}</tbody>
            </table>
            <table className="trips money">
              <thead><tr><th>Position</th><th>Estimate</th><th>Person-trips</th></tr></thead>
              <tbody>{f.by_position.map((p) => <tr key={p.position}><td>{p.position}</td><td>{money(p.cost)}</td><td>{p.person_trips}</td></tr>)}</tbody>
            </table>
          </div>
        </details>
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
              <p className="muted">Without any discount the fares would be {money(f.early_booking.fares_without_discount)}. Discount tiers: {a.tiers.map((t) => `${t.min_days_ahead}+ days: ${Math.round((1 - t.factor) * 100)}% off`).join(", ")}.</p>
            </>
          )}
        </section>
      )}

      {whole && <CostSettings year={year} isAdmin={isAdmin} onChanged={load} />}
    </>
  );
}
