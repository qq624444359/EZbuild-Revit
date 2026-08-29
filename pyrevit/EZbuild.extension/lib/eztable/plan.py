# -*- coding: utf-8 -*-
"""
plan.py -- list of CellModel -> Revit-free drawing instructions

This layer deliberately does not import the Revit API, so the error-prone
algorithms -- border de-duplication and run merging, fill scanline merging --
can be exercised under plain CPython. renderer.py does nothing but turn the
instructions produced here into elements.

Three key algorithms:
  1. Borders are registered on the *edges of the visible grid*. Each grid edge
     has exactly one slot, so an edge shared by two neighbouring cells is
     naturally only written once and de-duplication needs no extra coordinate
     set. Edges inside a merged cell are skipped automatically, because the
     inner cells never take part in registration at all.
  2. Border run merging -- consecutive segments of the same style along one
     boundary line become a single line.
  3. Fill scanline merging -- first merge horizontally into strips, then merge
     strips of equal colour and width vertically into blocks.
"""

from __future__ import division

from collections import namedtuple

from . import config as cfg
from . import metrics
from .geometry import (REVIT_LINE_PITCH_FACTOR, TEXT_PADDING_FT, Rect,
                       font_metrics, mm_to_feet, revit_text_size_feet,
                       text_anchor)
from .xlreader import BORDER_WEIGHT_RANK

FillItem = namedtuple('FillItem', 'rect rgb')
LineItem = namedtuple('LineItem', 'p1 p2 style rgb')
TextItem = namedtuple(
    'TextItem',
    'x y text font_name font_size bold italic rgb h_align n_lines '
    'coord width_ft avail_ft')


class Plan(object):
    __slots__ = ('fills', 'lines', 'texts', 'grid', 'warnings', 'blocks')

    def __init__(self, grid, warnings=None):
        self.grid = grid
        self.fills = []
        self.lines = []
        self.texts = []
        self.warnings = warnings if warnings is not None else []
        self.blocks = []        # [(block number, [Excel column numbers...], width ft, height ft)]

    @property
    def element_count(self):
        return len(self.fills) + len(self.lines) + len(self.texts)

    @property
    def overflows(self):
        """
        Text that does not fit its cell. Horizontal overflow is something the
        centring maths cannot rescue, so all that can be done is report it and
        let someone decide whether to shrink the font, widen the column, or
        leave it running up to the border.
        """
        return [t for t in self.texts
                if t.avail_ft > 0 and t.width_ft > t.avail_ft + 1e-9]

    def summary(self):
        return ('%d fills, %d lines, %d texts - %d total'
                % (len(self.fills), len(self.lines), len(self.texts),
                   self.element_count))


# ---------------------------------------------------------------- entry point

def build_plan(sheet, merge_borders=True, merge_fills=True,
               skip_white_fill=True, cap_height_ft=None):
    """
    sheet: xlreader.SheetData -> Plan

    cap_height_ft: when a project text type is reused, pass its TEXT_SIZE in
    feet; vertical centring is then computed against the real size rather than
    the one written in Excel.
    """
    grid = sheet.grid
    plan = Plan(grid, sheet.warnings)

    placed = []            # (cell, vr0, vc0, vr1, vc1)
    for cell in sheet.cells:
        span = grid.visible_span(cell.row, cell.col, cell.row_span, cell.col_span)
        if span is None:
            continue
        placed.append((cell, span[0], span[1], span[2], span[3]))

    # Fit the table to its text first (grow columns, wrap, grow rows), then
    # draw. The order cannot be reversed: border and fill coordinates both
    # depend on the final row and column dimensions.
    wrapped = fit_to_text(grid, placed, cap_height_ft)

    # Split an over-wide table into column blocks stacked downwards -- the only
    # way to fit A3 without wrecking the layout
    chunks = split_columns(grid, placed, plan.warnings)
    gap = mm_to_feet(cfg.BLOCK_GAP_MM)
    y_off = 0.0

    for index, vc_list in enumerate(chunks):
        if len(chunks) == 1:
            sub, mapping = grid, dict((i, i) for i in range(grid.n_cols))
        else:
            sub, mapping = grid.column_subset(vc_list)
        sub_placed = remap_placed(placed, mapping)

        fills = build_fills(sub, sub_placed, merge_fills, skip_white_fill)
        lines = build_borders(sub, sub_placed, merge_borders)
        texts = build_texts(sub, sub_placed, cap_height_ft, wrapped)

        if y_off:
            fills = [f._replace(rect=_shift_rect(f.rect, y_off)) for f in fills]
            lines = [l._replace(p1=(l.p1[0], l.p1[1] + y_off),
                                p2=(l.p2[0], l.p2[1] + y_off)) for l in lines]
            texts = [t._replace(y=t.y + y_off) for t in texts]

        plan.fills.extend(fills)
        plan.lines.extend(lines)
        plan.texts.extend(texts)
        plan.blocks.append((index + 1, [grid.cols[i] for i in vc_list],
                            sub.total_width_ft, sub.total_height_ft))
        y_off -= sub.total_height_ft + gap

    return plan


