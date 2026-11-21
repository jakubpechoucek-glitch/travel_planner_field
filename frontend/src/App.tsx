import { FormEvent, useCallback, useEffect, useState } from "react";
import Catalog from "./Catalog";
import Costs from "./Costs";
import MyPlan from "./MyPlan";
import Org from "./Org";
import Users from "./Users";
import Plan from "./Plan";
import Home, { Tab } from "./Home";
import Guide from "./Guide";
import { Icon, Logo } from "./icons";
import { initials, ROLE_LABEL } from "./theme";
import { api } from "./api";

type Me = { signed_in: boolean; linked: boolean; has_access: boolean; name: string | null; roles: string[]; person_id: number | null };
type State =
  | { kind: "loading" }
  | { kind: "signin" }
  | { kind: "error"; message: string }
  | { kind: "ready"; me: Me };

export default function App() {
  const [state, setState] = useState<State>({ kind: "loading" });
  const [tab, setTab] = useState<Tab>("home");
  const [years, setYears] = useState<{ year: number; status: string; trips: number }[]>([]);
  const [year, setYear] = useState(2027);

  const load = useCallback(async () => {
    try {
      const r = await fetch("/api/me");
      if (r.status === 401) {
        const mode = (await (await fetch("/api/auth/mode")).json()) as { mode: string };
        setState(
          mode.mode === "passcode"
            ? { kind: "signin" }
            : { kind: "error", message: "You are not signed in. Please open the app from Databricks." },
        );
        return;
      }
      if (!r.ok) throw new Error("The server could not be reached. Please try again later.");
      setState({ kind: "ready", me: (await r.json()) as Me });
    } catch (e) {
      setState({ kind: "error", message: (e as Error).message });
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (state.kind !== "ready" || !state.me.has_access || state.me.person_id === null) return;
    const planner = state.me.roles.some((r) => ["administrator", "national_planner", "regional_planner", "area_planner"].includes(r));
    if (!planner) setTab("myplan");   // supervisors land on their own plan
  }, [state]);

  const loadYears = useCallback(async () => {
    const r = await api<{ year: number; status: string; trips: number }[]>("/api/plan-years");
    if (r.ok && r.data.length) { setYears(r.data); setYear((y) => (r.data.some((x) => x.year === y) ? y : r.data[0].year)); }
  }, []);
  useEffect(() => {
    if (state.kind === "ready" && state.me.has_access) void loadYears();
  }, [state, loadYears]);

  const signOut = async () => {
    await fetch("/api/auth/logout", { method: "POST" });
    setState({ kind: "signin" });
  };

  const hasAccess = state.kind === "ready" && state.me.has_access;
  const hasPerson = hasAccess && state.kind === "ready" && state.me.person_id !== null;
  const isAdmin = state.kind === "ready" && state.me.roles.includes("administrator");
  const canSeeCosts =
    state.kind === "ready" && state.me.roles.some((r) => ["administrator", "national_planner", "regional_planner"].includes(r));
  const canSeePlan =
    state.kind === "ready" && state.me.roles.some((r) => ["administrator", "national_planner", "regional_planner", "area_planner"].includes(r));
  const canSeeOrg =
    state.kind === "ready" && state.me.roles.some((r) => r === "administrator" || r === "national_planner");

  if (state.kind !== "ready" || !state.me.has_access) {
    return (
      <div className="auth">
        <AuthArt />
        <div className="auth-form" aria-live="polite">
          {state.kind === "loading" && <div className="box"><p>Loading…</p></div>}
          {state.kind === "error" && <div className="box"><h2>Something is wrong</h2><p className="problem">{state.message}</p></div>}
          {state.kind === "signin" && <SignIn onDone={load} />}
          {state.kind === "ready" && (
            <div className="box">
              <h2>You do not have access yet</h2>
              <p>
                Your sign-in worked, but your account is not linked to a travel planning role. Please ask
                the Field Collections travel administrator to link your account.
              </p>
              <button className="secondary" onClick={signOut}>Sign out</button>
            </div>
          )}
        </div>
      </div>
    );
  }

  const me = state.me;
  const items: { id: Tab; label: string; icon: string; show: boolean }[] = [
    { id: "home", label: "Home", icon: "home", show: true },
    { id: "myplan", label: "My plan", icon: "calendar", show: hasPerson },
    { id: "plan", label: "Plan", icon: "send", show: canSeePlan },
    { id: "costs", label: "Costs", icon: "chart", show: canSeeCosts },
    { id: "catalog", label: "Events and rules", icon: "sliders", show: true },
    { id: "org", label: "Organization", icon: "org", show: canSeeOrg },
    { id: "users", label: "Users", icon: "users", show: isAdmin },
    { id: "guide", label: "User guide", icon: "help", show: true },
  ];
  const titles: Record<Tab, string> = {
    home: "Home", myplan: "My plan", plan: "Plan", costs: "Cost estimate", catalog: "Events and rules", org: "Organization", users: "Users", guide: "User guide",
  };

  return (
    <div className="app">
      <aside className="side">
        <div className="brand">
          <Logo size={38} />
          <div><b>Travel Planner</b><small>Field Collections</small></div>
        </div>
        <ul className="nav" aria-label="Main">
          {items.filter((i) => i.show).map((i) => (
            <li key={i.id}>
              <button className={tab === i.id ? "on" : ""} aria-current={tab === i.id ? "page" : undefined} onClick={() => setTab(i.id)}>
                <Icon name={i.icon} size={19} />{i.label}
              </button>
            </li>
          ))}
        </ul>
        <div className="usercard">
          <span className="avatar" aria-hidden="true">{initials(me.name)}</span>
          <span className="who"><b>{me.name ?? "Signed in"}</b><small>{ROLE_LABEL[me.roles[0]] ?? me.roles[0]}</small></span>
          <button className="icon" onClick={signOut} aria-label="Sign out" title="Sign out"><Icon name="logout" size={18} /></button>
        </div>
      </aside>
      <main className="content" key={tab}>
        {(tab === "home" || tab === "plan" || tab === "costs") && years.length > 1 && (
          <div className="page-head no-print" style={{ justifyContent: "flex-end", marginBottom: 8 }}>
            <label className="row" style={{ gap: 8, alignItems: "center", fontWeight: 600 }}>Plan year
              <select value={year} onChange={(e) => setYear(Number(e.target.value))} aria-label="Plan year">
                {years.map((y) => <option key={y.year} value={y.year}>{y.year}{y.status === "published" ? " · published" : y.status === "closed" ? " · closed" : ""}</option>)}
              </select>
            </label>
          </div>
        )}
        {tab !== "home" && (
          <div className="page-head"><div><h1>{titles[tab]}{tab === "plan" || tab === "costs" ? ` ${year}` : ""}</h1></div></div>
        )}
        <div className="page">
          {tab === "home" && <Home year={year} me={me} go={setTab} canSeePlan={canSeePlan} canSeeCosts={canSeeCosts} canSeeOrg={canSeeOrg} isAdmin={isAdmin} />}
          {hasPerson && tab === "myplan" && <MyPlan />}
          {canSeeCosts && tab === "costs" && <Costs year={year} isAdmin={isAdmin} whole={canSeeOrg} />}
          {tab === "catalog" && <Catalog isAdmin={isAdmin} />}
          {canSeeOrg && tab === "org" && <Org isAdmin={isAdmin} />}
          {isAdmin && tab === "users" && <Users myId={me.person_id} />}
          {canSeePlan && tab === "plan" && <Plan year={year} years={years} canGenerate={canSeeOrg} onYears={loadYears} onYear={setYear} />}
          {tab === "guide" && <Guide roles={me.roles} />}
        </div>
      </main>
    </div>
  );
}

function AuthArt() {
  return (
    <div className="auth-art">
      <div style={{ display: "flex", alignItems: "center", gap: 12, position: "relative", zIndex: 1 }}>
        <Logo size={44} /><b style={{ fontSize: 20 }}>Travel Planner</b>
      </div>
      <svg className="route" viewBox="0 0 560 320" aria-hidden="true">
        <path d="M20 280C120 270 140 150 250 170S400 60 540 30" fill="none" stroke="#fff" strokeOpacity=".5" strokeWidth="3" strokeLinecap="round" strokeDasharray="2 12" />
        {[[20, 280], [250, 170], [540, 30]].map(([x, y]) => (<g key={x}><circle cx={x} cy={y} r="16" fill="#fff" fillOpacity=".14" /><circle cx={x} cy={y} r="7" fill="#fff" /></g>))}
      </svg>
      <div style={{ position: "relative", zIndex: 1 }}>
        <h1>Meet in person. Plan it early.</h1>
        <p>One shared plan for field travel, so teams can meet, combine trips and book at a lower cost.</p>
        <ul>
          <li><Icon name="calendar" size={18} />A yearly plan built from clear rules</li>
          <li><Icon name="users" size={18} />Every change has a reason</li>
          <li><Icon name="chart" size={18} />Costs in pesos, against the budget</li>
        </ul>
      </div>
    </div>
  );
}

function SignIn({ onDone }: { onDone: () => void }) {
  const [email, setEmail] = useState("");
  const [passcode, setPasscode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    const r = await fetch("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, passcode }),
    });
    setBusy(false);
    if (r.ok) return onDone();
    const body = (await r.json().catch(() => ({}))) as { detail?: string };
    setError(body.detail ?? "Sign-in failed. Please try again.");
  };

  return (
    <form onSubmit={submit}>
      <div style={{ display: "flex", alignItems: "center", gap: 10 }}><Logo size={34} /><h2 style={{ margin: 0 }}>Sign in</h2></div>
      <p className="muted">
        This is a trial installation. Enter your work e-mail and the access code you were given. Your
        e-mail address is not stored; only a one-way code derived from it is kept for the session.
      </p>
      <label>
        Work e-mail
        <input type="email" required autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} />
      </label>
      <label>
        Access code
        <input type="password" required autoComplete="current-password" value={passcode} onChange={(e) => setPasscode(e.target.value)} />
      </label>
      {error && <p className="problem">{error}</p>}
      <button type="submit" disabled={busy}>{busy ? "Signing in…" : "Sign in"}</button>
    </form>
  );
}
