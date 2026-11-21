import { FormEvent, useCallback, useEffect, useState } from "react";
import { api } from "./api";

type Rate = { id: number; rate_kind: string; mode: string | null; position_id: number | null; position: string | null; amount: number; currency: string; valid_from: string; valid_to: string | null; note: string | null };
type Region = { id: number; name: string; code: string };
type Override = { id: number; from_region_id: number | null; from_region: string | null; to_unit_id: number; to_unit: string; to_kind: string; mode: string; note: string | null };
type Config = {
  rates: Rate[]; regions: Region[]; modes: { from_region_id: number; to_region_id: number; mode: string }[]; overrides: Override[];
  settings: Record<string, number | null>; effective_settings: Record<string, number | null>;
  tiers: { min_days_ahead: number; factor: number; note: string | null }[]; positions: { id: number; name: string }[];
};
type BudgetLine = { id: number; event_name: string; position_name: string | null; remarks: string | null; persons: number | null; frequency: number | null; unit_price: number | null; annual_cost: number; event_type_id: number | null; event: string | null };
type Events = { id: number; name: string }[];

const KIND: Record<string, string> = { airfare: "Air fare (round trip)", sea_fare: "Sea fare", land_transport: "Land transport", lodging_per_night: "Hotel per night", per_diem: "Per diem per day", local_transport: "Local transport per trip", other: "Other" };
const money = (n: number) => new Intl.NumberFormat("en-PH", { style: "currency", currency: "PHP", maximumFractionDigits: 0 }).format(n);

