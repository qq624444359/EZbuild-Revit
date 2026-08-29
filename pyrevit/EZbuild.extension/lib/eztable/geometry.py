# -*- coding: utf-8 -*-
"""
geometry.py -- unit conversion and coordinate maths

Coordinate convention (spec section 2; do not change once settled):
    origin  top-left corner of the table = (0, 0, 0)
    X axis  positive to the right (column direction)
    Y axis  negative downwards (increasing row -> decreasing Y)
    Z axis  always 0
    scale   view is 1:1, so every dimension is the real paper dimension
    units   feet throughout (Revit's internal unit)

No Revit API and no third-party libraries, so this module can be exercised under
both IronPython 2.7 and CPython 3.x.
"""

from __future__ import division

from collections import namedtuple

# ---------------------------------------------------------------- constants

EMU_PER_INCH = 914400          # unused, kept for reference
POINTS_PER_INCH = 72.0
INCHES_PER_FOOT = 12.0
PIXELS_PER_INCH = 96.0
MDW = 7.0                      # max digit width: pixel width of '0' in Calibri 11 @96dpi
CELL_PADDING_PX = 5.0          # total left+right cell padding in Excel, in pixels

# Excel's factory defaults (note: not baseColWidth's 8)
DEFAULT_COL_WIDTH_CHARS = 8.43
DEFAULT_ROW_HEIGHT_POINTS = 15.0

# TextNote padding on one side: Excel defaults to 2px on each side
TEXT_PADDING_FT = 2.0 / PIXELS_PER_INCH / INCHES_PER_FOOT

# ---- Revit's text size model (calibrated by measurement, see below) -------
#
# Revit's TEXT_SIZE parameter is not a font size -- it is the **cap height**.
# Feeding Excel's 7pt straight in makes Revit render a 7pt cap height, which
# corresponds to a 7/0.716 = 9.8pt font: 40% larger than Excel, and the text
# spills out of its cell.
#
# How it was calibrated: a Revit export was aligned against the known
# 78.05 x 97.90mm table (measured at 5.561 px/mm) and the ink height of a pure
# uppercase "RC" came out at 2.70mm = 7.65pt (antialiasing included; the true
# value is about 7.1pt) -- confirming TEXT_SIZE == cap height.
#
# Two more measured values:
#   line pitch (top to top)   = 1.60 x TEXT_SIZE   (= 1.146 em)
#   insertion point to cap top = 0.267 x TEXT_SIZE  (Arial's ascender/cap - 1 =
#                                                    0.264, which agrees)

# font -> (cap height / em, ascender / em)
FONT_METRICS = {
    'arial': (0.7163, 0.9052),
    'liberation sans': (0.7163, 0.9052),
    'helvetica': (0.7170, 0.9050),
    'arial narrow': (0.7163, 0.9052),
    'calibri': (0.6318, 0.7500),
    'times new roman': (0.6548, 0.8911),
    'tahoma': (0.7271, 1.0000),
    'verdana': (0.7271, 1.0050),
    'segoe ui': (0.7000, 0.9198),
    'microsoft yahei': (0.7300, 1.0000),
    'simsun': (0.7300, 0.8600),
    'simhei': (0.7300, 0.8600),
}
DEFAULT_FONT_METRICS = FONT_METRICS['arial']

REVIT_LINE_PITCH_FACTOR = 1.60      # line pitch / TEXT_SIZE, measured


def font_metrics(font_name):
    if not font_name:
        return DEFAULT_FONT_METRICS
    return FONT_METRICS.get(font_name.strip().lower(), DEFAULT_FONT_METRICS)


def revit_text_size_feet(size_pt, font_name=None):
    """Excel font size in points -> Revit TEXT_SIZE in feet. Remember that is a
    cap height, not a font size."""
    cap_ratio = font_metrics(font_name)[0]
    return points_to_feet(float(size_pt) * cap_ratio)


def revit_line_pitch_feet(size_pt, font_name=None):
    return revit_text_size_feet(size_pt, font_name) * REVIT_LINE_PITCH_FACTOR


def revit_top_gap_feet(size_pt, font_name=None):
    """Distance from a TextNote insertion point to the cap top of its first line."""
    cap_ratio, asc_ratio = font_metrics(font_name)
    return revit_text_size_feet(size_pt, font_name) * (asc_ratio / cap_ratio - 1.0)


# ---------------------------------------------------------------- conversions

def points_to_feet(pt):
    return float(pt) / POINTS_PER_INCH / INCHES_PER_FOOT


def feet_to_points(ft):
    return float(ft) * POINTS_PER_INCH * INCHES_PER_FOOT


def pixels_to_feet(px):
    return float(px) / PIXELS_PER_INCH / INCHES_PER_FOOT


def feet_to_mm(ft):
    """Only used for logging and acceptance output."""
    return float(ft) * INCHES_PER_FOOT * 25.4


