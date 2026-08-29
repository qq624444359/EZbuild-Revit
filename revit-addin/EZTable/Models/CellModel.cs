using System;

namespace EZTable.Models
{
    public class CellModel
    {
        public int Row { get; set; }
        public int Column { get; set; }
        
        // Span of a merged cell
        public int RowSpan { get; set; } = 1;
        public int ColSpan { get; set; } = 1;

        // Content
        public string Text { get; set; } = string.Empty;

        // Font styling
        public string FontName { get; set; } = "Arial";
        public double FontSizePt { get; set; } = 11.0;
        public bool IsBold { get; set; } = false;
        public bool IsItalic { get; set; } = false;
        public string FontColorHex { get; set; } = "000000";

        // Alignment
        public HorizontalAlignment HAlign { get; set; } = HorizontalAlignment.Left;
        public VerticalAlignment VAlign { get; set; } = VerticalAlignment.Bottom; // Excel's real default is bottom, not top
        public bool WrapText { get; set; } = false;

        // Fill colour
        public string FillColorHex { get; set; } // null or FFFFFF means no fill

        // Borders
        public BorderModel TopBorder { get; set; }
        public BorderModel BottomBorder { get; set; }
        public BorderModel LeftBorder { get; set; }
        public BorderModel RightBorder { get; set; }

        public bool IsMerged => RowSpan > 1 || ColSpan > 1;
    }

    public enum HorizontalAlignment
    {
        Left,
        Center,
        Right
    }

    public enum VerticalAlignment
    {
        Top,
        Center,
        Bottom
    }

    public class BorderModel
    {
        public BorderStyle Style { get; set; }
        public string ColorHex { get; set; } = "000000";

        public BorderModel(BorderStyle style, string colorHex = "000000")
        {
            Style = style;
            ColorHex = colorHex;
        }
    }

    public enum BorderStyle
    {
        None,
        Thin,
        Medium,
        Thick,
        Double,
        Dashed
    }
}
