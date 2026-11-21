import { useEffect, useMemo, useState } from "react";
import { api } from "./api";

type Person = { name: string; role: string; travels: boolean; position: string | null };
type Trip = {
  id: number; title: string; event: string; place: string | null; status: string; notes: string | null;
  start_date: string; end_date: string; generated_start_date: string | null; generated_end_date: string | null;
  cancel_reason: string | null; my_role: string; my_travels: boolean; organizer: string | null; combined: string[];
  last_change: { type: string; reason: string | null; category: string | null; at: string } | null;
  participants: Person[]; participant_count: number;
};
type Data = {
  linked: boolean; year: number | null; years: number[]; plan_status?: string; published: boolean; trips: Trip[];
};

const d = (s: string) => new Date(s + "T00:00:00");
const short = (s: string) => d(s).toLocaleDateString("en-US", { month: "short", day: "numeric" });
const range = (a: string, b: string) => (a === b ? short(a) : `${short(a)} to ${short(b)}`);
const monthName = (s: string) => d(s).toLocaleDateString("en-US", { month: "long", year: "numeric" });
const weekday = (s: string) => d(s).toLocaleDateString("en-US", { weekday: "short" });

const STATUS: Record<string, { label: string; hint: string }> = {
  generated: { label: "Proposed", hint: "Planned by the rules; your manager has not confirmed it yet." },
  planned: { label: "Confirmed", hint: "Confirmed by your manager." },
  requested: { label: "Requested", hint: "The travel request has been submitted." },
  approved: { label: "Approved", hint: "The travel request is approved." },
  completed: { label: "Done", hint: "The trip took place." },
  cancelled: { label: "Cancelled", hint: "This trip will not take place." },
};
const ROLE_TEXT: Record<string, string> = {
  organizer: "You organize this trip",
  traveler: "You travel",
  host: "You host this visit: your team is visited",
};
const CHANGE_WORD: Record<string, string> = {
  moved: "Moved", resized: "Length changed", reassigned: "People changed", edited: "Changed", cancelled: "Cancelled",
  status: "Updated", created: "Added",
};

export default function MyPlan() {
  const [data, setData] = useState<Data | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [year, setYear] = useState<number | null>(null);

  useEffect(() => {
    let live = true;
    void api<Data>(`/api/my/trips${year ? `?year=${year}` : ""}`).then((r) => {
      if (!live) return;
      if (r.ok) { setData(r.data); setError(null); } else setError(r.error);
    });
    return () => { live = false; };
  }, [year]);

  const today = new Date().toISOString().slice(0, 10);
  const groups = useMemo(() => {
    const upcoming = (data?.trips ?? []).filter((t) => t.status !== "cancelled" && t.end_date >= today);
    const earlier = (data?.trips ?? []).filter((t) => t.status !== "cancelled" && t.end_date < today);
    const cancelled = (data?.trips ?? []).filter((t) => t.status === "cancelled");
    const byMonth = new Map<string, Trip[]>();
    for (const t of upcoming) {
      const key = monthName(t.start_date);
      byMonth.set(key, [...(byMonth.get(key) ?? []), t]);
    }
    return { upcoming, earlier, cancelled, byMonth };
  }, [data, today]);

  if (error) return <section className="card"><p className="problem">{error}</p></section>;
  if (!data) return <section className="card"><p>Loading…</p></section>;

  const next = groups.upcoming[0];

  return (
    <>
      <details className="card help">
        <summary>Help: my plan</summary>
        <p>
          This page shows the trips you take part in: the trips you organize, the trips you travel on, and the visits to your team where you are the host.
          It is built from the travel plan of your area and updates when your manager changes it.
        </p>
        <p>
          <strong>Proposed</strong> means the plan suggests the trip and it is not confirmed yet. <strong>Confirmed</strong> trips are agreed. If a trip was moved
          or changed, you see the date it was first planned for and the reason. <strong>Add to my calendar</strong> downloads your trips as a file that Outlook, Google Calendar
          and phone calendars can open.
        </p>
        <p>To change a trip, ask your area manager. Only managers can change the plan.</p>
      </details>

      {!data.linked && (
        <section className="card">
          <h2>My plan</h2>
          <p className="muted">Your sign-in is not linked to a person in the organization, so there are no trips of your own to show. Administrators can still use the other pages.</p>
        </section>
      )}

      {data.linked && (
        <section className="card">
          <div className="head">
            <div>
              <h2>My plan{data.year ? ` ${data.year}` : ""}</h2>
              {data.published && (
                <p className="muted">
                  {groups.upcoming.length + groups.earlier.length} {groups.upcoming.length + groups.earlier.length === 1 ? "trip" : "trips"}
                  {groups.upcoming.length > 0 && ` · ${groups.upcoming.length} still to come`}
                  {data.plan_status === "review" && " · The plan is still being reviewed"}
                </p>
              )}
            </div>
            <div className="row">
              {data.years.length > 1 && (
                <label>Year
                  <select value={data.year ?? ""} onChange={(e) => setYear(Number(e.target.value))}>
                    {data.years.map((y) => <option key={y} value={y}>{y}</option>)}
                  </select></label>
              )}
              {data.published && data.trips.some((t) => t.status !== "cancelled") && (
                <a className="button" href={`/api/my/trips.ics?year=${data.year}`}>Add to my calendar</a>
              )}
            </div>
          </div>

          {!data.published && (
            <p className="note">
              The {data.year ?? ""} plan has not been published yet. Your trips will appear here as soon as it is.
            </p>
          )}
          {data.published && data.trips.length === 0 && (
            <p className="muted">You have no trips in the {data.year} plan.</p>
          )}
          {next && (
            <div className="nexttrip" aria-label="Your next trip">
              <span className="muted">Your next trip</span>
              <strong>{next.title}</strong>
              <span>{weekday(next.start_date)}, {range(next.start_date, next.end_date)} · {ROLE_TEXT[next.my_role] ?? "You travel"}</span>
            </div>
          )}
        </section>
      )}

      {[...groups.byMonth.entries()].map(([month, trips]) => (
        <section key={month} className="card">
          <h3>{month}</h3>
          <ul className="mytrips">{trips.map((t) => <TripCard key={t.id} t={t} />)}</ul>
        </section>
      ))}

      {groups.earlier.length > 0 && (
        <details className="card">
          <summary>Earlier trips ({groups.earlier.length})</summary>
          <ul className="mytrips">{groups.earlier.map((t) => <TripCard key={t.id} t={t} />)}</ul>
        </details>
      )}
      {groups.cancelled.length > 0 && (
        <details className="card">
          <summary>Cancelled trips ({groups.cancelled.length})</summary>
          <ul className="mytrips">{groups.cancelled.map((t) => <TripCard key={t.id} t={t} />)}</ul>
        </details>
      )}
    </>
  );
}

