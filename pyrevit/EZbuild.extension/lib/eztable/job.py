# -*- coding: utf-8 -*-
"""
job.py -- the pipeline shared by Import and Refresh

Parse -> lay out -> create types -> clear -> draw -> stamp, all in one place,
so both pushbuttons are only a thin layer of UI.
"""

from __future__ import division, unicode_literals

import os
import re

from Autodesk.Revit.DB import (
    CurveElement, FilledRegion, FilteredElementCollector, TextNote, Transaction,
)

from . import __version__, config as cfg, plan as planmod, storage, xlreader
from .renderer import Renderer, create_drafting_view, rename_view
from .styles import StyleFactory

# The three element classes EZTable draws into a view
DRAWN_CLASSES = (CurveElement, FilledRegion, TextNote)

# The part suffix PART_NAME_TEMPLATE puts on a split table's views: ' (2/3)',
# and the ' (1)' Revit-style suffix a duplicate name picks up
PART_SUFFIX_RE = re.compile(r'\s*\(\d+\s*(?:/\s*\d+)?\)\s*$')


class Job(object):
    """
    All the state one import or refresh needs.

    A table too tall for one sheet is laid out as several parts, one drafting
    view each -- so `drawings` and `results` are lists, with one entry per part,
    even when that list holds a single item.
    """

    __slots__ = ('doc', 'path', 'sheet_name', 'warnings',
                 'data', 'drawings', 'styles', 'cap_ft', 'results', 'cleared')

    def __init__(self, doc, path, sheet_name, warnings=None):
        self.doc = doc
        self.path = path
        self.sheet_name = sheet_name
        self.warnings = warnings if warnings is not None else []
        self.data = None
        self.drawings = []
        self.styles = None
        self.cap_ft = None
        self.results = []
        self.cleared = 0

    @property
    def part_count(self):
        return len(self.drawings)

    def result_summary(self):
        """The element counts of every part added up, for the report."""
        fills = sum(len(r.fills) for r in self.results)
        lines = sum(len(r.lines) for r in self.results)
        texts = sum(len(r.texts) for r in self.results)
        skipped = sum(r.skipped for r in self.results)
        return ('%d fills, %d lines, %d texts - %d total (%d skipped)'
                % (fills, lines, texts, fills + lines + texts, skipped))

    # -- Read-only: parse + lay out -------------------------------

    def prepare(self):
        self.data = xlreader.read_sheet(self.path, self.sheet_name)
        self.styles = StyleFactory(self.doc, self.warnings)
        # When reusing a project text type, the effective size comes from that
        # type rather than from Excel, and both vertical centring and wrapping
        # have to be computed against the real one -- so read it before laying
        # out. No transaction is needed for this step.
        self.cap_ft = self.styles.base_text_cap_height_ft()
        self.drawings = planmod.build_plans(self.data, cap_height_ft=self.cap_ft)
        return self

    # -- Transaction 1: type elements -----------------------------

    def create_styles(self):
        t = Transaction(self.doc, 'EZTable: Create Styles')
        t.Start()
        try:
            for drawing in self.drawings:
                self.styles.prebuild(drawing)
            # After NewSubcategory the document must be regenerated before
            # its GraphicsStyle can be fetched
            self.doc.Regenerate()
            t.Commit()
        except Exception:
            t.RollBack()
            raise

    # -- Transaction 2: the view and its elements -----------------

    def draw_new_views(self, view_name):
        """
        Draw every part into a new drafting view of its own. -> [view], in part
        order; a table that fits on one sheet gives a single view carrying the
        plain name, with no (1/2) suffix.

        One transaction covers the lot, so a failure halfway through leaves no
        half-drawn table behind.
        """
        t = Transaction(self.doc, 'EZTable: Draw Table')
        t.Start()
        try:
            views = []
            for drawing in self.drawings:
                name = cfg.part_view_name(view_name, drawing.part,
                                          drawing.part_count)
                view = create_drafting_view(self.doc, name)
                self.results.append(self.render(view, drawing))
                self.stamp(view, drawing)
                views.append(view)
            t.Commit()
            return views
        except Exception:
            t.RollBack()
            raise

    def redraw_views(self, views, view_name=None):
        """
        Clear and redraw a table's parts into the views it already owns.
        -> (views in part order, views newly created, views emptied because the
        table shrank)

        **An existing view is never deleted** -- its id survives, so viewports
        already placed on sheets stay valid and do not move. That holds for a
        part that has gone away as well: its view is emptied and reported, and
        removing it from the sheet is left to whoever placed it there.

        A workbook that grew since the import needs more parts than there are
        views; the extra ones are created here, named after `view_name` (the
        first view's name when none is given), and have to be placed on sheets
        by hand.

        Note that every detail line, filled region and text note in each view is
        deleted, including anything added by hand. Treat an EZTable view as a
        read-only artifact and put annotation on the sheet instead.
        """
        base = view_name or _base_view_name(views[0].Name if views else 'Table')
        t = Transaction(self.doc, 'EZTable: Refresh Table')
        t.Start()
        try:
            drawn, created = [], []
            for i, drawing in enumerate(self.drawings):
                name = cfg.part_view_name(base, drawing.part, drawing.part_count)
                if i < len(views):
                    view = views[i]
                    self.cleared += clear_view(self.doc, view)
                    # Only when the count changed: with it unchanged the name is
                    # already what part_view_name builds, so nothing moves.
                    rename_view(view, name)
                else:
                    view = create_drafting_view(self.doc, name)
                    created.append(view)
                self.results.append(self.render(view, drawing))
                self.stamp(view, drawing)
                drawn.append(view)

            emptied = []
            for view in views[len(self.drawings):]:
                self.cleared += clear_view(self.doc, view)
                storage.clear_stamp(view)
                emptied.append(view)

            t.Commit()
            return drawn, created, emptied
        except Exception:
            t.RollBack()
            raise

    def render(self, view, drawing):
        return Renderer(self.doc, view, self.styles,
                        warnings=self.warnings).draw(drawing)

    def stamp(self, view, drawing):
        storage.write_stamp(view, os.path.abspath(self.path), self.sheet_name,
                            self.data.source_hash, __version__,
                            drawing.part, drawing.part_count)


def _base_view_name(name):
    """Strip the part suffix off a view name, so a refreshed table keeps the
    name it was imported with even when its part count changes."""
    return PART_SUFFIX_RE.sub('', name or '').strip() or 'Table'


def clear_view(doc, view):
    """Delete what EZTable drew into a view. Must be called inside a
    transaction. -> number of elements deleted"""
    ids = []
    for cls in DRAWN_CLASSES:
        ids.extend(FilteredElementCollector(doc, view.Id)
                   .OfClass(cls).WhereElementIsNotElementType().ToElementIds())
    if not ids:
        return 0
    from System.Collections.Generic import List
    from Autodesk.Revit.DB import ElementId
    doc.Delete(List[ElementId](ids))
    return len(ids)


def is_stale(stamp):
    """
    -> (state, explanation)
       'stale'   the workbook changed
       'fresh'   unchanged
       'missing' the source file can no longer be found
    """
    path = stamp.get('SourcePath') or ''
    if not path or not os.path.isfile(path):
        return 'missing', 'Source file not found: %s' % (path or '(empty)')
    try:
        current = xlreader.file_hash(path)
    except Exception as exc:
        return 'missing', 'Source file unreadable: %s' % exc
    if current != (stamp.get('SourceHash') or ''):
        return 'stale', 'changed'
    return 'fresh', 'up to date'
