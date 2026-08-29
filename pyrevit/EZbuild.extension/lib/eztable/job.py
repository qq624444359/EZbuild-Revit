# -*- coding: utf-8 -*-
"""
job.py -- the pipeline shared by Import and Refresh

Parse -> lay out -> create types -> clear -> draw -> stamp, all in one place,
so both pushbuttons are only a thin layer of UI.
"""

from __future__ import division, unicode_literals

import os

from Autodesk.Revit.DB import (
    CurveElement, FilledRegion, FilteredElementCollector, TextNote, Transaction,
)

from . import __version__, plan as planmod, storage, xlreader
from .renderer import Renderer, create_drafting_view
from .styles import StyleFactory

# The three element classes EZTable draws into a view
DRAWN_CLASSES = (CurveElement, FilledRegion, TextNote)


class Job(object):
    """All the state one import or refresh needs."""

    __slots__ = ('doc', 'path', 'sheet_name', 'warnings',
                 'data', 'drawing', 'styles', 'cap_ft', 'result', 'cleared')

    def __init__(self, doc, path, sheet_name, warnings=None):
        self.doc = doc
        self.path = path
        self.sheet_name = sheet_name
        self.warnings = warnings if warnings is not None else []
        self.data = None
        self.drawing = None
        self.styles = None
        self.cap_ft = None
        self.result = None
        self.cleared = 0

    # -- Read-only: parse + lay out -------------------------------

    def prepare(self):
        self.data = xlreader.read_sheet(self.path, self.sheet_name)
        self.styles = StyleFactory(self.doc, self.warnings)
        # When reusing a project text type, the effective size comes from that
        # type rather than from Excel, and both vertical centring and wrapping
        # have to be computed against the real one -- so read it before laying
        # out. No transaction is needed for this step.
        self.cap_ft = self.styles.base_text_cap_height_ft()
        self.drawing = planmod.build_plan(self.data, cap_height_ft=self.cap_ft)
        return self

    # -- Transaction 1: type elements -----------------------------

    def create_styles(self):
        t = Transaction(self.doc, 'EZTable: Create Styles')
        t.Start()
        try:
            self.styles.prebuild(self.drawing)
            # After NewSubcategory the document must be regenerated before
            # its GraphicsStyle can be fetched
            self.doc.Regenerate()
            t.Commit()
        except Exception:
            t.RollBack()
            raise

    # -- Transaction 2: the view and its elements -----------------

    def draw_new_view(self, view_name):
        t = Transaction(self.doc, 'EZTable: Draw Table')
        t.Start()
        try:
            view = create_drafting_view(self.doc, view_name)
            self.result = Renderer(self.doc, view, self.styles,
                                   warnings=self.warnings).draw(self.drawing)
            self.stamp(view)
            t.Commit()
            return view
        except Exception:
            t.RollBack()
            raise

    def redraw_view(self, view):
        """
        Clear and redraw. **The view itself is never deleted** -- its id
        survives, so viewports already placed on sheets stay valid and do not
        move.

        Note that every detail line, filled region and text note in the view is
        deleted, including anything added by hand. Treat an EZTable view as a
        read-only artifact and put annotation on the sheet instead.
        """
        t = Transaction(self.doc, 'EZTable: Refresh Table')
        t.Start()
        try:
            self.cleared = clear_view(self.doc, view)
            self.result = Renderer(self.doc, view, self.styles,
                                   warnings=self.warnings).draw(self.drawing)
            self.stamp(view)
            t.Commit()
            return view
        except Exception:
            t.RollBack()
            raise

    def stamp(self, view):
        storage.write_stamp(view, os.path.abspath(self.path), self.sheet_name,
                            self.data.source_hash, __version__)


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
