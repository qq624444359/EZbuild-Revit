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

        /// <summary>Which part of the table this is, and how many there are. A
        /// table that fits one sheet is part 1 of 1.</summary>
        public int Part { get; set; } = 1;
        public int PartCount { get; set; } = 1;

        /// <summary>What this part occupies on paper, in feet.</summary>
        public double WidthFt { get; set; }
        public double HeightFt { get; set; }

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
        ///
        /// -> one Plan per part. An over-wide table is split by column and the
        /// blocks stacked downwards; once that stack passes MaxTableHeightMm it is
        /// cut into parts, each of which becomes its own drafting view to be placed
        /// on its own sheet. Nothing is ever scaled -- see Config.MaxTableHeightMm.
        /// </summary>
        public static List<Plan> BuildPlans(SheetData sheet, double? baseCapHeightFt = null, bool mergeBorders = true, bool mergeFills = true, bool skipWhiteFill = true)
        {
            var grid = new SheetGrid(sheet);

            var placed = new List<Tuple<CellModel, int, int, int, int>>();
            foreach (var cell in sheet.Cells)
            {
                var span = grid.VisibleSpan(cell.Row, cell.Column, cell.RowSpan, cell.ColSpan);
                if (span == null) continue;
                placed.Add(Tuple.Create(cell, span.Item1, span.Item2, span.Item3, span.Item4));
            }

            Config.EnsureLoaded();

            // Fit to text: with all three switches off this is a strict 1:1
            // copy of Excel's row and column sizes. It has to run before any
            // split decision, which is made against the final dimensions.
            if (Config.FitColumns || Config.FitRows || Config.WrapText)
                FitToText(grid, placed, baseCapHeightFt);
            grid.RebuildEdges();

            var colChunks = SplitColumns(grid, placed, sheet.Warnings);
            var rowChunks = SplitRows(grid, placed, sheet.Warnings);

            // Reading order: a column block in full (all its row bands) before
            // the next column block starts.
            var pieces = new List<Tuple<List<int>, List<int>>>();
            foreach (var vcList in colChunks)
                foreach (var vrList in rowChunks)
                    pieces.Add(Tuple.Create(vrList, vcList));

            double gapFt = Utils.Geometry.MmToFeet(Config.BlockGapMm);
            var pages = Paginate(grid, pieces, gapFt);

            var plans = new List<Plan>();
            for (int index = 0; index < pages.Count; index++)
            {
                var plan = new Plan(grid, sheet.Warnings)
                {
                    Part = index + 1,
                    PartCount = pages.Count,
                };
                double yOff = 0.0;

                foreach (var piece in pages[index])
                {
                    var subGrid = grid.Subset(piece.Item1, piece.Item2);
                    var subPlaced = RemapPlaced(placed, piece.Item1, piece.Item2);

                    var fills = BuildFills(subGrid, subPlaced, mergeFills, skipWhiteFill && Config.SkipWhiteFill);
                    var lines = BuildBorders(subGrid, subPlaced, mergeBorders);
                    var texts = BuildTexts(subGrid, subPlaced, baseCapHeightFt);

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

                    plan.WidthFt = Math.Max(plan.WidthFt, subGrid.TotalWidthFt);
                    plan.HeightFt += subGrid.TotalHeightFt + (yOff > 0 ? gapFt : 0.0);

                    yOff += subGrid.TotalHeightFt + gapFt;
                }

                plans.Add(plan);
            }

            return plans;
        }

        /// <summary>
        /// Group the stacked blocks into parts, each no taller than
        /// MaxTableHeightMm. A block is never broken up here -- SplitRows has
        /// already made sure none is taller than one part on its own -- so a
        /// part always holds at least one block.
        /// </summary>
        private static List<List<Tuple<List<int>, List<int>>>> Paginate(SheetGrid grid, List<Tuple<List<int>, List<int>>> pieces, double gapFt)
        {
            var pages = new List<List<Tuple<List<int>, List<int>>>>();
            double maxFt = Config.MaxTableHeightMm > 0
                ? Utils.Geometry.MmToFeet(Config.MaxTableHeightMm)
                : 0.0;
            if (maxFt <= 0)
            {
                pages.Add(new List<Tuple<List<int>, List<int>>>(pieces));
                return pages;
            }

            var current = new List<Tuple<List<int>, List<int>>>();
            double used = 0.0;
            foreach (var piece in pieces)
            {
                double height = grid.HeightOf(piece.Item1);
                double need = current.Count == 0 ? height : height + gapFt;
                if (current.Count > 0 && used + need > maxFt + 1e-9)
                {
                    pages.Add(current);
                    current = new List<Tuple<List<int>, List<int>>>();
                    used = 0.0;
                    need = height;
                }
                current.Add(piece);
                used += need;
            }
            if (current.Count > 0) pages.Add(current);
            return pages;
        }

        /// <summary>
        /// Cut one axis of the grid into chunks, each no longer than maxFt.
        /// -> (indices, cut is dirty), the flag saying the cut went through a
        /// merged cell because nothing cleaner was available.
        ///
        /// Both axes split the same way, which is why this is written once:
        /// columns against MaxTableWidthMm, rows against MaxTableHeightMm.
        /// `crossing` holds the boundaries a merged cell straddles (boundary b
        /// sits between index b-1 and index b), and repeatN how many leading
        /// indices -- the headers -- to repeat on every later chunk.
        /// </summary>
        private static List<Tuple<List<int>, bool>> SplitAxis(List<double> sizes, double maxFt, HashSet<int> crossing, int repeatN)
        {
            int n = sizes.Count;
            var chunks = new List<Tuple<List<int>, bool>>();

            if (maxFt <= 0 || n == 0 || sizes.Sum() <= maxFt)
            {
                chunks.Add(Tuple.Create(Enumerable.Range(0, n).ToList(), false));
                return chunks;
            }

            repeatN = Math.Max(0, Math.Min(repeatN, n - 1));

            int start = 0;
            while (start < n)
            {
                var prefix = new List<int>();
                if (chunks.Count > 0)
                {
                    for (int i = 0; i < Math.Min(repeatN, start); i++) prefix.Add(i);
                }

                double used = prefix.Sum(i => sizes[i]);
                int idx = start;
                int lastFit = start;
                int? bestClean = null;

                while (idx < n)
                {
                    double nxt = used + sizes[idx];
                    if (nxt > maxFt && idx > start) break;
                    used = nxt;
                    lastFit = idx;
                    if (!crossing.Contains(idx + 1)) bestClean = idx;
                    idx++;
                }

                int end = (bestClean.HasValue && bestClean.Value >= start) ? bestClean.Value : lastFit;

                var chunk = new List<int>(prefix);
                for (int i = start; i <= end; i++) chunk.Add(i);
                chunks.Add(Tuple.Create(chunk, crossing.Contains(end + 1)));

                start = end + 1;
            }

            return chunks;
        }

        /// <summary>
        /// Cut the visible columns into blocks, each no wider than
        /// MaxTableWidthMm. Cut points prefer boundaries not crossed by a merged
        /// cell -- splitting through the middle of one cuts its text in half.
        /// </summary>
        private static List<List<int>> SplitColumns(SheetGrid grid, List<Tuple<CellModel, int, int, int, int>> placed, List<string> warnings)
        {
            Config.EnsureLoaded();
            double maxFt = Config.MaxTableWidthMm > 0
                ? Utils.Geometry.MmToFeet(Config.MaxTableWidthMm)
                : 0.0;

            var crossing = new HashSet<int>();
            foreach (var p in placed)
                for (int c = p.Item3 + 1; c <= p.Item5; c++) crossing.Add(c);

            var chunks = SplitAxis(grid.ColWidthsFt, maxFt, crossing, Config.RepeatLeadingCols);

            var out_ = new List<List<int>>();
            foreach (var chunk in chunks)
            {
                if (chunk.Item2 && warnings != null)
                {
                    int end = chunk.Item1.Last();
                    Warn(warnings, $"Table split between columns {grid.Cols[end]} and {grid.Cols[end + 1]} cuts through a merged cell - that cell is drawn in both blocks.");
                }
                out_.Add(chunk.Item1);
            }
            return out_;
        }

        /// <summary>
        /// Cut the visible rows into bands, each no taller than
        /// MaxTableHeightMm. This is what saves a plain long schedule: narrow
        /// enough never to be split by column, yet far too tall for one sheet.
        /// The first RepeatLeadingRows rows are repeated at the top of every
        /// later band, so a part read on its own still names its columns.
        /// </summary>
        private static List<List<int>> SplitRows(SheetGrid grid, List<Tuple<CellModel, int, int, int, int>> placed, List<string> warnings)
        {
            Config.EnsureLoaded();
            double maxFt = Config.MaxTableHeightMm > 0
                ? Utils.Geometry.MmToFeet(Config.MaxTableHeightMm)
                : 0.0;

            var crossing = new HashSet<int>();
            foreach (var p in placed)
                for (int r = p.Item2 + 1; r <= p.Item4; r++) crossing.Add(r);

            var chunks = SplitAxis(grid.RowHeightsFt, maxFt, crossing, Config.RepeatLeadingRows);

            var out_ = new List<List<int>>();
            foreach (var chunk in chunks)
            {
                if (chunk.Item2 && warnings != null)
                {
                    int end = chunk.Item1.Last();
                    Warn(warnings, $"Table split between rows {grid.Rows[end]} and {grid.Rows[end + 1]} cuts through a merged cell - that cell is drawn in both parts.");
                }
                out_.Add(chunk.Item1);
            }
            return out_;
        }

        private static void Warn(List<string> warnings, string message)
        {
            if (!warnings.Contains(message)) warnings.Add(message);
        }

        /// <summary>
        /// Remap the visible row and column indices on to a block's sub-grid;
        /// cells lying entirely outside it are dropped, and one straddling its
        /// edge is clipped to what the block shows.
        /// </summary>
        private static List<Tuple<CellModel, int, int, int, int>> RemapPlaced(List<Tuple<CellModel, int, int, int, int>> placed, List<int> chunkRows, List<int> chunkCols)
        {
            var rowMap = new Dictionary<int, int>();
            for (int i = 0; i < chunkRows.Count; i++) rowMap[chunkRows[i]] = i;
            var colMap = new Dictionary<int, int>();
            for (int i = 0; i < chunkCols.Count; i++) colMap[chunkCols[i]] = i;

            var out_ = new List<Tuple<CellModel, int, int, int, int>>();
            foreach (var p in placed)
            {
                var rows = new List<int>();
                for (int r = p.Item2; r <= p.Item4; r++)
                    if (rowMap.TryGetValue(r, out int vr)) rows.Add(vr);
                var cols = new List<int>();
                for (int c = p.Item3; c <= p.Item5; c++)
                    if (colMap.TryGetValue(c, out int vc)) cols.Add(vc);

                if (rows.Count == 0 || cols.Count == 0) continue;
                out_.Add(Tuple.Create(p.Item1, rows.Min(), cols.Min(), rows.Max(), cols.Max()));
            }
            return out_;
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







