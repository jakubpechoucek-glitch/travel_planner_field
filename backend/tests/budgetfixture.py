"""A small fictitious budget workbook in the layout of 'Per Budget Travelling (FC)'."""

from pathlib import Path

import openpyxl


def build_budget(path: Path, *, no_table: bool = False):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Per Budget Travelling (FC)"
    if no_table:
        ws["A1"] = "nothing here"
        wb.save(path)
        return
    ws["E2"] = "Event or Item"
    ws["B3"] = "Travel Expense ~ COLFC"
    for col, title in zip("GHIJKLMN", ["DEPT/\nSTREAM", "Position", "Remarks", "Count", "Frequency", "Unit Price",
                                         " Annual Cost ", " Justification "], strict=True):
        ws[f"{col}4"] = title
    lines = [  # event, position, remarks, persons, frequency, unit price
        ("Area Visit", "Area Manager", "Area Visit - by plane", 4, 4, 30300),
        ("Area Visit", "Head of Nationwide Field", "Field Visit to areas", 1, 8, 34300),
        ("Area Meeting", "Field Supervisor", "Area Meeting - by land", 10, 4, 10800),
        ("Collection Conference", "Area Manager", "Conference", 12, 1, 30300),
        ("Incentive trip", "Head of Nationwide Field", "A line the catalog does not know", 1, 1, 120000),
    ]
    for i, (event, position, remarks, persons, freq, unit) in enumerate(lines, 5):
        ws[f"E{i}"], ws[f"F{i}"], ws[f"G{i}"], ws[f"H{i}"], ws[f"I{i}"] = event, "Medium", "COLFC", position, remarks
        ws[f"J{i}"], ws[f"K{i}"], ws[f"L{i}"] = persons, freq, unit
        ws[f"M{i}"] = persons * freq * unit
        ws[f"N{i}"] = "Justification text"
    ws["E12"] = "Group name (activity)"           # notes below the table must be ignored
    ws["H12"] = "Cluster Visit"
    wb.save(path)
