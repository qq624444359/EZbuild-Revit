# -*- coding: utf-8 -*-
"""
renderer.py -- turn plan.py's drawing instructions into Revit elements

This layer makes no geometric decisions: all merging, de-duplication and
alignment is already settled in plan.py. Drawing order is fills -> borders ->
text. What is drawn first sits underneath, so fills never cover the lines and
text.
"""

from __future__ import division, unicode_literals

from Autodesk.Revit.DB import (
    CurveLoop, ElementId, FilledRegion, HorizontalTextAlignment, Line,
    TextNote, TextNoteOptions, ViewDrafting, ViewFamily, ViewFamilyType,
    FilteredElementCollector, XYZ,
)

try:
    from Autodesk.Revit.DB import DetailElementOrderUtils
except ImportError:                                      # absent on older versions
    DetailElementOrderUtils = None

from System.Collections.Generic import List

# Revit's shortest curve tolerance is about 1/32"; leave a little margin
MIN_CURVE_LENGTH_FT = 0.0026

_ALIGN = {
    'left': HorizontalTextAlignment.Left,
    'center': HorizontalTextAlignment.Center,
    'right': HorizontalTextAlignment.Right,
}


class DrawResult(object):
    __slots__ = ('fills', 'lines', 'texts', 'skipped')

    def __init__(self):
        self.fills = []
        self.lines = []
        self.texts = []
        self.skipped = 0

    @property
    def total(self):
        return len(self.fills) + len(self.lines) + len(self.texts)

    def summary(self):
        return ('%d fills, %d lines, %d texts - %d total (%d skipped)'
                % (len(self.fills), len(self.lines), len(self.texts),
                   self.total, self.skipped))


# ---------------------------------------------------------------- the view

def create_drafting_view(doc, name):
    """Create a 1:1 drafting view, appending a suffix if the name is taken."""
    vft = None
    for v in FilteredElementCollector(doc).OfClass(ViewFamilyType):
        if v.ViewFamily == ViewFamily.Drafting:
            vft = v
            break
    if vft is None:
        raise RuntimeError('No Drafting view family type in this project')

    view = ViewDrafting.Create(doc, vft.Id)
    view.Scale = 1
    _assign_unique_name(view, name)
    return view


def _assign_unique_name(view, name):
    candidate = name
    for i in range(1, 100):
        try:
            view.Name = candidate
            return candidate
        except Exception:
            candidate = '%s (%d)' % (name, i)
    raise RuntimeError('Could not name the view - %r and its suffixes are all taken' % name)


# ---------------------------------------------------------------- drawing

class Renderer(object):

    def __init__(self, doc, view, styles, origin=None, warnings=None):
        self.doc = doc
        self.view = view
        self.styles = styles
        self.origin = origin or XYZ(0, 0, 0)
        self.warnings = warnings if warnings is not None else []
        self._invisible_id = None

    def warn(self, msg):
        if msg not in self.warnings:
            self.warnings.append(msg)

    def _pt(self, x, y):
        return XYZ(self.origin.X + x, self.origin.Y + y, 0.0)

    def draw(self, plan, send_fills_to_back=True):
        result = DrawResult()
        self.draw_fills(plan, result)
        self.draw_borders(plan, result)
        self.draw_texts(plan, result)
        if send_fills_to_back and result.fills and DetailElementOrderUtils:
            try:
                ids = List[ElementId]([e.Id for e in result.fills])
                DetailElementOrderUtils.SendToBack(self.doc, self.view, ids)
            except Exception as exc:
                self.warn('Could not send fills to back (harmless for printing): %s' % exc)
        return result

    # -- fills -----------------------------------------------------

    def draw_fills(self, plan, result):
        for item in plan.fills:
            r = item.rect
            if (r.x_right - r.x_left) < MIN_CURVE_LENGTH_FT or \
               (r.y_top - r.y_bottom) < MIN_CURVE_LENGTH_FT:
                result.skipped += 1
                continue
            p1 = self._pt(r.x_left, r.y_top)
            p2 = self._pt(r.x_right, r.y_top)
            p3 = self._pt(r.x_right, r.y_bottom)
            p4 = self._pt(r.x_left, r.y_bottom)
            loop = CurveLoop()
            loop.Append(Line.CreateBound(p1, p2))
            loop.Append(Line.CreateBound(p2, p3))
            loop.Append(Line.CreateBound(p3, p4))
            loop.Append(Line.CreateBound(p4, p1))
            frt = self.styles.get_filled_region_type(item.rgb)
            region = FilledRegion.Create(self.doc, frt.Id, self.view.Id,
                                         List[CurveLoop]([loop]))
            # The boundary line style goes on the instance -- FilledRegionType
            # has no LineStyleId. Without it the filled region's outline
            # overlaps the borders we draw ourselves and reads as a double line.
            self._hide_boundary(region)
            result.fills.append(region)

    def _hide_boundary(self, region):
        if self._invisible_id is None:
            self._invisible_id = self.styles.invisible_line_style_id()
        if not self._invisible_id or self._invisible_id == ElementId.InvalidElementId:
            return
        try:
            region.SetLineStyleId(self._invisible_id)
        except Exception as exc:
            self.warn('Could not hide the filled region boundary (may show double lines): %s' % exc)
            self._invisible_id = ElementId.InvalidElementId

    # -- borders ---------------------------------------------------

    def draw_borders(self, plan, result):
        for item in plan.lines:
            p1 = self._pt(item.p1[0], item.p1[1])
            p2 = self._pt(item.p2[0], item.p2[1])
            if p1.DistanceTo(p2) < MIN_CURVE_LENGTH_FT:
                result.skipped += 1
                continue
            curve = self.doc.Create.NewDetailCurve(self.view,
                                                   Line.CreateBound(p1, p2))
            gs = self.styles.get_line_style(item.style, item.rgb)
            if gs is not None:
                try:
                    curve.LineStyle = gs
                except Exception as exc:
                    self.warn('Could not apply line style %s: %s' % (item.style, exc))
            result.lines.append(curve)

    # -- text ------------------------------------------------------

    def draw_texts(self, plan, result):
        for item in plan.texts:
            text = item.text
            if not text or not text.strip():
                result.skipped += 1          # an empty string makes TextNote.Create throw
                continue
            ttype = self.styles.get_text_type(item.font_name, item.font_size,
                                              item.bold, item.italic, item.rgb)
            opts = TextNoteOptions(ttype.Id)
            opts.HorizontalAlignment = _ALIGN.get(item.h_align,
                                                  HorizontalTextAlignment.Left)
            opts.Rotation = 0.0
            # Use the overload without a width parameter -- passing a width
            # turns on Revit's own automatic wrapping
            note = TextNote.Create(self.doc, self.view.Id,
                                   self._pt(item.x, item.y), text, opts)
            result.texts.append(note)