# ---------------------------------------------------------------- splitting wide tables

def _shift_rect(rect, dy):
    return Rect(rect.x_left, rect.y_top + dy, rect.x_right, rect.y_bottom + dy)


def _column_signatures(grid, placed):
    """The content of each visible column (text of its single-column cells, by row)."""
    per_col = {}
    for cell, vr0, vc0, vr1, vc1 in placed:
        if vc0 != vc1:
            continue                    # cells spanning columns take no part in the comparison
        slot = per_col.setdefault(vc0, {})
        text = (cell.text or '').strip()
        for vr in range(vr0, vr1 + 1):
            slot[vr] = text
    out = {}
    for vc in range(grid.n_cols):
        slot = per_col.get(vc, {})
        out[vc] = tuple(slot.get(vr, '') for vr in range(grid.n_rows))
    return out


def _is_redundant(sig_a, sig_b):
    """
    Is column b already doing column a's job? If so there is no point repeating
    a as well.

    The test: the two columns must **not conflict** (no row where both have a
    value and the values differ) and must **overlap** (at least one row where
    both have a value and they match).

    Requiring an exact match is too strict. Measured on Part1, column V is a
    second copy of LOT RC. but only fills in LOT1~LOT3 and Pre-Construction,
    leaving the other rows blank. An exact-match test would miss it, and the
    result would be two LOT RC. headers side by side.
    """
    if not sig_a or not sig_b:
        return False
    overlap = False
    for x, y in zip(sig_a, sig_b):
        if x and y:
            if x != y:
                return False
            overlap = True
    return overlap


