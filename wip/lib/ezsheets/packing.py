# -*- coding: utf-8 -*-
"""Grid packing for detail sheets.

Pure geometry - no Revit API - so it can be unit-tested outside Revit.
Everything is millimetres in paper coordinates, origin bottom-left.

The layout model came out of measuring 11 hand-laid-out sheets:

- Columns use a fixed pitch. Horizontal gaps between adjacent details measured
  31.4 / 35.1 / 41.7 / 42.0 / 42.0 / 43.9 mm, four of six landing on 42.
- Rows do NOT. Vertical gaps measured 3.0 / 12.4 / 15.5 / 27.8 / 29.4 / 45.4 mm
  with no repeated value, because details differ in height and the designer
  spreads whatever is left. So the packer distributes the vertical slack rather
  than targeting a number.
- Every viewport outline equals its printed extent plus the title bar plus
  6.096 mm, so outlines can be packed directly with no correction.
"""

from __future__ import unicode_literals

from ezsheets import config


class Placement(object):
    """Where one viewport should end up."""

    def __init__(self, key, x0, y0, w, h, col, row):
        self.key = key
        self.x0 = x0
        self.y0 = y0
        self.w = w
        self.h = h
        self.col = col
        self.row = row

    @property
    def center(self):
        return (self.x0 + self.w / 2.0, self.y0 + self.h / 2.0)

    @property
    def x1(self):
        return self.x0 + self.w

    @property
    def y1(self):
        return self.y0 + self.h

    def __repr__(self):
        return "<{0} at ({1:.1f},{2:.1f}) {3:.1f}x{4:.1f} c{5}r{6}>".format(
            self.key, self.x0, self.y0, self.w, self.h, self.col, self.row)


class PackResult(object):
    def __init__(self, placements, overflow, columns, region, gap_x=None,
                 reason=""):
        self.placements = placements
        self.overflow = overflow          # keys that did not fit
        self.columns = columns            # count actually used
        self.region = region
        self.gap_x = gap_x                # horizontal gap actually used
        self.reason = reason              # why it did not fit, when it did not

    @property
    def ok(self):
        return not self.overflow


