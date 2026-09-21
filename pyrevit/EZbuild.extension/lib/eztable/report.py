# -*- coding: utf-8 -*-
"""
report.py -- the report printed in the output window

This module deliberately does not import pyrevit: the caller passes the output
object in, which keeps the module testable outside Revit.

Callers should ask should_report() first and only then fetch the output object.
pyRevit's output window appears on the first print, so not printing means no
window pops up.
"""

from __future__ import division, unicode_literals

import os

from . import config as cfg
from .geometry import feet_to_mm
from .xlsxlite import column_letter


def overflows(job):
    """Text that does not fit its cell, across every part."""
    out = []
    for drawing in job.drawings:
        out.extend(drawing.overflows)
    return out


def should_report(job):
    """
    Whether to open the output window. Under 'auto' it opens only when there
    is something worth saying -- a successful import already announces itself by
    switching to the new view, so a second confirmation window is just noise.
    A table split across several sheets always says so: the other parts are
    sitting in views the user has not been switched to.
    """
    mode = getattr(cfg, 'REPORT_MODE', 'auto')
    if mode == 'off':
        return False
    if mode == 'always':
        return True
    if job.warnings or job.part_count > 1:
        return True
    return bool(overflows(job))


def print_job(output, job, views=None, title='EZTable', linkify=None):
    data = job.data
    g = data.grid
    views = list(views or [])

    output.print_md('## %s' % title)
    output.print_md('**Source** `%s` - worksheet `%s`'
                    % (os.path.basename(job.path), job.sheet_name))
    if views:
        label = 'Views' if len(views) > 1 else 'View'
        names = [linkify(v.Id, v.Name) if linkify else v.Name for v in views]
        output.print_md('**%s** %s' % (label, ', '.join(names)))
    output.print_md('- %d visible rows, %d visible columns (hidden ones skipped)'
                    % (g.n_rows, g.n_cols))
    output.print_md('- Table size %.1f x %.1f mm at 1:1'
                    % (feet_to_mm(g.total_width_ft), feet_to_mm(g.total_height_ft)))
    if getattr(job, 'cleared', 0):
        output.print_md('- Removed %d old elements before redrawing' % job.cleared)
    if job.results:
        output.print_md('- Elements: %s' % job.result_summary())

    print_parts(output, job, views, linkify)
    print_blocks(output, job)
    print_types(output, job)
    print_growth(output, job)
    print_overflow(output, job)
    print_warnings(output, job.warnings)
    print_notes(output, getattr(job.data, 'infos', None))


def print_parts(output, job, views=None, linkify=None):
    """When a tall table was cut into parts, say which view holds which."""
    if job.part_count < 2:
        return
    views = list(views or [])
    output.print_md('### Split into %d parts - one view each' % job.part_count)
    output.print_md('Stacked, the table is taller than `MAX_TABLE_HEIGHT_MM` in '
                    '`config.py`, so it was cut into parts instead of being '
                    'scaled - every part stays 1:1. **Place each view on its own '
                    'sheet.**')
    rows = []
    for i, drawing in enumerate(job.drawings):
        view = views[i] if i < len(views) else None
        name = ''
        if view is not None:
            name = linkify(view.Id, view.Name) if linkify else view.Name
        rows.append(['%d of %d' % (drawing.part, drawing.part_count), name,
                     '%d' % len(drawing.blocks),
                     '%.1f' % feet_to_mm(drawing.width_ft),
                     '%.1f' % feet_to_mm(drawing.height_ft)])
    output.print_table(rows, columns=['Part', 'View', 'Blocks',
                                      'Width (mm)', 'Height (mm)'])


def ranges(values, label=None):
    """
    [1, 52, 53, 54] -> '1, 52-54'. A block starts with the repeated header row
    or column, which is nowhere near the rest of it, so a plain first-to-last
    span would claim the block holds everything in between.
    """
    label = label or (lambda v: '%d' % v)
    runs = []
    for v in values:
        if runs and v == runs[-1][1] + 1:
            runs[-1][1] = v
        else:
            runs.append([v, v])
    return ', '.join(label(a) if a == b else '%s-%s' % (label(a), label(b))
                     for a, b in runs)


