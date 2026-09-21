# -*- coding: utf-8 -*-
"""
Refresh -- re-read the workbooks and bring imported tables up to date.

The strategy is clear-and-redraw with no incremental diffing: inserting a row or
deleting a column in Excel throws every cell mapping out of alignment.
**The view itself is never deleted** -- its id survives, so viewports already
placed on sheets stay valid.

A table too tall for one sheet lives in several views, one part each. Those are
refreshed as a unit: redrawing one part on its own would leave the others
showing an older revision of the same workbook.
"""

from __future__ import division, unicode_literals

__title__ = 'Refresh'
__doc__ = ('Re-read the source Excel files and redraw the tables that changed. '
           'View ids are preserved, so viewports already placed on sheets stay '
           'valid. A table split across several sheets is refreshed as a unit.')

import os
import traceback

from pyrevit import forms, revit, script

from eztable import report as reportmod
from eztable import storage, xlreader
from eztable.job import Job, is_stale

doc = revit.doc
uidoc = revit.uidoc

STATUS_LABEL = {'stale': 'changed', 'fresh': 'up to date', 'missing': 'source missing'}


def table_label(views, stamp, status):
    name = views[0].Name
    if len(views) > 1:
        name = '%s + %d more' % (name, len(views) - 1)
    return '[%s]  %s  <-  %s / %s' % (
        STATUS_LABEL.get(status, status), name,
        os.path.basename(stamp.get('SourcePath') or '?'),
        stamp.get('SheetName') or '?')


def main():
    tables = storage.find_tables(doc)
    if not tables:
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

    for _key, members in tables:
        views = [view for view, _stamp in members]
        stamp = members[0][1]
        status, note = is_stale(stamp)
        label = table_label(views, stamp, status)
        lookup[label] = (views, stamp, status, note)
        if active_id is not None and any(v.Id == active_id for v in views):
            rows.insert(0, label)          # the table in the active view goes first
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
        views, stamp, status, note = lookup[label]
        if status == 'missing':
            failed.append((views[0].Name, note))
            continue
        if status == 'fresh':
            skipped.append((views[0].Name, 'unchanged, skipped'))
            continue

        job = Job(doc, stamp.get('SourcePath'), stamp.get('SheetName'))
        try:
            job.prepare()
            job.create_styles()
            drawn, created, emptied = job.redraw_views(views)
            done.append((drawn, job, created, emptied))
        except xlreader.CachedValuesMissing as exc:
            failed.append((views[0].Name, '%s' % exc))
        except Exception:
            failed.append((views[0].Name,
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
            [[', '.join(output.linkify(v.Id, v.Name) for v in views),
              os.path.basename(job.path), job.sheet_name, job.result_summary()]
             for views, job, _created, _emptied in done],
            columns=['Views', 'Source', 'Worksheet', 'Elements'])
    for name, why in skipped:
        output.print_md('- `%s` %s' % (name, why))
    if failed:
        output.print_md('### Failed')
        for name, why in failed:
            output.print_md('- `%s` - %s' % (name, why))

    print_part_changes(output, done)

    for views, job, _created, _emptied in done:
        if reportmod.should_report(job):
            output.print_md('---')
            reportmod.print_job(output, job, views,
                                'Details: %s' % views[0].Name, output.linkify)


def print_part_changes(output, done):
    """
    A workbook that grew or shrank changes how many sheets its table needs.
    Both directions need saying out loud: a new view is not on a sheet yet, and
    an emptied one is still sitting on the sheet it was placed on.
    """
    created = [(v, job) for _views, job, made, _e in done for v in made]
    emptied = [(v, job) for _views, job, _c, gone in done for v in gone]

    if created:
        output.print_md('### %d new part(s) - place these on sheets' % len(created))
        for view, job in created:
            output.print_md('- %s (from `%s`)'
                            % (output.linkify(view.Id, view.Name),
                               os.path.basename(job.path)))
    if emptied:
        output.print_md('### %d part(s) no longer needed' % len(emptied))
        output.print_md('The table now needs fewer sheets than it did. These '
                        'views were emptied but **not deleted** - a viewport may '
                        'still be placed on a sheet, so removing them is left to '
                        'you.')
        for view, _job in emptied:
            output.print_md('- %s' % output.linkify(view.Id, view.Name))


if __name__ == '__main__':
    main()
