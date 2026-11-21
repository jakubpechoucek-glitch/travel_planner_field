import { useEffect, useState } from "react";
import { api } from "./api";
import { Icon } from "./icons";
import { fmtDates } from "./TripPanel";

type Row = { id: number; title: string; event: string; place: string | null; end_date: string; due_date: string; state: string; open: number; done: number };
type Data = { counts: Record<string, number>; trips: Row[] };

const STATE: Record<string, { label: string; tone: string; hint: string }> = {
  overdue: { label: "Late", tone: "bad", hint: "The follow-up period has passed and actions are still open or missing." },
  missing: { label: "No actions yet", tone: "warn", hint: "The visit is over; record its top actions." },
  open: { label: "In progress", tone: "brand", hint: "Actions are open and within time." },
  upcoming: { label: "Not yet", tone: "", hint: "The trip has not ended yet." },
  closed: { label: "Closed", tone: "good", hint: "All actions are closed." },
};

/** Trips whose event asks for a follow-up: calendars track trips, this tracks what came of them. */
export default function FollowUps({ year, tick, onOpen }: { year: number; tick: number; onOpen: (id: number) => void }) {
  const [data, setData] = useState<Data | null>(null);
  const [all, setAll] = useState(false);
  useEffect(() => {
    let live = true;
    void api<Data>(`/api/plan/${year}/follow-ups`).then((r) => live && r.ok && setData(r.data));
    return () => { live = false; };
  }, [year, tick]);
  if (!data) return <div className="skeleton" style={{ height: 160 }} />;
  const rows = all ? data.trips : data.trips.filter((t) => ["overdue", "missing", "open"].includes(t.state));
  const c = data.counts;
  return (
    <div>
      <p className="muted">
        After a visit such as a Special Area visit, the top three actions are recorded on the trip and closed within the follow-up period of the event (30 days for the Head of Field's visits). Open a trip to record or close its actions.
      </p>
      <div className="row" style={{ alignItems: "center" }}>
        {(["overdue", "missing", "open", "upcoming", "closed"] as const).map((s) => (
          <span key={s} className={`pill ${STATE[s].tone}`} title={STATE[s].hint}>{STATE[s].label}: {c[s] ?? 0}</span>
        ))}
        <label className="check"><input type="checkbox" checked={all} onChange={(e) => setAll(e.target.checked)} /> Show all trips with a follow-up</label>
      </div>
      {rows.length === 0 ? (
        <p className="empty"><Icon name="ok" size={28} /><br />Nothing needs attention right now.</p>
      ) : (
        <div className="heatwrap">
          <table className="trips">
            <thead><tr><th>Trip</th><th>Ended</th><th>Follow-up due</th><th>Actions</th><th>State</th></tr></thead>
            <tbody>
              {rows.map((t) => (
                <tr key={t.id}>
                  <td><button className="link" onClick={() => onOpen(t.id)}>{t.title}</button></td>
                  <td>{fmtDates(t.end_date, t.end_date)}</td>
                  <td>{fmtDates(t.due_date, t.due_date)}</td>
                  <td>{t.open + t.done === 0 ? "–" : `${t.done} of ${t.open + t.done} closed`}</td>
                  <td><span className={`pill ${STATE[t.state].tone}`}>{STATE[t.state].label}</span></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
