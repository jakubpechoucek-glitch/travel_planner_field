import { useCallback, useEffect, useState } from "react";
import { api } from "./api";
import { AddTrip, TripPanel } from "./TripPanel";
import Timeline from "./Timeline";
import { Icon } from "./icons";

type Row = { unit_id: number | null; label: string; months: number[] };
type Summary = {
  year: number;
  status: string;
  published_at: string | null;
  regions: { id: number; name: string; rows: Row[] }[];
  nationwide: Row;
  totals: { trips: number; merged: number; manual: number };
};
type TripRow = {
  id: number; title: string; start_date: string; end_date: string; status: string; source: string;
  notes: string | null; event: string; travelers: number; merged_count: number; changed: boolean;
};
type Warning = { level: string; code: string; message: string };
type WarningSet = { total: number; counts: Record<string, number>; warnings: Warning[] };
type Report = {
  applied: boolean; trips_created: number; trips_merged: number; trips_replaced: number; trips_kept: number;
  by_event: { event: string; trips: number; merged: number }[];
  unplaced: string[]; skipped: string[]; warning_counts: Record<string, number>; warnings: Warning[];
  warning_total: number;
};

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const WARNING_TITLES: Record<string, string> = {
  period_cap: "Trip limits per person",
  period_min: "Too few trips",
  yearly_limit: "Yearly limit of an event",
  quota_short: "Too few trips for a place",
  quota_over: "Too many trips for a place",
  blackout: "Trips in blackout periods",
  overlap: "A person in two trips at once",
};
const STATUS_LABEL: Record<string, string> = { draft: "Draft", review: "In review", published: "Published", closed: "Closed" };

const fmt = (a: string, b: string) => {
  const f = (s: string) => new Date(s + "T00:00:00").toLocaleDateString("en-US", { month: "short", day: "numeric" });
  return a === b ? f(a) : `${f(a)} to ${f(b)}`;
};

