import { useEffect, useMemo, useState } from "react";
import { api } from "./api";
import { Icon } from "./icons";
import { daysFromToday, familyOf } from "./theme";

type Person = { name: string; role: string; travels: boolean; position: string | null };
type Trip = {
  id: number; title: string; event: string; event_code: string; place: string | null; status: string; notes: string | null;
  start_date: string; end_date: string; generated_start_date: string | null; generated_end_date: string | null;
  cancel_reason: string | null; area_pending?: boolean; my_request?: MyRequest | null; area_decide_by?: string | null; my_role: string; my_travels: boolean; organizer: string | null; combined: string[];
  last_change: { type: string; reason: string | null; category: string | null; at: string } | null;
  participants: Person[]; participant_count: number;
};
type MyRequest = { id: number; kind: string; message: string; status: string; proposed_start: string | null; proposed_end: string | null; decision_note: string | null };
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

  const [tick, setTick] = useState(0);
  const reload = () => setTick((n) => n + 1);
  useEffect(() => {
    let live = true;
    void api<Data>(`/api/my/trips${year ? `?year=${year}` : ""}`).then((r) => {
      if (!live) return;
      if (r.ok) { setData(r.data); setError(null); } else setError(r.error);
    });
    return () => { live = false; };
  }, [year, tick]);

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
        <p>
          To change a trip, use <strong>Suggest a change</strong> on its card: you can ask to move the trip or say that you cannot take part, and give a reason. Your manager reads it and answers; you see the answer on the card.
          The plan changes only when your manager changes it. Please do not write phone numbers or e-mail addresses.
        </p>
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
          {data.year && data.trips.some((x) => x.status !== "cancelled") && <YearStrip year={data.year} trips={data.trips.filter((x) => x.status !== "cancelled")} />}
          {next && (
            <div className="note" aria-label="Your next trip">
              <strong>Your next trip: {next.title}</strong> · {weekday(next.start_date)}, {range(next.start_date, next.end_date)} · {ROLE_TEXT[next.my_role] ?? "You travel"}
            </div>
          )}
        </section>
      )}

      {[...groups.byMonth.entries()].map(([month, trips]) => (
        <section key={month} className="card">
          <h3>{month}</h3>
          <ul className="mytrips">{trips.map((t) => <TripCard key={t.id} t={t} onChanged={reload} />)}</ul>
        </section>
      ))}

      {groups.earlier.length > 0 && (
        <details className="card">
          <summary>Earlier trips ({groups.earlier.length})</summary>
          <ul className="mytrips">{groups.earlier.map((t) => <TripCard key={t.id} t={t} onChanged={reload} />)}</ul>
        </details>
      )}
      {groups.cancelled.length > 0 && (
        <details className="card">
          <summary>Cancelled trips ({groups.cancelled.length})</summary>
          <ul className="mytrips">{groups.cancelled.map((t) => <TripCard key={t.id} t={t} onChanged={reload} />)}</ul>
        </details>
      )}
    </>
  );
}

