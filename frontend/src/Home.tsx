import { useEffect, useState } from "react";
import { api } from "./api";
import { Icon } from "./icons";
import { Ring, Sparkline } from "./charts";
import { money } from "./money";
import { daysFromToday, familyOf, ROLE_LABEL } from "./theme";

export type Tab = "home" | "myplan" | "org" | "catalog" | "plan" | "costs" | "users" | "guide";
type Me = { name: string | null; roles: string[]; person_id: number | null };
type MyTrips = { linked: boolean; published: boolean; year: number | null; trips: { id: number; title: string; event_code?: string; place: string | null; status: string; start_date: string; end_date: string }[] };
type Summary = { status: string; totals: { trips: number; merged: number; manual: number }; regions: { rows: { months: number[] }[] }[]; nationwide: { months: number[] } };
type Warnings = { total: number };
type Forecast = { totals: { cost: number; person_trips: number }; by_month: { cost: number }[]; budget: { budget_total: number } | null };

const greeting = () => {
  const h = new Date().getHours();
  return h < 12 ? "Good morning" : h < 18 ? "Good afternoon" : "Good evening";
};

export default function Home({ year, me, go, canSeePlan, canSeeCosts, canSeeOrg, isAdmin }: {
  year: number; me: Me; go: (t: Tab) => void; canSeePlan: boolean; canSeeCosts: boolean; canSeeOrg: boolean; isAdmin: boolean;
}) {
  const [mine, setMine] = useState<MyTrips | null>(null);
  const [plan, setPlan] = useState<Summary | null>(null);
  const [warn, setWarn] = useState<Warnings | null>(null);
  const [cost, setCost] = useState<Forecast | null>(null);

  useEffect(() => {
    if (me.person_id !== null) void api<MyTrips>(`/api/my/trips?year=${year}`).then((r) => r.ok && setMine(r.data));
    if (canSeePlan) void api<Summary>(`/api/plan/${year}/summary`).then((r) => r.ok && setPlan(r.data));
    if (canSeeOrg) void api<Warnings>(`/api/plan/${year}/warnings`).then((r) => r.ok && setWarn(r.data));
    if (canSeeCosts) void api<Forecast>(`/api/cost/${year}/forecast`).then((r) => r.ok && setCost(r.data));
  }, [year, me.person_id, canSeePlan, canSeeOrg, canSeeCosts]);

  const today = new Date().toISOString().slice(0, 10);
  const upcoming = (mine?.trips ?? []).filter((t) => t.status !== "cancelled" && t.end_date >= today).sort((a, b) => a.start_date.localeCompare(b.start_date));
  const next = upcoming[0];
  const days = next ? daysFromToday(next.start_date) : null;

  const perMonth = Array.from({ length: 12 }, (_, i) =>
    plan ? [...plan.regions.flatMap((r) => r.rows), { months: plan.nationwide.months }].reduce((s, r) => s + (r.months[i] ?? 0), 0) : 0);
  const role = me.roles.map((r) => ROLE_LABEL[r] ?? r)[0];

  const steps = [
    { done: !!plan && plan.regions.length > 0, title: "Organization loaded", hint: "Regions, areas and the people in them", go: "org" as Tab },
    { done: true, title: "Events and rules set", hint: "The catalog drives the plan", go: "catalog" as Tab },
    { done: !!plan && plan.totals.trips > 0, title: "Plan generated", hint: "Create the first proposal from the rules", go: "plan" as Tab },
    { done: !!plan && ["published", "closed"].includes(plan.status), title: "Plan published", hint: "Supervisors then see their trips", go: "plan" as Tab },
    { done: !!cost && cost.totals.cost > 0, title: "Costs estimated", hint: "Compare the plan with the budget", go: "costs" as Tab },
  ];
  const doneCount = steps.filter((s) => s.done).length;

  return (
    <div className="page">
      <section className="hero">
        <div className="hero-grid">
          <div>
            <h1>{greeting()}{me.name ? `, ${me.name.split(" ")[0]}` : ""}</h1>
            <p>{role ? `${role} · ` : ""}Plan field travel early, together, and at lower cost.</p>
            <div className="hero-actions">
              {mine?.linked && <button onClick={() => go("myplan")}><Icon name="calendar" size={16} className="ico" />Open my plan</button>}
              {canSeePlan && <button className="secondary" onClick={() => go("plan")}><Icon name="send" size={16} className="ico" />Open the {year} plan</button>}
            </div>
          </div>
          {next && days !== null && (
            <div className="big" aria-label="Days to your next trip">
              <span className="figure">{days <= 0 ? "Now" : days}</span>
              <span className="cap">{days <= 0 ? "your trip is under way" : days === 1 ? "day to your next trip" : "days to your next trip"}</span>
              <span className="pill" style={{ marginTop: 10 }}><Icon name="map" size={14} />{next.title}</span>
            </div>
          )}
        </div>
      </section>

      {(plan || cost) && (
        <div className="stats">
          {plan && (
            <div className="stat">
              <span className="label"><Icon name="send" size={16} />Trips in the {year} plan</span>
              <span className="value">{plan.totals.trips.toLocaleString("en-US")}</span>
              <span className="foot"><span>{plan.totals.merged} combined · {plan.totals.manual} by hand</span><Sparkline values={perMonth} /></span>
            </div>
          )}
          {cost && cost.totals.cost > 0 && (
            <div className="stat">
              <span className="label"><Icon name="chart" size={16} />Estimated travel cost</span>
              <span className="value">{money(cost.totals.cost)}</span>
              <span className="foot"><span>{cost.budget ? `Budget ${money(cost.budget.budget_total)}` : `${cost.totals.person_trips.toLocaleString("en-US")} person-trips`}</span>
                <Sparkline values={cost.by_month.map((m) => m.cost)} /></span>
            </div>
          )}
          {warn && (
            <div className={`stat ${warn.total === 0 ? "good" : "warn"}`}>
              <span className="label"><Icon name={warn.total === 0 ? "ok" : "alert"} size={16} />Rule checks</span>
              <span className="value">{warn.total === 0 ? "All clear" : warn.total}</span>
              <span className="foot"><span>{warn.total === 0 ? "No rule is broken" : warn.total === 1 ? "finding to review" : "findings to review"}</span>
                {warn.total > 0 && <button className="link" onClick={() => go("plan")}>Review</button>}</span>
            </div>
          )}
        </div>
      )}

      <div className="home-grid">
        <section className="card">
          <h2>{upcoming.length ? "Your next trips" : "Your trips"}</h2>
          {mine === null && me.person_id !== null && <div className="skeleton" style={{ height: 90 }} />}
          {mine && !mine.published && <p className="note">The {mine.year ?? year} plan has not been published yet. Your trips will appear here as soon as it is.</p>}
          {mine && mine.published && upcoming.length === 0 && <p className="muted">You have no upcoming trips.</p>}
          {me.person_id === null && <p className="muted">Your sign-in is not linked to a person in the organization, so there are no trips of your own to show.</p>}
          <ul className="mytrips" style={{ marginTop: 10 }}>
            {upcoming.slice(0, 3).map((t) => {
              const d = new Date(t.start_date + "T00:00:00");
              const left = daysFromToday(t.start_date);
              return (
                <li key={t.id} className="mytrip" style={{ ["--fam" as string]: familyOf(t.event_code).color }}>
                  <div className="when" aria-hidden="true"><strong>{d.getDate()}</strong><span>{d.toLocaleDateString("en-US", { month: "short" })}</span></div>
                  <div className="what">
                    <div className="titleline"><strong>{t.title}</strong></div>
                    <div className="meta">
                      <span className="pill brand"><Icon name="clock" size={13} />{left <= 0 ? "under way" : `in ${left} ${left === 1 ? "day" : "days"}`}</span>
                      {t.place && <span><Icon name="map" size={13} /> {t.place}</span>}
                    </div>
                  </div>
                </li>
              );
            })}
          </ul>
          {upcoming.length > 3 && <p><button className="link" onClick={() => go("myplan")}>See all {upcoming.length} upcoming trips</button></p>}
        </section>

        {isAdmin ? (
          <section className="card">
            <div className="head">
              <div><h2>Setup progress</h2><p className="muted" style={{ margin: 0 }}>{doneCount === steps.length ? "Everything is in place." : "What is left before everybody can use the plan."}</p></div>
              <Ring done={doneCount} total={steps.length} />
            </div>
            <ul className="steps">
              {steps.map((s) => (
                <li key={s.title} className={`step ${s.done ? "done" : ""}`}>
                  <span className="tick">{s.done ? <Icon name="check" size={15} /> : null}</span>
                  <span><b>{s.title}</b><small>{s.hint}</small></span>
                  {!s.done && <button className="link" onClick={() => go(s.go)}>Go</button>}
                </li>
              ))}
            </ul>
          </section>
        ) : (
          <section className="card">
            <h2>How it works</h2>
            <p>Your area manager plans the year with the rules of the event catalog. When the plan is published, your trips appear here, and you can add them to your calendar.</p>
            <p className="muted">To change a trip, ask your manager. Every change needs a reason that you can read in My plan.</p>
          </section>
        )}
      </div>

      <h3 style={{ margin: "22px 0 10px" }}>Quick links</h3>
      <div className="quick">
        {mine?.linked && <button onClick={() => go("myplan")}><Icon name="calendar" /><b>My plan</b><span>Your trips and calendar file</span></button>}
        {canSeePlan && <button onClick={() => go("plan")}><Icon name="send" /><b>Plan {year}</b><span>Timeline, heatmap and changes</span></button>}
        {canSeeCosts && <button onClick={() => go("costs")}><Icon name="chart" /><b>Costs</b><span>Estimate against budget</span></button>}
        <button onClick={() => go("catalog")}><Icon name="sliders" /><b>Events and rules</b><span>What is planned and why</span></button>
        <button onClick={() => go("guide")}><Icon name="help" /><b>User guide</b><span>How every page works, by role</span></button>
      </div>
    </div>
  );
}
