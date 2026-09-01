using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Text.RegularExpressions;

namespace EZTable.Core
{
    /// <summary>
    /// Drafting standards -- the counterpart of config.py in the pyRevit version.
    ///
    /// The defaults live in the fields below and are compiled into the DLL. If an
    /// EZTable.config text file sits next to the DLL it is read at startup and
    /// overrides them, so changing settings needs no rebuild.
    ///
    /// The format is the plainest possible key = value, with # for comments:
    ///
    ///     # grey shading always uses this existing type
    ///     GreyFillTypeName = Fill Grey 192
    ///     MaxTableWidthMm  = 380
    ///     FitColumns       = true
    ///
    /// Deliberately not JSON: net48's BCL has no System.Text.Json, and taking on
    /// a NuGet dependency to read a handful of key-value pairs is a bad trade.
    /// </summary>
    public static class Config
    {
        public const string CONFIG_FILE_NAME = "EZTable.config";

        // ---------------------------------------------------------- line styles
        // Excel border weight -> Revit line style name. A name that cannot be
        // found falls back to creating an EZ_* subcategory, with a warning.
        public static bool UseExistingLineStyles = true;
        public static string LineStyleThin = "<Thin Lines>";
        public static string LineStyleMedium = "<Medium Lines>";
        public static string LineStyleThick = "<Wide Lines>";

        // ---------------------------------------------------------- fills
        // Grey shading always uses this existing type; leave empty to create
        // types automatically by colour
        public static string GreyFillTypeName = "Fill Grey 192";
        // A colour counts as grey when the spread across R/G/B is no more than this
        public static int GreyTolerance = 12;

        // How far an Excel grey may sit from the level named in GreyFillTypeName and
        // still be drawn with it. Beyond this a faithful "Fill Grey <level>" type is
        // created instead. Without it every grey collapsed on to the one standard
        // type: Excel's 230 and 242 were both drawn at 192, visibly darker.
        public static int GreySnapTolerance = 16;
        public static string FillTypePrefix = "Fill";
        // White shading is not drawn -- the sheet background is white anyway
        public static bool SkipWhiteFill = true;

        // ---------------------------------------------------------- text
        // Derive from this existing type; bold, italic and coloured variants are
        // copies of it. Leave empty for fully automatic types.
        //
        // Plain black text at the base size uses this type as-is -- never
        // duplicated, never modified -- so whatever background it carries is what
        // gets drawn, while derived types are copies with their background forced
        // to Transparent. Point this at a type whose background is Transparent;
        // the 2.1mm one exists for exactly that reason, the 2.0mm standard being
        // opaque.
        public static string BaseTextTypeName = "2.1mm Arial";

        // Text types Cleanup must never offer for deletion, however much they look
        // like something this tool generated. A type whose name differs from the
        // base only in the size token -- "2.0mm Arial" against a "2.1mm Arial"
        // base -- is indistinguishable from a resized copy, and the 2.0mm standard
        // is exactly that case: the project's own type. Exact names only.
        public static string[] ProtectedTextTypeNames = { "2.0mm Arial" };

        // The base type above represents Excel text at this point size. Text at any
        // other size is drawn proportionally, so a sheet set in 9pt keeps the same
        // text-to-cell ratio as one set in 7pt. Forcing one fixed size makes sheets
        // inconsistent with each other, and here it also desynchronised layout from
        // rendering: the plan positioned text for Excel's real cap height while the
        // text type carried the base size.
        public static bool ScaleTextToExcel = true;
        public static double BaseTextSizePt = 7.0;
        
        public static double GeometryScale = 1.0;

        // ---------------------------------------------------------- view naming
        // Two placeholders are supported: {sheet} (worksheet name) and {file}
        // (file name without extension). A name already in use gets a (1) (2)
        // suffix automatically.
        public static string ViewNameTemplate = "Table";

        // ---------------------------------------------------- splitting wide tables
        // An A3 sheet cannot hold an over-long table. Changing the view scale
        // wrecks the layout, because text size is fixed on paper. Instead the
        // table is split by column and stacked downwards, every block staying
        // 1:1. Set to 0 to disable splitting.
        public static double MaxTableWidthMm = 380.0;
        public static double BlockGapMm = 10.0;
        public static int RepeatLeadingCols = 1;

        // ---------------------------------------------------------- fit to text
        // The default is to fit the table to its text: font size stays fixed, and
        // anything that does not fit widens the column and heightens the row.
        // Set all three to false for a strict 1:1 copy of Excel's dimensions.
        public static bool WrapText = true;
        public static bool FitColumns = true;
        public static bool FitRows = true;
        public static double MaxColGrowth = 4.0;
        public static double MaxRowGrowth = 6.0;
        public static double CellPaddingHMm = 0.8;
        public static double CellPaddingVMm = 0.4;

        private static bool _loaded;
        private static readonly object _lock = new object();

