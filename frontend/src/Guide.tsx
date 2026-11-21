import { Fragment, ReactNode, useMemo } from "react";
import guideText from "./guide/user-guide.md?raw";
import { Icon } from "./icons";

/** The user guide. The text lives in guide/user-guide.md (one source, edited like any document);
 *  this page turns it into a readable page with a table of contents. No HTML from the file is ever injected. */

const IMAGES = import.meta.glob("./guide/*.jpg", { eager: true, query: "?url", import: "default" }) as Record<string, string>;
const imageUrl = (name: string) => IMAGES[`./guide/${name}.jpg`];

const slug = (s: string) => s.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/(^-|-$)/g, "");

/** **bold** and `code` inside a line of text */
function inline(text: string): ReactNode[] {
  return text.split(/(\*\*[^*]+\*\*|\*[^*]+\*|`[^`]+`)/).filter(Boolean).map((p, i) =>
    p.startsWith("**") ? <strong key={i}>{p.slice(2, -2)}</strong> : p.startsWith("*") && p.length > 2 ? <em key={i}>{p.slice(1, -1)}</em> : p.startsWith("`") ? <code key={i}>{p.slice(1, -1)}</code> : <Fragment key={i}>{p}</Fragment>);
}

type Block =
  | { t: "h"; level: 1 | 2 | 3; text: string }
  | { t: "p"; text: string }
  | { t: "ul" | "ol"; items: string[] }
  | { t: "table"; head: string[]; rows: string[][] }
  | { t: "quote"; label: string; text: string }
  | { t: "img"; alt: string; name: string };

const cells = (line: string) => line.trim().replace(/^\||\|$/g, "").split("|").map((c) => c.trim());

function parse(src: string): Block[] {
  const lines = src.split("\n");
  const out: Block[] = [];
  for (let i = 0; i < lines.length; i++) {
    const l = lines[i];
    if (!l.trim()) continue;
    const h = /^(#{1,3}) (.*)$/.exec(l);
    if (h) { out.push({ t: "h", level: h[1].length as 1 | 2 | 3, text: h[2] }); continue; }
    const im = /^!\[(.*)\]\((.*)\)$/.exec(l);
    if (im) { out.push({ t: "img", alt: im[1], name: im[2] }); continue; }
    if (l.startsWith("> ")) {
      const m = /^> \*\*(.+?)\*\* (.*)$/.exec(l);
      out.push({ t: "quote", label: m ? m[1] : "", text: m ? m[2] : l.slice(2) });
      continue;
    }
    if (l.startsWith("|")) {
      const rows: string[] = [];
      while (i < lines.length && lines[i].startsWith("|")) rows.push(lines[i++]);
      i--;
      out.push({ t: "table", head: cells(rows[0]), rows: rows.slice(2).map(cells) });
      continue;
    }
    if (/^- /.test(l) || /^\d+\. /.test(l)) {
      const ordered = /^\d+\. /.test(l);
      const items: string[] = [];
      while (i < lines.length && (ordered ? /^\d+\. /.test(lines[i]) : /^- /.test(lines[i]))) items.push(lines[i++].replace(ordered ? /^\d+\. / : /^- /, ""));
      i--;
      out.push({ t: ordered ? "ol" : "ul", items });
      continue;
    }
    out.push({ t: "p", text: l });
  }
  return out;
}

/** which chapter to offer first for each role */
const ROLE_CHAPTER: [string, string][] = [
  ["administrator", "4.5 Administrator"],
  ["national_planner", "4.4 National planner (Head of Field)"],
  ["regional_planner", "4.3 Regional planner (Regional Manager)"],
  ["area_planner", "4.2 Area planner (Area Manager)"],
];

export default function Guide({ roles }: { roles: string[] }) {
  const blocks = useMemo(() => parse(guideText), []);
  const toc = blocks.filter((b): b is Extract<Block, { t: "h" }> => b.t === "h" && b.level <= 2);
  const mine = ROLE_CHAPTER.find(([r]) => roles.includes(r))?.[1] ?? "4.1 Field supervisor and other viewers";

  const go = (text: string) => document.getElementById(slug(text))?.scrollIntoView({ behavior: "smooth", block: "start" });

  return (
    <div className="guide">
      <aside className="guide-toc no-print" aria-label="Contents">
        <button type="button" className="toc-mine" onClick={() => go(mine)}><Icon name="arrow" size={16} />Go to my chapter</button>
        <ul>
          {toc.map((h) => (
            <li key={h.text} className={h.level === 1 ? "l1" : "l2"}>
              <a href={`#${slug(h.text)}`} onClick={(e) => { e.preventDefault(); go(h.text); }}>{h.text}</a>
            </li>
          ))}
        </ul>
      </aside>
      <article className="guide-body">
        <div className="no-print" style={{ display: "flex", justifyContent: "flex-end" }}>
          <button type="button" className="secondary" onClick={() => window.print()}><Icon name="download" size={16} className="ico" />Print or save as PDF</button>
        </div>
        {blocks.map((b, i) => {
          switch (b.t) {
            case "h": {
              const Tag = (`h${b.level + 1}` as "h2" | "h3" | "h4");
              return <Tag key={i} id={slug(b.text)} className={`g${b.level}`}>{b.text}</Tag>;
            }
            case "p": return <p key={i}>{inline(b.text)}</p>;
            case "ul": return <ul key={i}>{b.items.map((t, j) => <li key={j}>{inline(t)}</li>)}</ul>;
            case "ol": return <ol key={i}>{b.items.map((t, j) => <li key={j}>{inline(t)}</li>)}</ol>;
            case "quote": return <div key={i} className={`gnote ${b.label === "Tip" ? "tip" : "note"}`}><strong>{b.label}</strong> {inline(b.text)}</div>;
            case "img": {
              const url = imageUrl(b.name);
              return url ? <figure key={i}><img src={url} alt={b.alt} loading="lazy" /><figcaption>{b.alt}</figcaption></figure> : null;
            }
            case "table":
              return (
                <div key={i} className="heatwrap">
                  <table className="trips guide-table">
                    <thead><tr>{b.head.map((h, j) => <th key={j}>{inline(h)}</th>)}</tr></thead>
                    <tbody>{b.rows.map((r, j) => <tr key={j}>{r.map((c, k) => <td key={k}>{inline(c)}</td>)}</tr>)}</tbody>
                  </table>
                </div>
              );
          }
        })}
      </article>
    </div>
  );
}
