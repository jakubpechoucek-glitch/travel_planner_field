import { familyOf } from "./theme";
import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";

type Position = { id: number; code: string; name: string; level: number; function_area: string };
type Rule = {
  rule_key: string;
  event_type_id: number | null;
  rule_type: string;
  scope_kind: string;
  position_id: number | null;
  period: string | null;
  interval_n: number | null;
  min_count: number | null;
  max_count: number | null;
  params: Record<string, unknown>;
  severity: Severity;
  description: string | null;
  summary: string;
};
type Severity = "block" | "warn" | "info";
type Part = { position_id: number; participation: "organizer" | "participant"; yearly_limit: number | null; travels: boolean };
type Merge = { merges_into_id: number; merges_into_name?: string; condition_text: string | null; severity: Severity };
type EventType = {
  id: number;
  code: string;
  name: string;
  description: string | null;
  organizer_position_id: number | null;
  visited_kind: string;
  joint_visit: string;
  is_company_event: boolean;
  typical_days: number | null;
  typical_mode: string | null;
  scheduling_notes: string | null;
  active: boolean;
  participation: Part[];
  rules: Rule[];
  merges: Merge[];
};
type Blackout = {
  id: number;
  plan_year: number;
  name: string;
  start_date: string;
  end_date: string;
  reason: string | null;
  severity: Severity;
  event_type_ids: number[];
  caused_by_event_type_id: number | null;
};
type CatalogData = { positions: Position[]; event_types: EventType[]; general_rules: Rule[]; blackouts: Blackout[] };

const RULE_TYPES: Record<string, string> = {
  annual_quota: "Yearly quota (how many per year)",
  cadence: "Cadence (every N periods)",
  preferred_window: "Preferred months",
  rotation: "Rotation (spread over clusters or offices)",
  participation_cap: "Limit for a position",
  period_cap: "Trip limit per person or position",
  concurrency_cap: "Limit at the same time",
};
const SCOPES: Record<string, string> = {
  cluster: "each cluster",
  local_office: "each local office",
  region: "each region",
  nationwide: "nationwide",
  person: "each person",
  position: "a position",
};
const PERIODS: Record<string, string> = { week: "week", month: "month", quarter: "quarter", half_year: "half-year", year: "year" };
const VISITED: Record<string, string> = {
  cluster: "A cluster",
  local_office: "A local office",
  region: "A region",
  nationwide: "Nationwide",
  external: "An outside place (for example a court)",
};
const JOINT: Record<string, string> = { no: "No", partial: "Partly", yes: "Yes" };
const MODES: Record<string, string> = { land: "Land", air: "Air", sea: "Sea", air_land: "Air and land", air_sea: "Air and sea", mixed: "Mixed" };
const SEVERITY: Record<Severity, string> = { block: "Block", warn: "Warn", info: "Info" };
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

type Result = { error: string | null; data: { id?: number } };