function TripCard({ t, onChanged }: { t: Trip; onChanged: () => void }) {
  const [open, setOpen] = useState(false);
  const [asking, setAsking] = useState(false);
  const status = STATUS[t.status] ?? { label: t.status, hint: "" };
  const moved = t.generated_start_date && (t.generated_start_date !== t.start_date || t.generated_end_date !== t.end_date);
  const others = t.participants.filter((p) => p.name);
  // the generator adds "Includes X." to a combined trip; that is already shown as "Also held at this trip"
  const note = (t.notes ?? "").split(/(?<=\.)\s+/).filter((s) => s && !s.startsWith("Includes ")).join(" ");
  return (
    <li className={`mytrip ${t.status === "cancelled" ? "cancelled" : ""}`} style={{ ["--fam" as string]: familyOf(t.event_code).color }}>
      <div className="when" aria-hidden="true">
        <strong>{d(t.start_date).getDate()}</strong>
        <span>{d(t.start_date).toLocaleDateString("en-US", { month: "short" })}</span>
      </div>
      <div className="what">
        <div className="titleline">
          <strong>{t.title}</strong>
          <span className={`badge status-${t.status}`} title={status.hint}>{status.label}</span>
          {t.status !== "cancelled" && daysFromToday(t.end_date) >= 0 && (
            <span className="pill brand"><Icon name="clock" size={13} />{daysFromToday(t.start_date) <= 0 ? "under way" : `in ${daysFromToday(t.start_date)} days`}</span>
          )}
        </div>
        <div className="meta">
          <span>{weekday(t.start_date)}, {range(t.start_date, t.end_date)}</span>
          {t.place && <span><Icon name="map" size={13} /> {t.place}</span>}
          <span className="pill"><Icon name={t.my_role === "host" ? "building" : t.my_role === "organizer" ? "users" : "plane"} size={13} />{ROLE_TEXT[t.my_role] ?? "You travel"}</span>
          {t.organizer && t.my_role !== "organizer" && <span>Organized by {t.organizer}</span>}
        </div>
        {t.area_pending && <div className="note">The exact area will be chosen by {t.area_decide_by ? range(t.area_decide_by, t.area_decide_by) : "the planner"}; until then the date is reserved for the whole region.</div>}
        {t.combined.length > 0 && <div className="muted">Also held at this trip: {t.combined.join(", ")}</div>}
        {t.status === "cancelled" && t.cancel_reason && <div className="note">Cancelled: {t.cancel_reason}</div>}
        {t.status !== "cancelled" && (moved || (t.last_change && t.last_change.type !== "status")) && (
          <div className="note">
            {moved && <>Originally planned for {range(t.generated_start_date!, t.generated_end_date!)}. </>}
            {t.last_change?.reason && t.last_change.type !== "status" && <>{CHANGE_WORD[t.last_change.type] ?? "Changed"}: {t.last_change.reason}</>}
          </div>
        )}
        {note && <div>{note}</div>}
        <SuggestChange t={t} asking={asking} setAsking={setAsking} onChanged={onChanged} />
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

const MON = ["J", "F", "M", "A", "M", "J", "J", "A", "S", "O", "N", "D"];

/** The whole year in one line: a mark per trip, in the color of its event family. */
function YearStrip({ year, trips }: { year: number; trips: Trip[] }) {
  const a = new Date(year, 0, 1).getTime();
  const span = new Date(year + 1, 0, 1).getTime() - a;
  const pos = (ms: number) => ((ms - a) / span) * 100;
  const now = pos(Date.now());
  return (
    <div className="yearstrip" role="img" aria-label={`Your ${trips.length} trips across ${year}`}>
      {MON.map((m, i) => (
        <span key={i}>
          {i > 0 && <i style={{ left: `${pos(new Date(year, i, 1).getTime())}%` }} />}
          <span className="m" style={{ left: `${pos(new Date(year, i, 1).getTime())}%` }}>{m}</span>
        </span>
      ))}
      {trips.map((t) => {
        const s = pos(d(t.start_date).getTime());
        const w = Math.max(1.2, pos(d(t.end_date).getTime() + 86400000) - s);
        return <b key={t.id} title={`${t.title}: ${range(t.start_date, t.end_date)}`} style={{ left: `${s}%`, width: `${w}%`, ["--bar" as string]: familyOf(t.event_code).color }} />;
      })}
      {now > 0 && now < 100 && <span className="now" style={{ left: `${now}%` }} />}
    </div>
  );
}

const REQ_KIND: Record<string, string> = { move: "Move the trip", cannot_attend: "I cannot take part", other: "Something else" };
const REQ_STATUS: Record<string, { label: string; tone: string }> = {
  open: { label: "Waiting for your manager", tone: "warn" }, accepted: { label: "Accepted", tone: "good" },
  declined: { label: "Declined", tone: "bad" }, withdrawn: { label: "Withdrawn", tone: "" },
};

/** Ask the planner to move the trip or to take you off it. The plan changes only when the planner decides so. */
function SuggestChange({ t, asking, setAsking, onChanged }: { t: Trip; asking: boolean; setAsking: (b: boolean) => void; onChanged: () => void }) {
  const [kind, setKind] = useState("move");
  const [message, setMessage] = useState("");
  const [start, setStart] = useState("");
  const [error, setError] = useState<string | null>(null);
  const today = new Date().toISOString().slice(0, 10);
  if (t.status === "cancelled" || t.end_date < today) return null;
  const req = t.my_request;
  const send = async (e: React.FormEvent) => {
    e.preventDefault();
    const r = await api(`/api/my/trips/${t.id}/requests`, "POST", { kind, message, proposed_start: kind === "move" ? start || undefined : undefined });
    if (!r.ok) return setError(r.error);
    setAsking(false); setMessage(""); setStart(""); setError(null); onChanged();
  };
  const withdraw = async () => {
    const r = await api(`/api/my/requests/${req!.id}/withdraw`, "POST");
    if (!r.ok) return setError(r.error);
    onChanged();
  };
  return (
    <div style={{ marginTop: 6 }}>
      {req && (
        <div className="note">
          <strong>Your suggestion:</strong> {REQ_KIND[req.kind] ?? req.kind}
          {req.proposed_start && ` (${range(req.proposed_start, req.proposed_end ?? req.proposed_start)})`}: “{req.message}”{" "}
          <span className={`pill ${REQ_STATUS[req.status]?.tone ?? ""}`}>{REQ_STATUS[req.status]?.label ?? req.status}</span>
          {req.decision_note && <div>Answer: {req.decision_note}</div>}
          {req.status === "open" && <button type="button" className="link" onClick={withdraw}>Withdraw</button>}
        </div>
      )}
      {(!req || req.status !== "open") && !asking && (
        <button type="button" className="link" onClick={() => setAsking(true)}>Suggest a change</button>
      )}
      {asking && (
        <form className="subform" onSubmit={send}>
          <p className="muted" style={{ margin: 0 }}>Your manager reads this and decides. The plan does not change until then. Please do not write phone numbers or e-mail addresses.</p>
          <label>What would you like?
            <select value={kind} onChange={(e) => setKind(e.target.value)}>
              {Object.entries(REQ_KIND).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
            </select>
          </label>
          {kind === "move" && <label>Preferred start date<input type="date" required value={start} onChange={(e) => setStart(e.target.value)} /></label>}
          <label>Why?<textarea required minLength={3} maxLength={500} rows={3} value={message} onChange={(e) => setMessage(e.target.value)} /></label>
          {error && <p className="problem">{error}</p>}
          <p className="row"><button type="submit">Send suggestion</button><button type="button" className="link" onClick={() => setAsking(false)}>Cancel</button></p>
        </form>
      )}
      {!asking && error && <p className="problem">{error}</p>}
    </div>
  );
}