        /// <summary>Path of the config file that was read; null when there is
        /// none. Only used in diagnostics.</summary>
        public static string LoadedFrom { get; private set; }

        /// <summary>Problems hit while parsing the config file, shown alongside
        /// the import warnings.</summary>
        public static List<string> LoadWarnings { get; } = new List<string>();

        /// <summary>
        /// Read overrides from EZTable.config in the DLL's own directory. The
        /// file is only actually read on the first call. Its absence is the
        /// normal case, not an error.
        /// </summary>
        public static void EnsureLoaded()
        {
            if (_loaded) return;
            lock (_lock)
            {
                if (_loaded) return;
                _loaded = true;
                try
                {
                    string dir = Path.GetDirectoryName(
                        System.Reflection.Assembly.GetExecutingAssembly().Location);
                    if (string.IsNullOrEmpty(dir)) return;
                    string path = Path.Combine(dir, CONFIG_FILE_NAME);
                    if (!File.Exists(path)) return;
                    LoadFromFile(path);
                    LoadedFrom = path;
                }
                catch (Exception ex)
                {
                    LoadWarnings.Add("Could not read " + CONFIG_FILE_NAME + ": " + ex.Message);
                }
            }
        }

        private static void LoadFromFile(string path)
        {
            foreach (string raw in File.ReadAllLines(path))
            {
                string line = raw.Trim();
                if (line.Length == 0 || line.StartsWith("#") || line.StartsWith(";")) continue;

                int eq = line.IndexOf('=');
                if (eq <= 0)
                {
                    LoadWarnings.Add("Ignored line in " + CONFIG_FILE_NAME + ": " + raw.Trim());
                    continue;
                }

                string key = line.Substring(0, eq).Trim();
                string value = line.Substring(eq + 1).Trim();
                if (!Apply(key, value))
                    LoadWarnings.Add("Unknown setting in " + CONFIG_FILE_NAME + ": " + key);
            }
        }

        private static bool Apply(string key, string value)
        {
            switch (key.ToLowerInvariant())
            {
                case "useexistinglinestyles": UseExistingLineStyles = Bool(value, UseExistingLineStyles); return true;
                case "linestylethin": LineStyleThin = value; return true;
                case "linestylemedium": LineStyleMedium = value; return true;
                case "linestylethick": LineStyleThick = value; return true;

                case "greyfilltypename": GreyFillTypeName = Blank(value); return true;
                case "greytolerance": GreyTolerance = Int(value, GreyTolerance); return true;
                case "greysnaptolerance": GreySnapTolerance = Int(value, GreySnapTolerance); return true;
                case "filltypeprefix": FillTypePrefix = value; return true;
                case "skipwhitefill": SkipWhiteFill = Bool(value, SkipWhiteFill); return true;

                case "basetexttypename": BaseTextTypeName = Blank(value); return true;
                case "protectedtexttypenames": ProtectedTextTypeNames = NameList(value); return true;
                case "scaletexttoexcel": ScaleTextToExcel = Bool(value, ScaleTextToExcel); return true;
                case "basetextsizept": BaseTextSizePt = Double(value, BaseTextSizePt); return true;

                case "geometryscale": GeometryScale = Double(value, GeometryScale); return true;

                case "viewnametemplate": ViewNameTemplate = value; return true;

                case "maxtablewidthmm": MaxTableWidthMm = Double(value, MaxTableWidthMm); return true;
                case "blockgapmm": BlockGapMm = Double(value, BlockGapMm); return true;
                case "repeatleadingcols": RepeatLeadingCols = Int(value, RepeatLeadingCols); return true;

                case "wraptext": WrapText = Bool(value, WrapText); return true;
                case "fitcolumns": FitColumns = Bool(value, FitColumns); return true;
                case "fitrows": FitRows = Bool(value, FitRows); return true;
                case "maxcolgrowth": MaxColGrowth = Double(value, MaxColGrowth); return true;
                case "maxrowgrowth": MaxRowGrowth = Double(value, MaxRowGrowth); return true;
                case "cellpaddinghmm": CellPaddingHMm = Double(value, CellPaddingHMm); return true;
                case "cellpaddingvmm": CellPaddingVMm = Double(value, CellPaddingVMm); return true;

                default: return false;
            }
        }

        /// <summary>
        /// How much larger than the base text type a cell's text should be drawn.
        /// The base type stands for Excel text at BaseTextSizePt, so a 9pt cell in a
        /// 7pt-anchored standard comes out at 9/7 of the base size.
        /// </summary>
        public static double TextScale(double sizePt)
        {
            if (!ScaleTextToExcel || BaseTextSizePt <= 0 || sizePt <= 0) return 1.0;
            return sizePt / BaseTextSizePt;
        }

        private static readonly Regex SizeTokenRe =
            new Regex(@"^\s*\d+(?:\.\d+)?\s*mm\b", RegexOptions.IgnoreCase);