def _split_into_columns(items, n_cols, max_rows):
    """Chunk items into n_cols columns, in reading order, top to bottom.

    Column-major, because that is what the measured sheets do: on A522 the two
    left-hand details read top then bottom before the eye moves right.
    """
    n = len(items)
    per_col = -(-n // n_cols)          # ceil
    if max_rows:
        per_col = min(per_col, max_rows) or 1
    columns = []
    i = 0
    while i < n and len(columns) < n_cols:
        columns.append(list(items[i:i + per_col]))
        i += per_col
    if i < n:                          # leftovers past the last column
        columns[-1].extend(items[i:])
    return columns


def _layout_fits(columns, region, gap_x, gap_y_min):
    """Can this column split sit inside the region at this horizontal gap?"""
    x0, y0, x1, y1 = region
    widths = [max(w for _, w, _ in col) for col in columns]
    need_w = sum(widths) + gap_x * (len(columns) - 1)
    if need_w > (x1 - x0) + 0.1:
        return False
    for col in columns:
        need_h = sum(h for _, _, h in col) + gap_y_min * (len(col) - 1)
        if need_h > (y1 - y0) + 0.1:
            return False
    return True


def plan_columns(items, region, max_cols, max_rows, gap_x, gap_x_min, gap_y_min):
    """Choose a column count and horizontal gap that actually fit.

    Tries the most columns first, and only compresses the gap below the
    preferred value when the preferred value will not fit. That mirrors the
    measured behaviour: 42 mm is the habit, but A523 went to 35.0 and A522 to
    31.4 to make two columns work.

    An earlier version sized every column by the widest item on the sheet and
    concluded A523 could only take one column, overflowing all four details.
    Real columns have different widths - 137.3 and 160.2 on that sheet - so the
    test has to be run against the actual split.

    Returns (columns, gap_x_used, reason). On failure columns is None and
    reason says what would have made it fit, so the caller can tell the user
    something actionable instead of just "does not fit".
    """
    x0, y0, x1, y1 = region
    notes = []

    # max_rows is a soft preference, not a rule. Two rows is what the measured
    # sheets happen to use, but nothing says a third is forbidden - so try the
    # preferred cap first and only fall back to an unlimited column height if
    # nothing fits. Treating it as hard turned a large share of a 25-sheet batch
    # into false failures.
    for rows_cap in (max_rows, None):
        for n in range(min(max_cols, len(items)), 0, -1):
            columns = _split_into_columns(items, n, rows_cap)
            if len(columns) != n:
                continue
            for gap in (gap_x, gap_x_min):
                if _layout_fits(columns, region, gap, gap_y_min):
                    return columns, gap, ""

            if rows_cap is not None:
                continue      # only report reasons from the unconstrained pass

            widths = [max(w for _, w, _ in col) for col in columns]
            if n > 1:
                needed = ((x1 - x0) - sum(widths)) / float(n - 1)
                if needed < gap_x_min:
                    notes.append("{0} columns would need the gap down to "
                                 "{1:.1f} mm (floor is {2:.1f})"
                                 .format(n, needed, gap_x_min))
                    continue
            elif sum(widths) > (x1 - x0):
                # a single view wider than the whole usable area. Without this
                # branch the loop fell through with nothing recorded and the
                # caller reported a useless "no column count fits".
                notes.append("the widest view is {0:.1f} mm wider than the "
                             "usable area - it does not fit the sheet at this "
                             "scale".format(sum(widths) - (x1 - x0)))
                continue
            tallest = max(sum(h for _, _, h in col) + gap_y_min * (len(col) - 1)
                          for col in columns)
            if tallest > (y1 - y0):
                notes.append("{0} column(s) are {1:.1f} mm too tall"
                             .format(n, tallest - (y1 - y0)))
        if max_rows is None:
            break

    reason = "; ".join(notes) if notes else "no column count fits"
    return None, None, reason


def pack_grid(items, region=None, gap_x=None, gap_x_min=None,
              max_cols=None, max_rows=None, distribute=True):
    """Pack viewport outlines into a column grid.

    items   -- [(key, width_mm, height_mm), ...] in the order they should read.
    region  -- (x0, y0, x1, y1); defaults to the usable area from config.
    returns -- PackResult

    Columns are filled top to bottom in the given order. Within a column the
    leftover vertical space is shared evenly when `distribute` is set, because
    the measured vertical gaps showed no convention to aim at.
    """
    if region is None:
        region = (config.CONTENT_X0, config.CONTENT_Y0,
                  config.CONTENT_X1, config.CONTENT_Y1)
    if not items:
        return PackResult([], [], 0, region)

    if gap_x is None:
        gap_x = config.PACK["GAP_X"]
    if gap_x_min is None:
        gap_x_min = config.PACK["GAP_X_MIN"]
    if max_cols is None:
        max_cols = config.AREA_RULES["A-05"]["max_cols"]
    if max_rows is None:
        max_rows = config.AREA_RULES["A-05"]["max_rows"]

    x0, y0, x1, y1 = region
    region_h = y1 - y0
    gap_y_min = config.PACK["GAP_Y_MIN"]

    columns, gap_used, reason = plan_columns(items, region, max_cols, max_rows,
                                             gap_x, gap_x_min, gap_y_min)
    if columns is None:
        # nothing fits - report every item rather than drawing off the paper
        return PackResult([], [k for k, _, _ in items], 0, region,
                          reason=reason)

    # Horizontal: give the columns their preferred gap, then split whatever is
    # left into equal outer margins.
    #
    # The first version spread the leftover across the inter-column gaps
    # instead - with two columns that put ALL 115.5 mm of slack into the single
    # middle gap and pinned the columns to the sheet edges, leaving a void down
    # the centre. Splitting it into margins puts the columns at 46.8 and 194.4
    # on A522, against 56.3 and 203.6 in the hand-drawn original.
    col_widths = [max(w for _, w, _ in col) for col in columns]
    free_x = (x1 - x0) - sum(col_widths)
    pitch_gap = gap_used
    margin_x = max(0.0, (free_x - pitch_gap * (len(columns) - 1)) / 2.0)

    placements = []
    cursor_x = x0 + margin_x
    for ci, col in enumerate(columns):
        used = sum(h for _, _, h in col)
        free_y = region_h - used
        gap, margin_y = _distribute(len(col), free_y, gap_y_min, distribute)

        cursor_y = y1 - margin_y
        for ri, (key, w, h) in enumerate(col):
            cursor_y -= h
            placements.append(Placement(key, cursor_x, cursor_y, w, h, ci, ri))
            cursor_y -= gap
        cursor_x += col_widths[ci] + pitch_gap

    return PackResult(placements, [], len(columns), region, gap_x=gap_used)


def _distribute(count, free, gap_min, distribute):
    """Share vertical slack between the gaps and the top/bottom margins.

    Returns (gap, margin). Splitting the slack into count+1 equal shares centres
    the column and keeps the spacing even, which reads better than pinning the
    first and last item to the region edges and pooling every millimetre in
    between.

    Falls back to a tight pack when there is not enough room for the minimum
    gap, so a full column still fits rather than overflowing.
    """
    if free < 0:
        return (0.0, 0.0)
    if count <= 1:
        return (0.0, free / 2.0)          # a lone item sits centred
    if not distribute:
        return (gap_min, 0.0)

    even = free / float(count + 1)
    if even >= gap_min:
        return (even, even)

    gap = max(0.0, min(gap_min, free / float(count - 1)))
    margin = max(0.0, (free - gap * (count - 1)) / 2.0)
    return (gap, margin)


def fits(result):
    """True when every placement sits inside the region."""
    x0, y0, x1, y1 = result.region
    if result.overflow:
        return False
    for p in result.placements:
        if p.x0 < x0 - 0.1 or p.y0 < y0 - 0.1 \
                or p.x1 > x1 + 0.1 or p.y1 > y1 + 0.1:
            return False
    return True


def overlaps(result):
    """Pairs of placements whose outlines intersect - should always be empty."""
    bad = []
    ps = result.placements
    for i in range(len(ps)):
        for j in range(i + 1, len(ps)):
            a, b = ps[i], ps[j]
            if a.x0 < b.x1 - 0.1 and b.x0 < a.x1 - 0.1 \
                    and a.y0 < b.y1 - 0.1 and b.y0 < a.y1 - 0.1:
                bad.append((a.key, b.key))
    return bad
