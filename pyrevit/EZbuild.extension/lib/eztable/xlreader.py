# -*- coding: utf-8 -*-
"""
xlreader.py -- Excel worksheet -> list of CellModel

Section 3 of the spec. The essentials:
  * single-pass parse (xlsxlite hands back formula and cached value together,
    so openpyxl's two-pass data_only trick is unnecessary)
  * hidden rows and columns are skipped and take up no space (later rows shift up)
  * the render range comes from print_area when present, otherwise dimension
  * for merged cells only the anchor is kept; inner cells are discarded
  * error values render as blank and raise a warning

No Revit API and no third-party libraries; runs on IronPython 2.7 and CPython 3.x.
"""

from __future__ import division, unicode_literals

import hashlib
import os

from . import numfmt
from .compat import is_number, is_string
from .geometry import SheetGrid
from .theme import ThemePalette
from .xlsxlite import ERROR_VALUES, column_letter, load_workbook

# Excel border style -> normalised internal name (styles.py maps it on to a
# Revit LineStyle)
BORDER_STYLE_MAP = {
    'hair': 'hair',
    'thin': 'thin',
    'dotted': 'dashed',
    'dashed': 'dashed',
    'dashDot': 'dashed',
    'dashDotDot': 'dashed',
    'medium': 'medium',
    'mediumDashed': 'medium',
    'mediumDashDot': 'medium',
    'mediumDashDotDot': 'medium',
    'slantDashDot': 'medium',
    'thick': 'thick',
    'double': 'medium',          # drawn as medium for now, with a warning
}

BORDER_WEIGHT_RANK = {'hair': 1, 'dashed': 2, 'thin': 3, 'medium': 4, 'thick': 5}

DEFAULT_FONT_NAME = 'Arial'
DEFAULT_FONT_SIZE = 7.0


class CachedValuesMissing(Exception):
    """No formula cell carries a cached value -- the file was never opened and
    saved in Excel."""


class CellModel(object):
    __slots__ = ('row', 'col', 'row_span', 'col_span',
                 'value', 'text',
                 'fill_rgb',
                 'font_name', 'font_size', 'bold', 'italic', 'font_rgb',
                 'h_align', 'v_align', 'wrap',
                 'borders', 'is_error')

    def __init__(self, row, col):
        self.row = row
        self.col = col
        self.row_span = 1
        self.col_span = 1
        self.value = None
        self.text = ''
        self.fill_rgb = None
        self.font_name = DEFAULT_FONT_NAME
        self.font_size = DEFAULT_FONT_SIZE
        self.bold = False
        self.italic = False
        self.font_rgb = '000000'
        self.h_align = 'left'
        self.v_align = 'bottom'
        self.wrap = False
        self.borders = {'top': None, 'right': None, 'bottom': None, 'left': None}
        self.is_error = False

    @property
    def coord(self):
        return '%s%d' % (column_letter(self.col), self.row)

    def __repr__(self):
        return '<Cell %s %dx%d %r fill=%s>' % (
            self.coord, self.row_span, self.col_span, self.text, self.fill_rgb)


class SheetData(object):
    __slots__ = ('sheet_name', 'source_path', 'source_hash',
                 'grid', 'cells', 'warnings', 'infos', 'palette',
                 'min_row', 'max_row', 'min_col', 'max_col')

    def __init__(self):
        self.sheet_name = ''
        self.source_path = ''
        self.source_hash = ''
        self.grid = None
        self.cells = []
        self.warnings = []
        self.infos = []
        self.palette = None
        self.min_row = self.max_row = self.min_col = self.max_col = 0

    def warn(self, msg):
        """A real problem, worth putting in front of someone."""
        if msg not in self.warnings:
            self.warnings.append(msg)

    def info(self, msg):
        """Just describes what happened; not worth opening a window for
        (skipped hidden rows, range taken from print_area, and the like)."""
        if msg not in self.infos:
            self.infos.append(msg)


# ---------------------------------------------------------------- entry point