        /// <summary>
        /// Name for a scaled copy of the base text type, following the project's own
        /// convention of leading the name with the size:
        ///     "2.1mm Arial" at 2.57mm -> "2.6mm Arial"
        /// When the base name carries no size token the size is appended instead.
        /// </summary>
        public static string ResizeTextTypeName(string baseName, double capMm)
        {
            string token = capMm.ToString("0.0", CultureInfo.InvariantCulture) + "mm";
            string name = baseName ?? "";
            if (SizeTokenRe.IsMatch(name))
                return SizeTokenRe.Replace(name, token, 1);
            return (name + " " + token).Trim();
        }

        private static readonly Regex GreyLevelRe = new Regex(@"(\d{1,3})\s*$");

        /// <summary>
        /// The grey level encoded in a fill type name -- "Fill Grey 192" -> 192.
        /// Returns null when the name carries no trailing number.
        /// </summary>
        public static int? GreyTypeLevel(string typeName)
        {
            var m = GreyLevelRe.Match(typeName ?? "");
            return m.Success ? (int?)int.Parse(m.Groups[1].Value) : null;
        }

        /// <summary>Is this Excel grey close enough to the standard type to use it?</summary>
        public static bool SnapsToGreyType(int greyLevel, string typeName)
        {
            int? standard = GreyTypeLevel(typeName);
            if (standard == null) return true;   // no level in the name, nothing to compare
            return Math.Abs(greyLevel - standard.Value) <= GreySnapTolerance;
        }

        // An empty string, none or null all mean "switch this setting off",
        // matching None in config.py
        private static string Blank(string value)
        {
            if (string.IsNullOrWhiteSpace(value)) return null;
            string v = value.Trim();
            return (v.Equals("none", StringComparison.OrdinalIgnoreCase) ||
                    v.Equals("null", StringComparison.OrdinalIgnoreCase)) ? null : v;
        }

        /// <summary>Comma separated list of type names; blank or "none" gives an
        /// empty list. Names keep their spaces, so "2.0mm Arial" needs no quoting.</summary>
        private static string[] NameList(string value)
        {
            if (Blank(value) == null) return new string[0];
            var names = new List<string>();
            foreach (string part in value.Split(','))
            {
                string v = part.Trim();
                if (v.Length > 0) names.Add(v);
            }
            return names.ToArray();
        }

        private static bool Bool(string value, bool fallback)
        {
            string v = (value ?? "").Trim().ToLowerInvariant();
            if (v == "true" || v == "1" || v == "yes" || v == "on") return true;
            if (v == "false" || v == "0" || v == "no" || v == "off") return false;
            return fallback;
        }

        // Always parse with InvariantCulture: on a locale where the decimal
        // separator is a comma, "380.0" would otherwise parse as 3800
        private static double Double(string value, double fallback)
        {
            return double.TryParse((value ?? "").Trim(), NumberStyles.Float,
                                   CultureInfo.InvariantCulture, out double r) ? r : fallback;
        }

        private static int Int(string value, int fallback)
        {
            return int.TryParse((value ?? "").Trim(), NumberStyles.Integer,
                                CultureInfo.InvariantCulture, out int r) ? r : fallback;
        }

        private static readonly Regex ModifierRe = new Regex(@"^(?:BOLD|ITALIC|GREY|[A-Z]+|\d{1,3}|[0-9A-F]{6})$", RegexOptions.IgnoreCase);

        private static string StripSizeToken(string name)
        {
            return SizeTokenRe.Replace(name ?? "", "", 1).Trim();
        }

        public static bool IsGeneratedFillName(string name)
        {
            if (string.IsNullOrEmpty(name) || name == GreyFillTypeName)
                return false;
            
            string pattern = "^" + Regex.Escape(FillTypePrefix) + @"\s+(?:Grey\s+\d{1,3}|[A-Za-z]+\s+[0-9A-Fa-f]{6})$";
            return Regex.IsMatch(name, pattern, RegexOptions.IgnoreCase);
        }

        public static bool IsDerivedTextName(string name)
        {
            string baseName = BaseTextTypeName;
            if (string.IsNullOrEmpty(baseName) || string.IsNullOrEmpty(name) || name == baseName)
                return false;
            if (Array.IndexOf(ProtectedTextTypeNames ?? new string[0], name) >= 0)
                return false;

            var parts = new List<string>(name.Split(new[] { ' ' }, StringSplitOptions.RemoveEmptyEntries));
            while (parts.Count > 0 && ModifierRe.IsMatch(parts[parts.Count - 1]))
            {
                parts.RemoveAt(parts.Count - 1);
            }

            string stem = string.Join(" ", parts);
            if (string.IsNullOrEmpty(stem)) return false;

            return StripSizeToken(stem) == StripSizeToken(baseName);
        }
    }
}
