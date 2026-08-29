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

        private static readonly string[] FIELDS =
        {
            F_SOURCE_PATH, F_SHEET_NAME, F_SOURCE_HASH, F_IMPORT_TIME, F_VERSION
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
                                      string sheetName, string sourceHash, string version)
        {
            Schema schema = GetSchema();
            var entity = new Entity(schema);
            entity.Set<string>(F_SOURCE_PATH, sourcePath ?? "");
            entity.Set<string>(F_SHEET_NAME, sheetName ?? "");
            entity.Set<string>(F_SOURCE_HASH, sourceHash ?? "");
            entity.Set<string>(F_IMPORT_TIME, DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss"));
            entity.Set<string>(F_VERSION, version ?? "");
            view.SetEntity(entity);
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
                    SourcePath = entity.Get<string>(F_SOURCE_PATH),
                    SheetName = entity.Get<string>(F_SHEET_NAME),
                    SourceHash = entity.Get<string>(F_SOURCE_HASH),
                    ImportTime = entity.Get<string>(F_IMPORT_TIME),
                    Version = entity.Get<string>(F_VERSION),
                };
            }
            catch (Exception)
            {
                // Revit throws when the view holds no data for this schema;
                // that is not an error
                return null;
            }
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