def split_columns(grid, placed, warnings=None):
    """
    Cut the visible columns into blocks, each no wider than MAX_TABLE_WIDTH_MM.
    -> [[visible column indices...], ...]; returns the whole table as one block
    when no splitting is needed.

    Cut points prefer column boundaries **not crossed by a merged cell** --
    splitting through the middle of a merged region cuts that cell's text in
    half. Only when no clean cut point exists is one forced, with a warning.
    """
    max_mm = getattr(cfg, 'MAX_TABLE_WIDTH_MM', None)
    n = grid.n_cols
    if not max_mm or n == 0:
        return [list(range(n))]
    max_ft = mm_to_feet(max_mm)
    if grid.total_width_ft <= max_ft:
        return [list(range(n))]

    repeat_n = max(0, min(int(getattr(cfg, 'REPEAT_LEADING_COLS', 0) or 0), n - 1))

    # Column boundaries crossed by a merged cell (boundary b sits between
    # column b-1 and column b)
    crossing = set()
    for cell, vr0, vc0, vr1, vc1 in placed:
        for b in range(vc0 + 1, vc1 + 1):
            crossing.add(b)

    signatures = _column_signatures(grid, placed) if repeat_n else {}

    chunks = []
    start = 0
    while start < n:
        prefix = [c for c in range(repeat_n) if c < start] if chunks else []
        # If this block already starts with columns identical to the row-header
        # columns, do not repeat them -- otherwise two identical headers end up
        # side by side (measured: column V of Part1 is a second LOT RC.)
        if prefix:
            k = len(prefix)
            body = list(range(start, min(start + k, n)))
            if len(body) == k and all(_is_redundant(signatures.get(prefix[i]),
                                                     signatures.get(body[i]))
                                      for i in range(k)):
                prefix = []
        width = sum(grid.col_widths_ft[c] for c in prefix)
        c = start
        last_fit = start
        best_clean = None
        while c < n:
            nxt = width + grid.col_widths_ft[c]
            if nxt > max_ft and c > start:
                break
            width = nxt
            last_fit = c
            if (c + 1) not in crossing:
                best_clean = c
            c += 1
        end = best_clean if (best_clean is not None and best_clean >= start) else last_fit
        if (end + 1) in crossing and warnings is not None:
            msg = ('Table split between columns %d and %d cuts through a merged '
                   'cell - that cell is drawn in both blocks'
                   % (grid.cols[end], grid.cols[end + 1]))
            if msg not in warnings:
                warnings.append(msg)
        chunks.append(prefix + list(range(start, end + 1)))
        start = end + 1

    return chunks


def remap_placed(placed, mapping):
    """Remap the visible column indices in `placed` on to the sub-grid; cells
    lying entirely outside the block are dropped."""
    out = []
    for cell, vr0, vc0, vr1, vc1 in placed:
        inside = [mapping[c] for c in range(vc0, vc1 + 1) if c in mapping]
        if not inside:
            continue
        out.append((cell, vr0, min(inside), vr1, max(inside)))
    return out


def cap_height_for(cell, cap_height_ft):
    """
    The cap height to draw this cell's text at, in feet.

    cap_height_ft is the base text type's size, or None when there is no base
    type. With a base type in play the size is scaled by the cell's Excel font
    size relative to cfg.BASE_TEXT_SIZE_PT, so one sheet set in 9pt keeps the
    same text-to-cell ratio as another set in 7pt. Without the scaling every
    sheet is forced to one size and the taller-celled sheets read as sparse.
    """
    if cap_height_ft is None:
        return revit_text_size_feet(cell.font_size, cell.font_name)
    return cap_height_ft * cfg.text_scale(cell.font_size)


# ---------------------------------------------------------------- fit to text

def _cell_text(cell):
    t = cell.text
    if not t:
        return ''
    return t.replace('\r\n', '\n').replace('\r', '\n')


