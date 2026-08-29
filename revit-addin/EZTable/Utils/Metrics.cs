using System;
using System.Collections.Generic;
using System.Linq;

namespace EZTable.Utils
{
    /// <summary>
    /// Arial character width table, used to decide whether text fits.
    ///
    /// Revit will not tell you that a string overflowed its cell, and horizontal
    /// overflow is something the centring maths cannot rescue -- it has to be computed
    /// and warned about up front. The numbers here are Liberation Sans advance widths
    /// (in 1/1000 em), whose metrics match Arial exactly.
    /// </summary>
    public static class Metrics
    {
        private static readonly Dictionary<char, double> WidthsRegular = Expand(new Dictionary<int, string>
        {
            { 191, "'" },
            { 222, "ijl`'" },
            { 260, "|" },
            { 278, " !,./:;I[\\]ft" },
            { 333, "()-`r3\"\"" },
            { 334, "{}" },
            { 355, "\"" },
            { 389, "*" },
            { 400, "" },
            { 469, "^" },
            { 500, "Jcksvxyz" },
            { 549, "?" },
            { 556, "#$0123456789?L_abdeghnopqu-?" },
            { 576, "" },
            { 584, "+<=>~x" },
            { 611, "FTZ" },
            { 667, "&ABEKPSVXY" },
            { 722, "CDHNRUw" },
            { 778, "GOQ" },
            { 833, "Mm" },
            { 889, "%" },
            { 944, "W" },
            { 1000, "-.T" },
            { 1015, "@" },
            { 1073, "?" }
        });

        private static readonly Dictionary<char, double> WidthsBold = Expand(new Dictionary<int, string>
        {
            { 238, "'" },
            { 278, " ,./I\\ijl`'" },
            { 280, "|" },
            { 333, "!()-:;[]`ft3" },
            { 389, "*r{}" },
            { 400, "" },
            { 474, "\"" },
            { 500, "z\"\"" },
            { 549, "?" },
            { 556, "#$0123456789J_aceksvxy-?" },
            { 576, "" },
            { 584, "+<=>^~x" },
            { 611, "?FLTZbdghnopqu" },
            { 667, "EPSVXY" },
            { 722, "&ABCDHKNRU" },
            { 778, "GOQw" },
            { 833, "M" },
            { 889, "%m" },
            { 944, "W" },
            { 975, "@" },
            { 1000, "-.T" },
            { 1115, "?" }
        });

        private const double FallbackWidth = 0.55;
        private const double CjkWidth = 1.0;

        private static Dictionary<char, double> Expand(Dictionary<int, string> groups)
        {
            var outDict = new Dictionary<char, double>();
            foreach (var kvp in groups)
            {
                foreach (char ch in kvp.Value)
                {
                    outDict[ch] = kvp.Key / 1000.0;
                }
            }
            return outDict;
        }

        private static bool IsWide(char ch)
        {
            int o = ch;
            return (0x1100 <= o && o <= 0x115F) ||
                   (0x2E80 <= o && o <= 0xA4CF) ||
                   (0xAC00 <= o && o <= 0xD7A3) ||
                   (0xF900 <= o && o <= 0xFAFF) ||
                   (0xFE30 <= o && o <= 0xFE6F) ||
                   (0xFF00 <= o && o <= 0xFF60) ||
                   (0xFFE0 <= o && o <= 0xFFE6);
        }

        public static double StringWidthEm(string text, bool bold = false)
        {
            if (string.IsNullOrEmpty(text)) return 0.0;
            var table = bold ? WidthsBold : WidthsRegular;
            double total = 0.0;
            foreach (char ch in text)
            {
                if (table.TryGetValue(ch, out double w))
                {
                    total += w;
                }
                else
                {
                    total += IsWide(ch) ? CjkWidth : FallbackWidth;
                }
            }
            return total;
        }

        public static string WidestLine(string text)
        {
            if (string.IsNullOrEmpty(text)) return "";
            var lines = text.Split(new[] { '\n', '\r' }, StringSplitOptions.RemoveEmptyEntries);
            if (lines.Length == 0) return "";
            
            string widest = lines[0];
            double maxW = StringWidthEm(widest);
            for (int i = 1; i < lines.Length; i++)
            {
                double w = StringWidthEm(lines[i]);
                if (w > maxW)
                {
                    maxW = w;
                    widest = lines[i];
                }
            }
            return widest;
        }

        public static List<string> WrapLine(string line, double maxWidthEm, bool bold = false)
        {
            if (maxWidthEm <= 0 || StringWidthEm(line, bold) <= maxWidthEm)
                return new List<string> { line };

            var words = line.Split(' ');
            var outLines = new List<string>();
            string cur = "";

            foreach (var w in words)
            {
                string candidate = string.IsNullOrEmpty(cur) ? w : cur + " " + w;
                if (StringWidthEm(candidate, bold) <= maxWidthEm || string.IsNullOrEmpty(cur))
                {
                    cur = candidate;
                }
                else
                {
                    outLines.Add(cur);
                    cur = w;
                }
            }
            if (!string.IsNullOrEmpty(cur))
                outLines.Add(cur);

            if (outLines.Count == 0) outLines.Add("");
            return outLines;
        }

        public static List<string> WrapText(string text, double maxWidthEm, bool bold = false)
        {
            if (string.IsNullOrEmpty(text)) return new List<string> { "" };
            var outLines = new List<string>();
            foreach (var seg in text.Split(new[] { '\n', '\r' }, StringSplitOptions.RemoveEmptyEntries))
            {
                outLines.AddRange(WrapLine(seg, maxWidthEm, bold));
            }
            return outLines;
        }

        public static double LongestWordEm(string text, bool bold = false)
        {
            double widest = 0.0;
            if (string.IsNullOrEmpty(text)) return widest;
            
            foreach (var seg in text.Replace('\n', ' ').Replace('\r', ' ').Split(' '))
            {
                double w = StringWidthEm(seg, bold);
                if (w > widest) widest = w;
            }
            return widest;
        }
    }
}
