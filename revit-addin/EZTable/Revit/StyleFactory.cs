using System;
using System.Collections.Generic;
using System.Linq;
using Autodesk.Revit.DB;
using EZTable.Models;
using BorderStyle = EZTable.Models.BorderStyle;
using Color = Autodesk.Revit.DB.Color;

namespace EZTable.Revit
{
    public class StyleFactory
    {
        private Document _doc;
        private Dictionary<string, GraphicsStyle> _lineStyles = new Dictionary<string, GraphicsStyle>();
        private Dictionary<string, FilledRegionType> _fillTypes = new Dictionary<string, FilledRegionType>();
        private Dictionary<string, TextNoteType> _textTypes = new Dictionary<string, TextNoteType>();
        private ElementId _solidPatternId = null;

        public StyleFactory(Document doc)
        {
            _doc = doc;
        }

        private double? _baseCapFt;
        private bool _baseCapLookedUp;

        /// <summary>
        /// The base text type's TEXT_SIZE in feet, or null when there is no base
        /// type. Plan.BuildPlan needs it before any transaction opens, so that
        /// layout and rendering agree on the cap height.
        /// </summary>
        public double? BaseTextCapHeightFt()
        {
            if (_baseCapLookedUp) return _baseCapFt;
            _baseCapLookedUp = true;
            _baseCapFt = null;

            string baseName = Core.Config.BaseTextTypeName;
            if (string.IsNullOrEmpty(baseName)) return null;

            var baseType = new FilteredElementCollector(_doc)
                .OfClass(typeof(TextNoteType))
                .Cast<TextNoteType>()
                .FirstOrDefault(t => t.Name == baseName);
            if (baseType == null) return null;

            var p = baseType.get_Parameter(BuiltInParameter.TEXT_SIZE);
            if (p != null) _baseCapFt = p.AsDouble();
            return _baseCapFt;
        }

        public GraphicsStyle GetLineStyle(BorderStyle style, string colorHex)
        {
            string key = $"{style}_{colorHex}";
            if (_lineStyles.TryGetValue(key, out var gs)) return gs;

            string name = $"EZ_{style}";
            if (colorHex != "000000") 
            {
                name += $"_{colorHex}";
            }
            else
            {
                if (style == BorderStyle.Thin || style == BorderStyle.Dashed) name = Core.Config.LineStyleThin;
                else if (style == BorderStyle.Medium) name = Core.Config.LineStyleMedium;
                else if (style == BorderStyle.Thick) name = Core.Config.LineStyleThick;
            }

            var cats = _doc.Settings.Categories;
            var linesCat = cats.get_Item(BuiltInCategory.OST_Lines);

            Category subCat = null;
            foreach (Category c in linesCat.SubCategories)
            {
                if (c.Name == name)
                {
                    subCat = c;
                    break;
                }
            }

            if (subCat == null)
            {
                subCat = cats.NewSubcategory(linesCat, name);
                
                int weight = style == BorderStyle.Thick ? 5 : (style == BorderStyle.Medium ? 3 : 1);
                subCat.SetLineWeight(weight, GraphicsStyleType.Projection);
                
                var color = HexToColor(colorHex);
                subCat.LineColor = color;
            }

            var gStyle = subCat.GetGraphicsStyle(GraphicsStyleType.Projection);
            _lineStyles[key] = gStyle;
            return gStyle;
        }

        public FilledRegionType GetFillType(string colorHex)
        {
            if (string.IsNullOrEmpty(colorHex)) return null;
            if (colorHex.ToUpper() == "FFFFFF") return null;

            if (_fillTypes.TryGetValue(colorHex, out var frt)) return frt;

            string name = GetFillTypeName(colorHex);
            var existing = new FilteredElementCollector(_doc)
                .OfClass(typeof(FilledRegionType))
                .Cast<FilledRegionType>()
                .FirstOrDefault(f => f.Name == name);

            if (existing != null)
            {
                _fillTypes[colorHex] = existing;
                return existing;
            }

            var baseType = new FilteredElementCollector(_doc)
                .OfClass(typeof(FilledRegionType))
                .Cast<FilledRegionType>()
                .FirstOrDefault();

            if (baseType == null) throw new Exception("No FilledRegionType found in the project to duplicate.");

            var newType = baseType.Duplicate(name) as FilledRegionType;
            newType.ForegroundPatternId = GetSolidPatternId();
            newType.ForegroundPatternColor = HexToColor(colorHex);
            newType.BackgroundPatternId = ElementId.InvalidElementId;
            
            // Try to set the line style to invisible lines
            var invisibleId = GetInvisibleLinesId(_doc);
            if (invisibleId != ElementId.InvalidElementId && newType.get_Parameter(BuiltInParameter.LINE_PEN) != null)
            {
                // In Revit 2026, FilledRegionType does not have LineStyleId property, it's on FilledRegion
            }

            _fillTypes[colorHex] = newType;
            return newType;
        }

