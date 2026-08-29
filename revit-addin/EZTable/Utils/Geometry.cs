using System;
using System.Collections.Generic;

namespace EZTable.Utils
{
    public static class Geometry
    {
        public const double POINTS_PER_INCH = 72.0;
        public const double INCHES_PER_FOOT = 12.0;
        public const double PIXELS_PER_INCH = 96.0;
        
        // Pixel width of '0' in Calibri 11 @96dpi -- the basis of Excel column widths
        public const double MDW = 7.0;
        // Total left+right cell padding in Excel, in pixels
        public const double CELL_PADDING_PX = 5.0;

        public const double DEFAULT_COL_WIDTH_CHARS = 8.43;
        public const double DEFAULT_ROW_HEIGHT_POINTS = 15.0;

        // TextNote padding on one side: Excel's default 2px per side, in feet
        public const double TEXT_PADDING_FT = 2.0 / PIXELS_PER_INCH / INCHES_PER_FOOT;

        // Ratio of line pitch (top to top) to TEXT_SIZE (which is a cap height)
        public const double REVIT_LINE_PITCH_FACTOR = 1.60;

        // Font name -> (CapHeight / Em, Ascender / Em)
        private static readonly Dictionary<string, (double CapRatio, double AscRatio)> FontMetrics = 
            new Dictionary<string, (double, double)>(StringComparer.OrdinalIgnoreCase)
        {
            { "arial", (0.7163, 0.9052) },
            { "liberation sans", (0.7163, 0.9052) },
            { "helvetica", (0.7170, 0.9050) },
            { "arial narrow", (0.7163, 0.9052) },
            { "calibri", (0.6318, 0.7500) },
            { "times new roman", (0.6548, 0.8911) },
            { "tahoma", (0.7271, 1.0000) },
            { "verdana", (0.7271, 1.0050) },
            { "segoe ui", (0.7000, 0.9198) },
            { "microsoft yahei", (0.7300, 1.0000) },
            { "simsun", (0.7300, 0.8600) },
            { "simhei", (0.7300, 0.8600) }
        };

        public static (double CapRatio, double AscRatio) GetFontMetrics(string fontName)
        {
            if (string.IsNullOrWhiteSpace(fontName) || !FontMetrics.TryGetValue(fontName.Trim(), out var metrics))
            {
                return FontMetrics["arial"];
            }
            return metrics;
        }

        /// <summary>
        /// Excel font size in points -> Revit TEXT_SIZE in feet. Note that Revit
        /// wants a cap height, not the nominal font size.
        /// </summary>
        public static double RevitTextSizeFeet(double sizePt, string fontName = "Arial")
        {
            double capRatio = GetFontMetrics(fontName).CapRatio;
            return PointsToFeet(sizePt * capRatio);
        }

        /// <summary>
        /// The nominal font size in points that corresponds to a drawn cap height.
        /// The inverse of RevitTextSizeFeet, used so text is measured at the size it
        /// will actually be drawn rather than at Excel's own size.
        /// </summary>
        public static double EmSizePtFromCap(double capFt, string fontName = "Arial")
        {
            double capRatio = GetFontMetrics(fontName).CapRatio;
            return FeetToPoints(capFt) / capRatio;
        }

        public static double PointsToFeet(double pt) => pt / POINTS_PER_INCH / INCHES_PER_FOOT;
        public static double FeetToPoints(double ft) => ft * POINTS_PER_INCH * INCHES_PER_FOOT;
        public static double PixelsToFeet(double px) => px / PIXELS_PER_INCH / INCHES_PER_FOOT;
        public static double FeetToMm(double ft) => ft * INCHES_PER_FOOT * 25.4;
        public static double MmToFeet(double mm) => mm / 25.4 / INCHES_PER_FOOT;

        /// <summary>
        /// Convert an Excel character column width to feet. Pixels are rounded
        /// internally so the error cannot accumulate across columns.
        /// </summary>
        public static double ColWidthToFeet(double widthChars)
        {
            double px = Math.Round(widthChars * MDW + CELL_PADDING_PX);
            return PixelsToFeet(px);
        }

        public static double RowHeightToFeet(double heightPoints) => PointsToFeet(heightPoints);
    }
}
