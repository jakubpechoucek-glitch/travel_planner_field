import { ReactNode, useCallback, useState } from "react";

/* ------------------------------------------------------------------ tooltip */

type Tip = { x: number; y: number; content: ReactNode } | null;

/** A small hover and focus tooltip shared by the charts. */
export function useTip() {
  const [tip, setTip] = useState<Tip>(null);
  const show = useCallback((e: { clientX: number; clientY: number }, content: ReactNode) => setTip({ x: e.clientX, y: e.clientY, content }), []);
  const showAt = useCallback((el: Element, content: ReactNode) => {
    const r = el.getBoundingClientRect();
    setTip({ x: r.left + r.width / 2, y: r.top, content });
  }, []);
  const hide = useCallback(() => setTip(null), []);
  const node = tip ? (
    <div className="tip" role="tooltip" style={{ left: Math.min(tip.x + 14, window.innerWidth - 270), top: Math.max(tip.y - 12, 8) }}>
      {tip.content}
    </div>
  ) : null;
  return { show, showAt, hide, node };
}

export const compact = (n: number) => (n >= 1e6 ? `${(n / 1e6).toFixed(n >= 1e7 ? 0 : 1)}M` : n >= 1e3 ? `${Math.round(n / 1e3)}K` : String(Math.round(n)));

/* ------------------------------------------------------------------ columns */

export type Column = { label: string; value: number; tip: ReactNode };

/** One series as columns: thin (24px at most), a 4px rounded end, one baseline, hairline grid, tooltip per column. */
export function ColumnChart({ data, format, ariaLabel }: { data: Column[]; format: (n: number) => string; ariaLabel: string }) {
  const { show, showAt, hide, node } = useTip();
  const max = Math.max(1, ...data.map((d) => d.value));
  const top = Math.ceil(max / 1e5) * 1e5 > max * 1.05 ? Math.ceil(max / 1e5) * 1e5 : max;
  const ticks = [0, 0.5, 1].map((f) => f * top);
  return (
    <div className="colchart" role="img" aria-label={ariaLabel}>
      <div className="yaxis" aria-hidden="true">{[...ticks].reverse().map((t) => <span key={t}>{compact(t)}</span>)}</div>
      <div className="plot">
        {[0, 1, 2].map((i) => <i key={i} className="gridline" style={{ bottom: `${(i / 2) * 100}%` }} />)}
        <div className="cols">
          {data.map((d, i) => (
            <button key={d.label} type="button" className="col" aria-label={`${d.label}: ${format(d.value)}`}
              onMouseMove={(e) => show(e, d.tip)} onMouseLeave={hide} onFocus={(e) => showAt(e.currentTarget, d.tip)} onBlur={hide}>
              <span className="stick" style={{ height: `${(d.value / top) * 100}%` }} />
              <span className="xl">{d.label}</span>
            </button>
          ))}
        </div>
      </div>
      {node}
    </div>
  );
}

/* ------------------------------------------------------------------ horizontal bars */

export type HRow = { label: string; value: number; note?: string };

/** Ranked horizontal bars on one baseline, one hue, the value at the tip. */
export function HBars({ rows, format, limit = 8 }: { rows: HRow[]; format: (n: number) => string; limit?: number }) {
  const shown = rows.slice(0, limit);
  const max = Math.max(1, ...shown.map((r) => r.value));
  return (
    <ul className="hbars">
      {shown.map((r) => (
        <li key={r.label}>
          <span className="name" title={r.label}>{r.label}</span>
          <span className="track"><span className="fill" style={{ width: `${Math.max(1, (r.value / max) * 100)}%` }} /></span>
          <span className="num">{format(r.value)}</span>
          {r.note && <span className="sub">{r.note}</span>}
        </li>
      ))}
      {rows.length > limit && <li className="more">+ {rows.length - limit} more in the table below</li>}
    </ul>
  );
}

/* ------------------------------------------------------------------ paired bars (budget against estimate) */

export type PRow = { label: string; a: number; b: number; delta: number };

