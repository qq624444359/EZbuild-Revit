# -*- coding: utf-8 -*-
"""Sheet constants and the standard sheet list.

Every number here was measured programmatically from 296 pages of issued BC
drawings across 6 projects. See the "Sheet coordinate baseline" tab of
"Drawing Layout Rules v2".

If the real title block family differs from this, edit THIS FILE ONLY -
the scripts all read from here.
"""

from __future__ import unicode_literals

# ---------------------------------------------------------------
# Units: Revit stores lengths internally in feet
# ---------------------------------------------------------------
MM_PER_FT = 304.8


def mm(value):
    """millimetres -> Revit internal units (feet)"""
    return float(value) / MM_PER_FT


def to_mm(value):
    """Revit internal units (feet) -> millimetres"""
    return float(value) * MM_PER_FT


# ---------------------------------------------------------------
# A3 sheet constants (origin bottom-left, X right, Y up, millimetres)
# ---------------------------------------------------------------
SHEET_W = 420.0          # measured: all 6 PDF sets are 1191pt wide
SHEET_H = 297.0          # measured: all 6 PDF sets are 842pt tall
TITLEBLOCK_X = 370.0     # measured: full-height rule, zero deviation across 6 projects
TITLEBLOCK_W = SHEET_W - TITLEBLOCK_X   # = 50.0

MARGIN_L = 10.0
MARGIN_T = 10.0
MARGIN_B = 10.0
MARGIN_R = 4.0           # clear space between content and the title block rule

CONTENT_X0 = MARGIN_L                    # 10.0
CONTENT_X1 = TITLEBLOCK_X - MARGIN_R     # 366.0
CONTENT_Y0 = MARGIN_B                    # 10.0
CONTENT_Y1 = SHEET_H - MARGIN_T          # 287.0
CONTENT_W = CONTENT_X1 - CONTENT_X0      # 356.0
CONTENT_H = CONTENT_Y1 - CONTENT_Y0      # 277.0

# Used by the audit script to decide whether a title block really is A3
EXPECTED_SHEET_SIZE_MM = (SHEET_W, SHEET_H)
SHEET_SIZE_TOLERANCE_MM = 2.0


# ---------------------------------------------------------------
# Region rules (rules workbook, "Region rules" tab)
# Coordinates are millimetres, (x0, y0, x1, y1), origin bottom-left
# ---------------------------------------------------------------
AREA_RULES = {
    "A-01": {  # no notes: schedules and pure detail sheets
        "desc": "No note region; views or table fill the usable area",
        "note_region": None,
        "view_region": (CONTENT_X0, CONTENT_Y0, CONTENT_X1, CONTENT_Y1),
    },
    "A-02": {  # top band, 4 columns: floor plans, roof plans
        "desc": "Notes as a 4-column band across the top",
        "note_region": (CONTENT_X0, 216.0, CONTENT_X1, CONTENT_Y1),
        "note_columns_x": [10.0, 84.0, 171.0, 259.0],   # measured on A201
        "view_region": (CONTENT_X0, CONTENT_Y0, CONTENT_X1, 210.0),
    },
    "A-03": {  # left column: elevations, sections
        "desc": "Notes as a left column (plus keynote legend and risk matrix)",
        "note_region": (CONTENT_X0, CONTENT_Y0, 80.0, CONTENT_Y1),
        "view_region": (88.0, CONTENT_Y0, CONTENT_X1, CONTENT_Y1),
    },
    "A-04": {  # small top-left block: site plans, drainage plans
        "desc": "Notes as a small top-left block",
        "note_region": (CONTENT_X0, 216.0, 76.0, CONTENT_Y1),
        "view_region": (CONTENT_X0, CONTENT_Y0, CONTENT_X1, CONTENT_Y1),
    },
    "A-05": {  # detail grid
        "desc": "Detail grid, no dedicated note region",
        "note_region": None,
        "view_region": (CONTENT_X0, CONTENT_Y0, CONTENT_X1, CONTENT_Y1),
        "max_cols": 3,
        "max_rows": 2,
    },
}