function TripCard({ t }: { t: Trip }) {
  const [open, setOpen] = useState(false);
  const status = STATUS[t.status] ?? { label: t.status, hint: "" };
  const moved = t.generated_start_date && (t.generated_start_date !== t.start_date || t.generated_end_date !== t.end_date);
  const others = t.participants.filter((p) => p.name);
  // the generator adds "Includes X." to a combined trip; that is already shown as "Also held at this trip"
  const note = (t.notes ?? "").split(/(?<=\.)\s+/).filter((s) => s && !s.startsWith("Includes ")).join(" ");
  return (
    <li className={`mytrip ${t.status === "cancelled" ? "cancelled" : ""}`}>
      <div className="when" aria-hidden="true">
        <strong>{d(t.start_date).getDate()}</strong>
        <span>{d(t.start_date).toLocaleDateString("en-US", { month: "short" })}</span>
      </div>
      <div className="what">
        <div className="titleline">
          <strong>{t.title}</strong>
          <span className={`badge status-${t.status}`} title={status.hint}>{status.label}</span>
        </div>
        <div className="muted">
          {weekday(t.start_date)}, {range(t.start_date, t.end_date)}{t.place ? ` · ${t.place}` : ""} · {ROLE_TEXT[t.my_role] ?? "You travel"}
          {t.organizer && t.my_role !== "organizer" ? ` · Organized by ${t.organizer}` : ""}
        </div>
        {t.combined.length > 0 && <div className="muted">Also held at this trip: {t.combined.join(", ")}</div>}
        {t.status === "cancelled" && t.cancel_reason && <div className="note">Cancelled: {t.cancel_reason}</div>}
        {t.status !== "cancelled" && (moved || (t.last_change && t.last_change.type !== "status")) && (
          <div className="note">
            {moved && <>Originally planned for {range(t.generated_start_date!, t.generated_end_date!)}. </>}
            {t.last_change?.reason && t.last_change.type !== "status" && <>{CHANGE_WORD[t.last_change.type] ?? "Changed"}: {t.last_change.reason}</>}
          </div>
        )}
        {note && <div>{note}</div>}
        {others.length > 0 && (
          <>
            <button type="button" className="link" aria-expanded={open} onClick={() => setOpen(!open)}>
              {open ? "Hide" : "Who is on this trip"} ({t.participant_count})
            </button>
            {open && (
              <ul className="chips">
                {others.map((p) => (
                  <li key={p.name + p.role} className={p.role === "organizer" ? "chip strong" : "chip"}>
                    {p.name}{p.position ? ` · ${p.position}` : ""}{p.role === "organizer" ? " (organizer)" : ""}{!p.travels ? " (host)" : ""}
                  </li>
                ))}
              </ul>
            )}
          </>
        )}
      </div>
    </li>
  );
}
