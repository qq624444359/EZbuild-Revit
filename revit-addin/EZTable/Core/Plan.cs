using System;
using System.Collections.Generic;
using System.Linq;
using EZTable.Models;
using EZTable.Utils;
using BorderStyle = EZTable.Models.BorderStyle;
using HorizontalAlignment = EZTable.Models.HorizontalAlignment;
using VerticalAlignment = EZTable.Models.VerticalAlignment;

namespace EZTable.Core
{
    public class Plan
    {
        public SheetGrid Grid { get; }
        public List<FillItem> Fills { get; } = new List<FillItem>();
        public List<LineItem> Lines { get; } = new List<LineItem>();
        public List<TextItem> Texts { get; } = new List<TextItem>();
        public List<string> Warnings { get; }

        public Plan(SheetGrid grid, List<string> warnings)
        {
            Grid = grid;
            Warnings = warnings ?? new List<string>();
        }

        /// <summary>
        /// baseCapHeightFt is the base text type's TEXT_SIZE in feet, or null when
        /// there is no base type. Layout and rendering must agree on the cap height,
        /// so whatever is passed here is also what StyleFactory scales its derived
        /// types from.
        /// </summary>
        public static Plan BuildPlan(SheetData sheet, double? baseCapHeightFt = null, bool mergeBorders = true, bool mergeFills = true, bool skipWhiteFill = true)
        {
            var grid = new SheetGrid(sheet);
            var plan = new Plan(grid, sheet.Warnings);

            var placed = new List<Tuple<CellModel, int, int, int, int>>();
            foreach (var cell in sheet.Cells)
            {
                var span = grid.VisibleSpan(cell.Row, cell.Column, cell.RowSpan, cell.ColSpan);
                if (span == null) continue;
                placed.Add(Tuple.Create(cell, span.Item1, span.Item2, span.Item3, span.Item4));
            }

            Config.EnsureLoaded();

            // Fit to text: with all three switches off this is a strict 1:1
            // copy of Excel's row and column sizes
            if (Config.FitColumns || Config.FitRows || Config.WrapText)
                FitToText(grid, placed, baseCapHeightFt);
            grid.RebuildEdges();

            var chunks = SplitColumns(grid, placed, sheet.Warnings);
            double gapFt = Utils.Geometry.MmToFeet(Config.BlockGapMm);
            double yOff = 0.0;

            foreach (var chunk in chunks)
            {
                var subGrid = grid.CloneForChunk(chunk);
                var chunkPlaced = new List<Tuple<CellModel, int, int, int, int>>();
                foreach (var p in placed)
                {
                    int n_vc0 = chunk.IndexOf(p.Item3);
                    int n_vc1 = chunk.IndexOf(p.Item5);
                    
                    if (n_vc0 == -1 && n_vc1 == -1) continue;
                    if (n_vc0 == -1) n_vc0 = 0;
                    if (n_vc1 == -1) n_vc1 = chunk.Count - 1;
                    
                    chunkPlaced.Add(Tuple.Create(p.Item1, p.Item2, n_vc0, p.Item4, n_vc1));
                }

                var fills = BuildFills(subGrid, chunkPlaced, mergeFills, skipWhiteFill && Config.SkipWhiteFill);
                var lines = BuildBorders(subGrid, chunkPlaced, mergeBorders);
                var texts = BuildTexts(subGrid, chunkPlaced, baseCapHeightFt);

                foreach (var f in fills) f.Rect = f.Rect.ShiftY(-yOff);
                foreach (var l in lines)
                {
                    l.P1 = Tuple.Create(l.P1.Item1, l.P1.Item2 - yOff);
                    l.P2 = Tuple.Create(l.P2.Item1, l.P2.Item2 - yOff);
                }
                foreach (var t in texts) t.Y -= yOff;

                plan.Fills.AddRange(fills);
                plan.Lines.AddRange(lines);
                plan.Texts.AddRange(texts);

                yOff += subGrid.TotalHeightFt + gapFt;
            }

            return plan;
        }

