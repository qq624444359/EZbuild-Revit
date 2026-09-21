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

        /// <summary>One entry per part: a table too tall for one sheet is drawn
        /// into a drafting view apiece. Holds a single item for a table that
        /// fits.</summary>
        public List<Plan> Drawings { get; private set; } = new List<Plan>();
        public string SourceHash { get; private set; }
        public int Cleared { get; private set; }

        public int PartCount => Drawings.Count;

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
            Drawings = Plan.BuildPlans(Data, baseCapFt);
            return this;
        }

        /// <summary>Draw every part into a new drafting view of its own. Must be
        /// called inside a transaction. -> the views, in part order; a table that
        /// fits one sheet gives a single view with the plain name, no (1/2)
        /// suffix.</summary>
        public List<Autodesk.Revit.DB.View> DrawNewViews(Document doc)
        {
            var factory = new Revit.StyleFactory(doc);
            string baseName = ViewName(SheetName, Path);
            var views = new List<Autodesk.Revit.DB.View>();

            foreach (var drawing in Drawings)
            {
                var view = CreateDraftingView(doc,
                    PartViewName(baseName, drawing.Part, drawing.PartCount));
                Revit.Renderer.DrawPlan(doc, view, drawing, factory);
                Stamp(view, drawing);
                views.Add(view);
            }
            return views;
        }

        /// <summary>
        /// Clear and redraw a table's parts into the views it already owns. Must
        /// be called inside a transaction.
        /// -> (views in part order, views newly created, views emptied because
        /// the table shrank)
        ///
        /// **An existing view is never deleted** -- its id survives, so viewports
        /// already placed on sheets stay valid and do not move. That holds for a
        /// part that has gone away as well: its view is emptied and reported, and
        /// removing it from the sheet is left to whoever placed it there. A
        /// workbook that grew needs more parts than there are views; the extra
        /// ones are created here and have to be placed on sheets by hand.
        ///
        /// Note that every detail line, filled region and text note in each view
        /// is deleted, including anything added by hand. Treat an EZTable view
        /// as a read-only artifact and put annotation on the sheet instead.
        /// </summary>
        public Tuple<List<Autodesk.Revit.DB.View>, List<Autodesk.Revit.DB.View>, List<Autodesk.Revit.DB.View>>
            RedrawViews(Document doc, List<Autodesk.Revit.DB.View> views)
        {
            var factory = new Revit.StyleFactory(doc);
            string baseName = BaseViewName(views.Count > 0 ? views[0].Name : "Table");

            var drawn = new List<Autodesk.Revit.DB.View>();
            var created = new List<Autodesk.Revit.DB.View>();

            for (int i = 0; i < Drawings.Count; i++)
            {
                var drawing = Drawings[i];
                string name = PartViewName(baseName, drawing.Part, drawing.PartCount);
                Autodesk.Revit.DB.View view;
                if (i < views.Count)
                {
                    view = views[i];
                    Cleared += ClearView(doc, view);
                    // Only moves when the part count changed: otherwise the name
                    // already is what PartViewName builds.
                    RenameView(view, name);
                }
                else
                {
                    view = CreateDraftingView(doc, name);
                    created.Add(view);
                }
                Revit.Renderer.DrawPlan(doc, view, drawing, factory);
                Stamp(view, drawing);
                drawn.Add(view);
            }

            var emptied = new List<Autodesk.Revit.DB.View>();
            for (int i = Drawings.Count; i < views.Count; i++)
            {
                Cleared += ClearView(doc, views[i]);
                Revit.Storage.ClearStamp(views[i]);
                emptied.Add(views[i]);
            }

            return Tuple.Create(drawn, created, emptied);
        }

        /// <summary>A 1:1 drafting view with a free name. Must be called inside a
        /// transaction.</summary>
        private static Autodesk.Revit.DB.View CreateDraftingView(Document doc, string name)
        {
            var viewFamilyType = new FilteredElementCollector(doc)
                .OfClass(typeof(ViewFamilyType))
                .Cast<ViewFamilyType>()
                .FirstOrDefault(v => v.ViewFamily == ViewFamily.Drafting);

            if (viewFamilyType == null)
                throw new InvalidOperationException("No Drafting View type found in this project.");

            var view = ViewDrafting.Create(doc, viewFamilyType.Id);
            view.Scale = 1;
            AssignUniqueName(view, name);
            return view;
        }

        private void Stamp(Autodesk.Revit.DB.View view, Plan drawing)
        {
            Revit.Storage.WriteStamp(view, System.IO.Path.GetFullPath(Path),
                                     SheetName, SourceHash, Version,
                                     drawing.Part, drawing.PartCount);
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
        /// Name of one part of a table split across several views. A single-part
        /// table keeps its plain name -- no "(1/1)" on a table never split.
        /// </summary>
        public static string PartViewName(string name, int part, int parts)
        {
            if (parts <= 1) return name;
            Config.EnsureLoaded();
            string template = Config.PartNameTemplate ?? "{name} ({part}/{parts})";
            return template
                .Replace("{name}", name ?? "")
                .Replace("{part}", part.ToString())
                .Replace("{parts}", parts.ToString());
        }

        /// <summary>
        /// Strip the part suffix off a view name, so a refreshed table keeps the
        /// name it was imported with even when its part count changes. Covers
        /// both " (2/3)" and the " (1)" Revit-style suffix a duplicate picks up.
        /// </summary>
        public static string BaseViewName(string name)
        {
            string stripped = System.Text.RegularExpressions.Regex
                .Replace(name ?? "", @"\s*\(\d+\s*(?:/\s*\d+)?\)\s*$", "")
                .Trim();
            return string.IsNullOrEmpty(stripped) ? "Table" : stripped;
        }

        /// <summary>
        /// Rename an existing view, used when a refresh changes how many parts a
        /// table needs and the "(1/2)" suffixes no longer match. A name that is
        /// already right costs nothing, and one that cannot be taken is left
        /// alone: a stale suffix is a far smaller problem than a failed refresh.
        /// </summary>
        private static void RenameView(Autodesk.Revit.DB.View view, string name)
        {
            try
            {
                if (view.Name == name) return;
                AssignUniqueName(view, name);
            }
            catch (Exception) { }
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