def mm_to_feet(mm):
    return float(mm) / 25.4 / INCHES_PER_FOOT


def col_width_to_feet(width_chars):
    """
    Excel measures column width in characters; convert to pixels, then to feet.

    Why round: the width stored in the xlsx is a value like 11.42578125, which
    works out to 84.98px, but Excel renders whole pixels (85px). Rounding keeps
    each column from being a fraction of a percent off and accumulating into the
    total width. Measured on the Summary sheet of Planing_plan.xlsx, columns A-E
    compute to 84.98 / 70.98 / 43.99 / 37.98 / 56.98, which round to exactly
    85 / 71 / 44 / 38 / 57.
    """
    px = round(float(width_chars) * MDW + CELL_PADDING_PX)
    return pixels_to_feet(px)


def row_height_to_feet(height_points):
    """Excel measures row height in points."""
    return points_to_feet(height_points)


# ---------------------------------------------------------------- default fallbacks
# For rows and columns that were never set explicitly, xlsxlite either has no dim
# at all or reports width/height as None -- neither of which may be treated as 0.
# Both fallback paths (sheetFormatPr -> Excel factory default) do get exercised.

def get_col_width(ws, col_idx):
    d = ws.col_dims.get(col_idx)
    if d is not None and d.width is not None:
        return d.width
    if ws.default_col_width is not None:
        return ws.default_col_width
    return DEFAULT_COL_WIDTH_CHARS


def get_row_height(ws, row_idx):
    d = ws.row_dims.get(row_idx)
    if d is not None and d.height is not None:
        return d.height
    if ws.default_row_height is not None:
        return ws.default_row_height
    return DEFAULT_ROW_HEIGHT_POINTS


# ---------------------------------------------------------------- the grid

Rect = namedtuple('Rect', 'x_left y_top x_right y_bottom')


