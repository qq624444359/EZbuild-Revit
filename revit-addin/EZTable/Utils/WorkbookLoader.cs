using System;
using System.IO;
using System.IO.Compression;
using System.Linq;
using System.Text;
using System.Xml.Linq;
using ClosedXML.Excel;

namespace EZTable.Utils
{
    /// <summary>
    /// Opens a workbook for reading. Gets past the most common way a perfectly
    /// good .xlsx fails to open, and turns every other failure into an
    /// <see cref="UnreadableWorkbookException"/> that says what to do about it.
    ///
    /// **The common failure is not in the table at all.** Every .xlsx carries a
    /// small "core properties" part (author, last modified by, dates), which
    /// ClosedXML reads through System.IO.Packaging -- and that rejects any
    /// attribute it does not expect, with "Unexpected number of attributes is
    /// found on 'cp:lastModifiedBy'". Excel never writes one; some other tools
    /// do. Such a file opens in Excel without complaint and its cells are intact.
    ///
    /// So a failed load is retried once, from an in-memory copy whose core
    /// properties part is replaced by an empty one. **The file on disk is never
    /// written to**, and nothing the plug-in draws comes from those properties.
    ///
    /// No Revit API in here, so it can be exercised outside Revit.
    /// </summary>
    public static class WorkbookLoader
    {
        // Compound File header: an encrypted (password-protected) .xlsx, or a
        // legacy .xls, rather than the zip an .xlsx should be
        private static readonly byte[] CompoundFileHeader =
            { 0xD0, 0xCF, 0x11, 0xE0, 0xA1, 0xB1, 0x1A, 0xE1 };

        private const string BlankCoreProperties =
            "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>" +
            "<cp:coreProperties" +
            " xmlns:cp=\"http://schemas.openxmlformats.org/package/2006/metadata/core-properties\"" +
            " xmlns:dc=\"http://purl.org/dc/elements/1.1/\"" +
            " xmlns:dcterms=\"http://purl.org/dc/terms/\"" +
            " xmlns:dcmitype=\"http://purl.org/dc/dcmitype/\"" +
            " xmlns:xsi=\"http://www.w3.org/2001/XMLSchema-instance\"></cp:coreProperties>";

        /// <param name="propertiesIgnored">true when the workbook only opened
        /// after its document properties were set aside -- worth telling the
        /// user, though the table itself is unaffected</param>
        public static XLWorkbook Open(string path, out bool propertiesIgnored)
        {
            propertiesIgnored = false;
            byte[] bytes = ReadAll(path);

            if (bytes.Length >= CompoundFileHeader.Length &&
                CompoundFileHeader.SequenceEqual(bytes.Take(CompoundFileHeader.Length)))
                throw new UnreadableWorkbookException(path, UnreadableReason.EncryptedOrLegacy, null);

            Exception first;
            try
            {
                return new XLWorkbook(Writable(bytes));
            }
            catch (Exception ex)
            {
                first = ex;
            }

            // Retry with the properties set aside. If there is no properties
            // part to replace, or the file is not even a readable zip, they were
            // not the problem: report the original failure.
            MemoryStream retry = WithBlankCoreProperties(bytes);
            if (retry == null)
                throw new UnreadableWorkbookException(path, UnreadableReason.NotAWorkbook, first);

            try
            {
                var workbook = new XLWorkbook(retry);
                propertiesIgnored = true;
                return workbook;
            }
            catch (Exception ex)
            {
                throw new UnreadableWorkbookException(path, UnreadableReason.NotAWorkbook, ex);
            }
        }

        private static byte[] ReadAll(string path)
        {
            try
            {
                // FileShare.ReadWrite so the file can be read even while the
                // user has it open in Excel
                using (var fs = new FileStream(path, FileMode.Open, FileAccess.Read,
                                               FileShare.ReadWrite))
                using (var ms = new MemoryStream())
                {
                    fs.CopyTo(ms);
                    return ms.ToArray();
                }
            }
            catch (FileNotFoundException ex)
            {
                throw new UnreadableWorkbookException(path, UnreadableReason.Missing, ex);
            }
            catch (DirectoryNotFoundException ex)
            {
                throw new UnreadableWorkbookException(path, UnreadableReason.Missing, ex);
            }
            catch (UnauthorizedAccessException ex)
            {
                throw new UnreadableWorkbookException(path, UnreadableReason.NoAccess, ex);
            }
            catch (IOException ex)
            {
                throw new UnreadableWorkbookException(path, UnreadableReason.Locked, ex);
            }
        }

        private static MemoryStream Writable(byte[] bytes)
        {
            var ms = new MemoryStream();
            ms.Write(bytes, 0, bytes.Length);
            ms.Position = 0;
            return ms;
        }

