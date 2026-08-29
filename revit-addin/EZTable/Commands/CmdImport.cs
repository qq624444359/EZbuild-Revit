using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using Autodesk.Revit.Attributes;
using Autodesk.Revit.DB;
using Autodesk.Revit.UI;
using EZTable.Core;
using TaskDialog = Autodesk.Revit.UI.TaskDialog;

namespace EZTable.Commands
{
    /// <summary>
    /// Import Excel -- draw an Excel worksheet into a Revit drafting view,
    /// styling intact.
    ///
    /// The import stamps the view with its source (file path, worksheet name,
    /// MD5); that stamp is how Refresh recognises where the view came from.
    /// </summary>
    [Transaction(TransactionMode.Manual)]
    public class CmdImport : IExternalCommand
    {
        public Result Execute(ExternalCommandData commandData, ref string message,
                              ElementSet elements)
        {
            try
            {
                UIDocument uidoc = commandData.Application.ActiveUIDocument;
                Document doc = uidoc.Document;

                using (var ofd = new System.Windows.Forms.OpenFileDialog
                {
                    Filter = "Excel Files|*.xlsx",
                    Title = "Select an Excel File"
                })
                {
                    if (ofd.ShowDialog() != System.Windows.Forms.DialogResult.OK)
                        return Result.Cancelled;

                    string filePath = ofd.FileName;
                    string sheetName = PickSheet(filePath);
                    if (sheetName == null)
                        return Result.Cancelled;

                    TableJob job;
                    try
                    {
                        job = new TableJob(filePath, sheetName).Prepare(doc);
                    }
                    catch (Exception ex)
                    {
                        TaskDialog.Show("EZTable",
                            "Could not read the worksheet:\n\n" + ex.Message);
                        return Result.Failed;
                    }

                    Autodesk.Revit.DB.View view;
                    using (var t = new Transaction(doc, "EZTable: Import Excel Table"))
                    {
                        t.Start();
                        try
                        {
                            view = job.DrawNewView(doc);
                            t.Commit();
                        }
                        catch (Exception ex)
                        {
                            t.RollBack();
                            TaskDialog.Show("EZTable",
                                "Drawing failed and was rolled back:\n\n" + ex.ToString());
                            return Result.Failed;
                        }
                    }

                    // Switch to the new view once drawn. Must happen after the
                    // transaction commits.
                    try { uidoc.ActiveView = view; } catch (Exception) { }

                    ReportIfNeeded(job);
                    return Result.Succeeded;
                }
            }
            catch (Exception ex)
            {
                TaskDialog.Show("Crash Report", ex.ToString());
                return Result.Failed;
            }
        }

        /// <summary>Use the only worksheet when there is one, otherwise show the
        /// picker. Returns null when cancelled.</summary>
        private static string PickSheet(string filePath)
        {
            List<string> sheetNames;
            // FileShare.ReadWrite so the file can be read even while the user
            // has it open in Excel
            using (var fs = new FileStream(filePath, FileMode.Open, FileAccess.Read,
                                           FileShare.ReadWrite))
            using (var wb = new ClosedXML.Excel.XLWorkbook(fs))
            {
                sheetNames = wb.Worksheets.Select(ws => ws.Name).ToList();
            }

            if (sheetNames.Count == 0)
                throw new InvalidOperationException("That workbook has no worksheets.");
            if (sheetNames.Count == 1)
                return sheetNames[0];

            var selector = new UI.SheetSelector(sheetNames);
            return selector.ShowDialog() == true ? selector.SelectedSheet : null;
        }

        /// <summary>
        /// Only open a window when there is something worth saying. A successful
        /// import already announces itself by switching to the new view, so
        /// normally a second dialog is just noise.
        /// </summary>
        private static void ReportIfNeeded(TableJob job)
        {
            var lines = new List<string>();
            lines.AddRange(Config.LoadWarnings);
            if (job.Data?.Warnings != null)
                lines.AddRange(job.Data.Warnings);

            if (lines.Count == 0) return;

            const int MAX_SHOWN = 20;
            string body = string.Join("\n", lines.Take(MAX_SHOWN).Select(w => "- " + w));
            if (lines.Count > MAX_SHOWN)
                body += string.Format("\n... and {0} more", lines.Count - MAX_SHOWN);

            TaskDialog.Show("EZTable - imported with warnings", body);
        }
    }
}