        public TextNoteType GetTextType(string fontName, double sizePt, bool isBold, bool isItalic, string colorHex)
        {
            string baseName = Core.Config.BaseTextTypeName;
            var baseType = string.IsNullOrEmpty(baseName) ? null
                : new FilteredElementCollector(_doc)
                    .OfClass(typeof(TextNoteType))
                    .Cast<TextNoteType>()
                    .FirstOrDefault(t => t.Name == baseName);

            string name;
            bool useBaseFormat = false;

            double scale = 1.0;
            bool scaled = false;
            if (baseType != null)
            {
                // The base type stands for Excel text at Config.BaseTextSizePt; any
                // other size gets a proportionally scaled copy, named the way the
                // project names things: "2.0mm Arial" -> "2.6mm Arial".
                double? baseCap = BaseTextCapHeightFt();
                scale = Core.Config.TextScale(sizePt);
                scaled = baseCap != null && baseCap.Value > 0 && Math.Abs(scale - 1.0) > 1e-6;

                string stem = scaled
                    ? Core.Config.ResizeTextTypeName(baseName, baseCap.Value * scale * 304.8)
                    : baseName;
                name = GetTextTypeName(stem, isBold, isItalic, colorHex);
                useBaseFormat = true;
            }
            else
            {
                // "0.####" matches Python's '%g': 7.0 -> "7", 7.5 -> "7.5", so both
                // implementations name this type identically and do not create duplicates
                string sizeStr = sizePt.ToString("0.####",
                    System.Globalization.CultureInfo.InvariantCulture).Replace(".", "p");
                name = $"EZ_{fontName.Replace(" ", "")}_{sizeStr}_{(isBold ? "B" : "")}{(isItalic ? "I" : "")}_{colorHex}";
            }

            if (_textTypes.TryGetValue(name, out var tnt)) return tnt;

            var existing = new FilteredElementCollector(_doc)
                .OfClass(typeof(TextNoteType))
                .Cast<TextNoteType>()
                .FirstOrDefault(t => t.Name == name);

            if (existing != null)
            {
                _textTypes[name] = existing;
                return existing;
            }

            if (baseType == null)
            {
                baseType = new FilteredElementCollector(_doc)
                    .OfClass(typeof(TextNoteType))
                    .Cast<TextNoteType>()
                    .FirstOrDefault();
            }

            if (baseType == null) throw new Exception("No TextNoteType found in the project to duplicate.");

            var newType = baseType.Duplicate(name) as TextNoteType;
            
            // When not inheriting from a base type, override with Excel's own
            // font and size
            if (!useBaseFormat)
            {
                SetParameter(newType, BuiltInParameter.TEXT_FONT, fontName);
                SetParameter(newType, BuiltInParameter.TEXT_SIZE, Utils.Geometry.RevitTextSizeFeet(sizePt, fontName));
            }
            else if (scaled)
            {
                // TEXT_SIZE is a cap height in feet -- see Geometry.cs
                SetParameter(newType, BuiltInParameter.TEXT_SIZE,
                             BaseTextCapHeightFt().Value * scale);
            }

            SetParameter(newType, BuiltInParameter.TEXT_STYLE_BOLD, isBold ? 1 : 0);
            SetParameter(newType, BuiltInParameter.TEXT_STYLE_ITALIC, isItalic ? 1 : 0);
            SetParameter(newType, BuiltInParameter.LINE_COLOR, HexToInt(colorHex));
            SetParameter(newType, BuiltInParameter.TEXT_BACKGROUND, 1); // Transparent = 1

            _textTypes[name] = newType;
            return newType;
        }

        private string GetFillTypeName(string hex)
        {
            int r = Convert.ToInt32(hex.Substring(0, 2), 16);
            int g = Convert.ToInt32(hex.Substring(2, 2), 16);
            int b = Convert.ToInt32(hex.Substring(4, 2), 16);
            int max = Math.Max(r, Math.Max(g, b));
            int min = Math.Min(r, Math.Min(g, b));

            if (max - min <= Core.Config.GreyTolerance)
            {
                int greyLevel = (int)Math.Round((r + g + b) / 3.0);
                // Only greys close to the standard type's own level use it. Snapping
                // every grey on to one type made light shading come out far darker
                // than the source -- Excel's 230 and 242 both rendered at 192.
                if (!string.IsNullOrEmpty(Core.Config.GreyFillTypeName) &&
                    Core.Config.SnapsToGreyType(greyLevel, Core.Config.GreyFillTypeName))
                    return Core.Config.GreyFillTypeName;
                return $"{Core.Config.FillTypePrefix} Grey {greyLevel}";
            }
            return $"{Core.Config.FillTypePrefix} {GetColorName(r, g, b)} {hex.ToUpper()}";
        }