def fit_to_text(grid, placed, cap_height_ft=None):
    """
    Fit the table to its text rather than making the text put up with the
    table. Three steps:

      1. Grow columns -- a non-wrapping cell that does not fit widens the
         columns it occupies (a spanning cell shares out the shortfall)
      2. Wrap        -- cells with wrapText set in Excel are wrapped against
                        the final column width
      3. Grow rows   -- rows too short for the wrapped result are grown

    Returns {(row, col): wrapped text}; cells that were never wrapped do not
    appear. The grid's column widths and row heights are modified in place, so
    the caller receives the final dimensions.
    """
    wrapped = {}
    if not placed:
        return wrapped

    pad_h = mm_to_feet(cfg.CELL_PADDING_H_MM)
    pad_v = mm_to_feet(cfg.CELL_PADDING_V_MM)

    def em_of(cell):
        cap = cap_height_for(cell, cap_height_ft)
        return cap, cap / font_metrics(cell.font_name)[0]

    # -- 1. column widths ---------------------------------------
    if cfg.FIT_COLUMNS:
        # Single-column cells first, then spanning ones, and run the spanning
        # pass twice -- once single columns grow, the spanning shortfall shrinks
        singles = [p for p in placed if p[2] == p[4]]
        spans = [p for p in placed if p[2] != p[4]]
        for group in (singles, spans, spans):
            for cell, vr0, vc0, vr1, vc1 in group:
                text = _cell_text(cell)
                if not text.strip():
                    continue
                _cap, em = em_of(cell)
                if cfg.WRAP_TEXT and cell.wrap:
                    # For a wrapping cell, only guarantee the longest word fits
                    need_em = metrics.longest_word_em(text, cell.bold)
                else:
                    need_em = metrics.string_width_em(
                        metrics.widest_line(text), cell.bold)
                grid.grow_cols(vc0, vc1, need_em * em + 2 * pad_h,
                               cfg.MAX_COL_GROWTH)
        grid.rebuild_edges()

    # -- 2. wrapping --------------------------------------------
    if cfg.WRAP_TEXT:
        for cell, vr0, vc0, vr1, vc1 in placed:
            if not cell.wrap:
                continue
            text = _cell_text(cell)
            if not text.strip():
                continue
            _cap, em = em_of(cell)
            avail = grid.x_at(vc1 + 1) - grid.x_at(vc0) - 2 * pad_h
            if avail <= 0:
                continue
            lines = metrics.wrap_text(text, avail / em, cell.bold)
            if len(lines) > 1 or '\n' in text:
                wrapped[(cell.row, cell.col)] = '\n'.join(lines)

    # -- 3. row heights -----------------------------------------
    if cfg.FIT_ROWS:
        singles = [p for p in placed if p[1] == p[3]]
        spans = [p for p in placed if p[1] != p[3]]
        for group in (singles, spans):
            for cell, vr0, vc0, vr1, vc1 in group:
                text = wrapped.get((cell.row, cell.col), _cell_text(cell))
                if not text.strip():
                    continue
                cap, _em = em_of(cell)
                n = text.count('\n') + 1
                need = (n - 1) * cap * REVIT_LINE_PITCH_FACTOR + cap + 2 * pad_v
                grid.grow_rows(vr0, vr1, need, cfg.MAX_ROW_GROWTH)
        grid.rebuild_edges()

    return wrapped


# ---------------------------------------------------------------- fills

def build_fills(grid, placed, merge=True, skip_white=True):
    R, C = grid.n_rows, grid.n_cols
    colors = [[None] * C for _ in range(R)]

    for cell, vr0, vc0, vr1, vc1 in placed:
        rgb = cell.fill_rgb
        if rgb is None:
            continue
        if skip_white and rgb.upper() == 'FFFFFF':
            continue                       # the sheet background is white anyway
        for r in range(vr0, vr1 + 1):
            for c in range(vc0, vc1 + 1):
                colors[r][c] = rgb

    if not merge:
        out = []
        for r in range(R):
            for c in range(C):
                if colors[r][c]:
                    out.append(FillItem(grid.rect_from_visible(r, c, r, c),
                                        colors[r][c]))
        return out

    used = [[False] * C for _ in range(R)]
    out = []
    for r in range(R):
        for c in range(C):
            rgb = colors[r][c]
            if rgb is None or used[r][c]:
                continue
            # merge horizontally into strips
            c1 = c
            while c1 + 1 < C and colors[r][c1 + 1] == rgb and not used[r][c1 + 1]:
                c1 += 1
            # merge strips into blocks: only continue while the whole strip is
            # the same colour and still unclaimed
            r1 = r
            while r1 + 1 < R and all(colors[r1 + 1][cc] == rgb and not used[r1 + 1][cc]
                                     for cc in range(c, c1 + 1)):
                r1 += 1
            for rr in range(r, r1 + 1):
                for cc in range(c, c1 + 1):
                    used[rr][cc] = True
            out.append(FillItem(grid.rect_from_visible(r, c, r1, c1), rgb))
    return out


# ---------------------------------------------------------------- borders

