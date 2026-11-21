"""Read the budget lines of the planning workbook ("Per Budget Travelling (FC)" or "Traveling Plan Budget 2027").

Layout: a header row with Position, Remarks, Count, Frequency, Unit Price and Annual Cost; the event name sits three
columns left of Position. Values are read as saved in the file (formulas are not evaluated here).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import openpyxl

from .orgimport import clean, norm

PREFERRED_SHEETS = ("per budget travelling (fc)", "traveling plan budget 2027")


@dataclass
class BudgetRow:
    row: int
    event: str
    position: str
    remarks: str
    persons: float | None
    frequency: float | None
    unit_price: float | None
    annual_cost: float
    cost_center: str | None
    cost_item: str | None
    justification: str | None
    event_code: str | None


def map_event(event: str, position: str) -> str | None:
    """Which event of the catalog a budget line belongs to (by its name and position)."""
    e, p = norm(event), norm(position)
    if e.startswith("area visit"):
        if "head" in p:
            return "HEAD-AREA"
        return "RM-AM-VISIT" if "regional manager" in p else "AM-FSV-VISIT"
    table = (("area meeting", "AM-FSV-MEET"), ("field management meeting", "REGIONAL-FIELD-MEET"),
             ("local office visit", "LO-VISIT"), ("collection conference", "CONF"), ("collections university", "FLCU"),
             ("collection lakbay", "LAKBAY"), ("year end party", "YEAR-END"))
    return next((code for name, code in table if e.startswith(name)), None)


def _number(value: Any) -> float | None:
    return float(value) if isinstance(value, int | float) and not isinstance(value, bool) else None


def parse_budget(path: str | Path, cost_center: str = "COLFC") -> tuple[list[BudgetRow], list[str]]:
    """Return the budget rows and a list of problems (empty when all is well)."""
    wb = openpyxl.load_workbook(path, data_only=True)
    sheets = sorted(wb.worksheets, key=lambda s: (norm(s.title) not in PREFERRED_SHEETS, wb.worksheets.index(s)))
    for ws in sheets:
        for r in range(1, 16):
            cells = [norm(c.value) for c in ws[r]]
            needed = ("position", "count", "frequency", "unit price")
            if not all(n in cells for n in needed):
                continue
            col = {n: cells.index(n) for n in needed}
            col["annual cost"] = next((i for i, c in enumerate(cells) if c == "annual cost"), -1)
            if col["annual cost"] < 0:
                continue
            opt = {n: cells.index(n) for n in ("remarks", "justification", "cost center", "accounting cost item")
                   if n in cells}
            event_col = cells.index("event or item") if "event or item" in cells else col["position"] - 3
            rows: list[BudgetRow] = []
            problems: list[str] = []
            for i, row in enumerate(ws.iter_rows(min_row=r + 1, values_only=True), r + 1):
                def get(idx: int, row=row) -> Any:
                    return row[idx] if 0 <= idx < len(row) else None
                event, position = clean(get(event_col)), clean(get(col["position"]))
                cost = _number(get(col["annual cost"]))
                if not event or not position or cost is None:
                    continue
                center = clean(get(opt["cost center"])) if "cost center" in opt else None
                if center and cost_center and norm(center) != norm(cost_center):
                    continue
                rows.append(BudgetRow(
                    i, event, position, clean(get(opt["remarks"])) if "remarks" in opt else "",
                    _number(get(col["count"])), _number(get(col["frequency"])), _number(get(col["unit price"])),
                    cost, center or None,
                    clean(get(opt["accounting cost item"])) if "accounting cost item" in opt else None,
                    clean(get(opt["justification"])) or None if "justification" in opt else None,
                    map_event(event, position)))
            if not rows:
                problems.append(f"The sheet '{ws.title}' has the budget columns but no lines with an annual cost.")
            return rows, problems
    return [], ["No budget table was found. Expected columns: Position, Count, Frequency, Unit Price, Annual Cost."]
