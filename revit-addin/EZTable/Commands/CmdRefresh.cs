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
    ///
    /// A table too tall for one sheet lives in several views, one part each.
    /// Those are refreshed as a unit: redrawing one part on its own would leave
    /// the others showing an older revision of the same workbook.
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

                var stamped = Storage.FindTables(doc);
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
                    .Select(members => new Entry(members))
                    .OrderByDescending(e => hasActive && e.Views.Any(v => v.Id.Equals(activeId)))
                    .ThenBy(e => e.Views[0].Name)
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
                var created = new List<string>();
                var emptied = new List<string>();

                foreach (int index in dialog.SelectedIndices)
                {
                    if (index < 0 || index >= entries.Count) continue;
                    Entry entry = entries[index];

                    if (entry.State == Storage.Freshness.Missing)
                    {
                        failed.Add(entry.Views[0].Name + " - " + entry.Note);
                        continue;
                    }
                    if (entry.State == Storage.Freshness.Fresh)
                    {
                        skipped.Add(entry.Views[0].Name + " - unchanged, skipped");
                        continue;
                    }

                    // One transaction per table -- every part of it included, so a
                    // single failure cannot leave one part on a newer revision
                    // than the rest, nor roll back the tables already refreshed
                    using (var t = new Transaction(doc, "EZTable: Refresh Table"))
                    {
                        t.Start();
                        try
                        {
                            var job = new TableJob(entry.Stamp.SourcePath,
                                                   entry.Stamp.SheetName).Prepare(doc);
                            var outcome = job.RedrawViews(doc, entry.Views);
                            t.Commit();

                            int fills = job.Drawings.Sum(d => d.Fills.Count);
                            int lines = job.Drawings.Sum(d => d.Lines.Count);
                            int texts = job.Drawings.Sum(d => d.Texts.Count);
                            done.Add(string.Format("{0} - {1} fills, {2} lines, {3} texts{4}",
                                string.Join(", ", outcome.Item1.Select(v => v.Name)),
                                fills, lines, texts,
                                job.PartCount > 1
                                    ? string.Format(" ({0} parts)", job.PartCount) : ""));
                            created.AddRange(outcome.Item2.Select(v => v.Name));
                            emptied.AddRange(outcome.Item3.Select(v => v.Name));
                        }
                        catch (Exception ex)
                        {
                            t.RollBack();
                            failed.Add(entry.Views[0].Name + " - " + ex.Message);
                        }
                    }
                }

                Summarise(done, skipped, failed, created, emptied);
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
                                      List<string> failed, List<string> created,
                                      List<string> emptied)
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

            // A workbook that grew or shrank changes how many sheets its table
            // needs. Both directions need saying out loud: a new view is not on
            // a sheet yet, and an emptied one is still sitting on the sheet it
            // was placed on.
            if (created.Count > 0)
                lines.Add("\nNew parts - place these on sheets:\n  "
                          + string.Join("\n  ", created));
            if (emptied.Count > 0)
                lines.Add("\nNo longer needed. Emptied but NOT deleted, since a "
                          + "viewport may still be placed on a sheet:\n  "
                          + string.Join("\n  ", emptied));

            TaskDialog.Show("EZTable Refresh", string.Join("\n", lines));
        }

        /// <summary>One table: every view it is split across, and the state of
        /// the workbook behind them.</summary>
        private class Entry
        {
            public List<Autodesk.Revit.DB.View> Views { get; }
            public Storage.Stamp Stamp { get; }
            public Storage.Freshness State { get; }
            public string Note { get; }

            public Entry(List<Tuple<Autodesk.Revit.DB.View, Storage.Stamp>> members)
            {
                Views = members.Select(m => m.Item1).ToList();
                Stamp = members[0].Item2;
                var status = Storage.IsStale(Stamp);
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

                    string name = Views[0].Name;
                    if (Views.Count > 1)
                        name = string.Format("{0} + {1} more", name, Views.Count - 1);

                    return string.Format("[{0}]  {1}  <-  {2} / {3}",
                        state.PadRight(14), name, file, Stamp.SheetName ?? "?");
                }
            }
        }
    }
}
