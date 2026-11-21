import { useEffect, useMemo, useState } from "react";
import { FAMILIES, familyOf } from "./theme";
import { useTip } from "./charts";

type Row = { unit_id: number | null; label: string; months: number[] };
export type Summary = {
  year: number;
  regions: { id: number; name: string; rows: Row[] }[];
  nationwide: Row;
};
type Trip = {
  id: number; title: string; start_date: string; end_date: string; status: string; source: string; event: string;
  event_code: string; place: string | null; area_pending: boolean; row_unit_id: number | null; travelers: number; changed: boolean;
};

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const DAY = 86400000;
const t = (s: string) => new Date(s + "T00:00:00").getTime();
const fmt = (s: string) => new Date(s + "T00:00:00").toLocaleDateString("en-US", { month: "short", day: "numeric" });

type Placed = { trip: Trip; lane: number };

/** Packs overlapping trips of one row into lanes so that no bars lie on top of each other. */
function pack(trips: Trip[]): { placed: Placed[]; lanes: number } {
  const ends: number[] = [];
  const placed: Placed[] = [];
  for (const trip of [...trips].sort((a, b) => a.start_date.localeCompare(b.start_date))) {
    const s = t(trip.start_date);
    let lane = ends.findIndex((e) => e + DAY * 2 <= s);
    if (lane < 0) { lane = ends.length; ends.push(0); }
    ends[lane] = t(trip.end_date);
    placed.push({ trip, lane });
  }
  return { placed, lanes: Math.max(1, ends.length) };
}

/** The year as a timeline: one row per area, bars colored by event family. */
export default function Timeline({ year, summary, tick, onOpen }: { year: number; summary: Summary; tick: number; onOpen: (id: number) => void }) {
  const [trips, setTrips] = useState<Trip[] | null>(null);
  const [off, setOff] = useState<Set<string>>(new Set());
  const [quarter, setQuarter] = useState<number | null>(null);
  const { show, showAt, hide, node } = useTip();

  useEffect(() => {
    let live = true;
    void fetch(`/api/plan/${year}/trips`).then(async (r) => live && setTrips(r.ok ? ((await r.json()) as Trip[]) : []));
    return () => { live = false; };
  }, [year, tick]);

  const first = quarter === null ? 0 : quarter * 3;
  const last = quarter === null ? 12 : first + 3;
  const from = new Date(year, first, 1).getTime();
  const to = new Date(year, last, 1).getTime();
  const pct = (ms: number) => ((ms - from) / (to - from)) * 100;

  const byRow = useMemo(() => {
    const m = new Map<number | null, Trip[]>();
    for (const x of trips ?? []) {
      if (x.status === "cancelled" || off.has(familyOf(x.event_code).key)) continue;
      m.set(x.row_unit_id, [...(m.get(x.row_unit_id) ?? []), x]);
    }
    return m;
  }, [trips, off]);

  const nowPct = pct(Date.now());
  const months = Array.from({ length: last - first }, (_, i) => first + i);
  const gridStyle = { backgroundImage: `repeating-linear-gradient(90deg, transparent 0, transparent calc(100% / ${months.length} - 1px), var(--line) calc(100% / ${months.length} - 1px), var(--line) calc(100% / ${months.length}))` };

  const present = new Set((trips ?? []).filter((x) => x.status !== "cancelled").map((x) => familyOf(x.event_code).key));

  const lane = (id: string, key: number | null, label: string) => {
    const { placed, lanes } = pack(byRow.get(key) ?? []);
    return (
      <div className="tl-row" key={id}>
        <div className="tl-label">{label}</div>
        <div className="tl-lane" style={{ height: lanes * 26 + 10, ...gridStyle }}>
          {nowPct > 0 && nowPct < 100 && <i className="tl-today" style={{ left: `${nowPct}%` }} />}
          {placed.map(({ trip, lane: l }) => {
            const fam = familyOf(trip.event_code);
            const a = Math.max(from, t(trip.start_date));
            const b = Math.min(to, t(trip.end_date) + DAY);
            if (b <= a) return null;
            const wide = ((b - a) / (to - from)) * 100;
            const tip = (
              <>
                <b>{trip.title}</b>
                <div>{fmt(trip.start_date)}{trip.end_date !== trip.start_date ? ` to ${fmt(trip.end_date)}` : ""}</div>
                <div className="t-muted">{fam.label} · {trip.travelers} {trip.travelers === 1 ? "traveler" : "travelers"}{trip.place ? ` · ${trip.place}` : ""}</div>
                {trip.area_pending && <div className="t-muted">Area still to be chosen</div>}
              </>
            );
            return (
              <button key={trip.id} type="button" className={`tl-bar${trip.status === "generated" ? " draft" : ""}${trip.source === "manual" ? " manual" : ""}`}
                aria-label={`${trip.title}, ${fmt(trip.start_date)}`}
                style={{ left: `${pct(a)}%`, width: `${wide}%`, top: 6 + l * 26, ["--bar" as string]: fam.color, ["--bar-ink" as string]: fam.ink }}
                onMouseMove={(e) => show(e, tip)} onMouseLeave={hide} onFocus={(e) => showAt(e.currentTarget, tip)} onBlur={hide}
                onClick={() => onOpen(trip.id)}>
                {wide > 6 ? trip.event : ""}
              </button>
            );
          })}
        </div>
      </div>
    );
  };

  return (
    <div>
      <div className="row" style={{ justifyContent: "space-between", alignItems: "center" }}>
        <div className="segctl" role="group" aria-label="Zoom">
          <button type="button" className={quarter === null ? "on" : ""} onClick={() => setQuarter(null)}>Year</button>
          {[0, 1, 2, 3].map((q) => <button key={q} type="button" className={quarter === q ? "on" : ""} onClick={() => setQuarter(q)}>Q{q + 1}</button>)}
        </div>
        <span className="muted">Hatched bars are proposed by the rules. Click a bar to open the trip.</span>
      </div>
      <div className="legend" aria-label="Legend">
        {FAMILIES.filter((f) => present.has(f.key)).map((f) => (
          <button key={f.key} type="button" className={off.has(f.key) ? "off" : ""} aria-pressed={!off.has(f.key)}
            onClick={() => setOff((s) => { const n = new Set(s); if (n.has(f.key)) n.delete(f.key); else n.add(f.key); return n; })}>
            <i className="sw" style={{ background: f.color }} />{f.label}
          </button>
        ))}
      </div>
      {trips === null ? <div className="skeleton" style={{ height: 240 }} /> : (
        <div className="tl" role="group" aria-label={`Timeline ${year}`}>
          <div className="tl-inner" style={{ ["--n" as string]: months.length }}>
            <div className="tl-head">
              <div className="tl-label" style={{ borderRight: "1px solid var(--line)" }} />
              <div className="tl-months">
                {months.map((m, i) => <span key={m} style={{ left: `${(i / months.length) * 100}%` }}>{MONTHS[m]}</span>)}
              </div>
            </div>
            {summary.regions.map((reg) => (
              <div key={reg.id}>
                <div className="tl-group">{reg.name}</div>
                {reg.rows.map((r) => lane(`${reg.id}-${r.label}`, r.unit_id, r.label))}
              </div>
            ))}
            <div className="tl-group">Nationwide</div>
            {lane("nation", null, summary.nationwide.label)}
          </div>
        </div>
      )}
      {node}
    </div>
  );
}
