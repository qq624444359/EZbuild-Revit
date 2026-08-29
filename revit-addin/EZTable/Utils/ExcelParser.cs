using System;
using System.Collections.Generic;
using System.Linq;
using ClosedXML.Excel;
using EZTable.Models;
using BorderStyle = EZTable.Models.BorderStyle;
using HorizontalAlignment = EZTable.Models.HorizontalAlignment;
using VerticalAlignment = EZTable.Models.VerticalAlignment;

namespace EZTable.Utils
{
    public class ExcelParser
    {
        public static SheetData ParseSheet(XLWorkbook workbook, string sheetName)
        {
            var data = new SheetData { SheetName = sheetName };
            var ws = workbook.Worksheet(sheetName);

            var usedRange = ws.RangeUsed();
            if (usedRange == null)
            {
                data.Warnings.Add("The worksheet is empty - no used cells were found.");
                return data;
            }

            // Collect the hidden rows and columns so they can be skipped
            var hiddenRows = ws.Rows().Where(r => r.IsHidden).Select(r => r.RowNumber()).ToHashSet();
            var hiddenCols = ws.Columns().Where(c => c.IsHidden).Select(c => c.ColumnNumber()).ToHashSet();

            // Collect every merged range
            var mergedRanges = ws.MergedRanges;

            foreach (var row in usedRange.Rows())
            {
                int rIdx = row.RowNumber();
                if (hiddenRows.Contains(rIdx)) continue;

                foreach (var cell in row.Cells())
                {
                    int cIdx = cell.Address.ColumnNumber;
                    if (hiddenCols.Contains(cIdx)) continue;

                    // Skip cells inside a merged range that are not its
                    // top-left anchor
                    if (IsInnerMergedCell(cell, mergedRanges, out var mergedRange))
                        continue;

                    var model = new CellModel
                    {
                        Row = rIdx,
                        Column = cIdx,
                        // ClosedXML already applies some basic formatting to Value,
                        // but we Trim() to remove accounting format space-padding
                        // that would otherwise artificially inflate the text width in Revit.
                        Text = cell.GetFormattedString().Trim()
                    };

                    // On the top-left anchor, record the span
                    if (mergedRange != null)
                    {
                        model.RowSpan = mergedRange.RowCount();
                        model.ColSpan = mergedRange.ColumnCount();
                    }

                    // --- font ---
                    var font = cell.Style.Font;
                    model.FontName = font.FontName ?? "Arial";
                    model.FontSizePt = font.FontSize > 0 ? font.FontSize : 11.0;
                    model.IsBold = font.Bold;
                    model.IsItalic = font.Italic;
                    model.FontColorHex = GetSafeColorHex(font.FontColor, workbook) ?? "000000";

                    // --- fill colour ---
                    var fill = cell.Style.Fill;
                    if (fill.PatternType != XLFillPatternValues.None && fill.BackgroundColor.HasValue)
                    {
                        model.FillColorHex = GetSafeColorHex(fill.BackgroundColor, workbook);
                    }

                    // --- alignment ---
                    var align = cell.Style.Alignment;
                    model.WrapText = align.WrapText;

                    model.HAlign = align.Horizontal switch
                    {
                        XLAlignmentHorizontalValues.Center => HorizontalAlignment.Center,
                        XLAlignmentHorizontalValues.Right => HorizontalAlignment.Right,
                        _ => HorizontalAlignment.Left
                    };

                    model.VAlign = align.Vertical switch
                    {
                        XLAlignmentVerticalValues.Top => VerticalAlignment.Top,
                        XLAlignmentVerticalValues.Center => VerticalAlignment.Center,
                        _ => VerticalAlignment.Bottom
                    };

                    // --- borders ---
                    var border = cell.Style.Border;
                    model.TopBorder = ConvertBorder(border.TopBorder, border.TopBorderColor, data.Warnings, cell.Address.ToString(), "top", workbook);
                    model.BottomBorder = ConvertBorder(border.BottomBorder, border.BottomBorderColor, data.Warnings, cell.Address.ToString(), "bottom", workbook);
                    model.LeftBorder = ConvertBorder(border.LeftBorder, border.LeftBorderColor, data.Warnings, cell.Address.ToString(), "left", workbook);
                    model.RightBorder = ConvertBorder(border.RightBorder, border.RightBorderColor, data.Warnings, cell.Address.ToString(), "right", workbook);

                    data.Cells.Add(model);
                }
            }

            // Read the row heights and column widths
            foreach (var row in usedRange.Rows())
            {
                if (!hiddenRows.Contains(row.RowNumber()))
                {
                    data.RowHeightsFt[row.RowNumber()] = Geometry.RowHeightToFeet(ws.Row(row.RowNumber()).Height);
                }
            }

            foreach (var col in usedRange.Columns())
            {
                if (!hiddenCols.Contains(col.ColumnNumber()))
                {
                    data.ColWidthsFt[col.ColumnNumber()] = Geometry.ColWidthToFeet(ws.Column(col.ColumnNumber()).Width);
                }
            }

            return data;
        }