export function PairedBars({ rows, format, aLabel, bLabel }: { rows: PRow[]; format: (n: number) => string; aLabel: string; bLabel: string }) {
  const max = Math.max(1, ...rows.flatMap((r) => [r.a, r.b]));
  return (
    <div className="paired">
      <div className="legend" aria-label="Legend">
        <span><i className="sw gray" /> {aLabel}</span>
        <span><i className="sw brand" /> {bLabel}</span>
      </div>
      <ul>
        {rows.map((r) => (
          <li key={r.label}>
            <span className="name" title={r.label}>{r.label}</span>
            <span className="pair">
              <span className="line"><span className="bar gray" style={{ width: `${(r.a / max) * 100}%` }} /><span className="num">{r.a ? format(r.a) : "–"}</span></span>
              <span className="line"><span className="bar brand" style={{ width: `${(r.b / max) * 100}%` }} /><span className="num">{r.b ? format(r.b) : "–"}</span></span>
            </span>
            <span className={`delta ${r.delta > 0 ? "up" : r.delta < 0 ? "down" : ""}`}>
              {r.delta !== 0 && <>{r.delta > 0 ? "▲" : "▼"} </>}
              {r.delta === 0 ? "equal" : `${format(Math.abs(r.delta))} ${r.delta > 0 ? "above" : "below"}`}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

/* ------------------------------------------------------------------ segmented bar, meter, sparkline, ring */

export type Part = { label: string; value: number; color: string; ink?: string };

/** One whole split into a few parts: each block shows its share when it fits; the legend names the parts. */
export function SegBar({ parts, format = (n) => String(n), total }: { parts: Part[]; format?: (n: number) => string; total?: number }) {
  const sum = total ?? parts.reduce((s, p) => s + p.value, 0);
  const shown = parts.filter((p) => p.value > 0);
  return (
    <div className="seg">
      <div className="bar" role="img" aria-label={shown.map((p) => `${p.label}: ${Math.round((100 * p.value) / sum)}%`).join(", ")}>
        {shown.map((p) => {
          const pct = (100 * p.value) / sum;
          return (
            <span key={p.label} className="block" title={`${p.label}: ${format(p.value)} (${pct.toFixed(0)}%)`} style={{ flex: `${p.value} 0 0`, background: p.color, color: p.ink ?? "#fff" }}>
              {pct >= 12 ? `${Math.round(pct)}%` : ""}
            </span>
          );
        })}
      </div>
      <div className="legend">
        {shown.map((p) => <span key={p.label}><i className="sw" style={{ background: p.color }} /> {p.label} · {format(p.value)}</span>)}
      </div>
    </div>
  );
}

export function Meter({ value, max, label }: { value: number; max: number; label: string }) {
  const pct = Math.max(0, Math.min(100, (100 * value) / Math.max(1, max)));
  return (
    <div className="meter" role="meter" aria-valuenow={Math.round(pct)} aria-valuemin={0} aria-valuemax={100} aria-label={label}>
      <span style={{ width: `${pct}%` }} />
    </div>
  );
}

export function Sparkline({ values, width = 120, height = 34 }: { values: number[]; width?: number; height?: number }) {
  const max = Math.max(1, ...values);
  const step = width / values.length;
  const last = values.length - 1;
  return (
    <svg className="spark" width={width} height={height} viewBox={`0 0 ${width} ${height}`} aria-hidden="true">
      {values.map((v, i) => {
        const h = Math.max(2, (v / max) * (height - 4));
        return <rect key={i} x={i * step + 1} y={height - h} width={Math.max(2, step - 3)} height={h} rx="2" className={i === last ? "now" : ""} />;
      })}
    </svg>
  );
}

export function Ring({ done, total, size = 64 }: { done: number; total: number; size?: number }) {
  const r = (size - 8) / 2;
  const c = 2 * Math.PI * r;
  return (
    <svg className="ring" width={size} height={size} viewBox={`0 0 ${size} ${size}`} role="img" aria-label={`${done} of ${total} steps done`}>
      <circle cx={size / 2} cy={size / 2} r={r} className="bg" />
      <circle cx={size / 2} cy={size / 2} r={r} className="fg" strokeDasharray={c} strokeDashoffset={c * (1 - done / Math.max(1, total))} transform={`rotate(-90 ${size / 2} ${size / 2})`} />
      <text x="50%" y="50%" textAnchor="middle" dominantBaseline="central">{done}/{total}</text>
    </svg>
  );
}
