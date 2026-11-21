import { initials } from "./theme";
import { FormEvent, useCallback, useEffect, useState } from "react";
import { api } from "./api";

type RoleRow = { id: number; role: string; scope_id: number | null; scope: string | null };
type User = {
  id: number; full_name: string; employee_no: string | null; active: boolean; has_login: boolean;
  position_id: number | null; position: string | null; manager_id: number | null; manager: string | null;
  region_id: number | null; region: string | null; cluster_id: number | null; cluster: string | null;
  local_office_id: number | null; office: string | null; roles: RoleRow[];
};
type Unit = { id: number; name: string; parent_id: number | null };
type Meta = {
  positions: { id: number; code: string; name: string }[];
  regions: Unit[]; clusters: Unit[]; local_offices: Unit[];
  roles: { role: string; scope_kind: string | null }[];
  administrators: number;
  bootstrap_admin: boolean;
};
type Issue = { line: number; code: string; message: string };
type Bulk = { applied: boolean; lines: number; linked: number; unchanged: number; problems: number; issues: Issue[] };
type Suggest = { applied: boolean; to_add: number; already_there: number; roles: string[] };

const ROLE_LABEL: Record<string, string> = {
  administrator: "Administrator", national_planner: "National planner", regional_planner: "Regional planner",
  area_planner: "Area planner", function_planner: "Function planner", coordinator: "Coordinator", viewer: "Viewer",
};
const ROLE_HELP: Record<string, string> = {
  administrator: "Manages users, the organization, the catalog and the plan year.",
  national_planner: "Sees and changes the whole plan and generates it.",
  regional_planner: "Sees and changes the plan of one region.",
  area_planner: "Sees and changes the plan of one cluster and its local offices.",
  function_planner: "Plans for a function such as Training or Legal (later phase).",
  coordinator: "Helps with requests and itineraries (later phase).",
  viewer: "Can sign in; sees only their own trips (later phase).",
};
const PAGE = 25;

