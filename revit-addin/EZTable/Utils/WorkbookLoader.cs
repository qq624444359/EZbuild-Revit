using System;
using System.IO;
using System.IO.Compression;
using System.Linq;
using System.Xml;
using System.Xml.Linq;
using ClosedXML.Excel;

namespace EZTable.Utils
{
    /// <summary>
    /// Opens an .xlsx with ClosedXML, tolerating a malformed docProps/core.xml.
    ///
    /// System.IO.Packaging is far stricter about the document properties
    /// (author, last-modified-by, ...) than Excel is: an attribute it does not
    /// expect on one of them -- WPS and some exporters write e.g. xml:lang on
    /// cp:lastModifiedBy -- throws "Unexpected number of attributes is found
    /// on 'cp:lastModifiedBy'" and the whole workbook fails to load, although
    /// Excel opens it fine. Those properties play no part in drawing the table,
    /// so on that failure the file is loaded again from an in-memory copy with
    /// core.xml cleaned up. The file on disk is never touched.
    /// </summary>
    public static class WorkbookLoader
    {
        private const string CorePropsPath = "docProps/core.xml";
        private static readonly XNamespace Xsi = "http://www.w3.org/2001/XMLSchema-instance";
        private static readonly XNamespace DcTerms = "http://purl.org/dc/terms/";

        public static XLWorkbook Open(string path)
        {
            var mem = new MemoryStream();
            // FileShare.ReadWrite so the file can be read even while the user
            // has it open in Excel
            using (var fs = new FileStream(path, FileMode.Open, FileAccess.Read,
                                           FileShare.ReadWrite))
            {
                fs.CopyTo(mem);
            }

            try
            {
                mem.Position = 0;
                return new XLWorkbook(mem);
            }
            catch (XmlException)
            {
                if (!SanitizeCoreProperties(mem))
                    throw;
                mem.Position = 0;
                return new XLWorkbook(mem);
            }
        }

        /// <summary>Rewrite core.xml inside the package in place, keeping only
        /// what System.IO.Packaging accepts. Returns false when there was
        /// nothing to clean, i.e. the failure lies elsewhere.</summary>
        private static bool SanitizeCoreProperties(MemoryStream package)
        {
            package.Position = 0;
            using (var zip = new ZipArchive(package, ZipArchiveMode.Update, leaveOpen: true))
            {
                var entry = zip.Entries.FirstOrDefault(e =>
                    string.Equals(e.FullName, CorePropsPath, StringComparison.OrdinalIgnoreCase));
                if (entry == null) return false;

                XDocument doc;
                using (var s = entry.Open())
                {
                    try { doc = XDocument.Load(s); }
                    catch (XmlException) { doc = null; }
                }

                bool changed = false;
                if (doc?.Root == null)
                {
                    // Unreadable at all: an empty property set is still valid
                    doc = new XDocument(new XElement(
                        XName.Get("coreProperties",
                            "http://schemas.openxmlformats.org/package/2006/metadata/core-properties")));
                    changed = true;
                }
                else
                {
                    var seen = new System.Collections.Generic.HashSet<XName>();
                    foreach (var el in doc.Root.Elements().ToList())
                    {
                        // Each property may appear only once
                        if (!seen.Add(el.Name))
                        {
                            el.Remove();
                            changed = true;
                            continue;
                        }
                        // Properties hold plain text; nested markup is rejected
                        if (el.HasElements)
                        {
                            el.ReplaceNodes(el.Value);
                            changed = true;
                        }
                        // No attributes allowed, bar xsi:type on the two dates
                        bool isDate = el.Name == DcTerms + "created"
                                   || el.Name == DcTerms + "modified";
                        foreach (var a in el.Attributes().ToList())
                        {
                            if (a.IsNamespaceDeclaration) continue;
                            if (isDate && a.Name == Xsi + "type") continue;
                            a.Remove();
                            changed = true;
                        }
                    }
                }

                if (!changed) return false;

                entry.Delete();
                var fresh = zip.CreateEntry(CorePropsPath);
                using (var s = fresh.Open())
                {
                    doc.Save(s, SaveOptions.DisableFormatting);
                }
            }
            return true;
        }
    }
}