async function call(url: string, method: string, body?: unknown): Promise<Result> {
  const r = await fetch(url, {
    method,
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = (r.status === 204 ? {} : await r.json().catch(() => ({}))) as { id?: number; detail?: unknown };
  if (r.ok) return { error: null, data };
  const detail = typeof data.detail === "string" ? data.detail : "The change could not be saved. Please try again.";
  return { error: detail, data: {} };
}

export default function Catalog({ isAdmin }: { isAdmin: boolean }) {
  const [data, setData] = useState<CatalogData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<number | null>(null);
  const [editing, setEditing] = useState<EventType | "new" | null>(null);

  const load = useCallback(async () => {
    const r = await fetch("/api/catalog");
    if (!r.ok) return setError("The catalog could not be loaded. Please try again later.");
    const d = (await r.json()) as CatalogData;
    setData(d);
    setSelected((s) => s ?? d.event_types[0]?.id ?? null);
  }, []);
  useEffect(() => {
    void load();
  }, [load]);

  const positions = useMemo(() => new Map((data?.positions ?? []).map((p) => [p.id, p])), [data]);
  const current = data?.event_types.find((e) => e.id === selected) ?? null;

  if (error) return <section className="card"><p className="problem">{error}</p></section>;
  if (!data) return <section className="card"><p>Loading…</p></section>;

  return (
    <>
      <details className="card help">
        <summary>Help: event types and rules</summary>
        <p>
          An <strong>event type</strong> is a kind of trip or gathering, such as an area visit or the conference. Each
          one says who organizes it, who takes part, and how often it should happen. The <strong>rules</strong> below
          each event are used to build the yearly plan and to warn planners when a plan breaks them.
        </p>
        <p>
          <strong>Severity</strong> says what happens when a rule is broken: <em>Info</em> only shows a note,{" "}
          <em>Warn</em> asks the planner to confirm and give a reason, and <em>Block</em> does not allow saving.
          Changing a rule creates a new version; earlier plans keep the rule they were built with.
        </p>
        <p>
          <strong>Events that are not held every year.</strong> A yearly quota or cadence has a <em>Which years</em> setting. Enter <em>Held every 2 years</em> and the first year (for
          example 2027) and the event is planned in 2027, 2029, 2031 and so on, and left out of the years in between. Starting a second event one year later (2028) gives it the off years.
          Open the plan years you need with <em>Open plan year</em> on the Plan page.
        </p>
        <p>
          <strong>Blackout periods</strong> are dates when some events should not take place, for example the month of
          the conference. {isAdmin ? "" : "Only administrators can change the catalog."}
        </p>
      </details>

      <div className="catalog">
        <aside className="card events">
          <h2>Event types</h2>
          <ul>
            {data.event_types.map((e) => (
              <li key={e.id}>
                <button className={e.id === selected ? "pick on" : "pick"} onClick={() => { setSelected(e.id); setEditing(null); }}>
                  <i className="dot" style={{ background: familyOf(e.code).color }} />
                  {e.name}
                  {!e.active && <span className="muted"> (inactive)</span>}
                </button>
              </li>
            ))}
          </ul>
          {isAdmin && <button onClick={() => setEditing("new")}>Add event type</button>}
        </aside>

        <div>
          {editing ? (
            <EventForm
              key={editing === "new" ? "new" : editing.id}
              event={editing === "new" ? null : editing}
              data={data}
              onDone={async (id) => { setEditing(null); await load(); if (id) setSelected(id); }}
              onCancel={() => setEditing(null)}
            />
          ) : (
            current && (
              <EventView event={current} data={data} positions={positions} isAdmin={isAdmin}
                onEdit={() => setEditing(current)} onChanged={load} />
            )
          )}
          <GeneralRules rules={data.general_rules} positions={data.positions} isAdmin={isAdmin} onChanged={load} />
          <Blackouts data={data} isAdmin={isAdmin} onChanged={load} />
        </div>
      </div>
    </>
  );
}

function EventView({ event, data, positions, isAdmin, onEdit, onChanged }: {
  event: EventType; data: CatalogData; positions: Map<number, Position>; isAdmin: boolean;
  onEdit: () => void; onChanged: () => void;
}) {
  const organizer = event.organizer_position_id ? positions.get(event.organizer_position_id)?.name : null;
  return (
    <section className="card">
      <div className="head">
        <div>
          <h2>{event.name}</h2>
          <p className="muted">{event.code}{event.is_company_event ? " · Company event" : ""}</p>
        </div>
        {isAdmin && <button onClick={onEdit}>Edit</button>}
      </div>
      {event.description && <p>{event.description}</p>}
      <dl className="facts">
        <dt>Organizer</dt><dd>{organizer ?? "Not set"}</dd>
        <dt>Visits</dt><dd>{VISITED[event.visited_kind]}</dd>
        <dt>Others join</dt><dd>{JOINT[event.joint_visit]}</dd>
        <dt>Typical length</dt><dd>{event.typical_days ? `${event.typical_days} day${event.typical_days === 1 ? "" : "s"}` : "Not set"}</dd>
        <dt>Transport</dt><dd>{event.typical_mode ? MODES[event.typical_mode] : "Not set"}</dd>
      </dl>
      {event.scheduling_notes && <p className="note">{event.scheduling_notes}</p>}

      <h3>Who takes part</h3>
      {event.participation.length === 0 ? <p className="muted">No positions set.</p> : (
        <ul className="chips">
          {event.participation.map((p) => (
            <li key={p.position_id} className={p.participation === "organizer" ? "chip strong" : "chip"}>
              {positions.get(p.position_id)?.name}
              {p.participation === "organizer" && " (organizer)"}
              {p.yearly_limit !== null && ` · up to ${p.yearly_limit} a year`}
              {!p.travels && " · hosts, does not travel"}
            </li>
          ))}
        </ul>
      )}

      <h3>Rules</h3>
      <RuleList rules={event.rules} positions={data.positions} eventId={event.id} isAdmin={isAdmin} onChanged={onChanged} />

      {event.merges.length > 0 && (
        <>
          <h3>Combined with</h3>
          <ul>
            {event.merges.map((m) => (
              <li key={m.merges_into_id}>
                <strong>{m.merges_into_name}</strong>
                {m.condition_text && <span className="muted"> · {m.condition_text}</span>}
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}

function RuleList({ rules, positions, eventId, isAdmin, onChanged }: {
  rules: Rule[]; positions: Position[]; eventId: number | null; isAdmin: boolean; onChanged: () => void;
}) {
  const [editing, setEditing] = useState<Rule | "new" | null>(null);
  const remove = async (key: string) => {
    if (!window.confirm("Remove this rule? Earlier plans keep the version they were built with.")) return;
    const { error: err } = await call(`/api/admin/rules/${key}`, "DELETE");
    if (err) window.alert(err);
    onChanged();
  };
  return (
    <>
      {rules.length === 0 && <p className="muted">No rules yet.</p>}
      <ul className="rules">
        {rules.map((r) => (
          <li key={r.rule_key}>
            <div>
              <span className={`badge sev-${r.severity}`}>{SEVERITY[r.severity]}</span> {r.summary}
              {r.description && <div className="muted">{r.description}</div>}
            </div>
            {isAdmin && (
              <span className="actions">
                <button className="link" onClick={() => setEditing(r)}>Edit</button>
                <button className="link" onClick={() => remove(r.rule_key)}>Remove</button>
              </span>
            )}
          </li>
        ))}
      </ul>
      {isAdmin && !editing && <button onClick={() => setEditing("new")}>Add rule</button>}
      {editing && (
        <RuleForm rule={editing === "new" ? null : editing} eventId={eventId} positions={positions}
          onCancel={() => setEditing(null)} onSaved={() => { setEditing(null); onChanged(); }} />
      )}
    </>
  );
}

function RuleForm({ rule, eventId, positions, onCancel, onSaved }: {
  rule: Rule | null; eventId: number | null; positions: Position[]; onCancel: () => void; onSaved: () => void;
}) {
  const general = eventId === null;
  const [type, setType] = useState(rule?.rule_type ?? (general ? "period_cap" : "annual_quota"));
  const [scope, setScope] = useState(rule?.scope_kind ?? (general ? "position" : "cluster"));
  const [positionId, setPositionId] = useState<number | "">(rule?.position_id ?? "");
  const [period, setPeriod] = useState(rule?.period ?? (general ? "month" : "year"));
  const [interval, setInterval] = useState<number | "">(rule?.interval_n ?? 1);
  const [min, setMin] = useState<number | "">(rule?.min_count ?? "");
  const [max, setMax] = useState<number | "">(rule?.max_count ?? "");
  const [months, setMonths] = useState<number[]>((rule?.params.months as number[]) ?? []);
  const [unit, setUnit] = useState((rule?.params.unit as string) ?? "cluster");
  const [every, setEvery] = useState<number | "">((rule?.params.every_n_years as number) ?? 1);
  const [firstYear, setFirstYear] = useState<number | "">((rule?.params.first_year as number) ?? "");
  const [severity, setSeverity] = useState<Severity>(rule?.severity ?? "warn");
  const [note, setNote] = useState(rule?.description ?? "");
  const [error, setError] = useState<string | null>(null);

  const types = Object.entries(RULE_TYPES).filter(([t]) =>
    general ? ["period_cap", "participation_cap", "concurrency_cap"].includes(t) : true);
  const needsPeriod = ["cadence", "rotation", "participation_cap", "period_cap", "concurrency_cap"].includes(type);
  const scopes = Object.entries(SCOPES).filter(([s]) =>
    ["period_cap"].includes(type) ? ["person", "position"].includes(s)
      : ["participation_cap"].includes(type) ? s === "position"
      : !["person", "position"].includes(s));

  const toNum = (v: number | "") => (v === "" ? null : v);
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    const body = {
      event_type_id: eventId,
      rule_type: type,
      scope_kind: scopes.some(([s]) => s === scope) ? scope : scopes[0][0],
      position_id: ["period_cap", "participation_cap", "concurrency_cap"].includes(type) && (scope === "position" || type === "participation_cap")
        ? toNum(positionId) : null,
      period: type === "annual_quota" ? "year" : needsPeriod ? period : null,
      interval_n: type === "cadence" ? toNum(interval) : null,
      min_count: type === "cadence" || type === "preferred_window" ? null : toNum(min),
      max_count: type === "cadence" || type === "preferred_window" ? null : toNum(max),
      params: type === "preferred_window" ? { months } : type === "rotation" ? { unit }
        : (type === "annual_quota" || type === "cadence") && Number(every) >= 2 ? { every_n_years: Number(every), first_year: toNum(firstYear) } : {},
      severity,
      description: note || null,
    };
    const { error: err } = rule
      ? await call(`/api/admin/rules/${rule.rule_key}`, "PUT", body)
      : await call("/api/admin/rules", "POST", body);
    if (err) setError(err);
    else onSaved();
  };

  const num = (v: number | "", set: (n: number | "") => void) => ({
    type: "number" as const, min: 0, value: v, onChange: (e: React.ChangeEvent<HTMLInputElement>) =>
      set(e.target.value === "" ? "" : Number(e.target.value)),
  });

  return (
    <form className="subform" onSubmit={submit}>
      <h4>{rule ? "Edit rule" : "New rule"}</h4>
      <label>Kind of rule
        <select value={type} onChange={(e) => { setType(e.target.value); setScope(e.target.value === "period_cap" ? "position" : e.target.value === "participation_cap" ? "position" : "cluster"); }}>
          {types.map(([t, l]) => <option key={t} value={t}>{l}</option>)}
        </select>
      </label>
      {scopes.length > 1 && (
        <label>Applies to
          <select value={scope} onChange={(e) => setScope(e.target.value)}>
            {scopes.map(([s, l]) => <option key={s} value={s}>{l}</option>)}
          </select>
        </label>
      )}
      {(type === "participation_cap" || (type === "period_cap" && scope === "position")) && (
        <label>Position
          <select value={positionId} required onChange={(e) => setPositionId(e.target.value ? Number(e.target.value) : "")}>
            <option value="">Choose…</option>
            {positions.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
        </label>
      )}
      {needsPeriod && (
        <label>Per
          <select value={period} onChange={(e) => setPeriod(e.target.value)}>
            {Object.entries(PERIODS).map(([p, l]) => <option key={p} value={p}>{l}</option>)}
          </select>
        </label>
      )}
      {type === "cadence" && <label>Every how many periods<input required {...num(interval, setInterval)} min={1} /></label>}
      {!["cadence", "preferred_window"].includes(type) && (
        <div className="row">
          <label>Minimum<input {...num(min, setMin)} /></label>
          <label>Maximum<input {...num(max, setMax)} /></label>
        </div>
      )}
      {(type === "annual_quota" || type === "cadence") && (
        <fieldset>
          <legend>Which years</legend>
          <div className="row">
            <label>Held every … years<input type="number" min={1} max={10} value={every}
              onChange={(e) => setEvery(e.target.value === "" ? "" : Number(e.target.value))} /></label>
            {Number(every) >= 2 && (
              <label>First year<input type="number" min={2000} max={2100} required value={firstYear} placeholder="2027"
                onChange={(e) => setFirstYear(e.target.value === "" ? "" : Number(e.target.value))} /></label>
            )}
          </div>
          <p className="muted">1 means every year. With 2, the event is planned only in the first year and every second year after it (for example 2027, 2029, 2031); in the other years it is left out of the plan.</p>
        </fieldset>
      )}
      {type === "rotation" && (
        <label>Rotate through
          <select value={unit} onChange={(e) => setUnit(e.target.value)}>
            <option value="cluster">Clusters</option>
            <option value="local_office">Local offices</option>
          </select>
        </label>
      )}
      {type === "preferred_window" && (
        <fieldset>
          <legend>Months</legend>
          <div className="months">
            {MONTHS.map((m, i) => (
              <label key={m} className="check">
                <input type="checkbox" checked={months.includes(i + 1)}
                  onChange={(e) => setMonths(e.target.checked ? [...months, i + 1].sort((a, b) => a - b) : months.filter((x) => x !== i + 1))} />
                {m}
              </label>
            ))}
          </div>
        </fieldset>
      )}
      <label>If the rule is broken
        <select value={severity} onChange={(e) => setSeverity(e.target.value as Severity)}>
          <option value="info">Info: show a note</option>
          <option value="warn">Warn: ask for confirmation and a reason</option>
          <option value="block">Block: do not allow saving</option>
        </select>
      </label>
      <label>Note (optional)<input value={note} maxLength={500} onChange={(e) => setNote(e.target.value)} /></label>
      {error && <p className="problem">{error}</p>}
      <p className="row"><button type="submit">Save rule</button><button type="button" className="link" onClick={onCancel}>Cancel</button></p>
    </form>
  );
}

function GeneralRules({ rules, positions, isAdmin, onChanged }: {
  rules: Rule[]; positions: Position[]; isAdmin: boolean; onChanged: () => void;
}) {
  return (
    <section className="card">
      <h2>Limits for all events</h2>
      <p className="muted">These apply to a traveler across every event type, for example the number of trips per month.</p>
      <RuleList rules={rules} positions={positions} eventId={null} isAdmin={isAdmin} onChanged={onChanged} />
    </section>
  );
}

function EventForm({ event, data, onDone, onCancel }: {
  event: EventType | null; data: CatalogData; onDone: (id?: number) => void; onCancel: () => void;
}) {
  const [f, setF] = useState({
    code: event?.code ?? "",
    name: event?.name ?? "",
    description: event?.description ?? "",
    organizer_position_id: event?.organizer_position_id ?? ("" as number | ""),
    visited_kind: event?.visited_kind ?? "cluster",
    joint_visit: event?.joint_visit ?? "no",
    is_company_event: event?.is_company_event ?? false,
    typical_days: event?.typical_days ?? ("" as number | ""),
    typical_mode: event?.typical_mode ?? "",
    scheduling_notes: event?.scheduling_notes ?? "",
    active: event?.active ?? true,
  });
  const [parts, setParts] = useState<Record<number, Part>>(
    Object.fromEntries((event?.participation ?? []).map((p) => [p.position_id, p])));
  const [merges, setMerges] = useState<Set<number>>(new Set((event?.merges ?? []).map((m) => m.merges_into_id)));
  const [error, setError] = useState<string | null>(null);
  const keptMerges = new Map((event?.merges ?? []).map((m) => [m.merges_into_id, m]));

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    const body = {
      ...(event ? {} : { code: f.code.trim().toUpperCase() }),
      name: f.name,
      description: f.description || null,
      organizer_position_id: f.organizer_position_id === "" ? null : f.organizer_position_id,
      visited_kind: f.visited_kind,
      joint_visit: f.joint_visit,
      is_company_event: f.is_company_event,
      typical_days: f.typical_days === "" ? null : f.typical_days,
      typical_mode: f.typical_mode || null,
      scheduling_notes: f.scheduling_notes || null,
      active: f.active,
      participation: Object.values(parts),
      merges: [...merges].map((id) => ({
        merges_into_id: id,
        condition_text: keptMerges.get(id)?.condition_text ?? null,
        severity: keptMerges.get(id)?.severity ?? "info",
      })),
    };
    const { error: err, data: saved } = event
      ? await call(`/api/admin/event-types/${event.id}`, "PUT", body)
      : await call("/api/admin/event-types", "POST", body);
    if (err) return setError(err);
    onDone(event?.id ?? saved.id);
  };

  const togglePart = (id: number, on: boolean) =>
    setParts((p) => { const n = { ...p }; if (on) n[id] = { position_id: id, participation: "participant", yearly_limit: null, travels: true }; else delete n[id]; return n; });

  return (
    <form className="card" onSubmit={submit}>
      <h2>{event ? `Edit ${event.name}` : "New event type"}</h2>
      {!event && <label>Code (short, capital letters, for example AREA-WORKSHOP)
        <input required value={f.code} pattern="[A-Za-z0-9][A-Za-z0-9\-]{1,29}" onChange={(e) => setF({ ...f, code: e.target.value })} /></label>}
      <label>Name<input required maxLength={120} value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></label>
      <label>Description<textarea rows={2} maxLength={1000} value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} /></label>
      <div className="row">
        <label>Organizer
          <select value={f.organizer_position_id} onChange={(e) => setF({ ...f, organizer_position_id: e.target.value ? Number(e.target.value) : "" })}>
            <option value="">None</option>
            {data.positions.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select></label>
        <label>Visits
          <select value={f.visited_kind} onChange={(e) => setF({ ...f, visited_kind: e.target.value })}>
            {Object.entries(VISITED).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
          </select></label>
        <label>Others join
          <select value={f.joint_visit} onChange={(e) => setF({ ...f, joint_visit: e.target.value })}>
            {Object.entries(JOINT).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
          </select></label>
      </div>
      <div className="row">
        <label>Typical length (days)
          <input type="number" min={1} max={30} value={f.typical_days} onChange={(e) => setF({ ...f, typical_days: e.target.value ? Number(e.target.value) : "" })} /></label>
        <label>Transport
          <select value={f.typical_mode} onChange={(e) => setF({ ...f, typical_mode: e.target.value })}>
            <option value="">Not set</option>
            {Object.entries(MODES).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
          </select></label>
      </div>
      <label>Planning notes<textarea rows={2} maxLength={1000} value={f.scheduling_notes} onChange={(e) => setF({ ...f, scheduling_notes: e.target.value })} /></label>
      <label className="check"><input type="checkbox" checked={f.is_company_event} onChange={(e) => setF({ ...f, is_company_event: e.target.checked })} /> Company event (such as the conference)</label>
      <label className="check"><input type="checkbox" checked={f.active} onChange={(e) => setF({ ...f, active: e.target.checked })} /> Active</label>

      <fieldset>
        <legend>Who takes part (a position that does not travel is visited, for example the supervisors at an area visit)</legend>
        <table className="matrix">
          <thead><tr><th>Position</th><th>Takes part</th><th>Organizer</th><th>Travels</th><th>Yearly limit</th></tr></thead>
          <tbody>
            {data.positions.map((p) => {
              const part = parts[p.id];
              return (
                <tr key={p.id}>
                  <td>{p.name}</td>
                  <td><input type="checkbox" aria-label={`${p.name} takes part`} checked={!!part} onChange={(e) => togglePart(p.id, e.target.checked)} /></td>
                  <td><input type="checkbox" aria-label={`${p.name} organizes`} disabled={!part} checked={part?.participation === "organizer"}
                    onChange={(e) => setParts({ ...parts, [p.id]: { ...part, participation: e.target.checked ? "organizer" : "participant" } })} /></td>
                  <td><input type="checkbox" aria-label={`${p.name} travels`} disabled={!part} checked={part?.travels ?? true}
                    onChange={(e) => setParts({ ...parts, [p.id]: { ...part, travels: e.target.checked } })} /></td>
                  <td><input type="number" min={0} aria-label={`${p.name} yearly limit`} disabled={!part} value={part?.yearly_limit ?? ""}
                    onChange={(e) => setParts({ ...parts, [p.id]: { ...part, yearly_limit: e.target.value === "" ? null : Number(e.target.value) } })} /></td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </fieldset>

      <fieldset>
        <legend>Combined with (when both happen in the same place)</legend>
        <div className="months">
          {data.event_types.filter((x) => x.id !== event?.id).map((x) => (
            <label key={x.id} className="check">
              <input type="checkbox" checked={merges.has(x.id)}
                onChange={(e) => setMerges((s) => { const n = new Set(s); if (e.target.checked) n.add(x.id); else n.delete(x.id); return n; })} />
              {x.name}
            </label>
          ))}
        </div>
      </fieldset>
      {error && <p className="problem">{error}</p>}
      <p className="row"><button type="submit">Save</button><button type="button" className="link" onClick={onCancel}>Cancel</button></p>
    </form>
  );
}

function Blackouts({ data, isAdmin, onChanged }: { data: CatalogData; isAdmin: boolean; onChanged: () => void }) {
  const [editing, setEditing] = useState<Blackout | "new" | null>(null);
  const names = new Map(data.event_types.map((e) => [e.id, e.name]));
  const remove = async (b: Blackout) => {
    if (!window.confirm(`Remove "${b.name}"?`)) return;
    const { error: err } = await call(`/api/admin/blackouts/${b.id}`, "DELETE");
    if (err) window.alert(err);
    onChanged();
  };
  return (
    <section className="card">
      <h2>Blackout periods</h2>
      <p className="muted">Dates when the listed events should not take place. Plan year 2027 dates are tentative until confirmed.</p>
      {data.blackouts.length === 0 && <p className="muted">None yet.</p>}
      <ul className="rules">
        {data.blackouts.map((b) => (
          <li key={b.id}>
            <div>
              <span className={`badge sev-${b.severity}`}>{SEVERITY[b.severity]}</span> <strong>{b.name}</strong> · {b.start_date} to {b.end_date}
              <div className="muted">
                {b.event_type_ids.length ? b.event_type_ids.map((i) => names.get(i)).join(", ") : "All event types"}
                {b.caused_by_event_type_id && ` · Holds: ${names.get(b.caused_by_event_type_id)}`}
                {b.reason && ` · ${b.reason}`}
              </div>
            </div>
            {isAdmin && (
              <span className="actions">
                <button className="link" onClick={() => setEditing(b)}>Edit</button>
                <button className="link" onClick={() => remove(b)}>Remove</button>
              </span>
            )}
          </li>
        ))}
      </ul>
      {isAdmin && !editing && <button onClick={() => setEditing("new")}>Add blackout period</button>}
      {editing && <BlackoutForm blackout={editing === "new" ? null : editing} data={data}
        onCancel={() => setEditing(null)} onSaved={() => { setEditing(null); onChanged(); }} />}
    </section>
  );
}

function BlackoutForm({ blackout, data, onCancel, onSaved }: {
  blackout: Blackout | null; data: CatalogData; onCancel: () => void; onSaved: () => void;
}) {
  const [f, setF] = useState({
    plan_year: blackout?.plan_year ?? 2027,
    name: blackout?.name ?? "",
    start_date: blackout?.start_date ?? "2027-01-01",
    end_date: blackout?.end_date ?? "2027-01-31",
    reason: blackout?.reason ?? "",
    severity: blackout?.severity ?? ("warn" as Severity),
    caused_by_event_type_id: blackout?.caused_by_event_type_id ?? ("" as number | ""),
  });
  const [ids, setIds] = useState<Set<number>>(new Set(blackout?.event_type_ids ?? []));
  const [error, setError] = useState<string | null>(null);
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    const body = {
      ...f,
      reason: f.reason || null,
      event_type_ids: [...ids],
      caused_by_event_type_id: f.caused_by_event_type_id === "" ? null : f.caused_by_event_type_id,
    };
    const { error: err } = blackout
      ? await call(`/api/admin/blackouts/${blackout.id}`, "PUT", body)
      : await call("/api/admin/blackouts", "POST", body);
    if (err) setError(err); else onSaved();
  };
  return (
    <form className="subform" onSubmit={submit}>
      <h4>{blackout ? "Edit blackout period" : "New blackout period"}</h4>
      <label>Name<input required value={f.name} maxLength={120} onChange={(e) => setF({ ...f, name: e.target.value })} /></label>
      <div className="row">
        <label>Plan year<input type="number" min={2000} max={2100} value={f.plan_year} onChange={(e) => setF({ ...f, plan_year: Number(e.target.value) })} /></label>
        <label>From<input type="date" required value={f.start_date} onChange={(e) => setF({ ...f, start_date: e.target.value })} /></label>
        <label>To<input type="date" required value={f.end_date} onChange={(e) => setF({ ...f, end_date: e.target.value })} /></label>
      </div>
      <label>If a trip falls in this period
        <select value={f.severity} onChange={(e) => setF({ ...f, severity: e.target.value as Severity })}>
          <option value="info">Info: show a note</option>
          <option value="warn">Warn: ask for confirmation and a reason</option>
          <option value="block">Block: do not allow saving</option>
        </select></label>
      <label>Reason (optional)<input value={f.reason} maxLength={500} onChange={(e) => setF({ ...f, reason: e.target.value })} /></label>
      <label>Event held in this period (optional)
        <select value={f.caused_by_event_type_id}
          onChange={(e) => setF({ ...f, caused_by_event_type_id: e.target.value ? Number(e.target.value) : "" })}>
          <option value="">None</option>
          {data.event_types.map((x) => <option key={x.id} value={x.id}>{x.name}</option>)}
        </select>
      </label>
      <fieldset>
        <legend>Events affected (none selected means all events)</legend>
        <div className="months">
          {data.event_types.map((x) => (
            <label key={x.id} className="check">
              <input type="checkbox" checked={ids.has(x.id)}
                onChange={(e) => setIds((s) => { const n = new Set(s); if (e.target.checked) n.add(x.id); else n.delete(x.id); return n; })} />
              {x.name}
            </label>
          ))}
        </div>
      </fieldset>
      {error && <p className="problem">{error}</p>}
      <p className="row"><button type="submit">Save</button><button type="button" className="link" onClick={onCancel}>Cancel</button></p>
    </form>
  );
}
