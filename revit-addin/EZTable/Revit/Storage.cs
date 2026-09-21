using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using Autodesk.Revit.DB;
using Autodesk.Revit.DB.ExtensibleStorage;

namespace EZTable.Revit
{
    /// <summary>
    /// Records which Excel a view came from, via Extensible Storage.
    /// Refresh compares the MD5 to tell whether the source file has changed.
    ///
    /// **The schema GUID, name and field set must match storage.py in the
    /// pyRevit version exactly** -- that is what lets either version recognise
    /// views imported by the other. The GUID is the sole identity: schemas are
    /// looked up by GUID, so the name and vendor id are cosmetic, but they still
    /// have to agree across both sides. Changing the GUID orphans every view
    /// imported so far.
    ///
    /// **Adding a field is not retroactive.** A document stamped before
    /// Part/PartCount existed already holds the five-field schema, and
    /// Schema.Lookup returns that one; the GUID cannot change, so the new fields
    /// are simply absent there. Every read and write below therefore skips a
    /// field the document's schema does not have, and a missing part reads as
    /// part 1 of 1 -- which is what those views are.
    /// </summary>
    public static class Storage
    {
        // Identical, character for character, to
        // pyrevit/EZbuild.extension/lib/eztable/storage.py -- do not change
        private static readonly Guid SCHEMA_GUID =
            new Guid("7b2f1a54-3c9d-4e6b-8a11-5f0d2c9e4a77");
        private const string SCHEMA_NAME = "EZTableSource";
        private const string VENDOR_ID = "EZTB";

        public const string F_SOURCE_PATH = "SourcePath";
        public const string F_SHEET_NAME = "SheetName";
        public const string F_SOURCE_HASH = "SourceHash";
        public const string F_IMPORT_TIME = "ImportTime";
        public const string F_VERSION = "Version";
        public const string F_PART = "Part";
        public const string F_PART_COUNT = "PartCount";

        private static readonly string[] FIELDS =
        {
            F_SOURCE_PATH, F_SHEET_NAME, F_SOURCE_HASH, F_IMPORT_TIME, F_VERSION,
            F_PART, F_PART_COUNT
        };

        /// <summary>Look it up, create it if absent. Building a schema does not
        /// modify the document, so no transaction is needed.</summary>
        public static Schema GetSchema()
        {
            Schema schema = Schema.Lookup(SCHEMA_GUID);
            if (schema != null) return schema;

            var builder = new SchemaBuilder(SCHEMA_GUID);
            builder.SetSchemaName(SCHEMA_NAME);
            builder.SetVendorId(VENDOR_ID);
            builder.SetReadAccessLevel(AccessLevel.Public);
            builder.SetWriteAccessLevel(AccessLevel.Public);
            foreach (string name in FIELDS)
                builder.AddSimpleField(name, typeof(string));
            return builder.Finish();
        }

