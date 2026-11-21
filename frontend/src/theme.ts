/** Event families: the colors of the plan. The categorical palette is validated (adjacent pairs, light and dark).
 *  Identity is never color alone: every use also has a legend, a tooltip and a text label. */
export type Family = { key: string; label: string; color: string; ink: string; codes: string[] };

export const FAMILIES: Family[] = [
  { key: "area", label: "Area visits and meetings", color: "var(--c1)", ink: "#fff", codes: ["AM-FSV-VISIT", "AM-FSV-MEET", "LO-VISIT"] },
  { key: "region", label: "Region visits and meetings", color: "var(--c2)", ink: "#fff", codes: ["RM-AM-VISIT", "RM-AM-MEET"] },
  { key: "lakbay", label: "Lakbay", color: "var(--c3)", ink: "#fff", codes: ["LAKBAY"] },
  { key: "company", label: "Conference and parties", color: "var(--c4)", ink: "#0b0b0b", codes: ["CONF", "YEAR-END"] },
  { key: "head", label: "Head of Field", color: "var(--c5)", ink: "#fff", codes: ["HEAD-AREA", "REGIONAL-FIELD-MEET"] },
  { key: "training", label: "Training and quality", color: "var(--c6)", ink: "#fff", codes: ["FLCU", "TQACE-AWARE", "NEGOTIATION-P3"] },
  { key: "other", label: "Other events", color: "var(--c7)", ink: "#fff", codes: [] },
];

export const familyOf = (code: string | undefined | null): Family =>
  FAMILIES.find((f) => code && f.codes.includes(code)) ?? FAMILIES[FAMILIES.length - 1];

export const initials = (name: string | null | undefined) =>
  (name ?? "?").split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0]?.toUpperCase()).join("") || "?";

export const ROLE_LABEL: Record<string, string> = {
  administrator: "Administrator", national_planner: "National planner", regional_planner: "Regional planner",
  area_planner: "Area planner", function_planner: "Function planner", coordinator: "Coordinator", viewer: "Viewer",
};

/** days between today and a yyyy-mm-dd date (negative = past) */
export const daysFromToday = (iso: string) => {
  const d = new Date(iso + "T00:00:00");
  const t = new Date(); t.setHours(0, 0, 0, 0);
  return Math.round((d.getTime() - t.getTime()) / 86400000);
};
