# -*- coding: utf-8 -*-
"""
Import Excel -- draw an Excel worksheet into a Revit drafting view, styling intact.

A note on engines: this script **deliberately carries no `#! python3` shebang**
and runs on pyRevit's default IronPython engine. The netcore build of pyRevit
6.4.0 (Revit 2025+ / .NET 8) ships no usable CPython engine -- see docs/DESIGN.md.
"""

from __future__ import division, unicode_literals

__title__ = 'Import\nExcel'
__doc__ = ('Draw an Excel worksheet into a 1:1 drafting view using detail lines, '
           'filled regions and text notes. The view is stamped with its source '
           'so Refresh can update it later.')

import traceback

from pyrevit import forms, revit, script

from eztable import config as cfg
from eztable import report as reportmod
from eztable import xlreader
from eztable.job import Job
from eztable.xlsxlite import load_workbook

doc = revit.doc
uidoc = revit.uidoc


def list_sheets(path):
    wb = load_workbook(path)
    try:
        return list(wb.sheetnames)
    finally:
        wb.close()


def main():
    path = forms.pick_file(file_ext='xlsx', title='Select an Excel file')
    if not path:
        return

    try:
        sheet_names = list_sheets(path)
    except Exception as exc:
        forms.alert('Could not open that file:\n%s' % exc,
                    title='EZTable', exitscript=True)
        return

    if len(sheet_names) == 1:
        sheet_name = sheet_names[0]
    else:
        sheet_name = forms.SelectFromList.show(
            sheet_names, title='Select a worksheet', button_name='Import',
            multiselect=False)
    if not sheet_name:
        return

    job = Job(doc, path, sheet_name)

    try:
        job.prepare()
    except xlreader.CachedValuesMissing as exc:
        forms.alert('%s' % exc, title='No cached values', exitscript=True)
        return
    except Exception:
        forms.alert('Could not read the worksheet:\n%s' % traceback.format_exc(),
                    title='EZTable', exitscript=True)
        return

    try:
        job.create_styles()
    except Exception:
        forms.alert('Could not create the types:\n%s' % traceback.format_exc(),
                    title='EZTable', exitscript=True)
        return

    try:
        view = job.draw_new_view(cfg.view_name(sheet_name, path))
    except Exception:
        forms.alert('Drawing failed and was rolled back:\n%s'
                    % traceback.format_exc(), title='EZTable', exitscript=True)
        return

    try:
        uidoc.ActiveView = view
    except Exception:
        pass

    # Only open a window when there is something worth saying. get_output()
    # must wait until printing is certain -- pyRevit's output window appears on
    # the first print.
    if reportmod.should_report(job):
        output = script.get_output()
        reportmod.print_job(output, job, view, 'Import complete', output.linkify)


if __name__ == '__main__':
    main()