        private static List<List<int>> SplitColumns(SheetGrid grid, List<Tuple<CellModel, int, int, int, int>> placed, List<string> warnings)
        {
            Config.EnsureLoaded();
            // MaxTableWidthMm <= 0 disables splitting
            double maxFt = Config.MaxTableWidthMm > 0
                ? Utils.Geometry.MmToFeet(Config.MaxTableWidthMm)
                : 0.0;
            var crossing = new HashSet<int>();
            foreach (var p in placed)
            {
                if (p.Item3 != p.Item5)
                {
                    for (int c = p.Item3 + 1; c <= p.Item5; c++) crossing.Add(c);
                }
            }

            var chunks = new List<List<int>>();
            int start = 0;
            int n = grid.NCols;
            int repeatCols = Math.Max(0, Config.RepeatLeadingCols);

            if (maxFt <= 0)
            {
                var all = new List<int>();
                for (int i = 0; i < n; i++) all.Add(i);
                chunks.Add(all);
                return chunks;
            }

            while (start < n)
            {
                var prefix = new List<int>();
                if (start > 0 && repeatCols > 0)
                {
                    for (int i = 0; i < Math.Min(repeatCols, start); i++) prefix.Add(i);
                }

                double width = prefix.Sum(c => grid.ColWidthsFt[c]);
                int c_idx = start;
                int last_fit = start;
                int? best_clean = null;

                while (c_idx < n)
                {
                    double nxt = width + grid.ColWidthsFt[c_idx];
                    if (nxt > maxFt && c_idx > start) break;
                    width = nxt;
                    last_fit = c_idx;
                    if (!crossing.Contains(c_idx + 1)) best_clean = c_idx;
                    c_idx++;
                }

                int end = (best_clean.HasValue && best_clean.Value >= start) ? best_clean.Value : last_fit;
                
                if (crossing.Contains(end + 1))
                {
                    warnings?.Add($"Table split between columns {grid.Cols[end]} and {grid.Cols[end + 1]} cuts through a merged cell.");
                }

                var chunk = new List<int>(prefix);
                for (int i = start; i <= end; i++) chunk.Add(i);
                chunks.Add(chunk);

                start = end + 1;
            }

            return chunks;
        }

        /// <summary>
        /// The cap height to draw a cell's text at, in feet. With a base type in play
        /// the size is scaled by the cell's Excel font size relative to
        /// Config.BaseTextSizePt, so one sheet set in 9pt keeps the same
        /// text-to-cell ratio as another set in 7pt.
        /// </summary>
        public static double CapHeightFor(CellModel cell, double? baseCapHeightFt)
        {
            if (baseCapHeightFt == null)
                return Utils.Geometry.RevitTextSizeFeet(cell.FontSizePt, cell.FontName);
            return baseCapHeightFt.Value * Config.TextScale(cell.FontSizePt);
        }