export default function CostSettings({ year, isAdmin, onChanged }: { year: number; isAdmin: boolean; onChanged: () => void }) {
  const [cfg, setCfg] = useState<Config | null>(null);
  const [msg, setMsg] = useState<{ text: string; ok: boolean } | null>(null);
  const load = useCallback(async () => {
    const r = await api<Config>("/api/cost/config");
    if (r.ok) setCfg(r.data);
  }, []);
  useEffect(() => { void load(); }, [load]);
  const done = async (r: { ok: boolean; error: string | null }, text: string) => {
    setMsg(r.ok ? { text, ok: true } : { text: r.error ?? "", ok: false });
    if (r.ok) { await load(); onChanged(); }
    return r.ok;
  };
  if (!cfg) return null;
  const modeOf = (from: number, to: number) => cfg.modes.find((m) => m.from_region_id === from && m.to_region_id === to)?.mode ?? "";

  return (
    <details className="card">
      <summary>Rates and travel modes</summary>
      {msg && <p className={msg.ok ? "good" : "problem"} role={msg.ok ? "status" : "alert"}>{msg.text}</p>}

      <h4>Rates</h4>
      <p className="muted">Amounts in pesos. A rate for a position beats the general one. A new rate from a date ends the one it replaces; earlier trips keep the old price.</p>
      <div className="heatwrap">
        <table className="trips money">
          <thead><tr><th>Cost</th><th>Mode</th><th>Position</th><th>Amount</th><th>From</th><th>Until</th><th></th></tr></thead>
          <tbody>
            {cfg.rates.map((r) => (
              <tr key={r.id} className={r.valid_to ? "ended" : ""}>
                <td>{KIND[r.rate_kind] ?? r.rate_kind}</td><td>{r.mode ?? "All"}</td><td>{r.position ?? "Everybody"}</td>
                <td>{money(r.amount)}</td><td>{r.valid_from}</td><td>{r.valid_to ?? ""}</td>
                <td>{isAdmin && !r.valid_to && <button className="link" onClick={async () => window.confirm("End this rate today?") && done(await api(`/api/admin/cost/rates/${r.id}`, "DELETE"), "The rate was ended.")}>End</button>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {isAdmin && <RateForm cfg={cfg} onSave={async (body) => done(await api("/api/admin/cost/rates", "POST", body), "The rate was saved.")} />}

      <h4>Where people are based</h4>
      <SettingsForm cfg={cfg} isAdmin={isAdmin} onSave={async (body) => done(await api("/api/admin/cost/settings", "PUT", body), "Saved.")} />

      <h4>Travel modes between regions</h4>
      <p className="muted">How people travel from the region they are based in (rows) to the region of the trip (columns). Inside a region people go by land unless a place below says otherwise.</p>
      {cfg.modes.length === 0 ? (
        <p>
          No travel modes are loaded.{" "}
          {isAdmin && <button onClick={async () => done(await api("/api/admin/cost/modes/suggest", "POST"), "Suggested travel modes were loaded. Please check them.")}>Load suggested modes</button>}
          <span className="muted"> Suggested: land inside a region and between NCR, North Luzon and South Luzon; air otherwise.</span>
        </p>
      ) : (
        <div className="heatwrap">
          <table className="trips modes">
            <thead><tr><th>From \ To</th>{cfg.regions.map((r) => <th key={r.id}>{r.name}</th>)}</tr></thead>
            <tbody>
              {cfg.regions.map((from) => (
                <tr key={from.id}>
                  <th>{from.name}</th>
                  {cfg.regions.map((to) => (
                    <td key={to.id}>
                      {isAdmin ? (
                        <select aria-label={`From ${from.name} to ${to.name}`} value={modeOf(from.id, to.id)}
                          onChange={async (e) => done(await api("/api/admin/cost/modes", "PUT", { from_region_id: from.id, to_region_id: to.id, mode: e.target.value }), "Saved.")}>
                          <option value="">Land</option><option value="land">Land</option><option value="air">Air</option><option value="sea">Sea</option>
                        </select>
                      ) : (modeOf(from.id, to.id) || "land")}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <h4>Places that need another mode</h4>
      <p className="muted">For an island or a remote place: everybody (or everybody from one region) goes there by the mode below, whatever the table says.</p>
      {cfg.overrides.length === 0 && <p className="muted">None.</p>}
      <ul className="rules">
        {cfg.overrides.map((o) => (
          <li key={o.id}>
            <div><strong>{o.to_unit}</strong> · {o.mode} · {o.from_region ? `from ${o.from_region}` : "from anywhere"}{o.note && <span className="muted"> · {o.note}</span>}</div>
            {isAdmin && <button className="link" onClick={async () => done(await api(`/api/admin/cost/overrides/${o.id}`, "DELETE"), "Removed.")}>Remove</button>}
          </li>
        ))}
      </ul>
      {isAdmin && <OverrideForm onSave={async (body) => done(await api("/api/admin/cost/overrides", "POST", body), "Saved.")} />}

      <h4>Early booking discounts</h4>
      <TiersForm cfg={cfg} isAdmin={isAdmin} onSave={async (tiers) => done(await api("/api/admin/cost/booking-tiers", "PUT", { tiers }), "The discount tiers were saved.")} />

      <Budget year={year} isAdmin={isAdmin} onChanged={() => { void load(); onChanged(); }} />
    </details>
  );
}

function RateForm({ cfg, onSave }: { cfg: Config; onSave: (b: unknown) => Promise<boolean> }) {
  const [f, setF] = useState({ rate_kind: "per_diem", mode: "", position_id: "", amount: "", valid_from: "", note: "" });
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    const ok = await onSave({ rate_kind: f.rate_kind, mode: f.mode || null, position_id: f.position_id ? Number(f.position_id) : null, amount: Number(f.amount), valid_from: f.valid_from, note: f.note || null });
    if (ok) setF({ ...f, amount: "", note: "" });
  };
  return (
    <form className="subform" onSubmit={submit}>
      <h4>Set a rate</h4>
      <div className="row">
        <label>Cost<select value={f.rate_kind} onChange={(e) => setF({ ...f, rate_kind: e.target.value })}>{Object.entries(KIND).map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select></label>
        <label>Mode<select value={f.mode} onChange={(e) => setF({ ...f, mode: e.target.value })}><option value="">All</option><option value="air">Air</option><option value="land">Land</option><option value="sea">Sea</option></select></label>
        <label>Position<select value={f.position_id} onChange={(e) => setF({ ...f, position_id: e.target.value })}><option value="">Everybody</option>{cfg.positions.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}</select></label>
      </div>
      <div className="row">
        <label>Amount (₱)<input required type="number" min={0} step="1" value={f.amount} onChange={(e) => setF({ ...f, amount: e.target.value })} /></label>
        <label>Valid from<input required type="date" value={f.valid_from} onChange={(e) => setF({ ...f, valid_from: e.target.value })} /></label>
        <label>Note<input maxLength={200} value={f.note} onChange={(e) => setF({ ...f, note: e.target.value })} /></label>
      </div>
      <p><button type="submit">Save rate</button></p>
    </form>
  );
}

function SettingsForm({ cfg, isAdmin, onSave }: { cfg: Config; isAdmin: boolean; onSave: (b: unknown) => Promise<boolean> }) {
  const [hq, setHq] = useState<string>(String(cfg.settings.hq_region_id ?? ""));
  const [venue, setVenue] = useState<string>(String(cfg.settings.venue_region_id ?? ""));
  const name = (id: number | null) => cfg.regions.find((r) => r.id === id)?.name ?? "not set";
  if (!isAdmin) return <p>Head of Field is based in {name(cfg.effective_settings.hq_region_id)}. Nationwide events are held in {name(cfg.effective_settings.venue_region_id)}.</p>;
  return (
    <form className="row" onSubmit={async (e) => { e.preventDefault(); await onSave({ hq_region_id: hq ? Number(hq) : null, venue_region_id: venue ? Number(venue) : null }); }}>
      <label>The Head of Field is based in
        <select value={hq} onChange={(e) => setHq(e.target.value)}><option value="">NCR (default)</option>{cfg.regions.map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}</select></label>
      <label>Nationwide events are held in
        <select value={venue} onChange={(e) => setVenue(e.target.value)}><option value="">NCR (default)</option>{cfg.regions.map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}</select></label>
      <button type="submit">Save</button>
    </form>
  );
}

function OverrideForm({ onSave }: { onSave: (b: unknown) => Promise<boolean> }) {
  const [units, setUnits] = useState<{ id: number; name: string; kind: string }[]>([]);
  const [regions, setRegions] = useState<Region[]>([]);
  const [f, setF] = useState({ to_unit_id: "", from_region_id: "", mode: "air", note: "" });
  useEffect(() => {
    void api<{ regions: Region[]; clusters: { id: number; name: string }[]; local_offices: { id: number; name: string }[] }>("/api/admin/users/meta").then((r) => {
      if (!r.ok) return;
      setRegions(r.data.regions);
      setUnits([...r.data.clusters.map((c) => ({ ...c, kind: "Cluster" })), ...r.data.local_offices.map((c) => ({ ...c, kind: "Local office" }))]);
    });
  }, []);
  return (
    <form className="row" onSubmit={async (e) => { e.preventDefault(); if (await onSave({ to_unit_id: Number(f.to_unit_id), from_region_id: f.from_region_id ? Number(f.from_region_id) : null, mode: f.mode, note: f.note || null })) setF({ ...f, to_unit_id: "", note: "" }); }}>
      <label>Place<select required value={f.to_unit_id} onChange={(e) => setF({ ...f, to_unit_id: e.target.value })}><option value="">Choose…</option>{units.map((u) => <option key={`${u.kind}${u.id}`} value={u.id}>{u.kind}: {u.name}</option>)}</select></label>
      <label>From<select value={f.from_region_id} onChange={(e) => setF({ ...f, from_region_id: e.target.value })}><option value="">Anywhere</option>{regions.map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}</select></label>
      <label>Mode<select value={f.mode} onChange={(e) => setF({ ...f, mode: e.target.value })}><option value="air">Air</option><option value="sea">Sea</option><option value="land">Land</option></select></label>
      <label>Note<input maxLength={200} value={f.note} onChange={(e) => setF({ ...f, note: e.target.value })} /></label>
      <button type="submit">Add</button>
    </form>
  );
}

function TiersForm({ cfg, isAdmin, onSave }: { cfg: Config; isAdmin: boolean; onSave: (t: unknown[]) => Promise<boolean> }) {
  const [rows, setRows] = useState(cfg.tiers.map((t) => ({ days: String(t.min_days_ahead), off: String(Math.round((1 - t.factor) * 1000) / 10) })));
  if (!isAdmin) return cfg.tiers.length ? <ul>{cfg.tiers.map((t) => <li key={t.min_days_ahead}>{t.min_days_ahead}+ days ahead: {Math.round((1 - t.factor) * 100)}% off the fare</li>)}</ul> : <p className="muted">No discounts are set.</p>;
  return (
    <form onSubmit={async (e) => { e.preventDefault(); await onSave(rows.filter((r) => r.days).map((r) => ({ min_days_ahead: Number(r.days), factor: Math.round((1 - Number(r.off) / 100) * 1000) / 1000 }))); }}>
      <p className="muted">
        Enter what the travel desk can confirm: when a fare is booked at least this many days ahead, it is this many percent cheaper. Nothing is assumed: with no tiers the estimate shows no saving.
      </p>
      {rows.map((r, i) => (
        <div className="row" key={i}>
          <label>At least (days ahead)<input type="number" min={1} max={730} value={r.days} onChange={(e) => setRows(rows.map((x, j) => (j === i ? { ...x, days: e.target.value } : x)))} /></label>
          <label>Cheaper by (%)<input type="number" min={0} max={99} step="0.1" value={r.off} onChange={(e) => setRows(rows.map((x, j) => (j === i ? { ...x, off: e.target.value } : x)))} /></label>
          <button type="button" className="link" onClick={() => setRows(rows.filter((_, j) => j !== i))}>Remove</button>
        </div>
      ))}
      <p className="row"><button type="button" className="secondary" onClick={() => setRows([...rows, { days: "", off: "" }])}>Add a tier</button><button type="submit">Save tiers</button></p>
    </form>
  );
}

function Budget({ year, isAdmin, onChanged }: { year: number; isAdmin: boolean; onChanged: () => void }) {
  const [lines, setLines] = useState<BudgetLine[] | null>(null);
  const [events, setEvents] = useState<Events>([]);
  const [file, setFile] = useState<File | null>(null);
  const [report, setReport] = useState<{ applied: boolean; lines: number; total: number; unmatched_lines: number; unmatched_total: number } | null>(null);
  const [msg, setMsg] = useState<{ text: string; ok: boolean } | null>(null);
  const load = useCallback(async () => {
    const r = await api<BudgetLine[]>(`/api/cost/${year}/budget`);
    if (r.ok) setLines(r.data);
  }, [year]);
  useEffect(() => { void load(); void api<{ event_types: Events }>("/api/catalog").then((r) => r.ok && setEvents(r.data.event_types)); }, [load]);

  const upload = async (commit: boolean) => {
    if (!file) return;
    const form = new FormData(); form.append("file", file);
    const r = await fetch(`/api/admin/budget/import?year=${year}&commit=${commit}`, { method: "POST", body: form });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) { setReport(null); return setMsg({ text: typeof data.detail === "string" ? data.detail : "The import failed.", ok: false }); }
    setReport(data);
    if (commit) { setMsg({ text: "The budget was loaded.", ok: true }); setFile(null); await load(); onChanged(); } else setMsg(null);
  };

  return (
    <>
      <h4>Budget</h4>
      <p className="muted">The budget lines of {year} (Field Collections), from the planning workbook ("Per Budget Travelling (FC)"). Each line is matched to an event so that the plan can be compared with the budget.</p>
      {msg && <p className={msg.ok ? "good" : "problem"} role={msg.ok ? "status" : "alert"}>{msg.text}</p>}
      {isAdmin && (
        <div className="row">
          <label>Budget workbook (.xlsx)<input type="file" accept=".xlsx" onChange={(e) => { setFile(e.target.files?.[0] ?? null); setReport(null); setMsg(null); }} /></label>
          <button className="secondary" disabled={!file} onClick={() => upload(false)}>Check</button>
          {report && !report.applied && <button onClick={() => upload(true)}>Load {report.lines} lines</button>}
        </div>
      )}
      {report && !report.applied && <p>{report.lines} lines worth {money(report.total)}; {report.unmatched_lines} not matched to an event ({money(report.unmatched_total)}). Loading replaces the lines of {year}.</p>}
      {lines && lines.length > 0 && (
        <div className="heatwrap">
          <table className="trips money">
            <thead><tr><th>Event in the budget</th><th>Position</th><th>Persons</th><th>Freq.</th><th>Unit price</th><th>Annual cost</th><th>Matched to</th></tr></thead>
            <tbody>
              {lines.map((l) => (
                <tr key={l.id}>
                  <td>{l.event_name}</td><td>{l.position_name}</td><td>{l.persons}</td><td>{l.frequency}</td><td>{l.unit_price ? money(l.unit_price) : ""}</td><td>{money(l.annual_cost)}</td>
                  <td>{isAdmin ? (
                    <select aria-label={`Event for ${l.event_name}, ${l.position_name ?? ""}`} value={l.event_type_id ?? ""}
                      onChange={async (e) => { await api(`/api/admin/budget/lines/${l.id}`, "PUT", { event_type_id: e.target.value ? Number(e.target.value) : null }); await load(); onChanged(); }}>
                      <option value="">Not matched</option>{events.map((ev) => <option key={ev.id} value={ev.id}>{ev.name}</option>)}
                    </select>) : (l.event ?? "Not matched")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
