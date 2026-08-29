using System;

namespace EZTable.Models
{
    public class FillItem
    {
        public Utils.Rect Rect { get; set; }
        public string ColorHex { get; set; }

        public FillItem(Utils.Rect rect, string colorHex)
        {
            Rect = rect;
            ColorHex = colorHex;
        }
    }

    public class LineItem
    {
        // (X, Y)
        public Tuple<double, double> P1 { get; set; }
        public Tuple<double, double> P2 { get; set; }
        public BorderStyle Style { get; set; }
        public string ColorHex { get; set; }

        public LineItem(Tuple<double, double> p1, Tuple<double, double> p2, BorderStyle style, string colorHex)
        {
            P1 = p1;
            P2 = p2;
            Style = style;
            ColorHex = colorHex;
        }
    }

    public class TextItem
    {
        public double X { get; set; }
        public double Y { get; set; }
        public string Text { get; set; }
        public string FontName { get; set; }
        public double FontSizePt { get; set; }
        public bool IsBold { get; set; }
        public bool IsItalic { get; set; }
        public string ColorHex { get; set; }
        public HorizontalAlignment HAlign { get; set; }
        public int NLines { get; set; }
        
        // Cell reference such as "A1", for debugging
        public string Coord { get; set; }

        public TextItem(double x, double y, string text, CellModel cell, int nLines, string coord)
        {
            X = x;
            Y = y;
            Text = text;
            FontName = cell.FontName;
            FontSizePt = cell.FontSizePt;
            IsBold = cell.IsBold;
            IsItalic = cell.IsItalic;
            ColorHex = cell.FontColorHex;
            HAlign = cell.HAlign;
            NLines = nLines;
            Coord = coord;
        }
    }
}