        private static void FitToText(SheetGrid grid, List<Tuple<CellModel, int, int, int, int>> placed, double? baseCapHeightFt)
        {
            var wrapped = new Dictionary<Tuple<int, int>, string>();
            if (placed.Count == 0) return;

            double padHFt = Utils.Geometry.MmToFeet(Config.CellPaddingHMm);
            double padVFt = Utils.Geometry.MmToFeet(Config.CellPaddingVMm);

            (double capFt, double emFt) EmOf(CellModel cell)
            {
                double cap = CapHeightFor(cell, baseCapHeightFt);
                double capRatio = Utils.Geometry.GetFontMetrics(cell.FontName).CapRatio;
                return (cap, cap / capRatio);
            }

            // 1. Column widths
            if (Config.FitColumns)
            {
                var singles = placed.Where(p => p.Item3 == p.Item5).ToList();
                var spans = placed.Where(p => p.Item3 != p.Item5).ToList();
                var groups = new[] { singles, spans, spans };

                foreach (var group in groups)
                {
                    foreach (var p in group)
                    {
                        var cell = p.Item1;
                        if (string.IsNullOrWhiteSpace(cell.Text)) continue;
                        
                        var (cap, em) = EmOf(cell);
                        double needEm;
                        if (Config.WrapText && cell.WrapText)
                        {
                            needEm = Utils.Metrics.LongestWordEm(cell.Text, cell.IsBold);
                        }
                        else
                        {
                            needEm = Utils.Metrics.StringWidthEm(Utils.Metrics.WidestLine(cell.Text), cell.IsBold);
                        }
                        
                        grid.GrowCols(p.Item3, p.Item5, needEm * em + 2 * padHFt, Config.MaxColGrowth);
                    }
                }
                grid.RebuildEdges();
            }

            // 2. Wrapping
            if (Config.WrapText)
            {
                foreach (var p in placed)
                {
                    var cell = p.Item1;
                    if (!cell.WrapText || string.IsNullOrWhiteSpace(cell.Text)) continue;

                    var (cap, em) = EmOf(cell);
                    double avail = grid.XAt(p.Item5 + 1) - grid.XAt(p.Item3) - 2 * padHFt;
                    if (avail <= 0) continue;

                    var lines = Utils.Metrics.WrapText(cell.Text, avail / em, cell.IsBold);
                    if (lines.Count > 1 || cell.Text.Contains("\n") || cell.Text.Contains("\r"))
                    {
                        wrapped[Tuple.Create(cell.Row, cell.Column)] = string.Join("\n", lines);
                    }
                }
            }

            // 3. Row heights
            if (Config.FitRows)
            {
                var singles = placed.Where(p => p.Item2 == p.Item4).ToList();
                var spans = placed.Where(p => p.Item2 != p.Item4).ToList();
                
                foreach (var group in new[] { singles, spans })
                {
                    foreach (var p in group)
                    {
                        var cell = p.Item1;
                        string text;
                        if (!wrapped.TryGetValue(Tuple.Create(cell.Row, cell.Column), out text))
                            text = cell.Text;

                        if (string.IsNullOrWhiteSpace(text)) continue;

                        var (cap, _) = EmOf(cell);
                        int nLines = text.Count(c => c == '\n') + 1;
                        double visualH = (nLines - 1) * cap * Utils.Geometry.REVIT_LINE_PITCH_FACTOR + cap;

                        grid.GrowRows(p.Item2, p.Item4, visualH + 2 * padVFt, Config.MaxRowGrowth);
                    }
                }
                grid.RebuildEdges();
            }

            // Apply wrapped text back to cells
            foreach (var p in placed)
            {
                var cell = p.Item1;
                if (wrapped.TryGetValue(Tuple.Create(cell.Row, cell.Column), out string wText))
                {
                    cell.Text = wText;
                }
            }
        }

        private static List<FillItem> BuildFills(SheetGrid grid, List<Tuple<CellModel, int, int, int, int>> placed, bool merge, bool skipWhite)
        {
            int R = grid.NRows;
            int C = grid.NCols;
            string[,] colors = new string[R, C];

            foreach (var p in placed)
            {
                var cell = p.Item1;
                string rgb = cell.FillColorHex;
                if (string.IsNullOrEmpty(rgb)) continue;
                if (skipWhite && rgb.ToUpper() == "FFFFFF") continue;

                for (int r = p.Item2; r <= p.Item4; r++)
                {
                    for (int c = p.Item3; c <= p.Item5; c++)
                    {
                        colors[r, c] = rgb;
                    }
                }
            }

            var outFills = new List<FillItem>();
            if (!merge)
            {
                for (int r = 0; r < R; r++)
                {
                    for (int c = 0; c < C; c++)
                    {
                        if (colors[r, c] != null)
                        {
                            outFills.Add(new FillItem(grid.RectFromVisible(r, c, r, c), colors[r, c]));
                        }
                    }
                }
                return outFills;
            }

            bool[,] used = new bool[R, C];
            for (int r = 0; r < R; r++)
            {
                for (int c = 0; c < C; c++)
                {
                    string rgb = colors[r, c];
                    if (rgb == null || used[r, c]) continue;

                    // merge horizontally into strips
                    int c1 = c;
                    while (c1 + 1 < C && colors[r, c1 + 1] == rgb && !used[r, c1 + 1])
                    {
                        c1++;
                    }

                    // merge strips into blocks
                    int r1 = r;
                    while (r1 + 1 < R)
                    {
                        bool allMatch = true;
                        for (int cc = c; cc <= c1; cc++)
                        {
                            if (colors[r1 + 1, cc] != rgb || used[r1 + 1, cc])
                            {
                                allMatch = false;
                                break;
                            }
                        }
                        if (!allMatch) break;
                        r1++;
                    }

                    // mark as claimed
                    for (int rr = r; rr <= r1; rr++)
                    {
                        for (int cc = c; cc <= c1; cc++)
                        {
                            used[rr, cc] = true;
                        }
                    }

                    outFills.Add(new FillItem(grid.RectFromVisible(r, c, r1, c1), rgb));
                }
            }

            return outFills;
        }