def print_blocks(output, job):
    """When a wide table was split, list which columns landed in each block."""
    blocks = [(drawing, b) for drawing in job.drawings for b in drawing.blocks]
    if len(blocks) < 2:
        return
    by_column = len(set(tuple(b[1]) for _, b in blocks)) > 1
    by_row = len(set(tuple(b[2]) for _, b in blocks)) > 1
    output.print_md('### Cut into %d blocks stacked vertically' % len(blocks))
    reasons = []
    if by_column:
        reasons.append('wider than `MAX_TABLE_WIDTH_MM`, so it was cut by column')
    if by_row:
        reasons.append('taller than `MAX_TABLE_HEIGHT_MM`, so it was cut by row')
    output.print_md('The table is %s (`config.py`). Cutting keeps every block at '
                    '1:1; scaling the view instead would desynchronise the text '
                    'from the cells.' % ' and '.join(reasons))
    multi = job.part_count > 1
    rows = []
    for drawing, (i, cols, brows, w, h) in blocks:
        row = ['%d' % i,
               ranges(cols, column_letter),
               ranges(brows),
               '%.1f' % feet_to_mm(w), '%.1f' % feet_to_mm(h)]
        if multi:
            row.insert(1, '%d' % drawing.part)
        rows.append(row)
    columns = ['Block', 'Columns', 'Rows', 'Width (mm)', 'Height (mm)']
    if multi:
        columns.insert(1, 'Part')
    output.print_table(rows, columns=columns)


def print_types(output, job):
    if job.styles is None:
        return
    used = job.styles.describe()
    output.print_md('### Types used')
    for label, key in (('Line styles', 'lines'), ('Fills', 'fills'),
                       ('Text', 'texts')):
        names = used.get(key) or []
        output.print_md('- %s: %s'
                        % (label, ', '.join('`%s`' % n for n in names) or '(none)'))


def print_growth(output, job):
    cols, rows = job.data.grid.growth_report()
    if not cols and not rows:
        return
    note = ('%.2f mm' % feet_to_mm(job.cap_ft)) if job.cap_ft else 'the Excel font size'
    output.print_md('### Columns and rows widened to fit the text')
    output.print_md('Text height is fixed at %s, so anything that did not fit got '
                    'more room. Turn `FIT_COLUMNS` / `FIT_ROWS` off in `config.py` '
                    'to keep the Excel geometry exactly.' % note)
    if cols:
        output.print_table(
            [[column_letter(c), '%.2f' % feet_to_mm(a), '%.2f' % feet_to_mm(b),
              '%+.2f' % feet_to_mm(b - a)] for c, a, b in cols],
            columns=['Column', 'Was (mm)', 'Now (mm)', 'Delta'])
    if rows:
        output.print_table(
            [[str(r), '%.2f' % feet_to_mm(a), '%.2f' % feet_to_mm(b),
              '%+.2f' % feet_to_mm(b - a)] for r, a, b in rows],
            columns=['Row', 'Was (mm)', 'Now (mm)', 'Delta'])


def print_overflow(output, job):
    over = sorted(overflows(job), key=lambda t: t.avail_ft - t.width_ft)
    if not over:
        return
    output.print_md('### Text too wide for its cell - %d places' % len(over))
    output.print_md('Centring cannot fix horizontal overflow. Either use a smaller '
                    'base text type in `config.py`, or widen these columns in Excel.')
    output.print_table(
        [[t.coord, t.text.split('\n')[0][:28],
          '%.2f' % feet_to_mm(t.width_ft), '%.2f' % feet_to_mm(t.avail_ft),
          '%+.2f' % feet_to_mm(t.avail_ft - t.width_ft)] for t in over],
        columns=['Cell', 'Text', 'Needs (mm)', 'Cell (mm)', 'Spare'])


def print_notes(output, infos):
    if not infos:
        return
    output.print_md('### Notes')
    for n in infos:
        output.print_md('- %s' % n)


def print_warnings(output, warnings):
    if warnings:
        output.print_md('### Warnings - %d' % len(warnings))
        for w in warnings:
            output.print_md('- %s' % w)