        /// <summary>A copy of the package with its core properties part
        /// emptied, or null when there is no such part or the bytes are not a
        /// zip. The part is found through the package relationships rather than
        /// assumed to be docProps/core.xml: that is only Excel's choice, and
        /// files written through System.IO.Packaging put it elsewhere.</summary>
        private static MemoryStream WithBlankCoreProperties(byte[] bytes)
        {
            try
            {
                MemoryStream ms = Writable(bytes);
                using (var zip = new ZipArchive(ms, ZipArchiveMode.Update, leaveOpen: true))
                {
                    ZipArchiveEntry rels = zip.GetEntry("_rels/.rels");
                    if (rels == null) return null;

                    XDocument relsXml;
                    using (var s = rels.Open()) relsXml = XDocument.Load(s);
                    string target = relsXml.Root?
                        .Elements()
                        .Where(e => e.Name.LocalName == "Relationship" &&
                                    ((string)e.Attribute("Type") ?? "")
                                        .EndsWith("/metadata/core-properties", StringComparison.Ordinal))
                        .Select(e => ((string)e.Attribute("Target") ?? "").TrimStart('/'))
                        .FirstOrDefault(t => t.Length > 0);
                    if (target == null) return null;

                    ZipArchiveEntry part = zip.GetEntry(target) ??
                        zip.Entries.FirstOrDefault(e => string.Equals(
                            e.FullName, target, StringComparison.OrdinalIgnoreCase));
                    if (part == null) return null;

                    string name = part.FullName;
                    part.Delete();
                    using (var w = new StreamWriter(zip.CreateEntry(name).Open(),
                                                    new UTF8Encoding(false)))
                        w.Write(BlankCoreProperties);
                }
                ms.Position = 0;
                return ms;
            }
            catch (Exception)
            {
                return null;
            }
        }
    }

    public enum UnreadableReason { Missing, NoAccess, Locked, EncryptedOrLegacy, NotAWorkbook }

    /// <summary>
    /// A workbook that could not be opened, carrying what is wrong and what to
    /// do about it in words a user can act on. <see cref="Exception.Message"/>
    /// joins the two; the original exception, if any, is kept as the inner one
    /// for the technical detail.
    /// </summary>
    public class UnreadableWorkbookException : Exception
    {
        public string FilePath { get; }
        public UnreadableReason Reason { get; }

        public UnreadableWorkbookException(string filePath, UnreadableReason reason, Exception inner)
            : base(null, inner)
        {
            FilePath = filePath;
            Reason = reason;
        }

        /// <summary>One line: what is wrong.</summary>
        public string Summary
        {
            get
            {
                switch (Reason)
                {
                    case UnreadableReason.Missing:
                        return "The file could not be found.";
                    case UnreadableReason.NoAccess:
                        return "Windows denied access to the file.";
                    case UnreadableReason.Locked:
                        return "The file is locked by another program.";
                    case UnreadableReason.EncryptedOrLegacy:
                        return "The file is password-protected, or is an old .xls workbook renamed to .xlsx.";
                    default:
                        return "The file could not be read as an Excel workbook. It may be damaged, " +
                               "or saved by a program that writes non-standard .xlsx files.";
                }
            }
        }

        /// <summary>What to do about it.</summary>
        public string Fix
        {
            get
            {
                switch (Reason)
                {
                    case UnreadableReason.Missing:
                        return "If it was moved or renamed, put it back, or import it again from where it is now.";
                    case UnreadableReason.NoAccess:
                        return "Check that your Windows account can open the file - for example, that it is " +
                               "not on a network drive you no longer have access to - then try again.";
                    case UnreadableReason.Locked:
                        return "Close the program holding it, or wait for OneDrive or SharePoint to finish " +
                               "syncing it, then try again.";
                    case UnreadableReason.EncryptedOrLegacy:
                        return "Open it in Microsoft Excel. If it asks for a password, remove it under " +
                               "File > Info > Protect Workbook > Encrypt with Password. Then use " +
                               "File > Save As > Excel Workbook (*.xlsx) and import the new copy.";
                    default:
                        return "Open it in Microsoft Excel and use File > Save As > Excel Workbook (*.xlsx) " +
                               "to save a fresh copy, then import that. Excel rewrites the file in the " +
                               "standard form EZTable reads.";
                }
            }
        }

        /// <summary>The original error, first line only, for the details
        /// section of a dialog or a support email.</summary>
        public string Detail
        {
            get
            {
                if (InnerException == null) return "";
                string m = InnerException.Message ?? "";
                int nl = m.IndexOf('\n');
                return InnerException.GetType().Name + ": " + (nl >= 0 ? m.Substring(0, nl) : m).Trim();
            }
        }

        public override string Message => Summary + "\n\n" + Fix;
    }
}