export default function Plan({ canGenerate }: { canGenerate: boolean }) {
  const year = 2027;
  const [summary, setSummary] = useState<Summary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [sel, setSel] = useState<{ row: Row; month: number | null; nationwide: boolean } | null>(null);
  const [trips, setTrips] = useState<TripRow[] | null>(null);
  const [openId, setOpenId] = useState<number | null>(null);
  const [adding, setAdding] = useState(false);
  const [withCancelled, setWithCancelled] = useState(false);
  const [tick, setTick] = useState(0);
  const [warnings, setWarnings] = useState<WarningSet | null>(null);
  const [view, setView] = useState<"timeline" | "heatmap">("timeline");

  const load = useCallback(async () => {
    const r = await fetch(`/api/plan/${year}/summary`);
    if (!r.ok) return setError("The plan could not be loaded. Please try again later.");
    setSummary((await r.json()) as Summary);
    if (canGenerate) {
      const w = await fetch(`/api/plan/${year}/warnings`);
      if (w.ok) setWarnings((await w.json()) as WarningSet);
    }
  }, [canGenerate]);
  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (!sel) return setTrips(null);
    const q = new URLSearchParams();
    if (sel.nationwide) q.set("nationwide", "true");
    else if (sel.row.unit_id !== null) q.set("unit_id", String(sel.row.unit_id));
    if (sel.month) q.set("month", String(sel.month));
    void fetch(`/api/plan/${year}/trips?${q}`).then(async (r) => setTrips(r.ok ? ((await r.json()) as TripRow[]) : []));
  }, [sel, tick]);

  const [statusMsg, setStatusMsg] = useState<{ text: string; ok: boolean } | null>(null);
  const setStatus = async (to: "published" | "review" | "closed", confirm: string, done: string) => {
    if (!window.confirm(confirm)) return;
    const r = await api(`/api/admin/plan/${year}/status`, "POST", { status: to });
    setStatusMsg(r.ok ? { text: done, ok: true } : { text: r.error ?? "", ok: false });
    await load();
  };

  const changed = async () => {
    setTick((t) => t + 1);
    await load();
  };

  const max = Math.max(1, ...(summary ? [...summary.regions.flatMap((r) => r.rows), summary.nationwide].flatMap((r) => r.months) : [1]));
  const cell = (row: Row, nationwide = false) =>
    row.months.map((n, i) => (
      <td key={i}>
        <button
          className="cellbtn"
          disabled={n === 0}
          aria-label={`${row.label}, ${MONTHS[i]}: ${n} trips`}
          style={n ? ({
            ["--heat-bg" as string]: `color-mix(in srgb, var(--brand) ${Math.round(12 + (n / max) * 88)}%, var(--surface))`,
            ["--heat-ink" as string]: n / max > 0.45 ? "#fff" : "var(--ink)",
          } as React.CSSProperties) : undefined}
          onClick={() => setSel({ row, month: i + 1, nationwide })}
        >
          {n || ""}
        </button>
      </td>
    ));

  return (
    <>
      <details className="card help">
        <summary>Help: the yearly plan</summary>
        <p>
          The plan is built from the organization, the event types and their rules. Each cell shows how many trips start in that
          month for a cluster; click a number to see the trips, and a trip to see who takes part. A trip that is <strong>combined</strong>{" "}
          with a bigger event (for example a region visit held at an area meeting) is not counted twice: the bigger trip lists it.
        </p>
        <p>
          <strong>Generate plan</strong> first shows a preview and saves nothing. When you apply it, trips that nobody has changed are
          rebuilt from the rules, and trips that were edited or added by hand are kept and counted toward the rules. The checks on the
          right apply the same rules to the saved plan, so they also find problems after manual changes.
        </p>
        <p>
          <strong>Changing a trip.</strong> Open a trip and choose <em>Change this trip</em>. Every change needs a reason, which everyone who sees the
          trip can read in its history. Before you save, the app shows which rules the change would break; a warning must be confirmed, and a rule
          marked <em>block</em> does not allow the change. Trips you changed or added are kept when the plan is generated again. You can change the
          trips of your own area only.
        </p>
        <p>
          <strong>Publishing.</strong> A plan under review is visible to planners only. <em>Publish plan</em> makes everyone's own trips visible in <em>My plan</em>;
          from then on the plan is not generated again, and your changes are marked "after publication" in the history of a trip.
        </p>
        <p>
          <strong>Export to Excel</strong> downloads the plan you can see as a workbook: a summary by place and month, every trip, the people on the trips, days away per person,
          every manual change with its reason, and the rule checks. It is a snapshot and contains the trips of your own area only if you are a regional or area planner.
        </p>
        <p>The plan uses working days only (Monday to Friday) and does not know public holidays yet.</p>
      </details>

      {canGenerate && <Generate year={year} onApplied={load} />}

      <section className="card">
        <div className="head">
          <div>
            <h2>Yearly plan</h2>
            {summary && (
              <p className="muted">
                {STATUS_LABEL[summary.status] ?? summary.status} · {summary.totals.trips} trips
                {summary.totals.merged > 0 && ` · ${summary.totals.merged} combined into bigger trips`}
                {summary.totals.manual > 0 && ` · ${summary.totals.manual} added by hand`}
              </p>
            )}
          </div>
          <div className="row">
            {summary && summary.totals.trips > 0 && (
              <a className="button secondary" href={`/api/plan/${year}/export.xlsx${withCancelled ? "?include=cancelled" : ""}`}
                download><Icon name="download" size={16} className="ico" />Export to Excel</a>
            )}
            {!adding && <button onClick={() => setAdding(true)}><Icon name="plus" size={16} className="ico" />Add a trip</button>}
          </div>
        </div>
        {summary && summary.totals.trips > 0 && (
          <label className="check"><input type="checkbox" checked={withCancelled} onChange={(e) => setWithCancelled(e.target.checked)} /> Include cancelled and combined trips in the Excel file</label>
        )}
        {canGenerate && summary && summary.totals.trips > 0 && (
          <p className="row">
            {summary.status === "review" && (
              <button className="secondary" onClick={() => setStatus("published",
                `Publish the ${year} plan? Everyone with a trip will see it in My plan, and the plan can no longer be generated again.`,
                "The plan is published. People can now see their trips in My plan.")}>Publish plan</button>
            )}
            {summary.status === "published" && (
              <>
                <button className="secondary" onClick={() => setStatus("review",
                  `Withdraw the publication? People will no longer see their trips in My plan until it is published again.`,
                  "The publication was withdrawn.")}>Withdraw publication</button>
                <button className="link" onClick={() => setStatus("closed",
                  `Close the ${year} plan? It becomes read-only.`, "The plan year is closed.")}>Close the year</button>
              </>
            )}
            {summary.published_at && summary.status !== "review" && (
              <span className="muted">Published {new Date(summary.published_at).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" })}</span>
            )}
          </p>
        )}
        {statusMsg && <p className={statusMsg.ok ? "good" : "problem"} role={statusMsg.ok ? "status" : "alert"}>{statusMsg.text}</p>}
        {error && <p className="problem">{error}</p>}
        {!summary && !error && <p>Loading…</p>}
        {summary && summary.totals.trips === 0 && (
          <p className="muted">No plan yet.{canGenerate ? " Use Generate plan above." : ""}</p>
        )}
        {summary && summary.totals.trips > 0 && (
          <>
          <div className="segctl" role="group" aria-label="View" style={{ margin: "6px 0 14px" }}>
            <button type="button" className={view === "timeline" ? "on" : ""} onClick={() => setView("timeline")}>Timeline</button>
            <button type="button" className={view === "heatmap" ? "on" : ""} onClick={() => setView("heatmap")}>Heatmap by month</button>
          </div>
          {view === "timeline" && <Timeline year={year} summary={summary} tick={tick} onOpen={setOpenId} />}
          {view === "heatmap" && (
          <div className="heatwrap">
            <table className="heat">
              <thead>
                <tr><th></th>{MONTHS.map((m) => <th key={m}>{m}</th>)}</tr>
              </thead>
              <tbody>
                {summary.regions.map((reg) => (
                  <RegionRows key={reg.id} name={reg.name} rows={reg.rows} cell={cell} onRow={(row) => setSel({ row, month: null, nationwide: false })} />
                ))}
                <tr className="regionhead"><th colSpan={13}>Nationwide</th></tr>
                <tr>
                  <th className="rowlabel"><button className="link" onClick={() => setSel({ row: summary.nationwide, month: null, nationwide: true })}>{summary.nationwide.label}</button></th>
                  {cell(summary.nationwide, true)}
                </tr>
              </tbody>
            </table>
            <div className="heat-legend">Fewer trips <span className="ramp" /> More trips · click a cell to list its trips</div>
          </div>
          )}
          </>
        )}
      </section>

      {adding && (
        <AddTrip year={year} onCancel={() => setAdding(false)}
          onDone={(id) => { setAdding(false); setOpenId(id || null); void changed(); }} />
      )}

      {sel && (
        <section className="card">
          <div className="head">
            <h3>{sel.row.label}{sel.month ? `, ${MONTHS[sel.month - 1]}` : ", whole year"}</h3>
            <button className="link" onClick={() => setSel(null)}>Close</button>
          </div>
          {trips === null && <p>Loading…</p>}
          {trips?.length === 0 && <p className="muted">No trips.</p>}
          {trips && trips.length > 0 && (
            <table className="trips">
              <thead><tr><th>When</th><th>Trip</th><th>Travelers</th><th></th></tr></thead>
              <tbody>
                {trips.map((t) => (
                  <tr key={t.id}>
                    <td>{fmt(t.start_date, t.end_date)}</td>
                    <td>
                      <button className="link" onClick={() => setOpenId(t.id)}>{t.title}</button>
                      {t.merged_count > 0 && <span className="muted"> · combined with {t.merged_count}</span>}
                    </td>
                    <td>{t.travelers}</td>
                    <td>
                      {t.source === "manual" && <span className="badge">by hand</span>}{" "}
                      {t.changed && <span className="badge">changed</span>}{" "}
                      {t.status !== "generated" && <span className="badge">{t.status}</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          {openId !== null && <TripPanel id={openId} onChanged={changed} onClose={() => setOpenId(null)} />}
        </section>
      )}

      {!sel && openId !== null && (
        <section className="card"><TripPanel id={openId} onChanged={changed} onClose={() => setOpenId(null)} /></section>
      )}

      {warnings && <Checks w={warnings} />}
    </>
  );
}

function RegionRows({ name, rows, cell, onRow }: {
  name: string; rows: Row[]; cell: (r: Row) => JSX.Element[]; onRow: (r: Row) => void;
}) {
  return (
    <>
      <tr className="regionhead"><th colSpan={13}>{name}</th></tr>
      {rows.map((r) => (
        <tr key={`${name}-${r.label}`}>
          <th className="rowlabel"><button className="link" onClick={() => onRow(r)}>{r.label}</button></th>
          {cell(r)}
        </tr>
      ))}
    </>
  );
}

function Checks({ w }: { w: WarningSet }) {
  const groups = Object.entries(w.counts);
  return (
    <section className="card">
      <h2>Checks</h2>
      {w.total === 0 ? (
        <p>The plan follows all rules.</p>
      ) : (
        <>
          <p className="muted">
            {w.total} {w.total === 1 ? "point needs" : "points need"} attention. These are warnings, not errors: the plan can stay as it
            is when there is a reason.
          </p>
          {groups.map(([code, n]) => (
            <details key={code} className="check">
              <summary>{WARNING_TITLES[code] ?? code} <span className="badge">{n}</span></summary>
              <ul className="issues">
                {w.warnings.filter((x) => x.code === code).slice(0, 25).map((x, i) => (
                  <li key={i} className={x.level === "block" ? "error" : x.level === "warn" ? "warning" : "info"}>{x.message}</li>
                ))}
              </ul>
            </details>
          ))}
        </>
      )}
    </section>
  );
}

function Generate({ year, onApplied }: { year: number; onApplied: () => void }) {
  const [report, setReport] = useState<Report | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const run = async (commit: boolean) => {
    setBusy(true);
    setMessage(null);
    try {
      const r = await fetch(`/api/admin/plan/${year}/generate?commit=${commit}`, { method: "POST" });
      const body = (await r.json().catch(() => ({}))) as Report & { detail?: string };
      if (!r.ok) {
        setReport(null);
        return setMessage(typeof body.detail === "string" ? body.detail : "The plan could not be generated.");
      }
      setReport(body);
      if (commit) {
        setMessage("The plan was saved.");
        onApplied();
      }
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="card">
      <h2>Generate plan</h2>
      <p className="muted">
        Builds the {year} plan from the organization and the rules. Trips nobody has changed are rebuilt; trips changed or added by hand stay.
      </p>
      <p>
        <button disabled={busy} onClick={() => run(false)}>{busy ? "Working…" : "Preview"}</button>
      </p>
      {message && <p aria-live="polite">{message}</p>}
      {report && (
        <>
          <h3>{report.applied ? "Result" : "Preview (nothing saved yet)"}</h3>
          <ul className="summary">
            <li><strong>{report.trips_created}</strong> trips planned</li>
            <li><strong>{report.trips_merged}</strong> combined into bigger trips</li>
            <li><strong>{report.trips_replaced}</strong> earlier generated trips replaced</li>
            <li><strong>{report.trips_kept}</strong> trips kept (edited or added by hand)</li>
          </ul>
          <table className="trips">
            <thead><tr><th>Event</th><th>Trips</th><th>Combined</th></tr></thead>
            <tbody>
              {report.by_event.map((e) => <tr key={e.event}><td>{e.event}</td><td>{e.trips}</td><td>{e.merged || ""}</td></tr>)}
            </tbody>
          </table>
          {report.unplaced.length > 0 && (
            <>
              <h4>Could not be fully planned</h4>
              <ul className="issues">{report.unplaced.map((u, i) => <li key={i} className="warning">{u}</li>)}</ul>
            </>
          )}
          {report.skipped.length > 0 && (
            <>
              <h4>Not planned</h4>
              <ul className="issues">{report.skipped.map((u, i) => <li key={i} className="info">{u}</li>)}</ul>
            </>
          )}
          <p className="muted">
            {report.warning_total === 0 ? "No rule warnings." : `${report.warning_total} rule warnings (see Checks below after saving).`}
          </p>
          {!report.applied && (
            <p><button disabled={busy} onClick={() => run(true)}>Apply plan</button></p>
          )}
        </>
      )}
    </section>
  );
}