        private static List<LineItem> BuildBorders(SheetGrid grid, List<Tuple<CellModel, int, int, int, int>> placed, bool merge)
        {
            int R = grid.NRows;
            int C = grid.NCols;

            var hEdges = new Dictionary<Tuple<int, int>, Tuple<BorderStyle, string>>(); // (vr_edge, vc) -> (style, rgb)
            var vEdges = new Dictionary<Tuple<int, int>, Tuple<BorderStyle, string>>(); // (vc_edge, vr) -> (style, rgb)

            foreach (var p in placed)
            {
                var cell = p.Item1;
                int vr0 = p.Item2, vc0 = p.Item3, vr1 = p.Item4, vc1 = p.Item5;

                if (cell.TopBorder != null)
                {
                    for (int c = vc0; c <= vc1; c++)
                        StrongerBorder(hEdges, Tuple.Create(vr0, c), cell.TopBorder);
                }
                if (cell.BottomBorder != null)
                {
                    for (int c = vc0; c <= vc1; c++)
                        StrongerBorder(hEdges, Tuple.Create(vr1 + 1, c), cell.BottomBorder);
                }
                if (cell.LeftBorder != null)
                {
                    for (int r = vr0; r <= vr1; r++)
                        StrongerBorder(vEdges, Tuple.Create(vc0, r), cell.LeftBorder);
                }
                if (cell.RightBorder != null)
                {
                    for (int r = vr0; r <= vr1; r++)
                        StrongerBorder(vEdges, Tuple.Create(vc1 + 1, r), cell.RightBorder);
                }
            }

            var lines = new List<LineItem>();

            // merge horizontal runs
            for (int edge = 0; edge <= R; edge++)
            {
                var slots = new List<Tuple<int, Tuple<BorderStyle, string>>>();
                for (int c = 0; c < C; c++)
                {
                    hEdges.TryGetValue(Tuple.Create(edge, c), out var spec);
                    slots.Add(Tuple.Create(c, spec));
                }
                
                double y = grid.YAt(edge);
                var runs = GetRuns(slots, merge);
                foreach (var run in runs)
                {
                    int c0 = run.Item1;
                    int c1 = run.Item2;
                    var spec = run.Item3;
                    lines.Add(new LineItem(Tuple.Create(grid.XAt(c0), y), Tuple.Create(grid.XAt(c1 + 1), y), spec.Item1, spec.Item2));
                }
            }

            // merge vertical runs
            for (int edge = 0; edge <= C; edge++)
            {
                var slots = new List<Tuple<int, Tuple<BorderStyle, string>>>();
                for (int r = 0; r < R; r++)
                {
                    vEdges.TryGetValue(Tuple.Create(edge, r), out var spec);
                    slots.Add(Tuple.Create(r, spec));
                }
                
                double x = grid.XAt(edge);
                var runs = GetRuns(slots, merge);
                foreach (var run in runs)
                {
                    int r0 = run.Item1;
                    int r1 = run.Item2;
                    var spec = run.Item3;
                    lines.Add(new LineItem(Tuple.Create(x, grid.YAt(r0)), Tuple.Create(x, grid.YAt(r1 + 1)), spec.Item1, spec.Item2));
                }
            }

            return lines;
        }

