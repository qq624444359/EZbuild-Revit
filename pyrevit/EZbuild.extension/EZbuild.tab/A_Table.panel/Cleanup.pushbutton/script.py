# -*- coding: utf-8 -*-
"""
Cleanup -- delete the unused generated types left in the project.

Both prefixes are scanned. `EZ_` is what the tool creates now; `XL_` is what it
created when the extension was still called XLTable, and those leftovers are
exactly what this button exists to clear out, so dropping the old prefix would
defeat the point.

Only types **no element uses** are deleted. Anything still in use is listed and
skipped, so no elements are taken down with it.
"""

from __future__ import division, unicode_literals

__title__ = 'Cleanup'
__doc__ = ('Delete leftover EZ_* and XL_* text types, filled region types, line '
           'styles and line patterns that no element uses any more. Anything '
           'still in use is listed but never touched.')

import traceback

from pyrevit import forms, revit, script

from Autodesk.Revit.DB import (
    BuiltInCategory, CurveElement, ElementId, FilledRegion, FilledRegionType,
    FilteredElementCollector, GraphicsStyleType, LinePatternElement, TextNote,
    TextNoteType, Transaction,
)
from System.Collections.Generic import List

from eztable import config as cfg
from eztable.styles import elem_name

doc = revit.doc

# EZ_ is the current prefix; XL_ is the legacy one from when this was XLTable.
# Both only appear in fully-automatic mode. When config.py points at existing
# project standards the generated names follow those instead ('Fill Grey 242',
# '2.0mm Arial BOLD'), which is why the type-specific checks below also ask
# config.py whether a name is one it would have produced.
PREFIXES = ('EZ_', 'XL_')


def _prefixed(name):
    return bool(name) and name.startswith(PREFIXES)


def _is_generated_text(name):
    return _prefixed(name) or cfg.is_derived_text_name(name)


def _is_generated_fill(name):
    return _prefixed(name) or cfg.is_generated_fill_name(name)


def collect_candidates():
    """-> [(kind, name, element_id, in_use)]"""
    used_text = set()
    for note in FilteredElementCollector(doc).OfClass(TextNote)\
            .WhereElementIsNotElementType():
        used_text.add(note.GetTypeId().IntegerValue
                      if hasattr(note.GetTypeId(), 'IntegerValue')
                      else note.GetTypeId())

    used_fill = set()
    for region in FilteredElementCollector(doc).OfClass(FilledRegion)\
            .WhereElementIsNotElementType():
        used_fill.add(region.GetTypeId().IntegerValue
                      if hasattr(region.GetTypeId(), 'IntegerValue')
                      else region.GetTypeId())

    used_style = set()
    for curve in FilteredElementCollector(doc).OfClass(CurveElement)\
            .WhereElementIsNotElementType():
        try:
            gs = curve.LineStyle
            if gs is not None:
                used_style.add(gs.Id.IntegerValue)
        except Exception:
            pass

    out = []

    for t in FilteredElementCollector(doc).OfClass(TextNoteType):
        name = elem_name(t)
        if _is_generated_text(name):
            out.append(('Text type', name, t.Id,
                        t.Id.IntegerValue in used_text))

    for t in FilteredElementCollector(doc).OfClass(FilledRegionType):
        name = elem_name(t)
        if _is_generated_fill(name):
            out.append(('Filled region type', name, t.Id,
                        t.Id.IntegerValue in used_fill))

    used_patterns = set()
    lines_cat = doc.Settings.Categories.get_Item(BuiltInCategory.OST_Lines)
    for sub in lines_cat.SubCategories:
        name = elem_name(sub)
        try:
            pid = sub.GetLinePatternId(GraphicsStyleType.Projection)
            if pid is not None:
                used_patterns.add(pid.IntegerValue)
        except Exception:
            pass
        if not _prefixed(name):
            continue
        gs = sub.GetGraphicsStyle(GraphicsStyleType.Projection)
        in_use = gs is not None and gs.Id.IntegerValue in used_style
        out.append(('Line style', name, sub.Id, in_use))

    for lp in FilteredElementCollector(doc).OfClass(LinePatternElement):
        name = elem_name(lp)
        if _prefixed(name):
            out.append(('Line pattern', name, lp.Id,
                        lp.Id.IntegerValue in used_patterns))

    out.sort(key=lambda row: (row[0], row[1]))
    return out


def main():
    try:
        rows = collect_candidates()
    except Exception:
        forms.alert('Scan failed:\n%s' % traceback.format_exc(),
                    title='EZTable Cleanup', exitscript=True)
        return

    if not rows:
        forms.alert('Nothing to clean up.\n\n'
                    'No leftover line styles or patterns (EZ_* / XL_*), and no '
                    'unused fill or text types generated from your standards '
                    '(%s / %s).\n\n'
                    'Types you maintain yourself are never listed here.'
                    % (cfg.GREY_FILL_TYPE_NAME or 'auto',
                       cfg.BASE_TEXT_TYPE_NAME or 'auto'),
                    title='EZTable Cleanup', exitscript=True)
        return

    unused = [r for r in rows if not r[3]]
    in_use = [r for r in rows if r[3]]

    if not unused:
        forms.alert('All %d generated items are still in use - nothing to delete.'
                    % len(rows), title='EZTable Cleanup', exitscript=True)
        return

    labels, lookup = [], {}
    for kind, name, eid, _ in unused:
        label = '%-20s %s' % (kind, name)
        labels.append(label)
        lookup[label] = eid

    picked = forms.SelectFromList.show(
        labels, title='Unused EZTable leftovers - select what to delete',
        button_name='Delete', multiselect=True)
    if not picked:
        return
    if not isinstance(picked, list):
        picked = [picked]

    ids = List[ElementId]([lookup[p] for p in picked])
    t = Transaction(doc, 'EZTable: Cleanup')
    t.Start()
    try:
        deleted = doc.Delete(ids)
        t.Commit()
    except Exception:
        t.RollBack()
        forms.alert('Delete failed and was rolled back:\n%s'
                    % traceback.format_exc(), title='EZTable Cleanup',
                    exitscript=True)
        return

    output = script.get_output()
    output.print_md('## EZTable cleanup')
    output.print_md('- Deleted **%d** items (%d elements removed in total)'
                    % (len(picked), len(deleted) if deleted else len(picked)))
    for p in picked:
        output.print_md('- `%s`' % p.strip())
    if in_use:
        output.print_md('### Still in use - left alone')
        for kind, name, _eid, _ in in_use:
            output.print_md('- %s `%s`' % (kind, name))


if __name__ == '__main__':
    main()