export default function Users({ myId }: { myId: number | null }) {
  const [meta, setMeta] = useState<Meta | null>(null);
  const [list, setList] = useState<{ total: number; users: User[] } | null>(null);
  const [q, setQ] = useState("");
  const [role, setRole] = useState("");
  const [login, setLogin] = useState("");
  const [inactive, setInactive] = useState(false);
  const [page, setPage] = useState(0);
  const [open, setOpen] = useState<number | "new" | null>(null);
  const [error, setError] = useState<string | null>(null);

  const loadMeta = useCallback(async () => {
    const r = await api<Meta>("/api/admin/users/meta");
    if (r.ok) setMeta(r.data); else setError(r.error);
  }, []);
  const loadList = useCallback(async () => {
    const p = new URLSearchParams({ limit: String(PAGE), offset: String(page * PAGE), active: inactive ? "false" : "true" });
    if (q.trim()) p.set("q", q.trim());
    if (role) p.set("role", role);
    if (login) p.set("login", login);
    const r = await api<{ total: number; users: User[] }>(`/api/admin/users?${p}`);
    if (r.ok) setList(r.data); else setError(r.error);
  }, [q, role, login, inactive, page]);

  useEffect(() => { void loadMeta(); }, [loadMeta]);
  useEffect(() => {
    const t = setTimeout(() => void loadList(), 250);
    return () => clearTimeout(t);
  }, [loadList]);
  useEffect(() => setPage(0), [q, role, login, inactive]);

  // the person's page opens below a long list: bring it into view
  useEffect(() => {
    if (open !== null) setTimeout(() => document.getElementById("user-panel")?.scrollIntoView({ behavior: "smooth", block: "start" }), 80);
  }, [open]);

  const changed = async () => { await Promise.all([loadMeta(), loadList()]); };

  return (
    <>
      <details className="card help">
        <summary>Help: users, roles and sign-ins</summary>
        <p>
          A <strong>person</strong> comes from the organization import. To let someone use the app, link their <strong>sign-in</strong> and give
          them a <strong>role</strong>. Until a sign-in is linked, nobody can sign in as that person.
        </p>
        <p>
          <strong>E-mail addresses are never stored.</strong> When you type an address, the server turns it into a one-way code, keeps only the code and
          forgets the address. It cannot be shown again, so if you make a typo, link the sign-in again.
        </p>
        <ul>{Object.entries(ROLE_LABEL).map(([k, l]) => <li key={k}><strong>{l}.</strong> {ROLE_HELP[k]}</li>)}</ul>
        <p>
          Regional and area planners need a <em>scope</em>: the region or cluster they cover. The application always keeps at least one administrator who can sign in.
        </p>
      </details>

      {meta && meta.administrators < 2 && (
        <p className="note" role="status">
          {meta.administrators === 0
            ? meta.bootstrap_admin
              ? "Only the bootstrap administrator from the configuration can manage the application."
              : "No administrator can sign in at the moment."
            : "Only one administrator can sign in."}{" "}
          We recommend at least two people with the role Administrator and a linked sign-in, so that the application can still be managed when one of them is away.
        </p>
      )}
      {error && <p className="problem" role="alert">{error}</p>}

      {meta && <Suggested onDone={changed} />}
      {meta && <BulkLogin onDone={changed} />}

      <section className="card">
        <div className="head">
          <h2>People</h2>
          {open !== "new" && <button onClick={() => setOpen("new")}>Add a person</button>}
        </div>
        <div className="row">
          <label>Search<input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Name or employee number" /></label>
          <label>Role
            <select value={role} onChange={(e) => setRole(e.target.value)}>
              <option value="">Any</option>
              <option value="none">No role</option>
              {Object.entries(ROLE_LABEL).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
            </select></label>
          <label>Sign-in
            <select value={login} onChange={(e) => setLogin(e.target.value)}>
              <option value="">Any</option><option value="linked">Linked</option><option value="unlinked">Not linked</option>
            </select></label>
          <label className="check"><input type="checkbox" checked={inactive} onChange={(e) => setInactive(e.target.checked)} /> Show inactive people</label>
        </div>
        {!list && <p>Loading…</p>}
        {list && list.users.length === 0 && <p className="muted">No people match.</p>}
        {list && list.users.length > 0 && (
          <>
            <table className="trips people">
              <thead><tr><th>Name</th><th>Position</th><th>Place</th><th>Roles</th><th>Sign-in</th></tr></thead>
              <tbody>
                {list.users.map((u) => (
                  <tr key={u.id} className={open === u.id ? "on" : ""}>
                    <td>
                      <span className="avatar s" aria-hidden="true" style={{ display: "inline-grid", marginRight: 8, verticalAlign: "middle" }}>{initials(u.full_name)}</span><button className="link" onClick={() => setOpen(u.id)}>{u.full_name}</button>
                      {u.employee_no && <span className="muted"> · {u.employee_no}</span>}
                      {!u.active && <span className="badge"> inactive</span>}
                    </td>
                    <td>{u.position ?? <span className="muted">None</span>}</td>
                    <td>{u.cluster ?? u.region ?? <span className="muted">None</span>}</td>
                    <td>{u.roles.length === 0 ? <span className="muted">None</span> : u.roles.map((r) => (
                      <span key={r.id} className="chip">{ROLE_LABEL[r.role]}{r.scope ? `: ${r.scope}` : ""}</span>))}</td>
                    <td>{u.has_login ? "Linked" : <span className="muted">Not linked</span>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="row">
              <button className="secondary" disabled={page === 0} onClick={() => setPage(page - 1)}>Previous</button>
              <span className="muted">{page * PAGE + 1} to {Math.min((page + 1) * PAGE, list.total)} of {list.total}</span>
              <button className="secondary" disabled={(page + 1) * PAGE >= list.total} onClick={() => setPage(page + 1)}>Next</button>
            </p>
          </>
        )}
      </section>

      <div id="user-panel" style={{ scrollMarginTop: 16 }}>
        {meta && open === "new" && <NewPerson meta={meta} onCancel={() => setOpen(null)} onDone={async (id) => { await changed(); setOpen(id); }} />}
        {meta && typeof open === "number" && (
          <UserPanel key={open} id={open} meta={meta} myId={myId} onChanged={changed} onClose={() => setOpen(null)} />
        )}
      </div>
    </>
  );
}

function Suggested({ onDone }: { onDone: () => void }) {
  const [r, setR] = useState<Suggest | null>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const run = async (commit: boolean) => {
    setBusy(true);
    const res = await api<Suggest>(`/api/admin/users/suggest-roles?commit=${commit}`, "POST");
    setBusy(false);
    if (!res.ok) return setMsg(res.error);
    setR(res.data);
    setMsg(commit ? `${res.data.to_add} ${res.data.to_add === 1 ? "role was" : "roles were"} added.` : null);
    if (commit) onDone();
  };
  return (
    <section className="card">
      <h3>Suggested roles</h3>
      <p className="muted">The Head of Field becomes a national planner, each Regional Manager the planner of their region, and each Area Manager the planner of their cluster. Roles that exist stay.</p>
      <p><button className="secondary" disabled={busy} onClick={() => run(false)}>Show suggestions</button></p>
      {msg && <p className="good" role="status">{msg}</p>}
      {r && !r.applied && (
        r.to_add === 0 ? <p>Nothing to add: all suggested roles exist already.</p> : (
          <>
            <ul>{r.roles.map((x) => <li key={x}>{x}</li>)}</ul>
            <p><button disabled={busy} onClick={() => run(true)}>Add {r.to_add} {r.to_add === 1 ? "role" : "roles"}</button></p>
          </>
        )
      )}
    </section>
  );
}

function BulkLogin({ onDone }: { onDone: () => void }) {
  const [text, setText] = useState("");
  const [r, setR] = useState<Bulk | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState<string | null>(null);
  const run = async (commit: boolean) => {
    setBusy(true); setErr(null); setDone(null);
    const res = await api<Bulk>(`/api/admin/users/bulk-login?commit=${commit}`, "POST", { text });
    setBusy(false);
    if (!res.ok) { setErr(res.error); if (!commit) setR(null); return; }
    setR(res.data);
    if (commit) {
      setDone(`${res.data.linked} ${res.data.linked === 1 ? "sign-in was" : "sign-ins were"} linked.`);
      setText(""); setR(null); onDone();
    }
  };
  return (
    <details className="card help">
      <summary>Link many sign-ins at once</summary>
      <p className="muted">
        Paste one person per line: the work e-mail address and the employee number (or the full name), separated by a comma, semicolon or tab. A first line with column titles is fine.
        The addresses are turned into one-way codes and are not kept.
      </p>
      <textarea rows={6} value={text} onChange={(e) => { setText(e.target.value); setR(null); }} placeholder={"first.last@company.example, 123456\nsecond.person@company.example, Second Person"} />
      <p className="row">
        <button className="secondary" disabled={busy || !text.trim()} onClick={() => run(false)}>Check</button>
        {r && !r.applied && r.problems === 0 && r.linked > 0 && <button disabled={busy} onClick={() => run(true)}>Link {r.linked} {r.linked === 1 ? "sign-in" : "sign-ins"}</button>}
      </p>
      {err && <p className="problem" role="alert">{err}</p>}
      {done && <p className="good" role="status">{done}</p>}
      {r && (
        <>
          <p>{r.lines} {r.lines === 1 ? "line" : "lines"}: <strong>{r.linked}</strong> to link, {r.unchanged} already linked, <strong>{r.problems}</strong> with problems.</p>
          {r.issues.length > 0 && <ul className="issues">{r.issues.map((i, n) => <li key={n} className="warning">{i.message}</li>)}</ul>}
          {r.problems > 0 && <p className="muted">Fix the lines with problems; nothing is saved until all lines are fine.</p>}
        </>
      )}
    </details>
  );
}

function NewPerson({ meta, onCancel, onDone }: { meta: Meta; onCancel: () => void; onDone: (id: number) => void }) {
  const [f, setF] = useState({ full_name: "", employee_no: "" });
  const [a, setA] = useState<Assign>(blankAssign(meta));
  const [error, setError] = useState<string | null>(null);
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    const r = await api<User>("/api/admin/users", "POST", { full_name: f.full_name, employee_no: f.employee_no || null, assignment: assignBody(a) });
    if (r.ok) onDone(r.data.id); else setError(r.error);
  };
  return (
    <form className="card" onSubmit={submit}>
      <h3>Add a person</h3>
      <p className="muted">For people who are not in the organization import. Most people come from the import.</p>
      <div className="row">
        <label>Full name<input required maxLength={120} value={f.full_name} onChange={(e) => setF({ ...f, full_name: e.target.value })} /></label>
        <label>Employee number (optional)<input maxLength={30} value={f.employee_no} onChange={(e) => setF({ ...f, employee_no: e.target.value })} /></label>
      </div>
      <AssignFields meta={meta} a={a} setA={setA} />
      {error && <p className="problem" role="alert">{error}</p>}
      <p className="row"><button type="submit">Add the person</button><button type="button" className="link" onClick={onCancel}>Cancel</button></p>
    </form>
  );
}

type Assign = { position_id: number | ""; manager_id: number | ""; region_id: number | ""; cluster_id: number | ""; local_office_id: number | ""; effective_date: string };
const blankAssign = (meta: Meta): Assign => ({ position_id: meta.positions.find((p) => p.code === "FSV")?.id ?? "", manager_id: "", region_id: "", cluster_id: "", local_office_id: "", effective_date: new Date().toISOString().slice(0, 10) });
const assignBody = (a: Assign) => ({
  position_id: a.position_id, manager_id: a.manager_id === "" ? null : a.manager_id, region_id: a.region_id === "" ? null : a.region_id,
  cluster_id: a.cluster_id === "" ? null : a.cluster_id, local_office_id: a.local_office_id === "" ? null : a.local_office_id,
  effective_date: a.effective_date || null,
});

function AssignFields({ meta, a, setA, managerName }: { meta: Meta; a: Assign; setA: (a: Assign) => void; managerName?: string | null }) {
  const [q, setQ] = useState("");
  const [found, setFound] = useState<User[]>([]);
  const [picked, setPicked] = useState<string | null>(managerName ?? null);
  useEffect(() => {
    if (q.trim().length < 2) { setFound([]); return; }
    const t = setTimeout(async () => {
      const r = await api<{ users: User[] }>(`/api/admin/users?q=${encodeURIComponent(q.trim())}&limit=8`);
      if (r.ok) setFound(r.data.users);
    }, 300);
    return () => clearTimeout(t);
  }, [q]);
  const sel = (key: keyof Assign, units: Unit[]) => (
    <select value={a[key]} onChange={(e) => setA({ ...a, [key]: e.target.value ? Number(e.target.value) : "" })}>
      <option value="">None</option>
      {units.map((u) => <option key={u.id} value={u.id}>{u.name}</option>)}
    </select>
  );
  return (
    <>
      <div className="row">
        <label>Position
          <select required value={a.position_id} onChange={(e) => setA({ ...a, position_id: e.target.value ? Number(e.target.value) : "" })}>
            <option value="">Choose…</option>
            {meta.positions.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select></label>
        <label>Region{sel("region_id", meta.regions)}</label>
        <label>Cluster{sel("cluster_id", meta.clusters)}</label>
        <label>Local office{sel("local_office_id", meta.local_offices)}</label>
      </div>
      <div className="row">
        <div className="picker">
          <label>Manager{picked ? ` (now: ${picked})` : ""}
            <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Type at least two letters to search" /></label>
          {found.length > 0 && (
            <ul className="found">
              {found.map((u) => (
                <li key={u.id}><button type="button" className="link" onClick={() => { setA({ ...a, manager_id: u.id }); setPicked(u.full_name); setQ(""); setFound([]); }}>{u.full_name} · {u.position}</button></li>
              ))}
            </ul>
          )}
          {a.manager_id !== "" && <button type="button" className="link" onClick={() => { setA({ ...a, manager_id: "" }); setPicked(null); }}>No manager</button>}
        </div>
        <label>Valid from<input type="date" value={a.effective_date} onChange={(e) => setA({ ...a, effective_date: e.target.value })} /></label>
      </div>
    </>
  );
}

function UserPanel({ id, meta, myId, onChanged, onClose }: { id: number; meta: Meta; myId: number | null; onChanged: () => void; onClose: () => void }) {
  const [u, setU] = useState<User | null>(null);
  const [msg, setMsg] = useState<{ text: string; ok: boolean } | null>(null);
  const [email, setEmail] = useState("");
  const [roleSel, setRoleSel] = useState("regional_planner");
  const [scopeSel, setScopeSel] = useState<number | "">("");
  const [basic, setBasic] = useState({ full_name: "", employee_no: "" });
  const [a, setA] = useState<Assign>(blankAssign(meta));

  const apply = useCallback((user: User) => {
    setU(user);
    setBasic({ full_name: user.full_name, employee_no: user.employee_no ?? "" });
    setA({ position_id: user.position_id ?? "", manager_id: user.manager_id ?? "", region_id: user.region_id ?? "", cluster_id: user.cluster_id ?? "",
      local_office_id: user.local_office_id ?? "", effective_date: new Date().toISOString().slice(0, 10) });
  }, []);
  useEffect(() => { void api<User>(`/api/admin/users/${id}`).then((r) => r.ok ? apply(r.data) : setMsg({ text: r.error ?? "", ok: false })); }, [id, apply]);

  if (!u) return <section className="card"><p>Loading…</p></section>;

  const act = async (url: string, method: string, body?: unknown, okText?: string) => {
    const r = await api<User>(url, method, body);
    if (!r.ok) return setMsg({ text: r.error ?? "", ok: false });
    apply(r.data); setMsg(okText ? { text: okText, ok: true } : null); onChanged();
    return r.data;
  };
  const scopeKind = meta.roles.find((r) => r.role === roleSel)?.scope_kind ?? null;
  const scopes = scopeKind === "region" ? meta.regions : scopeKind === "cluster" ? meta.clusters : [];

  return (
    <section className="card">
      <div className="head">
        <div>
          <h3>{u.full_name}</h3>
          <p className="muted">{u.position ?? "No position"}{u.employee_no && ` · ${u.employee_no}`}{!u.active && " · Inactive"}</p>
        </div>
        <button className="link" onClick={onClose}>Close</button>
      </div>
      {msg && <p className={msg.ok ? "good" : "problem"} role={msg.ok ? "status" : "alert"}>{msg.text}</p>}

      <h4>Sign-in</h4>
      {u.has_login ? <p>A sign-in is linked. <span className="muted">(The address itself is not stored.)</span></p> : <p className="muted">No sign-in is linked, so this person cannot use the app yet.</p>}
      <form className="row" onSubmit={async (e) => { e.preventDefault(); const r = await act(`/api/admin/users/${id}/login`, "POST", { email }, "The sign-in was linked."); if (r) setEmail(""); }}>
        <label>{u.has_login ? "Replace with a different work e-mail" : "Work e-mail"}
          <input type="email" autoComplete="off" required value={email} onChange={(e) => setEmail(e.target.value)} placeholder="first.last@company.example" /></label>
        <button type="submit" disabled={!u.active}>{u.has_login ? "Replace sign-in" : "Link sign-in"}</button>
        {u.has_login && <button type="button" className="link" onClick={() => window.confirm("Unlink this sign-in? The person can no longer sign in.") && void act(`/api/admin/users/${id}/login`, "DELETE", undefined, "The sign-in was unlinked.")}>Unlink</button>}
      </form>
      <p className="muted">The address is turned into a one-way code and is not kept. Type it exactly as the person signs in.</p>

      <h4>Roles</h4>
      {u.roles.length === 0 && <p className="muted">No role: this person can sign in but sees nothing yet.</p>}
      <ul className="chips">
        {u.roles.map((r) => (
          <li key={r.id} className="chip strong">{ROLE_LABEL[r.role]}{r.scope ? `: ${r.scope}` : ""}
            <button type="button" className="link" onClick={() => void act(`/api/admin/users/${id}/roles/${r.id}`, "DELETE", undefined, "The role was removed.")}>Remove</button></li>
        ))}
      </ul>
      <form className="row" onSubmit={async (e) => { e.preventDefault(); await act(`/api/admin/users/${id}/roles`, "POST", { role: roleSel, scope_org_unit_id: scopeSel === "" ? null : scopeSel }, "The role was added."); }}>
        <label>Add a role
          <select value={roleSel} onChange={(e) => { setRoleSel(e.target.value); setScopeSel(""); }}>
            {Object.entries(ROLE_LABEL).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
          </select></label>
        {scopeKind && (
          <label>{scopeKind === "region" ? "Region" : "Cluster"}
            <select required value={scopeSel} onChange={(e) => setScopeSel(e.target.value ? Number(e.target.value) : "")}>
              <option value="">Choose…</option>
              {scopes.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
            </select></label>
        )}
        <button type="submit" disabled={!u.active}>Add role</button>
      </form>
      <p className="muted">{ROLE_HELP[roleSel]}</p>

      <details>
        <summary>Details and assignment</summary>
        <form className="editbox" onSubmit={async (e) => { e.preventDefault(); await act(`/api/admin/users/${id}`, "PUT", { full_name: basic.full_name, employee_no: basic.employee_no || null }, "Saved."); }}>
          <div className="row">
            <label>Full name<input required maxLength={120} value={basic.full_name} onChange={(e) => setBasic({ ...basic, full_name: e.target.value })} /></label>
            <label>Employee number<input maxLength={30} value={basic.employee_no} onChange={(e) => setBasic({ ...basic, employee_no: e.target.value })} /></label>
            <button type="submit">Save</button>
          </div>
        </form>
        <form className="editbox" onSubmit={async (e) => { e.preventDefault(); await act(`/api/admin/users/${id}`, "PUT", { assignment: assignBody(a) }, "The assignment was saved. The previous one stays in the history."); }}>
          <h4>Position, manager and place</h4>
          <AssignFields meta={meta} a={a} setA={setA} managerName={u.manager} />
          <p><button type="submit">Save assignment</button></p>
        </form>
      </details>

      <h4>Status</h4>
      {u.active ? (
        <p><button className="secondary" disabled={u.id === myId}
          onClick={() => window.confirm(`Deactivate ${u.full_name}? They can no longer sign in; their history stays.`) && void act(`/api/admin/users/${id}`, "PUT", { active: false }, "The person was deactivated.")}>Deactivate</button>
          {u.id === myId && <span className="muted"> You cannot deactivate yourself.</span>}</p>
      ) : (
        <p><button onClick={() => void act(`/api/admin/users/${id}`, "PUT", { active: true }, "The person is active again.")}>Reactivate</button></p>
      )}
    </section>
  );
}
