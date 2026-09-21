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
    """
    One drafting view's worth of drawing instructions.

    A table too tall for one sheet is cut into several parts, one Plan each;
    `part` / `part_count` say which this is. The whole table produces a single
    Plan with part 1 of 1.
    """

    __slots__ = ('fills', 'lines', 'texts', 'grid', 'warnings', 'blocks',
                 'part', 'part_count', 'width_ft', 'height_ft')

    def __init__(self, grid, warnings=None, part=1, part_count=1):
        self.grid = grid
        self.fills = []
        self.lines = []
        self.texts = []
        self.warnings = warnings if warnings is not None else []
        self.blocks = []        # [(block number, [Excel columns], [Excel rows],
                                #   width ft, height ft)]
        self.part = part
        self.part_count = part_count
        self.width_ft = 0.0     # what this part occupies on paper
        self.height_ft = 0.0

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

def build_plans(sheet, merge_borders=True, merge_fills=True,
                skip_white_fill=True, cap_height_ft=None):
    """
    sheet: xlreader.SheetData -> [Plan], one per part

    A table that fits on one sheet returns a single Plan. An over-wide one is
    split by column and the blocks stacked downwards; once that stack passes
    MAX_TABLE_HEIGHT_MM it is cut into parts, each of which becomes its own
    drafting view to be placed on its own sheet. Nothing is ever scaled.

    cap_height_ft: when a project text type is reused, pass its TEXT_SIZE in
    feet; vertical centring is then computed against the real size rather than
    the one written in Excel.
    """
    grid = sheet.grid

    placed = []            # (cell, vr0, vc0, vr1, vc1)
    for cell in sheet.cells:
        span = grid.visible_span(cell.row, cell.col, cell.row_span, cell.col_span)
        if span is None:
            continue
        placed.append((cell, span[0], span[1], span[2], span[3]))

    # Fit the table to its text first (grow columns, wrap, grow rows), then
    # draw. The order cannot be reversed: border and fill coordinates both
    # depend on the final row and column dimensions, and so does every split
    # decision below.
    wrapped = fit_to_text(grid, placed, cap_height_ft)

    warnings = sheet.warnings if sheet.warnings is not None else []

    # Split an over-wide table into column blocks stacked downwards -- the only
    # way to fit A3 without wrecking the layout -- and an over-tall block by
    # row, so that no single block is taller than one sheet on its own.
    col_chunks = split_columns(grid, placed, warnings)
    row_chunks = split_rows(grid, placed, warnings)

    # Reading order: a column block in full (all its row bands) before the next
    # column block starts.
    pieces = [(vr_list, vc_list)
              for vc_list in col_chunks for vr_list in row_chunks]

    gap = mm_to_feet(cfg.BLOCK_GAP_MM)
    pages = paginate(grid, pieces, gap)

    plans = []
    number = 0
    for index, page in enumerate(pages):
        plan = Plan(grid, warnings, index + 1, len(pages))
        y_off = 0.0
        for vr_list, vc_list in page:
            sub, row_map, col_map = _sub_grid(grid, vr_list, vc_list)
            sub_placed = remap_placed(placed, row_map, col_map)

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

            number += 1
            plan.blocks.append((number,
                                [grid.cols[i] for i in vc_list],
                                [grid.rows[i] for i in vr_list],
                                sub.total_width_ft, sub.total_height_ft))
            plan.width_ft = max(plan.width_ft, sub.total_width_ft)
            plan.height_ft += sub.total_height_ft + (gap if y_off else 0.0)
            y_off -= sub.total_height_ft + gap

        plans.append(plan)

    return plans


def _sub_grid(grid, vr_list, vc_list):
    """The grid for one block, with the old -> new index maps. The whole table
    is its own sub-grid, and cloning it would only cost time."""
    if (vr_list == list(range(grid.n_rows))
            and vc_list == list(range(grid.n_cols))):
        return (grid,
                dict((i, i) for i in range(grid.n_rows)),
                dict((i, i) for i in range(grid.n_cols)))
    return grid.subset(vr_list, vc_list)


def paginate(grid, pieces, gap_ft):
    """
    Group the stacked blocks into parts, each no taller than
    MAX_TABLE_HEIGHT_MM. -> [[(vr_list, vc_list), ...], ...]

    A block is never broken up here: split_rows has already made sure no single
    block is taller than one part on its own, so a part always holds at least
    one block even when that block is over the limit (a single row taller than
    the sheet cannot be helped).
    """
    max_mm = getattr(cfg, 'MAX_TABLE_HEIGHT_MM', None)
    max_ft = mm_to_feet(max_mm) if max_mm else 0.0
    if not max_ft:
        return [list(pieces)]

    pages = []
    current = []
    used = 0.0
    for piece in pieces:
        height = grid.height_of(piece[0])
        need = height if not current else height + gap_ft
        if current and used + need > max_ft + 1e-9:
            pages.append(current)
            current, used, need = [], 0.0, height
        current.append(piece)
        used += need
    if current:
        pages.append(current)
    return pages


# ---------------------------------------------------------------- splitting

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


