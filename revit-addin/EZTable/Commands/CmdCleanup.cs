using System;
using System.Collections.Generic;
using System.Linq;
using Autodesk.Revit.Attributes;
using Autodesk.Revit.DB;
using Autodesk.Revit.UI;
using EZTable.Core;
using TaskDialog = Autodesk.Revit.UI.TaskDialog;

namespace EZTable.Commands
{
    /// <summary>
    /// Cleanup -- delete the unused generated types left in the project.
    ///
    /// Both prefixes are scanned. EZ_ is what the tool creates now; XL_ is what it
    /// created when the extension was still called XLTable.
    ///
    /// Only types **no element uses** are deleted.
    /// </summary>
    [Transaction(TransactionMode.Manual)]
    public class CmdCleanup : IExternalCommand
    {
        private static readonly string[] Prefixes = { "EZ_", "XL_" };

        private static bool Prefixed(string name)
        {
            if (string.IsNullOrEmpty(name)) return false;
            foreach (var p in Prefixes)
                if (name.StartsWith(p)) return true;
            return false;
        }

        private static bool IsGeneratedText(string name)
        {
            return Prefixed(name) || Config.IsDerivedTextName(name);
        }

        private static bool IsGeneratedFill(string name)
        {
            return Prefixed(name) || Config.IsGeneratedFillName(name);
        }

        private class Candidate
        {
            public string Kind { get; }
            public string Name { get; }
            public ElementId Id { get; }
            public bool InUse { get; }

            public Candidate(string kind, string name, ElementId id, bool inUse)
            {
                Kind = kind;
                Name = name;
                Id = id;
                InUse = inUse;
            }
        }

        public Result Execute(ExternalCommandData commandData, ref string message, ElementSet elements)
        {
            try
            {
                Document doc = commandData.Application.ActiveUIDocument.Document;
                var candidates = CollectCandidates(doc);

                if (candidates.Count == 0)
                {
                    TaskDialog.Show("EZTable Cleanup",
                        "Nothing to clean up.\n\n" +
                        "No leftover line styles or patterns (EZ_* / XL_*), and no " +
                        "unused fill or text types generated from your standards (" +
                        (Config.GreyFillTypeName ?? "auto") + " / " +
                        (Config.BaseTextTypeName ?? "auto") + ").\n\n" +
                        "Types you maintain yourself are never listed here.");
                    return Result.Succeeded;
                }

                var unused = candidates.Where(c => !c.InUse).ToList();
                var inUse = candidates.Where(c => c.InUse).ToList();

                if (unused.Count == 0)
                {
                    TaskDialog.Show("EZTable Cleanup",
                        $"All {candidates.Count} generated items are still in use - nothing to delete.");
                    return Result.Succeeded;
                }

                // Show UI to pick what to delete
                var rows = unused.Select((c, i) => new UI.RefreshSelector.Row(i, $"{c.Kind,-20} {c.Name}")).ToList();
                
                // Preselect all of them by default
                var preselect = Enumerable.Range(0, unused.Count).ToList();

                var dialog = new UI.RefreshSelector(rows, preselect)
                {
                    Title = "Unused EZTable leftovers - select what to delete"
                };

                if (dialog.ShowDialog() != true || dialog.SelectedIndices.Count == 0)
                    return Result.Cancelled;

                var toDelete = dialog.SelectedIndices.Select(i => unused[i].Id).ToList();
                int deletedCount = 0;

                using (var t = new Transaction(doc, "EZTable: Cleanup"))
                {
                    t.Start();
                    try
                    {
                        var deletedIds = doc.Delete(toDelete);
                        deletedCount = deletedIds?.Count ?? toDelete.Count;
                        t.Commit();
                    }
                    catch (Exception ex)
                    {
                        t.RollBack();
                        TaskDialog.Show("EZTable Cleanup", "Delete failed and was rolled back:\n" + ex.Message);
                        return Result.Failed;
                    }
                }

                string msg = $"Deleted {dialog.SelectedIndices.Count} items ({deletedCount} elements removed in total).\n\n";
                if (inUse.Count > 0)
                {
                    msg += $"Still in use ({inUse.Count} items, left alone):\n";
                    int count = 0;
                    foreach (var u in inUse)
                    {
                        if (++count > 10)
                        {
                            msg += $"... and {inUse.Count - 10} more";
                            break;
                        }
                        msg += $"- {u.Kind} '{u.Name}'\n";
                    }
                }
                
                TaskDialog.Show("EZTable Cleanup", msg);
                return Result.Succeeded;
            }
            catch (Exception ex)
            {
                TaskDialog.Show("Crash Report", ex.ToString());
                return Result.Failed;
            }
        }

        private List<Candidate> CollectCandidates(Document doc)
        {
            var usedText = new HashSet<ElementId>();
            foreach (TextNote note in new FilteredElementCollector(doc).OfClass(typeof(TextNote)).WhereElementIsNotElementType())
            {
                usedText.Add(note.GetTypeId());
            }

            var usedFill = new HashSet<ElementId>();
            foreach (FilledRegion region in new FilteredElementCollector(doc).OfClass(typeof(FilledRegion)).WhereElementIsNotElementType())
            {
                usedFill.Add(region.GetTypeId());
            }

            var usedStyle = new HashSet<ElementId>();
            foreach (CurveElement curve in new FilteredElementCollector(doc).OfClass(typeof(CurveElement)).WhereElementIsNotElementType())
            {
                try
                {
                    var gs = curve.LineStyle;
                    if (gs != null) usedStyle.Add(gs.Id);
                }
                catch { }
            }

            var outList = new List<Candidate>();

            foreach (TextNoteType t in new FilteredElementCollector(doc).OfClass(typeof(TextNoteType)))
            {
                if (IsGeneratedText(t.Name))
                    outList.Add(new Candidate("Text type", t.Name, t.Id, usedText.Contains(t.Id)));
            }

            foreach (FilledRegionType t in new FilteredElementCollector(doc).OfClass(typeof(FilledRegionType)))
            {
                if (IsGeneratedFill(t.Name))
                    outList.Add(new Candidate("Filled region type", t.Name, t.Id, usedFill.Contains(t.Id)));
            }

            var usedPatterns = new HashSet<ElementId>();
            var linesCat = doc.Settings.Categories.get_Item(BuiltInCategory.OST_Lines);
            if (linesCat != null)
            {
                foreach (Category sub in linesCat.SubCategories)
                {
                    try
                    {
                        var pid = sub.GetLinePatternId(GraphicsStyleType.Projection);
                        if (pid != null && pid != ElementId.InvalidElementId)
                            usedPatterns.Add(pid);
                    }
                    catch { }

                    if (Prefixed(sub.Name))
                    {
                        var gs = sub.GetGraphicsStyle(GraphicsStyleType.Projection);
                        bool inUse = gs != null && usedStyle.Contains(gs.Id);
                        outList.Add(new Candidate("Line style", sub.Name, sub.Id, inUse));
                    }
                }
            }

            foreach (LinePatternElement lp in new FilteredElementCollector(doc).OfClass(typeof(LinePatternElement)))
            {
                if (Prefixed(lp.Name))
                    outList.Add(new Candidate("Line pattern", lp.Name, lp.Id, usedPatterns.Contains(lp.Id)));
            }

            return outList.OrderBy(c => c.Kind).ThenBy(c => c.Name).ToList();
        }
    }
}
