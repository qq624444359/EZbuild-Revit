using System;
using System.Collections.Generic;
using System.Linq;
using Autodesk.Revit.DB;
using EZTable.Core;
using EZTable.Models;

namespace EZTable.Revit
{
    public class Renderer
    {
        public static void DrawPlan(Document doc, Autodesk.Revit.DB.View view, Plan plan, StyleFactory styles)
        {
            // 1. Create every line style, fill and text type the plan needs
            //    (all created or fetched inside the current transaction)
            foreach (var line in plan.Lines)
            {
                styles.GetLineStyle(line.Style, line.ColorHex);
            }
            foreach (var fill in plan.Fills)
            {
                styles.GetFillType(fill.ColorHex);
            }
            foreach (var text in plan.Texts)
            {
                styles.GetTextType(text.FontName, text.FontSizePt, text.IsBold, text.IsItalic, text.ColorHex);
            }

            // Regenerate so the styles just created become usable
            doc.Regenerate();

            // 2. Draw the fills (filled regions)
            foreach (var fill in plan.Fills)
            {
                var frt = styles.GetFillType(fill.ColorHex);
                if (frt == null) continue;

                var loop = new List<Curve>();
                var p1 = new XYZ(fill.Rect.XLeft, fill.Rect.YTop, 0);
                var p2 = new XYZ(fill.Rect.XRight, fill.Rect.YTop, 0);
                var p3 = new XYZ(fill.Rect.XRight, fill.Rect.YBottom, 0);
                var p4 = new XYZ(fill.Rect.XLeft, fill.Rect.YBottom, 0);

                loop.Add(Line.CreateBound(p1, p2));
                loop.Add(Line.CreateBound(p2, p3));
                loop.Add(Line.CreateBound(p3, p4));
                loop.Add(Line.CreateBound(p4, p1));

                var curveLoop = CurveLoop.Create(loop);
                var region = FilledRegion.Create(doc, frt.Id, view.Id, new List<CurveLoop> { curveLoop });
                
                // On Revit 2026 the boundary line style is set on the
                // FilledRegion instance. Assigning invisible lines keeps the
                // region outline from doubling up with the borders we draw.
                var invisibleId = GetInvisibleLinesId(doc);
                if (invisibleId != ElementId.InvalidElementId)
                {
                    region.SetLineStyleId(invisibleId);
                }
            }

            // 3. Draw the borders (detail lines)
            foreach (var line in plan.Lines)
            {
                var gs = styles.GetLineStyle(line.Style, line.ColorHex);
                if (gs == null) continue;

                var p1 = new XYZ(line.P1.Item1, line.P1.Item2, 0);
                var p2 = new XYZ(line.P2.Item1, line.P2.Item2, 0);
                if (p1.DistanceTo(p2) < doc.Application.ShortCurveTolerance) continue;

                var geomLine = Line.CreateBound(p1, p2);
                var detailCurve = doc.Create.NewDetailCurve(view, geomLine);
                detailCurve.LineStyle = gs;
            }

            // 4. Draw the text (text notes)
            var textOptions = new TextNoteOptions
            {
                TypeId = ElementId.InvalidElementId,
                HorizontalAlignment = Autodesk.Revit.DB.HorizontalTextAlignment.Left
            };

            foreach (var text in plan.Texts)
            {
                var type = styles.GetTextType(text.FontName, text.FontSizePt, text.IsBold, text.IsItalic, text.ColorHex);
                textOptions.TypeId = type.Id;

                textOptions.HorizontalAlignment = text.HAlign switch
                {
                    EZTable.Models.HorizontalAlignment.Center => Autodesk.Revit.DB.HorizontalTextAlignment.Center,
                    EZTable.Models.HorizontalAlignment.Right => Autodesk.Revit.DB.HorizontalTextAlignment.Right,
                    _ => Autodesk.Revit.DB.HorizontalTextAlignment.Left
                };

                var origin = new XYZ(text.X, text.Y, 0);
                TextNote.Create(doc, view.Id, origin, text.Text, textOptions);
            }
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
    }
}