def build_borders(grid, placed, merge=True):
    R, C = grid.n_rows, grid.n_cols
    h_edges = {}       # (vr_edge 0..R, vc 0..C-1) -> (style, rgb)
    v_edges = {}       # (vc_edge 0..C, vr 0..R-1) -> (style, rgb)

    for cell, vr0, vc0, vr1, vc1 in placed:
        top = cell.borders.get('top')
        bottom = cell.borders.get('bottom')
        left = cell.borders.get('left')
        right = cell.borders.get('right')
        if top:
            for c in range(vc0, vc1 + 1):
                _stronger(h_edges, (vr0, c), top)
        if bottom:
            for c in range(vc0, vc1 + 1):
                _stronger(h_edges, (vr1 + 1, c), bottom)
        if left:
            for r in range(vr0, vr1 + 1):
                _stronger(v_edges, (vc0, r), left)
        if right:
            for r in range(vr0, vr1 + 1):
                _stronger(v_edges, (vc1 + 1, r), right)

    lines = []

    # horizontal lines: merge along X
    for edge in range(R + 1):
        runs = _runs([(c, h_edges.get((edge, c))) for c in range(C)], merge)
        y = grid.y_at(edge)
        for c0, c1, spec in runs:
            lines.append(LineItem((grid.x_at(c0), y),
                                  (grid.x_at(c1 + 1), y),
                                  spec[0], spec[1]))

    # vertical lines: merge along Y
    for edge in range(C + 1):
        runs = _runs([(r, v_edges.get((edge, r))) for r in range(R)], merge)
        x = grid.x_at(edge)
        for r0, r1, spec in runs:
            lines.append(LineItem((x, grid.y_at(r0)),
                                  (x, grid.y_at(r1 + 1)),
                                  spec[0], spec[1]))

    return lines


def _stronger(store, key, spec):
    """When both cells either side define the same grid edge, keep the heavier one."""
    cur = store.get(key)
    if cur is None:
        store[key] = spec
        return
    if BORDER_WEIGHT_RANK.get(spec[0], 0) > BORDER_WEIGHT_RANK.get(cur[0], 0):
        store[key] = spec


def _runs(slots, merge):
    """[(idx, spec_or_None)] -> [(idx0, idx1, spec)]; no merging when merge=False."""
    out = []
    start = None
    cur = None
    for idx, spec in slots:
        if spec is None:
            if start is not None:
                out.append((start, idx - 1, cur))
                start, cur = None, None
            continue
        if not merge:
            out.append((idx, idx, spec))
            continue
        if start is None:
            start, cur = idx, spec
        elif spec != cur:
            out.append((start, idx - 1, cur))
            start, cur = idx, spec
    if start is not None:
        out.append((start, slots[-1][0], cur))
    return out


# ---------------------------------------------------------------- text

def build_texts(grid, placed, cap_height_ft=None, wrapped=None):
    wrapped = wrapped or {}
    out = []
    for cell, vr0, vc0, vr1, vc1 in placed:
        text = wrapped.get((cell.row, cell.col))
        if text is None:
            text = _cell_text(cell)
        if not text.strip():
            continue                       # an empty string makes TextNote.Create throw
        rect = grid.rect_from_visible(vr0, vc0, vr1, vc1)
        n_lines = text.count('\n') + 1
        cap_ft = cap_height_for(cell, cap_height_ft)
        x, y = text_anchor(rect, cell.h_align, cell.v_align, n_lines,
                           cell.font_size, cell.font_name, cap_ft=cap_ft)

        # Horizontal extent: convert the cap height back to an em size, then
        # look up the character width table
        em_ft = cap_ft / font_metrics(cell.font_name)[0]
        width_ft = metrics.text_width_feet(metrics.widest_line(text), em_ft,
                                           cell.bold, cell.italic)
        # Available width is the whole cell, with no padding deducted: text
        # touching the border line is acceptable, and what actually needs
        # reporting is text spilling into the neighbouring cell.
        avail_ft = rect.x_right - rect.x_left

        out.append(TextItem(x, y, text, cell.font_name, cell.font_size,
                            cell.bold, cell.italic, cell.font_rgb,
                            cell.h_align, n_lines,
                            cell.coord, width_ft, avail_ft))
    return out