        private static bool IsInnerMergedCell(IXLCell cell, IXLRanges mergedRanges, out IXLRange mergedRange)
        {
            mergedRange = mergedRanges.FirstOrDefault(r => r.Contains(cell));
            if (mergedRange == null) return false;
            
            // A cell inside a merged range that is not its first cell counts
            // as an inner cell
            return cell.Address.RowNumber != mergedRange.FirstRow().RowNumber() ||
                   cell.Address.ColumnNumber != mergedRange.FirstColumn().ColumnNumber();
        }

        private static EZTable.Models.BorderModel ConvertBorder(XLBorderStyleValues style, XLColor color, List<string> warnings, string cellAddr, string side, IXLWorkbook wb)
        {
            if (style == XLBorderStyleValues.None) return null;

            var borderStyle = BorderStyle.Thin; // default
            switch (style)
            {
                case XLBorderStyleValues.Hair:
                case XLBorderStyleValues.Thin:
                    borderStyle = BorderStyle.Thin;
                    break;
                case XLBorderStyleValues.Medium:
                case XLBorderStyleValues.MediumDashed:
                case XLBorderStyleValues.MediumDashDot:
                case XLBorderStyleValues.MediumDashDotDot:
                case XLBorderStyleValues.SlantDashDot:
                    borderStyle = BorderStyle.Medium;
                    break;
                case XLBorderStyleValues.Thick:
                    borderStyle = BorderStyle.Thick;
                    break;
                case XLBorderStyleValues.Dotted:
                case XLBorderStyleValues.Dashed:
                case XLBorderStyleValues.DashDot:
                case XLBorderStyleValues.DashDotDot:
                    borderStyle = BorderStyle.Dashed;
                    break;
                case XLBorderStyleValues.Double:
                    borderStyle = BorderStyle.Medium;
                    warnings.Add($"Cell {cellAddr} has a double border on the {side} side - drawn as medium");
                    break;
                default:
                    warnings.Add($"Unknown border style {style} at {cellAddr} - fell back to thin");
                    break;
            }

            string hex = GetSafeColorHex(color, wb) ?? "000000";
            return new EZTable.Models.BorderModel(borderStyle, hex);
        }

        private static int ApplyTint(int v, double tint)
        {
            if (tint < 0)
            {
                return Math.Max(0, Math.Min(255, (int)Math.Round(v * (1 + tint))));
            }
            else
            {
                return Math.Max(0, Math.Min(255, (int)Math.Round(v * (1 - tint) + 255 * tint)));
            }
        }

        private static string GetSafeColorHex(XLColor c, IXLWorkbook wb)
        {
            if (c == null || !c.HasValue) return null;
            
            try
            {
                if (c.ColorType == XLColorType.Color)
                {
                    return c.Color.R.ToString("X2") + c.Color.G.ToString("X2") + c.Color.B.ToString("X2");
                }
                else if (c.ColorType == XLColorType.Theme)
                {
                    try
                    {
                        var resolved = wb.Theme.ResolveThemeColor(c.ThemeColor).Color;
                                                  double tint = c.ThemeTint;
                          if (tint != 0)
                          {
                              int r = resolved.R;
                              int g = resolved.G;
                              int b = resolved.B;
                              r = ApplyTint(r, tint);
                              g = ApplyTint(g, tint);
                              b = ApplyTint(b, tint);
                              return r.ToString("X2") + g.ToString("X2") + b.ToString("X2");
                          }
                          return resolved.R.ToString("X2") + resolved.G.ToString("X2") + resolved.B.ToString("X2");
                    }
                    catch
                    {
                        return "000000";
                    }
                }
                else if (c.ColorType == XLColorType.Indexed)
                {
                    // Indexed colors in newer ClosedXML usually can be resolved to Color
                    return c.Color.R.ToString("X2") + c.Color.G.ToString("X2") + c.Color.B.ToString("X2");
                }
            }
            catch
            {
                return "000000";
            }
            
            return "000000";
        }
    }
}