        private string GetTextTypeName(string baseName, bool isBold, bool isItalic, string hex)
        {
            var parts = new List<string> { baseName };
            if (isBold) parts.Add("BOLD");
            if (isItalic) parts.Add("ITALIC");

            if (!string.IsNullOrEmpty(hex) && hex.ToUpper() != "000000")
            {
                int r = Convert.ToInt32(hex.Substring(0, 2), 16);
                int g = Convert.ToInt32(hex.Substring(2, 2), 16);
                int b = Convert.ToInt32(hex.Substring(4, 2), 16);
                int max = Math.Max(r, Math.Max(g, b));
                int min = Math.Min(r, Math.Min(g, b));

                if (max - min <= Core.Config.GreyTolerance)
                {
                    int greyLevel = (int)Math.Round((r + g + b) / 3.0);
                    parts.Add($"GREY {greyLevel}");
                }
                else
                {
                    parts.Add(GetColorName(r, g, b).ToUpper());
                }
            }

            return string.Join(" ", parts);
        }

        private string GetColorName(int r, int g, int b)
        {
            int max = Math.Max(r, Math.Max(g, b));
            int min = Math.Min(r, Math.Min(g, b));
            double d = max - min;
            double hue = 0;
            if (d == 0) return "Grey";

            if (max == r) hue = 60.0 * (((g - b) / d) % 6.0);
            else if (max == g) hue = 60.0 * (((b - r) / d) + 2.0);
            else hue = 60.0 * (((r - g) / d) + 4.0);

            if (hue < 0) hue += 360.0;

            if (hue < 15) return "Red";
            if (hue < 45) return "Orange";
            if (hue < 70) return "Yellow";
            if (hue < 160) return "Green";
            if (hue < 200) return "Cyan";
            if (hue < 260) return "Blue";
            if (hue < 290) return "Purple";
            if (hue < 345) return "Pink";
            return "Red";
        }

        private static ElementId GetInvisibleLinesId(Document doc)
        {
            var target = new ElementId(BuiltInCategory.OST_InvisibleLines);
            foreach (var gs in new FilteredElementCollector(doc).OfClass(typeof(GraphicsStyle)).Cast<GraphicsStyle>())
            {
                if (gs.GraphicsStyleCategory != null && gs.GraphicsStyleCategory.Id == target)
                {
                    return gs.Id;
                }
            }
            return ElementId.InvalidElementId;
        }

        private ElementId GetSolidPatternId()
        {
            if (_solidPatternId != null) return _solidPatternId;
            
            var patterns = new FilteredElementCollector(_doc)
                .OfClass(typeof(FillPatternElement))
                .Cast<FillPatternElement>();

            foreach (var fp in patterns)
            {
                if (fp.GetFillPattern().IsSolidFill && fp.GetFillPattern().Target == FillPatternTarget.Drafting)
                {
                    _solidPatternId = fp.Id;
                    return fp.Id;
                }
            }
            throw new Exception("No Solid fill pattern found.");
        }

        private Color HexToColor(string hex)
        {
            if (string.IsNullOrEmpty(hex) || hex.Length < 6) return new Color(0, 0, 0);
            byte r = Convert.ToByte(hex.Substring(0, 2), 16);
            byte g = Convert.ToByte(hex.Substring(2, 2), 16);
            byte b = Convert.ToByte(hex.Substring(4, 2), 16);
            return new Color(r, g, b);
        }

        private int HexToInt(string hex)
        {
            if (string.IsNullOrEmpty(hex) || hex.Length < 6) return 0;
            int r = Convert.ToInt32(hex.Substring(0, 2), 16);
            int g = Convert.ToInt32(hex.Substring(2, 2), 16);
            int b = Convert.ToInt32(hex.Substring(4, 2), 16);
            // Revit color integer is R + G * 256 + B * 65536
            return r + (g << 8) + (b << 16);
        }

        private void SetParameter(Element el, BuiltInParameter bip, object value)
        {
            var p = el.get_Parameter(bip);
            if (p != null && !p.IsReadOnly)
            {
                if (value is string s) p.Set(s);
                else if (value is double d) p.Set(d);
                else if (value is int i) p.Set(i);
            }
        }
    }
}



