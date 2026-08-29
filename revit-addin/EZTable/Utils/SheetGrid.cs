using System;
using System.Collections.Generic;
using System.Linq;
using EZTable.Models;

namespace EZTable.Utils
{
    public class Rect
    {
        public double XLeft { get; }
        public double YTop { get; }
        public double XRight { get; }
        public double YBottom { get; }

        public Rect(double xLeft, double yTop, double xRight, double yBottom)
        {
            XLeft = xLeft;
            YTop = yTop;
            XRight = xRight;
            YBottom = yBottom;
        }

        public Rect ShiftY(double dy)
        {
            return new Rect(XLeft, YTop + dy, XRight, YBottom + dy);
        }
    }

    /// <summary>
    /// Coordinate table for the visible rows and columns.
    /// Two index spaces are exposed: Excel indices (1-based) and visible
    /// indices (0-based).
    /// </summary>
    public class SheetGrid
    {
        public List<int> Rows { get; private set; }
        public List<int> Cols { get; private set; }

        private Dictionary<int, int> _rowPos;
        private Dictionary<int, int> _colPos;

        public List<double> ColWidthsFt { get; private set; }
        public List<double> RowHeightsFt { get; private set; }

        public List<double> OrigColWidthsFt { get; private set; }
        public List<double> OrigRowHeightsFt { get; private set; }

        private List<double> _xEdges;
        private List<double> _yEdges;

        public SheetGrid(SheetData data, double defaultRowHeightFt = 15.0 / 72.0 / 12.0, double defaultColWidthFt = 8.43 * 7.0 / 96.0 / 12.0)
        {
            var rowSet = new HashSet<int>();
            var colSet = new HashSet<int>();
            foreach (var cell in data.Cells)
            {
                for (int r = cell.Row; r < cell.Row + cell.RowSpan; r++) rowSet.Add(r);
                for (int c = cell.Column; c < cell.Column + cell.ColSpan; c++) colSet.Add(c);
            }

            Rows = rowSet.OrderBy(r => r).ToList();
            Cols = colSet.OrderBy(c => c).ToList();

            _rowPos = Rows.Select((r, i) => new { r, i }).ToDictionary(x => x.r, x => x.i);
            _colPos = Cols.Select((c, i) => new { c, i }).ToDictionary(x => x.c, x => x.i);

            ColWidthsFt = Cols.Select(c => (data.ColWidthsFt.TryGetValue(c, out var w) ? w : defaultColWidthFt) * Core.Config.GeometryScale).ToList();
            RowHeightsFt = Rows.Select(r => (data.RowHeightsFt.TryGetValue(r, out var h) ? h : defaultRowHeightFt) * Core.Config.GeometryScale).ToList();

            OrigColWidthsFt = new List<double>(ColWidthsFt);
            OrigRowHeightsFt = new List<double>(RowHeightsFt);

            RebuildEdges();
        }

        // Used when cloning a sub-grid
        private SheetGrid() { }

        public void RebuildEdges()
        {
            _xEdges = new List<double> { 0.0 };
            foreach (var w in ColWidthsFt)
            {
                _xEdges.Add(_xEdges.Last() + w);
            }

            _yEdges = new List<double> { 0.0 };
            foreach (var h in RowHeightsFt)
            {
                _yEdges.Add(_yEdges.Last() - h);
            }
        }

        public int NRows => Rows.Count;
        public int NCols => Cols.Count;
        public double TotalWidthFt => _xEdges.Last();
        public double TotalHeightFt => -_yEdges.Last();

        public Tuple<int, int, int, int> VisibleSpan(int row, int col, int rowSpan = 1, int colSpan = 1)
        {
            var vrs = new List<int>();
            for (int r = row; r < row + rowSpan; r++)
            {
                if (_rowPos.TryGetValue(r, out int vr)) vrs.Add(vr);
            }

            var vcs = new List<int>();
            for (int c = col; c < col + colSpan; c++)
            {
                if (_colPos.TryGetValue(c, out int vc)) vcs.Add(vc);
            }

            if (vrs.Count == 0 || vcs.Count == 0) return null;
            return Tuple.Create(vrs.Min(), vcs.Min(), vrs.Max(), vcs.Max());
        }

        public Rect RectFromVisible(int vr0, int vc0, int vr1, int vc1)
        {
            return new Rect(_xEdges[vc0], _yEdges[vr0], _xEdges[vc1 + 1], _yEdges[vr1 + 1]);
        }

        public double XAt(int vcEdge) => _xEdges[vcEdge];
        public double YAt(int vrEdge) => _yEdges[vrEdge];

        public SheetGrid CloneForChunk(List<int> chunkCols)
        {
            var sub = new SheetGrid();
            sub.Rows = new List<int>(this.Rows);
            sub._rowPos = new Dictionary<int, int>(this._rowPos);
            sub.RowHeightsFt = new List<double>(this.RowHeightsFt);
            
            sub.Cols = new List<int>();
            sub.ColWidthsFt = new List<double>();
            sub._colPos = new Dictionary<int, int>();
            
            for(int i = 0; i < chunkCols.Count; i++)
            {
                int orig_vc = chunkCols[i];
                int orig_c = this.Cols[orig_vc];
                
                sub.Cols.Add(orig_c);
                sub._colPos[orig_c] = i;
                sub.ColWidthsFt.Add(this.ColWidthsFt[orig_vc]);
            }
            
            sub.RebuildEdges();
            return sub;
        }

        public void GrowCols(int vc0, int vc1, double needFt, double maxGrowthFactor)
        {
            double hasFt = 0;
            for (int c = vc0; c <= vc1; c++) hasFt += ColWidthsFt[c];
            if (hasFt >= needFt) return;

            double addEach = (needFt - hasFt) / (vc1 - vc0 + 1);
            for (int c = vc0; c <= vc1; c++)
            {
                double maxAllowed = OrigColWidthsFt[c] * maxGrowthFactor;
                ColWidthsFt[c] = Math.Min(ColWidthsFt[c] + addEach, maxAllowed);
            }
        }

        public void GrowRows(int vr0, int vr1, double needFt, double maxGrowthFactor)
        {
            double hasFt = 0;
            for (int r = vr0; r <= vr1; r++) hasFt += RowHeightsFt[r];
            if (hasFt >= needFt) return;

            double addEach = (needFt - hasFt) / (vr1 - vr0 + 1);
            for (int r = vr0; r <= vr1; r++)
            {
                double maxAllowed = OrigRowHeightsFt[r] * maxGrowthFactor;
                RowHeightsFt[r] = Math.Min(RowHeightsFt[r] + addEach, maxAllowed);
            }
        }
    }
}
