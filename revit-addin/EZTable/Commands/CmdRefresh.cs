using System;
using System.Collections.Generic;
using System.Linq;
using Autodesk.Revit.Attributes;
using Autodesk.Revit.DB;
using Autodesk.Revit.UI;
using EZTable.Core;
using EZTable.Revit;
using TaskDialog = Autodesk.Revit.UI.TaskDialog;

namespace EZTable.Commands
{
    /// <summary>
    /// Refresh -- re-read the workbooks and bring imported tables up to date.
    ///
    /// The strategy is clear-and-redraw with no incremental diffing: inserting a
    /// row or deleting a column in Excel throws every cell mapping out of
    /// alignment, which makes incremental updates a poor trade.
    ///
    /// **The view itself is never deleted** -- its id survives, so viewports
    /// already placed on sheets stay valid.
    /// </summary>
    [Transaction(TransactionMode.Manual)]
    public class CmdRefresh : IExternalCommand
    {
        public Result Execute(ExternalCommandData commandData, ref string message,
                              ElementSet elements)
        {
            try
            {
                UIDocument uidoc = commandData.Application.ActiveUIDocument;
                Document doc = uidoc.Document;

                var stamped = Storage.FindStampedViews(doc);
                if (stamped.Count == 0)
                {
                    TaskDialog.Show("EZTable Refresh",
                        "No EZTable views in this project yet.\n\n" +
                        "Only views that carry a source stamp can be refreshed. Views " +
                        "imported before the Refresh feature existed need to be " +
                        "imported again.");
                    return Result.Cancelled;
                }

                // The active view goes first. A bool flag avoids comparing an
                // ElementId against null, which would depend on how ElementId's
                // == overload handles it.
                bool hasActive = false;
                ElementId activeId = ElementId.InvalidElementId;
                try
                {
                    var activeView = uidoc.ActiveView;
                    if (activeView != null) { activeId = activeView.Id; hasActive = true; }
                }
                catch (Exception) { }

                var entries = stamped
                    .Select(pair => new Entry(pair.Item1, pair.Item2))
                    .OrderByDescending(e => hasActive && e.View.Id.Equals(activeId))
                    .ThenBy(e => e.View.Name)
                    .ToList();

                var rows = entries.Select((e, i) => new UI.RefreshSelector.Row(i, e.Label)).ToList();
                var stalePositions = entries
                    .Select((e, i) => new { e, i })
                    .Where(x => x.e.State == Storage.Freshness.Stale)
                    .Select(x => x.i)
                    .ToList();

                var dialog = new UI.RefreshSelector(rows, stalePositions);
                if (dialog.ShowDialog() != true || dialog.SelectedIndices.Count == 0)
                    return Result.Cancelled;

                var done = new List<string>();
                var skipped = new List<string>();
                var failed = new List<string>();

                foreach (int index in dialog.SelectedIndices)
                {
                    if (index < 0 || index >= entries.Count) continue;
                    Entry entry = entries[index];

                    if (entry.State == Storage.Freshness.Missing)
                    {
                        failed.Add(entry.View.Name + " - " + entry.Note);
                        continue;
                    }
                    if (entry.State == Storage.Freshness.Fresh)
                    {
                        skipped.Add(entry.View.Name + " - unchanged, skipped");
                        continue;
                    }

                    // One transaction per table, so a single failure cannot roll
                    // back the tables already refreshed
                    using (var t = new Transaction(doc, "EZTable: Refresh Table"))
                    {
                        t.Start();
                        try
                        {
                            var job = new TableJob(entry.Stamp.SourcePath,
                                                   entry.Stamp.SheetName).Prepare(doc);
                            job.RedrawView(doc, entry.View);
                            t.Commit();
                            done.Add(string.Format("{0} - {1} fills, {2} lines, {3} texts",
                                entry.View.Name, job.Drawing.Fills.Count,
                                job.Drawing.Lines.Count, job.Drawing.Texts.Count));
                        }
                        catch (Exception ex)
                        {
                            t.RollBack();
                            failed.Add(entry.View.Name + " - " + ex.Message);
                        }
                    }
                }

                Summarise(done, skipped, failed);
                return failed.Count > 0 && done.Count == 0 ? Result.Failed : Result.Succeeded;
            }
            catch (Exception ex)
            {
                TaskDialog.Show("Crash Report", ex.ToString());
                return Result.Failed;
            }
        }

        // Refresh is an explicit action, so always report the outcome; failures
        // and skips have to be visible
        private static void Summarise(List<string> done, List<string> skipped,
                                      List<string> failed)
        {
            var lines = new List<string>
            {
                string.Format("{0} updated, {1} skipped, {2} failed",
                              done.Count, skipped.Count, failed.Count)
            };
            if (done.Count > 0)
                lines.Add("\nUpdated:\n  " + string.Join("\n  ", done));
            if (skipped.Count > 0)
                lines.Add("\nSkipped:\n  " + string.Join("\n  ", skipped));
            if (failed.Count > 0)
                lines.Add("\nFailed:\n  " + string.Join("\n  ", failed));

            TaskDialog.Show("EZTable Refresh", string.Join("\n", lines));
        }

        private class Entry
        {
            public Autodesk.Revit.DB.View View { get; }
            public Storage.Stamp Stamp { get; }
            public Storage.Freshness State { get; }
            public string Note { get; }

            public Entry(Autodesk.Revit.DB.View view, Storage.Stamp stamp)
            {
                View = view;
                Stamp = stamp;
                var status = Storage.IsStale(stamp);
                State = status.Item1;
                Note = status.Item2;
            }

            public string Label
            {
                get
                {
                    string state;
                    switch (State)
                    {
                        case Storage.Freshness.Stale: state = "changed"; break;
                        case Storage.Freshness.Fresh: state = "up to date"; break;
                        default: state = "source missing"; break;
                    }
                    string file;
                    try { file = System.IO.Path.GetFileName(Stamp.SourcePath ?? "?"); }
                    catch (Exception) { file = "?"; }

                    return string.Format("[{0}]  {1}  <-  {2} / {3}",
                        state.PadRight(14), View.Name, file, Stamp.SheetName ?? "?");
                }
            }
        }
    }
}