def _split_axis(sizes, max_ft, crossing, repeat_n, is_redundant=None):
    """
    Cut one axis of the grid into chunks, each no longer than max_ft.
    -> [([indices...], cut_is_dirty), ...]

    sizes:      length of every index along the axis, in feet
    crossing:   boundaries crossed by a merged cell (boundary b sits between
                index b-1 and index b); a cut there halves that cell's text, so
                one is only made when nothing cleaner is available
    repeat_n:   repeat the first N indices (the headers) at the start of every
                later chunk
    is_redundant(a, b): optional test for "index b is already doing index a's
                job", used to drop a header repeat the sheet makes itself

    Both axes split the same way, which is why this is written once: columns
    against MAX_TABLE_WIDTH_MM, rows against MAX_TABLE_HEIGHT_MM.
    """
    n = len(sizes)
    if not max_ft or n == 0 or sum(sizes) <= max_ft:
        return [(list(range(n)), False)]

    repeat_n = max(0, min(int(repeat_n or 0), n - 1))

    chunks = []
    start = 0
    while start < n:
        prefix = [i for i in range(repeat_n) if i < start] if chunks else []
        # If this chunk already starts with indices identical to the header
        # ones, do not repeat them -- otherwise two identical headers end up
        # next to each other (measured: column V of Part1 is a second LOT RC.)
        if prefix and is_redundant:
            k = len(prefix)
            body = list(range(start, min(start + k, n)))
            if len(body) == k and all(is_redundant(prefix[i], body[i])
                                      for i in range(k)):
                prefix = []
        used = sum(sizes[i] for i in prefix)
        i = start
        last_fit = start
        best_clean = None
        while i < n:
            nxt = used + sizes[i]
            if nxt > max_ft and i > start:
                break
            used = nxt
            last_fit = i
            if (i + 1) not in crossing:
                best_clean = i
            i += 1
        end = best_clean if (best_clean is not None and best_clean >= start) else last_fit
        chunks.append((prefix + list(range(start, end + 1)),
                       (end + 1) in crossing))
        start = end + 1

    return chunks


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
    max_ft = mm_to_feet(max_mm) if max_mm else 0.0

    crossing = set()
    for cell, vr0, vc0, vr1, vc1 in placed:
        for b in range(vc0 + 1, vc1 + 1):
            crossing.add(b)

    repeat_n = getattr(cfg, 'REPEAT_LEADING_COLS', 0)
    signatures = _column_signatures(grid, placed) if repeat_n else {}

    def redundant(a, b):
        return _is_redundant(signatures.get(a), signatures.get(b))

    chunks = _split_axis(grid.col_widths_ft, max_ft, crossing, repeat_n,
                         redundant if repeat_n else None)

    out = []
    for vc_list, dirty in chunks:
        if dirty and warnings is not None:
            end = vc_list[-1]
            _warn(warnings,
                  'Table split between columns %d and %d cuts through a merged '
                  'cell - that cell is drawn in both blocks'
                  % (grid.cols[end], grid.cols[end + 1]))
        out.append(vc_list)
    return out


def split_rows(grid, placed, warnings=None):
    """
    Cut the visible rows into bands, each no taller than MAX_TABLE_HEIGHT_MM.
    -> [[visible row indices...], ...]; the whole table as one band when it
    already fits.

    This is what saves a plain long schedule: it is narrow enough never to be
    split by column, yet far too tall for one sheet. The first
    REPEAT_LEADING_ROWS rows -- the column headers -- are repeated at the top of
    every later band, so a part read on its own still says what its columns are.

    No redundancy test here, unlike the column side: a sheet repeating its own
    header rows partway down is not something these tables do.
    """
    max_mm = getattr(cfg, 'MAX_TABLE_HEIGHT_MM', None)
    max_ft = mm_to_feet(max_mm) if max_mm else 0.0

    crossing = set()
    for cell, vr0, vc0, vr1, vc1 in placed:
        for b in range(vr0 + 1, vr1 + 1):
            crossing.add(b)

    chunks = _split_axis(grid.row_heights_ft, max_ft, crossing,
                         getattr(cfg, 'REPEAT_LEADING_ROWS', 0))

    out = []
    for vr_list, dirty in chunks:
        if dirty and warnings is not None:
            end = vr_list[-1]
            _warn(warnings,
                  'Table split between rows %d and %d cuts through a merged '
                  'cell - that cell is drawn in both parts'
                  % (grid.rows[end], grid.rows[end + 1]))
        out.append(vr_list)
    return out


def _warn(warnings, msg):
    if msg not in warnings:
        warnings.append(msg)


def remap_placed(placed, row_map, col_map):
    """Remap the visible row and column indices in `placed` on to the sub-grid;
    cells lying entirely outside the block are dropped, and one straddling its
    edge is clipped to what the block shows."""
    out = []
    for cell, vr0, vc0, vr1, vc1 in placed:
        rows = [row_map[r] for r in range(vr0, vr1 + 1) if r in row_map]
        cols = [col_map[c] for c in range(vc0, vc1 + 1) if c in col_map]
        if not rows or not cols:
            continue
        out.append((cell, min(rows), min(cols), max(rows), max(cols)))
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
