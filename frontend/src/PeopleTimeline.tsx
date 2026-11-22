import { useEffect, useMemo, useState } from "react";
import { api } from "./api";
import { Icon } from "./icons";
import { useTip } from "./charts";
import { FAMILIES, familyOf } from "./theme";
import type { Summary } from "./Timeline";

type Trip = { id: number; title: string; event: string; event_code: string; start_date: string; end_date: string; status: string; role: string; travels: boolean; clash: boolean };
type Person = { person_id: number; name: string; position: string | null; unit: string | null; days_away: number; clashes: number; trips: Trip[] };
type Data = { total: number; truncated: boolean; people: Person[]; blackouts: { id: number; name: string; start_date: string; end_date: string; severity: string }[] };

const DAY = 86400000;
const ts = (s: string) => new Date(s + "T00:00:00").getTime();
const iso = (ms: number) => new Date(ms - new Date(ms).getTimezoneOffset() * 60000).toISOString().slice(0, 10);
const fmt = (s: string) => new Date(s + "T00:00:00").toLocaleDateString("en-US", { month: "short", day: "numeric" });
const MONTH = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];

/** Rows are people, columns are days: who is away when, with clashes and blackout periods. */
export default function PeopleTimeline({ year, summary, tick, onOpen }: { year: number; summary: Summary; tick: number; onOpen: (id: number) => void }) {
  const now = new Date();
  const [span, setSpan] = useState<"month" | "quarter">("month");
  const [first, setFirst] = useState(now.getFullYear() === year ? now.getMonth() : 0);   // first month of the window
  const [unit, setUnit] = useState("");
  const [name, setName] = useState("");
  const [hosts, setHosts] = useState(false);
  const [sort, setSort] = useState<"name" | "away">("name");
  const [data, setData] = useState<Data | null>(null);
  const [error, setError] = useState<string | null>(null);
  const { show, showAt, hide, node } = useTip();

  const months = span === "month" ? 1 : 3;
  const m0 = span === "quarter" ? Math.floor(first / 3) * 3 : first;
  const from = new Date(year, m0, 1).getTime();
  const to = new Date(year, m0 + months, 1).getTime();            // exclusive
  const days = Math.round((to - from) / DAY);

  useEffect(() => {
    let live = true;
    const p = new URLSearchParams({ start: iso(from), end: iso(to - DAY), hosts: String(hosts) });
    if (unit) p.set("unit_id", unit);
    if (name.trim()) p.set("q", name.trim());
    const t = setTimeout(() => void api<Data>(`/api/plan/${year}/people-timeline?${p}`).then((r) => {
      if (!live) return;
      if (r.ok) { setData(r.data); setError(null); } else setError(r.error);
    }), name ? 250 : 0);
    return () => { live = false; clearTimeout(t); };
  }, [year, from, to, unit, name, hosts, tick]);

  const people = useMemo(() => {
    const l = [...(data?.people ?? [])];
    if (sort === "away") l.sort((a, b) => b.days_away - a.days_away || a.name.localeCompare(b.name));
    return l;
  }, [data, sort]);

  const pct = (ms: number) => ((ms - from) / (to - from)) * 100;
  const todayPct = pct(Date.now());
  const step = (d: number) => setFirst((f) => Math.max(0, Math.min(11, (span === "quarter" ? Math.floor(f / 3) * 3 + d * 3 : f + d))));
  const label = span === "month" ? `${MONTH[m0]} ${year}` : `${MONTH[m0]} to ${MONTH[m0 + 2]} ${year}`;
  const units = summary.regions.flatMap((r) => [{ id: r.id, name: `${r.name} (all)` }, ...r.rows.filter((x) => x.unit_id !== null && x.unit_id !== r.id).map((x) => ({ id: x.unit_id as number, name: `${r.name}: ${x.label}` }))]);
  const dayTicks = Array.from({ length: days }, (_, i) => new Date(from + i * DAY));
  const grid = { backgroundImage: `repeating-linear-gradient(90deg, transparent 0, transparent calc(100% / ${days} - 1px), var(--line) calc(100% / ${days} - 1px), var(--line) calc(100% / ${days}))` };
  const present = new Set(people.flatMap((p) => p.trips.map((t) => familyOf(t.event_code).key)));

  return (
    <div>
      <div className="row" style={{ alignItems: "center", justifyContent: "space-between" }}>
        <div className="row" style={{ alignItems: "center", gap: 8 }}>
          <button type="button" className="secondary" aria-label="Earlier" onClick={() => step(-1)} disabled={m0 === 0}>‹</button>
          <strong style={{ minWidth: 190, textAlign: "center" }}>{label}</strong>
          <button type="button" className="secondary" aria-label="Later" onClick={() => step(1)} disabled={m0 + months >= 12}>›</button>
        </div>
        <div className="segctl" role="group" aria-label="Window">
          <button type="button" className={span === "month" ? "on" : ""} onClick={() => setSpan("month")}>Month</button>
          <button type="button" className={span === "quarter" ? "on" : ""} onClick={() => setSpan("quarter")}>Quarter</button>
        </div>
      </div>
      <div className="row" style={{ marginTop: 10 }}>
        <label>Area<select value={unit} onChange={(e) => setUnit(e.target.value)}>
          <option value="">Everyone in my scope</option>
          {units.map((u) => <option key={u.id} value={u.id}>{u.name}</option>)}
        </select></label>
        <label>Person<input placeholder="Name" value={name} onChange={(e) => setName(e.target.value)} /></label>
        <label>Sort by<select value={sort} onChange={(e) => setSort(e.target.value as "name" | "away")}>
          <option value="name">Name</option><option value="away">Days away (most first)</option>
        </select></label>
        <label className="check"><input type="checkbox" checked={hosts} onChange={(e) => setHosts(e.target.checked)} /> Include people who host a visit</label>
      </div>
      <div className="legend" aria-label="Legend">
        {FAMILIES.filter((f) => present.has(f.key)).map((f) => <span key={f.key}><i className="sw" style={{ background: f.color }} /> {f.label}</span>)}
        <span><i className="sw" style={{ background: "repeating-linear-gradient(135deg, var(--bad-soft) 0 3px, var(--surface) 3px 6px)", border: "1px solid var(--bad)" }} /> Blackout period</span>
        <span><i className="sw" style={{ background: "var(--surface)", border: "2px solid var(--bad)" }} /> Two trips at once</span>
      </div>
      {error && <p className="problem">{error}</p>}
      {!data && !error && <div className="skeleton" style={{ height: 220 }} />}
      {data && people.length === 0 && <p className="empty"><Icon name="calendar" size={28} /><br />Nobody travels in this window{unit || name ? " for this filter" : ""}.</p>}
      {data && people.length > 0 && (
        <>
          <p className="muted">{data.total} {data.total === 1 ? "person" : "people"} with trips in this window{data.truncated ? `, the first ${people.length} shown` : ""}. The number next to a name is the days away.</p>
          <div className="tl" role="group" aria-label={`People timeline, ${label}`} style={{ ["--label" as string]: "210px" }}>
            <div className="tl-inner" style={{ minWidth: span === "month" ? 900 : 1100 }}>
              <div className="tl-head">
                <div className="tl-label" style={{ borderRight: "1px solid var(--line)" }} />
                <div className="tl-months" style={{ height: 40 }}>
                  {dayTicks.map((d, i) => {
                    const monday = d.getDay() === 1;
                    if (span === "quarter" && !monday) return null;
                    return (
                      <span key={i} style={{ left: `${(i / days) * 100}%`, top: 4, textAlign: "center", opacity: d.getDay() === 0 || d.getDay() === 6 ? 0.55 : 1 }}>
                        {span === "month" ? <>{d.getDate()}<br /><small>{"SMTWTFS"[d.getDay()]}</small></> : fmt(iso(d.getTime()))}
                      </span>
                    );
                  })}
                </div>
              </div>
              {people.map((p) => (
                <div className="tl-row" key={p.person_id}>
                  <div className="tl-label" title={`${p.name} · ${p.position ?? ""}`}>
                    <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", flex: 1 }}>
                      {p.name}<small> {p.position}</small>
                    </span>
                    <span className={`pill ${p.clashes ? "bad" : p.days_away > 10 ? "warn" : ""}`} title={`${p.days_away} days away${p.clashes ? `, ${p.clashes} trips at the same time` : ""}`}>{p.days_away}</span>
                  </div>
                  <div className="tl-lane" style={{ height: 34, ...grid }}>
                    {data.blackouts.map((b) => {
                      const a = Math.max(from, ts(b.start_date)), z = Math.min(to, ts(b.end_date) + DAY);
                      return z > a ? <i key={b.id} className="tl-blackout" title={`${b.name} (${fmt(b.start_date)} to ${fmt(b.end_date)})`} style={{ left: `${pct(a)}%`, width: `${pct(z) - pct(a)}%` }} /> : null;
                    })}
                    {todayPct > 0 && todayPct < 100 && <i className="tl-today" style={{ left: `${todayPct}%` }} />}
                    {p.trips.map((t) => {
                      const fam = familyOf(t.event_code);
                      const a = Math.max(from, ts(t.start_date)), z = Math.min(to, ts(t.end_date) + DAY);
                      if (z <= a) return null;
                      const tip = (<><b>{t.title}</b><div>{fmt(t.start_date)}{t.end_date !== t.start_date ? ` to ${fmt(t.end_date)}` : ""}</div>
                        <div className="t-muted">{fam.label}{t.travels ? "" : " · hosts the visit"}{t.clash ? " · at the same time as another trip" : ""}</div></>);
                      return (
                        <button key={t.id} type="button" aria-label={`${p.name}: ${t.title}, ${fmt(t.start_date)}`}
                          className={`tl-bar${t.status === "generated" ? " draft" : ""}${t.clash ? " clash" : ""}${t.travels ? "" : " host"}`}
                          style={{ left: `${pct(a)}%`, width: `${pct(z) - pct(a)}%`, top: 8, ["--bar" as string]: fam.color, ["--bar-ink" as string]: fam.ink }}
                          onMouseMove={(e) => show(e, tip)} onMouseLeave={hide} onFocus={(e) => showAt(e.currentTarget, tip)} onBlur={hide}
                          onClick={() => onOpen(t.id)}>
                          {(z - a) / (to - from) > 0.07 ? t.event : ""}
                        </button>
                      );
                    })}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </>
      )}
      {node}
    </div>
  );
}
