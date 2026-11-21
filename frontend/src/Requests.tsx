import { useCallback, useEffect, useState } from "react";
import { api } from "./api";
import { Icon } from "./icons";
import { fmtDates } from "./TripPanel";

type Req = {
  id: number; kind: string; kind_label: string; message: string; status: string; requester: string; decided_by: string | null;
  decision_note: string | null; created_at: string; proposed_start: string | null; proposed_end: string | null; editable: boolean;
  trip: { id: number; title: string; start_date: string; end_date: string };
};
type Data = { open: number; requests: Req[] };

const TONE: Record<string, string> = { open: "warn", accepted: "good", declined: "bad", withdrawn: "" };

/** Suggestions from people on a trip, for the planner who looks after that trip. */
export default function Requests({ year, tick, onOpen, onChanged }: { year: number; tick: number; onOpen: (id: number) => void; onChanged: () => void }) {
  const [data, setData] = useState<Data | null>(null);
  const [all, setAll] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    const r = await api<Data>(`/api/plan/${year}/requests?state=${all ? "all" : "open"}`);
    if (r.ok) { setData(r.data); setError(null); } else setError(r.error);
  }, [year, all]);
  useEffect(() => { void load(); }, [load, tick]);

  const decide = async (q: Req, decision: "accepted" | "declined") => {
    const note = window.prompt(decision === "declined" ? "Why are you declining? The person will read this." : "Note for the person (optional), for example the new date:");
    if (note === null) return;
    const r = await api(`/api/plan/requests/${q.id}/decide`, "POST", { decision, note: note || undefined });
    if (!r.ok) return setError(r.error);
    await load(); onChanged();
  };

  return (
    <div>
      <p className="muted">
        People on a trip can suggest a change in My plan. A suggestion changes nothing by itself: open the trip and make the change (with a reason), then mark the suggestion as <em>accepted</em>, or <em>decline</em> it and say why.
      </p>
      <label className="check"><input type="checkbox" checked={all} onChange={(e) => setAll(e.target.checked)} /> Show answered suggestions too</label>
      {error && <p className="problem">{error}</p>}
      {!data && !error && <div className="skeleton" style={{ height: 120 }} />}
      {data && data.requests.length === 0 && <p className="empty"><Icon name="ok" size={28} /><br />No suggestions waiting.</p>}
      {data && data.requests.length > 0 && (
        <ul className="issues">
          {data.requests.map((q) => (
            <li key={q.id} style={{ listStyle: "none" }}>
              <div className="titleline">
                <strong>{q.requester}</strong> · {q.kind_label}
                <span className={`pill ${TONE[q.status]}`}>{q.status}</span>
              </div>
              <div>
                <button className="link" onClick={() => onOpen(q.trip.id)}>{q.trip.title}</button>{" "}
                <span className="muted">{fmtDates(q.trip.start_date, q.trip.end_date)}</span>
                {q.proposed_start && <span> → prefers <strong>{fmtDates(q.proposed_start, q.proposed_end ?? q.proposed_start)}</strong></span>}
              </div>
              <div>“{q.message}”</div>
              {q.decision_note && <div className="muted">Answer{q.decided_by ? ` by ${q.decided_by}` : ""}: {q.decision_note}</div>}
              {q.status === "open" && (
                q.editable ? (
                  <span className="actions">
                    <button className="link" onClick={() => onOpen(q.trip.id)}>Open the trip</button>
                    <button className="link" onClick={() => decide(q, "accepted")}>Mark as accepted</button>
                    <button className="link" onClick={() => decide(q, "declined")}>Decline</button>
                  </span>
                ) : <span className="muted">Only the planner of this trip can answer.</span>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
