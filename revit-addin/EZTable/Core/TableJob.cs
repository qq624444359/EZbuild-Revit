using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using Autodesk.Revit.DB;
using ClosedXML.Excel;
using EZTable.Models;

namespace EZTable.Core
{
    /// <summary>
    /// The pipeline shared by Import and Refresh -- the counterpart of job.py
    /// in the pyRevit version.
    ///
    /// Parse -> lay out -> draw -> stamp, all in one place, so both commands are
    /// only a thin layer of UI. Both paths must run the same code, or a
    /// refreshed table could drift from the one originally imported.
    /// </summary>
    public class TableJob
    {
        /// <summary>The three element classes EZTable draws into a view.</summary>
        private static readonly Type[] DRAWN_CLASSES =
        {
            typeof(CurveElement), typeof(FilledRegion), typeof(TextNote)
        };

        public string Path { get; }
        public string SheetName { get; }
        public SheetData Data { get; private set; }
        public Plan Drawing { get; private set; }
        public string SourceHash { get; private set; }
        public int Cleared { get; private set; }

        public TableJob(string path, string sheetName)
        {
            Path = path;
            SheetName = sheetName;
        }

        public static string Version
        {
            get
            {
                try
                {
                    return System.Reflection.Assembly.GetExecutingAssembly()
                        .GetName().Version.ToString();
                }
                catch (Exception) { return ""; }
            }
        }

        /// <summary>
        /// The read-only half: read the workbook and lay it out. No transaction
        /// needed -- reading the base text type's size only queries a parameter.
        ///
        /// The base cap height has to be known *before* layout, because when a
        /// project text type is reused it, not Excel's font size, is what decides
        /// wrapping and vertical centring.
        /// </summary>
        public TableJob Prepare(Document doc)
        {
            Config.EnsureLoaded();
            SourceHash = Revit.Storage.FileHash(Path);

            // FileShare.ReadWrite so the file can be read even while the user
            // has it open in Excel
            using (var fs = new FileStream(Path, FileMode.Open, FileAccess.Read,
                                           FileShare.ReadWrite))
            using (var wb = new XLWorkbook(fs))
            {
                Data = Utils.ExcelParser.ParseSheet(wb, SheetName);
            }
            double? baseCapFt = new Revit.StyleFactory(doc).BaseTextCapHeightFt();
            Drawing = Plan.BuildPlan(Data, baseCapFt);
            return this;
        }

        /// <summary>Create a new drafting view and draw into it. Must be called
        /// inside a transaction.</summary>
        public Autodesk.Revit.DB.View DrawNewView(Document doc)
        {
            var viewFamilyType = new FilteredElementCollector(doc)
                .OfClass(typeof(ViewFamilyType))
                .Cast<ViewFamilyType>()
                .FirstOrDefault(v => v.ViewFamily == ViewFamily.Drafting);

            if (viewFamilyType == null)
                throw new InvalidOperationException("No Drafting View type found in this project.");

            var view = ViewDrafting.Create(doc, viewFamilyType.Id);
            view.Scale = 1;
            AssignUniqueName(view, ViewName(SheetName, Path));

            var factory = new Revit.StyleFactory(doc);
            Revit.Renderer.DrawPlan(doc, view, Drawing, factory);
            Stamp(view);
            return view;
        }

        /// <summary>
        /// Clear and redraw. **The view itself is never deleted** -- its id
        /// survives, so viewports already placed on sheets stay valid and do
        /// not move. Must be called inside a transaction.
        ///
        /// Note that every detail line, filled region and text note in the view
        /// is deleted, including anything added by hand. Treat an EZTable view
        /// as a read-only artifact and put annotation on the sheet instead.
        /// </summary>
        public Autodesk.Revit.DB.View RedrawView(Document doc, Autodesk.Revit.DB.View view)
        {
            Cleared = ClearView(doc, view);
            var factory = new Revit.StyleFactory(doc);
            Revit.Renderer.DrawPlan(doc, view, Drawing, factory);
            Stamp(view);
            return view;
        }

        private void Stamp(Autodesk.Revit.DB.View view)
        {
            Revit.Storage.WriteStamp(view, System.IO.Path.GetFullPath(Path),
                                     SheetName, SourceHash, Version);
        }

        /// <summary>Delete what EZTable drew into a view. Must be called inside
        /// a transaction. -> number of elements deleted</summary>
        public static int ClearView(Document doc, Autodesk.Revit.DB.View view)
        {
            var ids = new List<ElementId>();
            foreach (Type cls in DRAWN_CLASSES)
            {
                ids.AddRange(new FilteredElementCollector(doc, view.Id)
                    .OfClass(cls)
                    .WhereElementIsNotElementType()
                    .ToElementIds());
            }
            if (ids.Count == 0) return 0;
            doc.Delete(ids);
            return ids.Count;
        }

        /// <summary>Build a view name from Config.ViewNameTemplate.</summary>
        public static string ViewName(string sheetName, string filePath)
        {
            Config.EnsureLoaded();
            string template = Config.ViewNameTemplate ?? "Table";
            string file = "";
            try
            {
                if (!string.IsNullOrEmpty(filePath))
                    file = System.IO.Path.GetFileNameWithoutExtension(filePath);
            }
            catch (Exception) { }

            return template
                .Replace("{sheet}", sheetName ?? "")
                .Replace("{file}", file);
        }

        /// <summary>
        /// Append a (1) (2) suffix when the name is taken. Revit throws an
        /// ArgumentException on a duplicate and offers no "is this name free?"
        /// query, so trying is the only option.
        /// </summary>
        private static void AssignUniqueName(Autodesk.Revit.DB.View view, string name)
        {
            string baseName = string.IsNullOrWhiteSpace(name) ? "Table" : name;
            for (int i = 0; i < 100; i++)
            {
                string candidate = i == 0 ? baseName : string.Format("{0} ({1})", baseName, i);
                try
                {
                    view.Name = candidate;
                    return;
                }
                catch (Exception)
                {
                    // name taken, try the next one
                }
            }
            // All 100 collided; fall back to a timestamped name so the view is
            // guaranteed to be created
            view.Name = baseName + " " + DateTime.Now.ToString("HHmmss");
        }
    }
}