        /// <summary>Stamp the source onto a view. Must be called inside a
        /// transaction.</summary>
        public static void WriteStamp(Autodesk.Revit.DB.View view, string sourcePath,
                                      string sheetName, string sourceHash, string version,
                                      int part = 1, int partCount = 1)
        {
            Schema schema = GetSchema();
            var entity = new Entity(schema);
            var values = new Dictionary<string, string>
            {
                { F_SOURCE_PATH, sourcePath ?? "" },
                { F_SHEET_NAME, sheetName ?? "" },
                { F_SOURCE_HASH, sourceHash ?? "" },
                { F_IMPORT_TIME, DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss") },
                { F_VERSION, version ?? "" },
                { F_PART, Math.Max(1, part).ToString() },
                { F_PART_COUNT, Math.Max(1, partCount).ToString() },
            };
            foreach (string name in FIELDS)
            {
                Field field = schema.GetField(name);
                if (field == null) continue;   // older schema here; see the header
                entity.Set<string>(field, values[name]);
            }
            view.SetEntity(entity);
        }

        /// <summary>Un-stamp a view, so Refresh stops offering it. Must be called
        /// inside a transaction. Used when a table shrinks and a part is left
        /// with no content.</summary>
        public static bool ClearStamp(Autodesk.Revit.DB.View view)
        {
            try
            {
                view.DeleteEntity(GetSchema());
                return true;
            }
            catch (Exception) { return false; }
        }

        /// <summary>Read the stamp; returns null for a view that carries none.</summary>
        public static Stamp ReadStamp(Autodesk.Revit.DB.View view)
        {
            try
            {
                Schema schema = Schema.Lookup(SCHEMA_GUID);
                if (schema == null) return null;

                Entity entity = view.GetEntity(schema);
                if (entity == null || !entity.IsValid()) return null;

                return new Stamp
                {
                    SourcePath = Read(schema, entity, F_SOURCE_PATH, ""),
                    SheetName = Read(schema, entity, F_SHEET_NAME, ""),
                    SourceHash = Read(schema, entity, F_SOURCE_HASH, ""),
                    ImportTime = Read(schema, entity, F_IMPORT_TIME, ""),
                    Version = Read(schema, entity, F_VERSION, ""),
                    Part = Number(Read(schema, entity, F_PART, "1")),
                    PartCount = Number(Read(schema, entity, F_PART_COUNT, "1")),
                };
            }
            catch (Exception)
            {
                // Revit throws when the view holds no data for this schema;
                // that is not an error
                return null;
            }
        }

        /// <summary>One field, or the fallback when this document's schema
        /// predates it.</summary>
        private static string Read(Schema schema, Entity entity, string name, string fallback)
        {
            Field field = schema.GetField(name);
            if (field == null) return fallback;
            return entity.Get<string>(field) ?? fallback;
        }

        private static int Number(string value)
        {
            int n;
            return int.TryParse(value, out n) && n > 0 ? n : 1;
        }

        /// <summary>
        /// What makes two views parts of the same table: the source file and the
        /// worksheet. Paths are compared case-insensitively and normalised,
        /// because Windows hands back the same file under more than one spelling.
        /// </summary>
        public static string TableKey(Stamp stamp)
        {
            string path = stamp?.SourcePath ?? "";
            try { path = System.IO.Path.GetFullPath(path); }
            catch (Exception) { }
            return path.ToLowerInvariant() + "|" + (stamp?.SheetName ?? "");
        }

        /// <summary>
        /// The stamped views grouped into the tables they belong to, each list in
        /// part order and sorted by its first view's name.
        ///
        /// A table split across several sheets is refreshed as a unit: redrawing
        /// one part on its own would leave the others showing a different
        /// revision of the same workbook.
        /// </summary>
        public static List<List<Tuple<Autodesk.Revit.DB.View, Stamp>>> FindTables(Document doc)
        {
            var groups = new Dictionary<string, List<Tuple<Autodesk.Revit.DB.View, Stamp>>>();
            foreach (var pair in FindStampedViews(doc))
            {
                string key = TableKey(pair.Item2);
                if (!groups.ContainsKey(key))
                    groups[key] = new List<Tuple<Autodesk.Revit.DB.View, Stamp>>();
                groups[key].Add(pair);
            }

            var tables = groups.Values.ToList();
            foreach (var members in tables)
            {
                // By recorded part, with the view name to settle stamps that
                // predate the Part field (all of which read as part 1)
                members.Sort((a, b) => a.Item2.Part != b.Item2.Part
                    ? a.Item2.Part.CompareTo(b.Item2.Part)
                    : string.Compare(a.Item1.Name, b.Item1.Name, StringComparison.Ordinal));
            }
            tables.Sort((a, b) => string.Compare(a[0].Item1.Name, b[0].Item1.Name,
                                                 StringComparison.Ordinal));
            return tables;
        }

        /// <summary>Every stamped drafting view in the project.</summary>
        public static List<Tuple<Autodesk.Revit.DB.View, Stamp>> FindStampedViews(Document doc)
        {
            var found = new List<Tuple<Autodesk.Revit.DB.View, Stamp>>();
            foreach (var view in new FilteredElementCollector(doc)
                         .OfClass(typeof(ViewDrafting))
                         .Cast<ViewDrafting>())
            {
                if (view.IsTemplate) continue;
                Stamp stamp = ReadStamp(view);
                if (stamp != null)
                    found.Add(Tuple.Create((Autodesk.Revit.DB.View)view, stamp));
            }
            return found;
        }

        /// <summary>MD5 of the source file, matching xlreader.file_hash.</summary>
        public static string FileHash(string path)
        {
            // FileShare.ReadWrite so the hash can be computed even while the
            // user has the file open in Excel
            using (var stream = new FileStream(path, FileMode.Open, FileAccess.Read,
                                               FileShare.ReadWrite))
            using (var md5 = System.Security.Cryptography.MD5.Create())
            {
                byte[] hash = md5.ComputeHash(stream);
                var sb = new System.Text.StringBuilder(hash.Length * 2);
                foreach (byte b in hash) sb.Append(b.ToString("x2"));
                return sb.ToString();
            }
        }

        public class Stamp
        {
            public string SourcePath { get; set; }
            public string SheetName { get; set; }
            public string SourceHash { get; set; }
            public string ImportTime { get; set; }
            public string Version { get; set; }
            public int Part { get; set; } = 1;
            public int PartCount { get; set; } = 1;
        }

        public enum Freshness { Stale, Fresh, Missing }

        /// <summary>Has the source file changed? -> (state, human-readable
        /// explanation)</summary>
        public static Tuple<Freshness, string> IsStale(Stamp stamp)
        {
            string path = stamp?.SourcePath ?? "";
            if (string.IsNullOrEmpty(path) || !File.Exists(path))
                return Tuple.Create(Freshness.Missing,
                    "Source file not found: " + (string.IsNullOrEmpty(path) ? "(empty)" : path));
            try
            {
                string current = FileHash(path);
                return current != (stamp.SourceHash ?? "")
                    ? Tuple.Create(Freshness.Stale, "changed")
                    : Tuple.Create(Freshness.Fresh, "up to date");
            }
            catch (Exception ex)
            {
                return Tuple.Create(Freshness.Missing, "Source file unreadable: " + ex.Message);
            }
        }
    }
}
