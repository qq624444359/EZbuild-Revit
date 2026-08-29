# -*- coding: utf-8 -*-
"""
Refresh -- re-read the workbooks and bring imported tables up to date.

The strategy is clear-and-redraw with no incremental diffing: inserting a row or
deleting a column in Excel throws every cell mapping out of alignment.
**The view itself is never deleted** -- its id survives, so viewports already
placed on sheets stay valid.
"""

from __future__ import division, unicode_literals

__title__ = 'Refresh'
__doc__ = ('Re-read the source Excel files and redraw the tables that changed. '
           'View ids are preserved, so viewports already placed on sheets stay '
           'valid.')

import os
import traceback

from pyrevit import forms, revit, script

from eztable import report as reportmod
from eztable import storage, xlreader
from eztable.job import Job, is_stale

doc = revit.doc
uidoc = revit.uidoc

STATUS_LABEL = {'stale': 'changed', 'fresh': 'up to date', 'missing': 'source missing'}


def main():
    stamped = storage.find_stamped_views(doc)
    if not stamped:
        forms.alert('No EZTable views in this project yet.\n\n'
                    'Only views imported with v0.7.0 or later carry a source '
                    'stamp - older ones need to be imported again.',
                    title='EZTable Refresh', exitscript=True)
        return

    rows, lookup = [], {}
    active_id = None
    try:
        active_id = uidoc.ActiveView.Id
    except Exception:
        pass

    for view, stamp in stamped:
        status, note = is_stale(stamp)
        label = '[%s]  %s  <-  %s / %s' % (
            STATUS_LABEL.get(status, status), view.Name,
            os.path.basename(stamp.get('SourcePath') or '?'),
            stamp.get('SheetName') or '?')
        lookup[label] = (view, stamp, status, note)
        if active_id is not None and view.Id == active_id:
            rows.insert(0, label)          # the active view goes first
        else:
            rows.append(label)

    picked = forms.SelectFromList.show(
        rows, title='Select the tables to refresh', button_name='Refresh',
        multiselect=True)
    if not picked:
        return
    if not isinstance(picked, list):
        picked = [picked]

    done, skipped, failed = [], [], []

    for label in picked:
        view, stamp, status, note = lookup[label]
        if status == 'missing':
            failed.append((view.Name, note))
            continue
        if status == 'fresh':
            skipped.append((view.Name, 'unchanged, skipped'))
            continue

        job = Job(doc, stamp.get('SourcePath'), stamp.get('SheetName'))
        try:
            job.prepare()
            job.create_styles()
            job.redraw_view(view)
            done.append((view, job))
        except xlreader.CachedValuesMissing as exc:
            failed.append((view.Name, '%s' % exc))
        except Exception:
            failed.append((view.Name,
                           traceback.format_exc().strip().split('\n')[-1]))

    summarise(done, skipped, failed)


def summarise(done, skipped, failed):
    # Refresh is an explicit action, so always report the outcome; failures and
    # skips have to be visible
    output = script.get_output()
    output.print_md('## EZTable refresh')
    output.print_md('- %d updated, %d skipped, %d failed'
                    % (len(done), len(skipped), len(failed)))

    if done:
        output.print_table(
            [[output.linkify(v.Id, v.Name), os.path.basename(j.path),
              j.sheet_name, j.result.summary()] for v, j in done],
            columns=['View', 'Source', 'Worksheet', 'Elements'])
    for name, why in skipped:
        output.print_md('- `%s` %s' % (name, why))
    if failed:
        output.print_md('### Failed')
        for name, why in failed:
            output.print_md('- `%s` - %s' % (name, why))

    for view, job in done:
        if reportmod.should_report(job):
            output.print_md('---')
            reportmod.print_job(output, job, view, 'Details: %s' % view.Name,
                                output.linkify)


if __name__ == '__main__':
    main()
