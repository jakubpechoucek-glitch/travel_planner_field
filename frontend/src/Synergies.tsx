import { useCallback, useEffect, useState } from "react";
import { api } from "./api";
import { Icon } from "./icons";
import { fmtDates } from "./TripPanel";

type Brief = { id: number; title: string; event: string; start_date: string; end_date: string; editable: boolean };
type Item = { place: string | null; gap_days: number; shared: string[]; people: number; first: Brief; second: Brief };
type Data = { total: number; within_days: number; suggestions: Item[] };

/** Two trips to the same place a few days apart: a chance to travel once, and to book earlier and cheaper. */
export default function Synergies({ year, tick, onOpen }: { year: number; tick: number; onOpen: (id: number) => void }) {
  const [days, setDays] = useState(14);
  const [data, setData] = useState<Data | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    const r = await api<Data>(`/api/plan/${year}/synergies?within_days=${days}`);
    if (r.ok) { setData(r.data); setError(null); } else setError(r.error);
  }, [year, days]);
  useEffect(() => { void load(); }, [load, tick]);

  const dismiss = async (s: Item) => {
    const reason = window.prompt("Why is this not a good match? (optional)") ?? null;
    if (reason === null) return;
    const r = await api(`/api/plan/${year}/synergies/dismiss`, "POST", { trip_a: s.first.id, trip_b: s.second.id, reason: reason || undefined });
    if (!r.ok) return setError(r.error);
    await load();
  };

  return (
    <div>
      <p className="muted">
        Trips to the same place that are a few days apart could be held together, so people travel once and fares can be booked earlier. Open a trip to move it (every change needs a reason), or dismiss the suggestion if the trips belong apart.
      </p>
      <label className="row" style={{ alignItems: "center", gap: 8 }}>Trips up to
        <input className="inline" type="number" min={1} max={60} value={days} onChange={(e) => setDays(Math.max(1, Math.min(60, Number(e.target.value) || 1)))} /> days apart
      </label>
      {error && <p className="problem">{error}</p>}
      {!data && !error && <div className="skeleton" style={{ height: 120 }} />}
      {data && data.suggestions.length === 0 && (
        <p className="empty"><Icon name="ok" size={28} /><br />No trips to the same place within {days} days of each other.</p>
      )}
      {data && data.suggestions.length > 0 && (
        <>
          <p><strong>{data.total}</strong> {data.total === 1 ? "suggestion" : "suggestions"}{data.total > data.suggestions.length ? `, the first ${data.suggestions.length} shown` : ""}.</p>
          <div className="heatwrap">
            <table className="trips">
              <thead><tr><th>Place</th><th>First trip</th><th>Then, after</th><th>Same people</th><th></th></tr></thead>
              <tbody>
                {data.suggestions.map((s) => (
                  <tr key={`${s.first.id}-${s.second.id}`}>
                    <td>{s.place ?? "–"}</td>
                    <td><button className="link" onClick={() => onOpen(s.first.id)}>{s.first.event}</button><br /><span className="muted">{fmtDates(s.first.start_date, s.first.end_date)}</span></td>
                    <td><button className="link" onClick={() => onOpen(s.second.id)}>{s.second.event}</button><br /><span className="muted">{s.gap_days} {s.gap_days === 1 ? "day" : "days"} · {fmtDates(s.second.start_date, s.second.end_date)}</span></td>
                    <td>
                      {s.shared.length > 0
                        ? <span className="pill warn" title={s.shared.join(", ")}><Icon name="users" size={13} />{s.shared.length} travel twice</span>
                        : <span className="muted">{s.people} people in total</span>}
                    </td>
                    <td><button className="link" disabled={!s.first.editable && !s.second.editable} onClick={() => dismiss(s)}>Dismiss</button></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}
