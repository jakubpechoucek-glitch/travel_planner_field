import { ChangeEvent, useCallback, useEffect, useState } from "react";

type Cluster = { id: number; name: string; lead: string | null; supervisors: number; offices: string[] };
type Region = { id: number; name: string; lead: string | null; clusters: Cluster[] };
type Tree = { regions: Region[]; local_offices: string[] };
type Issue = { level: "error" | "warning" | "info"; code: string; message: string };
type Report = {
  applied: boolean;
  effective_date: string;
  summary: Record<string, number>;
  issues: Issue[];
  errors: number;
  warnings: number;
};

const label = (key: string) => {
  const text = key.replace(/_/g, " ");
  return text.charAt(0).toUpperCase() + text.slice(1);
};

export default function Org({ isAdmin }: { isAdmin: boolean }) {
  const [tree, setTree] = useState<Tree | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    const r = await fetch("/api/org/tree");
    if (r.status === 403) return setError("You do not have permission to see the organization.");
    if (!r.ok) return setError("The organization could not be loaded. Please try again later.");
    setTree((await r.json()) as Tree);
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const empty = tree !== null && tree.regions.length === 0;

  return (
    <>
      <Help />
      {isAdmin && <ImportPanel onApplied={load} />}
      <section className="card">
        <h2>Organization</h2>
        {error && <p className="problem">{error}</p>}
        {!tree && !error && <p>Loading…</p>}
        {empty && (
          <p className="muted">
            No organization has been imported yet.{isAdmin ? " Upload the planning workbook above." : ""}
          </p>
        )}
        {tree?.regions.map((region) => (
          <div key={region.id} className="region" style={{ ["--rc" as string]: `var(--c${(tree.regions.indexOf(region) % 7) + 1})` }}>
            <h3>
              <span className="dot" style={{ background: "var(--rc)" }} />{region.name}
              {region.lead && <span className="muted"> · Regional Manager: {region.lead}</span>}
            </h3>
            <div className="clusters">
              {region.clusters.map((c) => (
                <article key={c.id} className="cluster">
                  <h4>{c.name}</h4>
                  <p>{c.lead ?? <span className="muted">No leader</span>}</p>
                  <p className="muted">
                    {c.supervisors} {c.supervisors === 1 ? "supervisor" : "supervisors"}
                    {c.offices.length > 0 && <> · {c.offices.join(", ")}</>}
                  </p>
                </article>
              ))}
            </div>
          </div>
        ))}
      </section>
    </>
  );
}

function Help() {
  return (
    <details className="card help">
      <summary>Help: how the organization works</summary>
      <p>
        The organization is the structure used to plan travel: <strong>regions</strong> contain{" "}
        <strong>clusters</strong>, each led by an Area Manager (or by the Regional Manager when there is no Area
        Manager). Supervisors report to the leader of their cluster and meet at a <strong>local office</strong>.
      </p>
      <p>
        Administrators update it by uploading the planning workbook (.xlsx). Every upload is first shown as a{" "}
        <strong>preview</strong>: nothing is saved until you press <em>Apply import</em>. Uploading the same file
        again changes nothing. If a person changes manager or cluster, set the date the change takes effect; the old
        assignment is kept as history.
      </p>
      <p>
        <strong>Errors</strong> must be fixed in the workbook before the import can be applied.{" "}
        <strong>Warnings</strong> mean the data is ambiguous and the import chose a sensible default, so please
        check them. Names and structure are visible to administrators and national planners only.
      </p>
    </details>
  );
}

function ImportPanel({ onApplied }: { onApplied: () => void }) {
  const [file, setFile] = useState<File | null>(null);
  const [effective, setEffective] = useState("2027-01-01");
  const [report, setReport] = useState<Report | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const send = async (commit: boolean) => {
    if (!file) return;
    setBusy(true);
    setMessage(null);
    const form = new FormData();
    form.append("file", file);
    try {
      const r = await fetch(`/api/admin/org-import?effective_date=${effective}&commit=${commit}`, {
        method: "POST",
        body: form,
      });
      if (!r.ok) {
        const body = (await r.json().catch(() => ({}))) as { detail?: string };
        setReport(null);
        setMessage(body.detail ?? "The import failed. Please try again.");
        return;
      }
      const data = (await r.json()) as Report;
      setReport(data);
      if (data.applied) {
        setMessage("The organization was imported.");
        onApplied();
      }
    } finally {
      setBusy(false);
    }
  };

  const pick = (e: ChangeEvent<HTMLInputElement>) => {
    setFile(e.target.files?.[0] ?? null);
    setReport(null);
    setMessage(null);
  };

  const changed = report ? Object.entries(report.summary).filter(([k]) => !k.endsWith("unchanged")) : [];
  const order = { error: 0, warning: 1, info: 2 } as const;

  return (
    <section className="card">
      <h2>Import organization</h2>
      <div className="row">
        <label>
          Planning workbook (.xlsx)
          <input type="file" accept=".xlsx" onChange={pick} />
        </label>
        <label>
          Valid from
          <input type="date" value={effective} onChange={(e) => setEffective(e.target.value)} required />
        </label>
      </div>
      <p>
        <button disabled={!file || busy} onClick={() => send(false)}>
          {busy ? "Working…" : "Preview"}
        </button>
      </p>
      {message && <p aria-live="polite">{message}</p>}
      {report && (
        <>
          <h3>{report.applied ? "Result" : "Preview (nothing saved yet)"}</h3>
          {changed.length === 0 ? (
            <p className="muted">No changes: the database already matches this file.</p>
          ) : (
            <ul className="summary">
              {changed.map(([k, v]) => (
                <li key={k}>
                  <strong>{v}</strong> {label(k).toLowerCase()}
                </li>
              ))}
            </ul>
          )}
          {report.issues.length > 0 && (
            <ul className="issues">
              {[...report.issues]
                .sort((a, b) => order[a.level] - order[b.level])
                .map((i, n) => (
                  <li key={n} className={i.level}>
                    <span className="badge">{i.level}</span> {i.message}
                  </li>
                ))}
            </ul>
          )}
          {!report.applied && (
            <p>
              <button disabled={busy || report.errors > 0} onClick={() => send(true)}>
                Apply import
              </button>
              {report.errors > 0 && <span className="problem"> Fix the errors first.</span>}
            </p>
          )}
        </>
      )}
    </section>
  );
}