def read_sheet(path, sheet_name=None, trim_empty_trailing=True):
    """Parse one worksheet and return a SheetData."""
    data = SheetData()
    data.source_path = os.path.abspath(path)
    data.source_hash = file_hash(path)

    wb = load_workbook(path)
    try:
        if sheet_name is None:
            sheet_name = wb.sheetnames[0]
        ws = wb.worksheet(sheet_name)
        data.sheet_name = sheet_name
        data.palette = ThemePalette.from_workbook(wb, xlsx_path=path,
                                                  warnings=data.warnings)

        hidden_rows = ws.hidden_rows()
        hidden_cols = ws.hidden_cols()
        min_row, min_col, max_row, max_col = resolve_range(ws, data)

        if trim_empty_trailing:
            max_row, max_col = trim_range(ws, min_row, max_row, min_col, max_col,
                                          hidden_rows, hidden_cols)

        data.min_row, data.max_row = min_row, max_row
        data.min_col, data.max_col = min_col, max_col

        merged_anchor, merged_inner = collect_merges(ws)

        data.grid = SheetGrid(ws, min_row, max_row, min_col, max_col,
                              hidden_rows, hidden_cols)
        if data.grid.n_rows == 0 or data.grid.n_cols == 0:
            raise ValueError('No visible rows or columns inside the render range')

        shown_hidden_rows = [r for r in sorted(hidden_rows)
                             if min_row <= r <= max_row]
        shown_hidden_cols = [c for c in sorted(hidden_cols)
                             if min_col <= c <= max_col]
        if shown_hidden_rows:
            data.info('Skipped hidden rows: %s'
                      % ', '.join(str(r) for r in shown_hidden_rows))
        if shown_hidden_cols:
            data.info('Skipped hidden columns: %s'
                      % ', '.join(column_letter(c) for c in shown_hidden_cols))

        stale_formulas = []

        for row in range(min_row, max_row + 1):
            if row in hidden_rows:
                continue
            for col in range(min_col, max_col + 1):
                if col in hidden_cols:
                    continue
                if (row, col) in merged_inner:
                    continue

                cell = ws.cell(row, col)
                if cell.formula and not cell.has_cached:
                    stale_formulas.append(cell.coordinate)

                model = build_cell(cell, data)
                span = merged_anchor.get((row, col))
                if span:
                    model.row_span, model.col_span = span
                data.cells.append(model)

        if stale_formulas and not any(c.text for c in data.cells):
            raise CachedValuesMissing(
                'Worksheet %r has formulas but no cached values (e.g. %s). '
                'Open the file in Excel, save it once, then import again.'
                % (sheet_name, ', '.join(stale_formulas[:5])))
        if stale_formulas:
            data.warn('%d formula cells have no cached value and were left blank (e.g. %s)'
                      % (len(stale_formulas), ', '.join(stale_formulas[:5])))
    finally:
        wb.close()

    return data


# ---------------------------------------------------------------- the steps

def file_hash(path, chunk=1 << 20):
    h = hashlib.md5()
    fh = open(path, 'rb')
    try:
        while True:
            block = fh.read(chunk)
            if not block:
                break
            h.update(block)
    finally:
        fh.close()
    return h.hexdigest()


def resolve_range(ws, data):
    """print_area when present, otherwise fall back to dimension."""
    if ws.print_area:
        min_row = min(a[0] for a in ws.print_area)
        min_col = min(a[1] for a in ws.print_area)
        max_row = max(a[2] for a in ws.print_area)
        max_col = max(a[3] for a in ws.print_area)
        data.info('Range taken from print_area: %s'
                  % ', '.join('%s%d:%s%d' % (column_letter(a[1]), a[0],
                                             column_letter(a[3]), a[2])
                              for a in ws.print_area))
        return min_row, min_col, max_row, max_col

    r0, c0, r1, c1 = ws.used_range()
    return r0, c0, r1, c1


def trim_range(ws, min_row, max_row, min_col, max_col, hidden_rows, hidden_cols):
    """
    Trim trailing rows and columns that are entirely blank -- no value, no fill,
    no border. max_row is routinely inflated by leftover history, and without
    trimming that turns into a block of empty cells on the drawing.
    """
    def row_has_content(r):
        for c in range(min_col, max_col + 1):
            if c in hidden_cols:
                continue
            if _has_content(ws.cells.get((r, c))):
                return True
        return False

    def col_has_content(c):
        for r in range(min_row, max_row + 1):
            if r in hidden_rows:
                continue
            if _has_content(ws.cells.get((r, c))):
                return True
        return False

    while max_row > min_row and not row_has_content(max_row):
        max_row -= 1
    while max_col > min_col and not col_has_content(max_col):
        max_col -= 1
    return max_row, max_col


