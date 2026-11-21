"""Builds a small, fictitious planning workbook shaped like the real one (no real people)."""

from pathlib import Path

import openpyxl

NB = "\xa0"


def build_workbook(path: Path, *, bad_position: bool = False, move_bob: bool = False, no_tables: bool = False):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Emp Tables"
    if no_tables:
        ws["A1"] = "nothing here"
    else:
        for col, title in ((2, "RM TABLE"), (10, "AM_TABLE"), (18, "FSV TABLE")):
            ws.cell(2, col, title)

        def header(c0, cols):
            for i, h in enumerate(cols):
                ws.cell(4, c0 + i, h)

        hdr = ["EMP NAME", "POSITION", "REGION", "CLUSTER", "AREA", "Local Office"]
        header(2, hdr)
        header(10, hdr)
        header(18, hdr)
        header(26, ["EMP NAME", "POSITION"])

        def put(c0, r, values):
            for i, v in enumerate(values):
                ws.cell(r, c0 + i, v)

        rms = [
            ("Rita Rivera", "REGIONAL MANAGER", "NORTH", "ALPHA 1", None, "Port One"),
            ("Rita Rivera", "REGIONAL MANAGER", "NORTH", "ALPHA 2", None, "Port One"),
            ("Ramon Reyes", "REGIONAL MANAGER", "SOUTH", "BETA 1", None, "Port Three"),
            ("HANA HEAD", "HEAD OF FIELD COLLECTIONS", "NORTH", "NORTH", None, None),
        ]
        for i, row in enumerate(rms):
            put(2, 5 + i, row)
        ams = [
            ("AMY ALVAREZ", "AREA MANAGER", "NORTH", "ALPHA 1", "A", "Port One"),
            ("ALAN ABAD", "AREA MANAGER", "NORTH", "ALPHA 2", "A", "Port Two"),
            ("RAMON REYES", "AM TEMP/REGIONAL MANAGER", "SOUTH", "BETA 1", "B", "Port Three"),
        ]
        for i, row in enumerate(ams):
            put(10, 5 + i, row)
        bob_cluster = "ALPHA 2" if move_bob else "BETA 1"
        bob_office = "Port Two" if move_bob else "Port Three"
        bob_region = "NORTH" if move_bob else "SOUTH"
        fsvs = [
            ("SAM STONE", "FIELD SUPERVISOR", "NORTH", "ALPHA 1", "A", "Port One"),
            (f"SUE{NB}SMITH", "FIELD SUPERVISOR II", "NORTH", "ALPHA 2", "A", "Port Two"),
            ("BOB BETA", "SENIOR FIELD SUPERVISOR", bob_region, bob_cluster, "B", bob_office),
            ("DIGI MENTOR", "DIGITAL MENTOR", "NORTH", "ALPHA 1", "A", "Port One"),
        ]
        if bad_position:
            fsvs.append(("WEIRD PERSON", "WIZARD", "NORTH", "ALPHA 1", "A", "Port One"))
        for i, row in enumerate(fsvs):
            put(18, 5 + i, row)

    lst = wb.create_sheet("EMP LIST FC upload")
    lst.append(["EMP NO", "EMP NAME", "USERNAME", "POSITION", "AM", "REGION", "AREA", "CRM", "PHONE"])
    people = [
        ("1001", "SAM STONE", "FIELD SUPERVISOR", "Amy Alvarez", "NORTH", "Port One"),
        ("1002", "SUE SMITH", "FIELD SUPERVISOR II", "Amy Alvarez", "NORTH", "Port Two"),
        ("1003", "BOB BETA", "SENIOR FIELD SUPERVISOR", "Ramon Reyes", "SOUTH", "Port Three"),
        ("1004", "ONLY LIST", "FIELD SUPERVISOR", "Ramon Reyes", "SOUTH", "Port Three"),
    ]
    for no, name, pos, manager, region, office in people:
        # USERNAME and PHONE exist in the real file; the importer must ignore them
        lst.append([no, name, name.lower().replace(" ", "."), pos, manager, region, office, "R", f"90870{no}"])
    wb.save(path)
