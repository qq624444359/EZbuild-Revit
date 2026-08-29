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


def should_report(job):
    """
    Whether to open the output window. Under 'auto' it opens only when there
    is something worth saying -- a successful import already announces itself by
    switching to the new view, so a second confirmation window is just noise.
    """
    mode = getattr(cfg, 'REPORT_MODE', 'auto')
    if mode == 'off':
        return False
    if mode == 'always':
        return True
    if job.warnings:
        return True
    return bool(job.drawing is not None and job.drawing.overflows)


def print_job(output, job, view=None, title='EZTable', linkify=None):
    data, drawing, result = job.data, job.drawing, job.result
    g = data.grid

    output.print_md('## %s' % title)
    output.print_md('**Source** `%s` - worksheet `%s`'
                    % (os.path.basename(job.path), job.sheet_name))
    if view is not None:
        label = linkify(view.Id, view.Name) if linkify else view.Name
        output.print_md('**View** %s' % label)
    output.print_md('- %d visible rows, %d visible columns (hidden ones skipped)'
                    % (g.n_rows, g.n_cols))
    output.print_md('- Table size %.1f x %.1f mm at 1:1'
                    % (feet_to_mm(g.total_width_ft), feet_to_mm(g.total_height_ft)))
    if getattr(job, 'cleared', 0):
        output.print_md('- Removed %d old elements before redrawing' % job.cleared)
    if result is not None:
        output.print_md('- Elements: %s' % result.summary())

    print_blocks(output, drawing)
    print_types(output, job)
    print_growth(output, job)
    print_overflow(output, drawing)
    print_warnings(output, job.warnings)
    print_notes(output, getattr(job.data, 'infos', None))


def print_blocks(output, drawing):
    """When a wide table was split, list which columns landed in each block."""
    blocks = getattr(drawing, 'blocks', None) or []
    if len(blocks) < 2:
        return
    output.print_md('### Split into %d blocks stacked vertically' % len(blocks))
    output.print_md('The table is wider than `MAX_TABLE_WIDTH_MM` in `config.py`, '
                    'so it was cut by column and stacked instead of being scaled - '
                    'every block stays 1:1.')
    output.print_table(
        [['%d' % i,
          '%s - %s' % (column_letter(cols[0]), column_letter(cols[-1])),
          '%d' % len(cols),
          '%.1f' % feet_to_mm(w), '%.1f' % feet_to_mm(h)]
         for i, cols, w, h in blocks],
        columns=['Block', 'Columns', 'Count', 'Width (mm)', 'Height (mm)'])


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


def print_overflow(output, drawing):
    if drawing is None:
        return
    over = sorted(drawing.overflows, key=lambda t: t.avail_ft - t.width_ft)
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