class SheetGrid(object):
    """
    Coordinate table for the visible rows and columns.

    Two index spaces are exposed:
      * Excel indices (row/col, 1-based, hidden rows and columns included)
      * visible indices (vr/vc, 0-based, hidden rows and columns removed)

    The rendering algorithms -- border run merging, fill scanline merging -- all
    work in visible index space and only convert to feet at the last step, which
    keeps the merging logic from having to care about unequal widths and heights.
    """

    __slots__ = ('rows', 'cols', 'row_pos', 'col_pos',
                 'x_edges', 'y_edges', 'col_widths_ft', 'row_heights_ft',
                 'orig_col_widths_ft', 'orig_row_heights_ft')

    def __init__(self, ws, min_row, max_row, min_col, max_col,
                 hidden_rows=None, hidden_cols=None):
        hidden_rows = hidden_rows or set()
        hidden_cols = hidden_cols or set()

        self.rows = [r for r in range(min_row, max_row + 1)
                     if r not in hidden_rows]
        self.cols = [c for c in range(min_col, max_col + 1)
                     if c not in hidden_cols]

        self.row_pos = dict((r, i) for i, r in enumerate(self.rows))
        self.col_pos = dict((c, i) for i, c in enumerate(self.cols))

        self.col_widths_ft = [col_width_to_feet(get_col_width(ws, c))
                              for c in self.cols]
        self.row_heights_ft = [row_height_to_feet(get_row_height(ws, r))
                               for r in self.rows]

        self.orig_col_widths_ft = list(self.col_widths_ft)
        self.orig_row_heights_ft = list(self.row_heights_ft)
        self.rebuild_edges()

    def rebuild_edges(self):
        """Must be called after any column width or row height changes."""
        # X is positive to the right
        self.x_edges = [0.0]
        for w in self.col_widths_ft:
            self.x_edges.append(self.x_edges[-1] + w)

        # Y is negative downwards
        self.y_edges = [0.0]
        for h in self.row_heights_ft:
            self.y_edges.append(self.y_edges[-1] - h)

    # -- dimensions -----------------------------------------------

    @property
    def n_rows(self):
        return len(self.rows)

    @property
    def n_cols(self):
        return len(self.cols)

    @property
    def total_width_ft(self):
        return self.x_edges[-1]

    @property
    def total_height_ft(self):
        return -self.y_edges[-1]

    # -- index conversion -----------------------------------------

    def visible_span(self, row, col, row_span=1, col_span=1):
        """
        Excel anchor + span -> closed range of visible indices
        (vr0, vc0, vr1, vc1). Hidden rows and columns inside the span are
        dropped; returns None when the whole area is invisible.
        """
        vrs = [self.row_pos[r] for r in range(row, row + row_span)
               if r in self.row_pos]
        vcs = [self.col_pos[c] for c in range(col, col + col_span)
               if c in self.col_pos]
        if not vrs or not vcs:
            return None
        return (min(vrs), min(vcs), max(vrs), max(vcs))

    # -- geometry -------------------------------------------------

    def rect_from_visible(self, vr0, vc0, vr1, vc1):
        return Rect(self.x_edges[vc0], self.y_edges[vr0],
                    self.x_edges[vc1 + 1], self.y_edges[vr1 + 1])

    def cell_rect(self, row, col, row_span=1, col_span=1):
        span = self.visible_span(row, col, row_span, col_span)
        if span is None:
            return None
        return self.rect_from_visible(*span)

    @classmethod
    def _clone(cls, rows, cols, col_widths, row_heights):
        obj = cls.__new__(cls)
        obj.rows = list(rows)
        obj.cols = list(cols)
        obj.row_pos = dict((r, i) for i, r in enumerate(obj.rows))
        obj.col_pos = dict((c, i) for i, c in enumerate(obj.cols))
        obj.col_widths_ft = list(col_widths)
        obj.row_heights_ft = list(row_heights)
        obj.orig_col_widths_ft = list(col_widths)
        obj.orig_row_heights_ft = list(row_heights)
        obj.rebuild_edges()
        return obj

    def column_subset(self, vc_list):
        """
        Take a subset of visible columns as a new grid (rows unchanged), used
        when splitting an over-wide table.
        -> (sub-grid, {original visible column index: new visible column index})
        """
        cols = [self.cols[i] for i in vc_list]
        widths = [self.col_widths_ft[i] for i in vc_list]
        sub = SheetGrid._clone(self.rows, cols, widths, self.row_heights_ft)
        return sub, dict((vc, i) for i, vc in enumerate(vc_list))

    def grow_cols(self, vc0, vc1, needed_ft, max_growth=None):
        """Grow the total width of columns vc0..vc1 to needed_ft, sharing the
        shortfall evenly between them. Returns True if anything grew."""
        cur = sum(self.col_widths_ft[vc0:vc1 + 1])
        if needed_ft <= cur + 1e-12:
            return False
        share = (needed_ft - cur) / (vc1 - vc0 + 1)
        for c in range(vc0, vc1 + 1):
            w = self.col_widths_ft[c] + share
            if max_growth:
                w = min(w, self.orig_col_widths_ft[c] * max_growth)
            self.col_widths_ft[c] = w
        return True

    def grow_rows(self, vr0, vr1, needed_ft, max_growth=None):
        cur = sum(self.row_heights_ft[vr0:vr1 + 1])
        if needed_ft <= cur + 1e-12:
            return False
        share = (needed_ft - cur) / (vr1 - vr0 + 1)
        for r in range(vr0, vr1 + 1):
            h = self.row_heights_ft[r] + share
            if max_growth:
                h = min(h, self.orig_row_heights_ft[r] * max_growth)
            self.row_heights_ft[r] = h
        return True

    def growth_report(self):
        """Which columns and rows were grown, for the report."""
        cols = [(self.cols[i], self.orig_col_widths_ft[i], self.col_widths_ft[i])
                for i in range(self.n_cols)
                if self.col_widths_ft[i] > self.orig_col_widths_ft[i] + 1e-9]
        rows = [(self.rows[i], self.orig_row_heights_ft[i], self.row_heights_ft[i])
                for i in range(self.n_rows)
                if self.row_heights_ft[i] > self.orig_row_heights_ft[i] + 1e-9]
        return cols, rows

    def x_at(self, vc_edge):
        return self.x_edges[vc_edge]

    def y_at(self, vr_edge):
        return self.y_edges[vr_edge]


# ---------------------------------------------------------------- text placement

def text_anchor(rect, h_align, v_align, n_lines, size_pt, font_name=None,
                padding_ft=TEXT_PADDING_FT, cap_ft=None):
    """
    Compute the TextNote insertion point (x, y) for the given alignment.

    Vertically the text is centred on the **block of capitals**: block height =
    (line count - 1) x line pitch + cap height. Once the cap top is known, the
    insertion-point-to-cap-top gap is added to get the y actually passed to
    TextNote.Create.

    cap_ft: the cap height in feet, given directly. When a project text type is
    reused, the effective size comes from that type rather than from Excel, and
    the centring has to be computed against the real one.
    """
    if h_align == 'center':
        x = (rect.x_left + rect.x_right) / 2.0
    elif h_align == 'right':
        x = rect.x_right - padding_ft
    else:
        x = rect.x_left + padding_ft

    if cap_ft is None:
        cap_ft = revit_text_size_feet(size_pt, font_name)
    pitch_ft = cap_ft * REVIT_LINE_PITCH_FACTOR
    n = max(1, int(n_lines))
    visual_h = (n - 1) * pitch_ft + cap_ft

    cell_h = rect.y_top - rect.y_bottom
    if v_align == 'center':
        cap_top = rect.y_top - (cell_h - visual_h) / 2.0
    elif v_align == 'bottom':
        cap_top = rect.y_bottom + visual_h
    else:
        cap_top = rect.y_top

    cap_ratio, asc_ratio = font_metrics(font_name)
    return x, cap_top + cap_ft * (asc_ratio / cap_ratio - 1.0)