        private static void StrongerBorder(Dictionary<Tuple<int, int>, Tuple<BorderStyle, string>> store, Tuple<int, int> key, BorderModel newBorder)
        {
            if (newBorder.Style == BorderStyle.None) return;

            if (!store.TryGetValue(key, out var curBorder))
            {
                store[key] = Tuple.Create(newBorder.Style, newBorder.ColorHex);
                return;
            }

            // compare weight ranks
            int Rank(BorderStyle s)
            {
                switch (s)
                {
                    case BorderStyle.Dashed: return 2;
                    case BorderStyle.Thin: return 3;
                    case BorderStyle.Medium: return 4;
                    case BorderStyle.Thick: return 5;
                    default: return 0;
                }
            }

            if (Rank(newBorder.Style) > Rank(curBorder.Item1))
            {
                store[key] = Tuple.Create(newBorder.Style, newBorder.ColorHex);
            }
        }

        private static List<Tuple<int, int, Tuple<BorderStyle, string>>> GetRuns(List<Tuple<int, Tuple<BorderStyle, string>>> slots, bool merge)
        {
            var outRuns = new List<Tuple<int, int, Tuple<BorderStyle, string>>>();
            int? start = null;
            Tuple<BorderStyle, string> cur = null;

            foreach (var slot in slots)
            {
                int idx = slot.Item1;
                var spec = slot.Item2;

                if (spec == null)
                {
                    if (start.HasValue)
                    {
                        outRuns.Add(Tuple.Create(start.Value, idx - 1, cur));
                        start = null;
                        cur = null;
                    }
                    continue;
                }

                if (!merge)
                {
                    outRuns.Add(Tuple.Create(idx, idx, spec));
                    continue;
                }

                if (!start.HasValue)
                {
                    start = idx;
                    cur = spec;
                }
                else if (spec.Item1 != cur.Item1 || spec.Item2 != cur.Item2)
                {
                    outRuns.Add(Tuple.Create(start.Value, idx - 1, cur));
                    start = idx;
                    cur = spec;
                }
            }

            if (start.HasValue)
            {
                outRuns.Add(Tuple.Create(start.Value, slots.Last().Item1, cur));
            }

            return outRuns;
        }

        private static List<TextItem> BuildTexts(SheetGrid grid, List<Tuple<CellModel, int, int, int, int>> placed, double? baseCapHeightFt)
        {
            var outTexts = new List<TextItem>();

            foreach (var p in placed)
            {
                var cell = p.Item1;
                string text = cell.Text?.Replace("\r\n", "\n").Replace("\r", "\n");
                if (string.IsNullOrWhiteSpace(text)) continue;

                var rect = grid.RectFromVisible(p.Item2, p.Item3, p.Item4, p.Item5);
                int nLines = text.Count(c => c == '\n') + 1;

                // Compute the anchor (x, y)
                double x;
                if (cell.HAlign == HorizontalAlignment.Center)
                    x = (rect.XLeft + rect.XRight) / 2.0;
                else if (cell.HAlign == HorizontalAlignment.Right)
                    x = rect.XRight - Geometry.TEXT_PADDING_FT;
                else
                    x = rect.XLeft + Geometry.TEXT_PADDING_FT;

                double capFt = CapHeightFor(cell, baseCapHeightFt);
                double pitchFt = capFt * Geometry.REVIT_LINE_PITCH_FACTOR;
                double visualH = (nLines - 1) * pitchFt + capFt;

                double cellH = rect.YTop - rect.YBottom;
                double capTop;
                if (cell.VAlign == VerticalAlignment.Center)
                    capTop = rect.YTop - (cellH - visualH) / 2.0;
                else if (cell.VAlign == VerticalAlignment.Bottom)
                    capTop = rect.YBottom + visualH;
                else
                    capTop = rect.YTop;

                // Add Revit's own ascender offset
                // default ascRatio / capRatio for Arial is 0.9052 / 0.7163 ≈ 1.264
                // ascender/cap - 1 = 0.264
                double y = capTop + capFt * (0.264);

                outTexts.Add(new TextItem(x, y, text, cell, nLines, $"R{cell.Row}C{cell.Column}"));
            }

            return outTexts;
        }
    }
}