def _has_content(cell):
    if cell is None:
        return False
    if cell.value is not None or cell.formula:
        return True
    fill = cell.style.fill
    if fill is not None and fill.patternType not in (None, 'none'):
        return True
    border = cell.style.border
    if border is not None:
        for side in (border.top, border.right, border.bottom, border.left):
            if side is not None and side.style:
                return True
    return False


def collect_merges(ws):
    merged_anchor = {}
    merged_inner = set()
    for min_row, min_col, max_row, max_col in ws.merged_ranges:
        merged_anchor[(min_row, min_col)] = (max_row - min_row + 1,
                                             max_col - min_col + 1)
        for r in range(min_row, max_row + 1):
            for c in range(min_col, max_col + 1):
                if (r, c) != (min_row, min_col):
                    merged_inner.add((r, c))
    return merged_anchor, merged_inner


def build_cell(cell, data):
    m = CellModel(cell.row, cell.column)
    style = cell.style
    value = cell.value

    if is_string(value) and value.strip() in ERROR_VALUES:
        m.is_error = True
        data.warn('Error value %s at %s - rendered as blank' % (value.strip(), m.coord))
        value = None

    m.value = value
    text, fmt_color = numfmt.render(value, style.number_format, data.warnings)
    m.text = text

    # -- fill --
    m.fill_rgb = _read_fill(style.fill, m.coord, data)

    # -- font --
    font = style.font
    if font is not None:
        m.font_name = font.name or DEFAULT_FONT_NAME
        m.font_size = float(font.sz) if font.sz else DEFAULT_FONT_SIZE
        m.bold = bool(font.b)
        m.italic = bool(font.i)
        m.font_rgb = data.palette.resolve(font.color, default='000000')
    if fmt_color:
        m.font_rgb = fmt_color

    # -- alignment --
    al = style.alignment
    h = al.horizontal if al is not None else None
    v = al.vertical if al is not None else None
    if h in (None, 'general'):
        # Excel's implicit rule: numbers right-aligned, text left-aligned
        h = 'right' if is_number(value) else 'left'
    if h == 'centerContinuous':
        h = 'center'
    elif h in ('distributed', 'justify', 'fill'):
        h = 'left'
    m.h_align = h
    m.v_align = v if v in ('top', 'center', 'bottom') else 'bottom'
    m.wrap = bool(al.wrapText) if al is not None else False

    if al is not None and al.textRotation:
        data.warn('Cell %s has text rotation %s deg - not supported, rendered horizontally'
                  % (m.coord, al.textRotation))

    # -- borders --
    border = style.border
    if border is not None:
        for name in ('top', 'right', 'bottom', 'left'):
            m.borders[name] = _read_side(getattr(border, name), m.coord, name, data)

    return m


def _read_fill(fill, coord, data):
    if fill is None:
        return None
    pattern = fill.patternType
    if pattern in (None, 'none'):
        return None
    if pattern != 'solid':
        data.warn('Cell %s uses a non-solid pattern fill %r - approximated with its foreground colour'
                  % (coord, pattern))
    rgb = data.palette.resolve(fill.fgColor, default=None)
    if rgb is None:
        rgb = data.palette.resolve(fill.bgColor, default=None)
    return rgb


def _read_side(side, coord, name, data):
    if side is None or not side.style:
        return None
    style = side.style
    if style == 'double':
        data.warn('Cell %s has a double border on the %s side - drawn as medium'
                  % (coord, name))
    mapped = BORDER_STYLE_MAP.get(style)
    if mapped is None:
        data.warn('Unknown border style %r at %s - fell back to thin' % (style, coord))
        mapped = 'thin'
    rgb = data.palette.resolve(getattr(side, 'color', None), default='000000')
    return (mapped, rgb or '000000')