# ---------------------------------------------------------------
# Packing parameters (rules workbook, "Packing parameters" tab)
# Values marked TO CALIBRATE are estimates until Measure Layout is run
# ---------------------------------------------------------------
PACK = {
    # Measured on 54 Windrush Close: horizontal gaps between adjacent detail
    # viewports were 42.0, 42.0, 41.6, 43.9, 35.1, 31.4 mm. Three sit on 42,
    # so 42 is the habitual column spacing rather than the minimum.
    "GAP_X": 42.0,

    # ...but the designer compresses it when a sheet is tight. On A523 two
    # columns 137.3 and 160.2 wide were spaced 35.0 mm apart; on A522 the
    # tighter row went to 31.4. So 42 is a preference, 31 is the floor.
    "GAP_X_MIN": 31.0,

    # Vertical spacing showed NO cluster once measured between genuinely
    # adjacent viewports: 3.0, 12.4, 15.5, 27.8, 29.4, 45.4 mm. Details differ
    # in height, so the designer spreads whatever space is left. The packer
    # should therefore treat GAP_Y as a floor and distribute the slack evenly
    # down the column, not aim for a target value.
    "GAP_Y_MIN": 3.0,
    "V_DISTRIBUTE": True,

    "ALIGN_MODE": "top-left",
    "FLOW": "row-major",
    "SHRINK_ALLOWED": False,   # never auto-change view scale, warn instead
}

# Revit pads a viewport outline by exactly 0.01 ft per side, so the outline is
# 0.02 ft = 6.096 mm larger than the drawing in both axes. Verified on 14
# drafting-view viewports in 54 Windrush Close: every single one measured 6.1 mm
# in both width and height. Because it is exact, the packer can plan in content
# sizes and convert to outline sizes without error.
VIEWPORT_OUTLINE_PADDING_MM = 0.02 * 12 * 25.4    # = 6.096


# ---------------------------------------------------------------
# Standard sheet set (rules workbook, "Standard sheets" tab)
# The A5xx sheet numbers common to all 5 complete BC sets - pure reuse
# ---------------------------------------------------------------
STANDARD_DETAIL_SHEETS = [
    ("A501", "Ground Clearance & Silt Fence Detail"),
    ("A502", "General Fixing Detail - Bottom Plate"),
    ("A503", "General Fixing Detail - Bottom Plate"),
    ("A504", "General Fixing Detail - Top Plate & Lintel"),
    ("A505", "General Fixing Detail - Truss"),
    ("A506", "Durability Requirement"),
    ("A507", "Nailing Schedule - 1"),
    ("A508", "Nailing Schedule - 2"),
    ("A509", "Stair & Handrail Detail"),
    ("A511", "Window Detail"),
    ("A512", "Window Detail"),
    ("A531", "Roof Detail"),
    ("A532", "Roof Detail"),
    ("A533", "Roof Detail"),
    ("A541", "Wet Area Detail"),
    ("A542", "Wet Area Detail"),
    ("A543", "Wet Area Detail"),
]

# Present in some projects only - worth folding into the standard library
OPTIONAL_DETAIL_SHEETS = [
    ("A510", "Garage Door & Aluminium Door Sill Detail"),
    ("A513", "Wall Detail"),
    ("A514", "Wall Detail"),
    ("A515", "Wall Detail"),
    ("A516", "Block Wall Detail"),
    ("A517", "Wall Detail"),
    ("A518", "Wall Detail"),
    ("A519", "Allco Tanking Detail"),
    ("A520", "Allco Tanking Detail"),
    ("A534", "Roof Detail"),
    ("A544", "Wet Area Detail"),
]

STANDARD_SHEET_NUMBERS = [n for n, _ in STANDARD_DETAIL_SHEETS]
OPTIONAL_SHEET_NUMBERS = [n for n, _ in OPTIONAL_DETAIL_SHEETS]
