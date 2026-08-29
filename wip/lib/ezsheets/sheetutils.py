# -*- coding: utf-8 -*-
"""Shared Revit sheet / view helpers.

Depends only on the Revit API and this extension's config, not on pyRevit UI,
so the functions stay callable from anywhere.
"""

from __future__ import unicode_literals

from Autodesk.Revit.DB import (
    BuiltInCategory,
    BuiltInParameter,
    FilteredElementCollector,
    ViewDrafting,
    ViewSheet,
    ViewType,
    XYZ,
)

from ezsheets import config


# ---------------------------------------------------------------
# Version-safe helpers
# ---------------------------------------------------------------
def id_value(element_id):
    """ElementId -> plain int, across Revit versions.

    `ElementId.IntegerValue` was deprecated in Revit 2024 and REMOVED in 2026,
    where `ElementId.Value` (Int64) replaces it. Always go through this helper
    rather than touching either property directly.
    """
    try:
        return int(element_id.Value)
    except AttributeError:
        return int(element_id.IntegerValue)


# ---------------------------------------------------------------
# Collectors
# ---------------------------------------------------------------
def all_sheets(doc):
    """Every sheet in the document, view templates excluded."""
    return [v for v in FilteredElementCollector(doc)
            .OfClass(ViewSheet)
            .WhereElementIsNotElementType()
            .ToElements()
            if not v.IsTemplate]


def all_drafting_views(doc):
    """Every drafting view in the document, view templates excluded."""
    return [v for v in FilteredElementCollector(doc)
            .OfClass(ViewDrafting)
            .WhereElementIsNotElementType()
            .ToElements()
            if not v.IsTemplate]


def sheets_by_number(doc):
    """{sheet number: ViewSheet}"""
    return dict((s.SheetNumber, s) for s in all_sheets(doc))


def titleblock_instances(doc, sheet):
    """Title block instances placed on a given sheet."""
    return list(FilteredElementCollector(doc, sheet.Id)
                .OfCategory(BuiltInCategory.OST_TitleBlocks)
                .WhereElementIsNotElementType()
                .ToElements())


def titleblock_types(doc):
    """Every title block family symbol loaded in the document."""
    return list(FilteredElementCollector(doc)
                .OfCategory(BuiltInCategory.OST_TitleBlocks)
                .WhereElementIsElementType()
                .ToElements())


def viewports_on(doc, sheet):
    """Every viewport on a given sheet."""
    return [doc.GetElement(vp_id) for vp_id in sheet.GetAllViewports()]


# ---------------------------------------------------------------
# Measurement
# ---------------------------------------------------------------
def sheet_size_mm(doc, sheet):
    """Return (width mm, height mm).

    Reads the title block type parameters first, falls back to the instance
    bounding box. Returns (None, None) when neither is available.
    """
    tbs = titleblock_instances(doc, sheet)
    if not tbs:
        return (None, None)
    tb = tbs[0]

    # route 1: title block type parameters (most reliable)
    symbol = doc.GetElement(tb.GetTypeId())
    if symbol is not None:
        p_w = symbol.get_Parameter(BuiltInParameter.SHEET_WIDTH)
        p_h = symbol.get_Parameter(BuiltInParameter.SHEET_HEIGHT)
        if p_w and p_h:
            return (config.to_mm(p_w.AsDouble()), config.to_mm(p_h.AsDouble()))

    # route 2: instance bounding box
    bb = tb.get_BoundingBox(sheet)
    if bb is not None:
        return (config.to_mm(bb.Max.X - bb.Min.X),
                config.to_mm(bb.Max.Y - bb.Min.Y))
    return (None, None)


def is_a3(width_mm, height_mm):
    """True when the size matches A3 within tolerance, either orientation."""
    if width_mm is None or height_mm is None:
        return False
    tol = config.SHEET_SIZE_TOLERANCE_MM
    ew, eh = config.EXPECTED_SHEET_SIZE_MM
    return ((abs(width_mm - ew) <= tol and abs(height_mm - eh) <= tol) or
            (abs(width_mm - eh) <= tol and abs(height_mm - ew) <= tol))


def titleblock_origin_mm(doc, sheet):
    """Bottom-left corner of the title block instance, in sheet coordinates (mm).

    A Revit sheet's own (0,0) is wherever the sheet coordinate system happens to
    sit - it is NOT guaranteed to be the corner of the paper. The title block
    instance is the only reliable anchor for real paper coordinates, so every
    measurement should be expressed relative to this point.

    Returns None when the sheet carries no title block.
    """
    tbs = titleblock_instances(doc, sheet)
    if not tbs:
        return None
    bb = tbs[0].get_BoundingBox(sheet)
    if bb is None:
        return None
    return (config.to_mm(bb.Min.X), config.to_mm(bb.Min.Y))


def viewport_box_mm(vp, origin=None):
    """Outline of a viewport as (x0, y0, x1, y1) in millimetres.

    Pass `origin` (from titleblock_origin_mm) to get true paper coordinates with
    the paper's bottom-left corner as (0, 0). Without it the numbers are in raw
    sheet coordinates, whose origin is arbitrary.

    IMPORTANT: GetBoxOutline() bounds the view's *extents* - the crop region or
    the bounding box of every element in the view - not the ink you can see.
    On uncropped drafting views it can be substantially larger than the visible
    drawing, which is why measured gaps between outlines do not match the gaps
    a designer perceives. Compare against viewport_content_size_mm() to see how
    much slack a given viewport carries.
    """
    outline = vp.GetBoxOutline()
    lo, hi = outline.MinimumPoint, outline.MaximumPoint
    ox, oy = origin if origin else (0.0, 0.0)
    return (config.to_mm(lo.X) - ox, config.to_mm(lo.Y) - oy,
            config.to_mm(hi.X) - ox, config.to_mm(hi.Y) - oy)


_TWO_D_VIEWS = (ViewType.DraftingView, ViewType.Legend)


def viewport_content_size_mm(doc, vp):
    """Size of the *printed* drawing inside a viewport, as (width mm, height mm).

    Two different sources, because one method does not fit both kinds of view:

    - 2D views (drafting, legend): union the bounding boxes of every element.
      Everything sits in the view plane, so the union is the ink.
    - Model views (plan, elevation, section): use the crop box. Element bounding
      boxes are 3D and include datums whose extents run for tens of metres, so
      unioning them yields nonsense - measured 1807 mm of "content" on a 1:100
      elevation, which was the length of a level line.

    Returns (None, None) when the size cannot be established, e.g. an uncropped
    model view.
    """
    view = doc.GetElement(vp.ViewId)
    if view is None:
        return (None, None)
    try:
        scale = float(view.Scale)
    except Exception:
        return (None, None)
    if scale <= 0:
        return (None, None)

    if view.ViewType not in _TWO_D_VIEWS:
        return _cropbox_size_mm(view, scale)
    return _element_union_size_mm(doc, view, scale)


def _cropbox_size_mm(view, scale):
    """Printed size of a model view on paper. (None, None) when uncropped.

    Uses the ANNOTATION crop, not the model crop. What prints is the annotation
    crop: dimension strings, tags and level datums routinely stick out past the
    model crop, and Revit prints all of it. Measuring the model crop alone made
    one elevation look 81.7 mm narrower than its own viewport outline, while an
    elevation whose annotations stayed inside the model crop measured a perfect
    6.1 mm - the same view type cannot be both, so the model crop was simply the
    wrong box to read.
    """
    try:
        if not view.CropBoxActive:
            return (None, None)
        cb = view.CropBox
    except Exception:
        return (None, None)

    w = cb.Max.X - cb.Min.X
    h = cb.Max.Y - cb.Min.Y

    try:
        mgr = view.GetCropRegionShapeManager()
        if mgr.CanHaveAnnotationCrop and mgr.AnnotationCropActive:
            w += mgr.LeftAnnotationCropOffset + mgr.RightAnnotationCropOffset
            h += mgr.TopAnnotationCropOffset + mgr.BottomAnnotationCropOffset
    except Exception:
        pass   # older API or view type without an annotation crop

    return (config.to_mm(w) / scale, config.to_mm(h) / scale)


def _element_union_size_mm(doc, view, scale):
    """Union of every element's bounding box in a 2D view, converted to paper."""
    lo_x = lo_y = hi_x = hi_y = None
    for el in FilteredElementCollector(doc, view.Id) \
            .WhereElementIsNotElementType().ToElements():
        try:
            bb = el.get_BoundingBox(view)
        except Exception:
            bb = None
        if bb is None:
            continue
        if lo_x is None:
            lo_x, lo_y = bb.Min.X, bb.Min.Y
            hi_x, hi_y = bb.Max.X, bb.Max.Y
        else:
            lo_x = min(lo_x, bb.Min.X)
            lo_y = min(lo_y, bb.Min.Y)
            hi_x = max(hi_x, bb.Max.X)
            hi_y = max(hi_y, bb.Max.Y)

    if lo_x is None:
        return (None, None)
    return (config.to_mm(hi_x - lo_x) / scale,
            config.to_mm(hi_y - lo_y) / scale)


def viewport_label_box_mm(vp, origin=None):
    """Title bar outline as (x0, y0, x1, y1) in mm, or None when there is none."""
    try:
        outline = vp.GetLabelOutline()
    except Exception:
        return None
    if outline is None:
        return None
    lo, hi = outline.MinimumPoint, outline.MaximumPoint
    ox, oy = origin if origin else (0.0, 0.0)
    box = (config.to_mm(lo.X) - ox, config.to_mm(lo.Y) - oy,
           config.to_mm(hi.X) - ox, config.to_mm(hi.Y) - oy)
    if box[2] - box[0] <= 0.01 or box[3] - box[1] <= 0.01:
        return None
    return box


def viewport_total_box_mm(vp, origin=None):
    """Full footprint of a viewport: the view outline UNION its title bar.

    This is the box that must be packed, not GetBoxOutline() on its own.

    GetBoxOutline() covers the view only - the title (number bubble, name,
    scale and the rule under them) lives in a separate GetLabelOutline() and
    normally hangs BELOW the view. Packing the view outline alone pushed the
    bottom row down to the region floor and pushed every title off the paper,
    which is exactly what happened on A522.

    An earlier note in this file claimed detail sheets carried no viewport
    titles, inferred from the outline matching the ink to within 6.096 mm. That
    inference was backwards: the match proves the outline EXCLUDES the title.
    """
    box = viewport_box_mm(vp, origin)
    label = viewport_label_box_mm(vp, origin)
    if label is None:
        return box
    return (min(box[0], label[0]), min(box[1], label[1]),
            max(box[2], label[2]), max(box[3], label[3]))


def viewport_label_size_mm(vp):
    """Size of a viewport's title bar as (width mm, height mm).

    The view title - number bubble, name, scale and the rule under them - is
    included in GetBoxOutline() but not in any crop box, and its line can be set
    far wider than the view itself. That is why outline-minus-crop came out at
    81.7 mm on one elevation and 6.1 mm on another: the wide one had a title, the
    other did not.

    Returns (0.0, 0.0) when the viewport shows no title, which is the case on
    detail sheets here - their titles are ordinary text drawn inside the
    drafting view rather than Revit viewport labels.
    """
    try:
        outline = vp.GetLabelOutline()
    except Exception:
        return (0.0, 0.0)
    if outline is None:
        return (0.0, 0.0)
    lo, hi = outline.MinimumPoint, outline.MaximumPoint
    w = config.to_mm(hi.X - lo.X)
    h = config.to_mm(hi.Y - lo.Y)
    if w <= 0.01 or h <= 0.01:
        return (0.0, 0.0)
    return (w, h)


def outline_to_content_mm(w_mm, h_mm):
    """Convert a viewport outline size to the drawing size inside it."""
    p = config.VIEWPORT_OUTLINE_PADDING_MM
    return (w_mm - p, h_mm - p)


def content_to_outline_mm(w_mm, h_mm):
    """Convert a drawing size to the viewport outline it will occupy.

    Measured across 14 drafting-view viewports in 54 Windrush Close: the outline
    exceeds the content by exactly 6.1 mm in both axes, every time. That is
    0.02 ft - Revit pads the outline by 0.01 ft per side. Because the padding is
    an exact constant, a packing algorithm can plan in content sizes and convert
    to outline sizes losslessly.
    """
    p = config.VIEWPORT_OUTLINE_PADDING_MM
    return (w_mm + p, h_mm + p)


def viewport_size_mm(vp):
    """Return (width mm, height mm) of a placed viewport outline."""
    x0, y0, x1, y1 = viewport_box_mm(vp)
    return (x1 - x0, y1 - y0)


def set_viewport_center_mm(vp, x_mm, y_mm):
    """Move a viewport so its box centre lands on (x_mm, y_mm).

    The API exposes SetBoxCenter only - there is no way to set a corner
    directly, so corner alignment has to be converted to a centre.
    """
    vp.SetBoxCenter(XYZ(config.mm(x_mm), config.mm(y_mm), 0.0))


def set_viewport_topleft_mm(vp, x_mm, y_mm):
    """Align the top-left corner of a viewport's outline to (x_mm, y_mm)."""
    w, h = viewport_size_mm(vp)
    set_viewport_center_mm(vp, x_mm + w / 2.0, y_mm - h / 2.0)


# ---------------------------------------------------------------
# Parameter read / write
# ---------------------------------------------------------------
_SHEET_PARAMS = {
    "date": BuiltInParameter.SHEET_ISSUE_DATE,
    "drawn_by": BuiltInParameter.SHEET_DRAWN_BY,
    "checked_by": BuiltInParameter.SHEET_CHECKED_BY,
}


def set_sheet_field(sheet, field, value):
    """Write a sheet parameter. field is one of date / drawn_by / checked_by.
    Returns True on success, False when the parameter is missing or read-only.
    """
    bip = _SHEET_PARAMS.get(field)
    if bip is None:
        return False
    p = sheet.get_Parameter(bip)
    if p is None or p.IsReadOnly:
        return False
    p.Set(value)
    return True


_PROJECT_PARAMS = {
    "project_number": BuiltInParameter.PROJECT_NUMBER,
    "project_name": BuiltInParameter.PROJECT_NAME,
    "project_address": BuiltInParameter.PROJECT_ADDRESS,
    "client_name": BuiltInParameter.CLIENT_NAME,
}


def set_project_field(doc, field, value):
    """Write a Project Information parameter. Returns True / False."""
    bip = _PROJECT_PARAMS.get(field)
    if bip is None:
        return False
    info = doc.ProjectInformation
    p = info.get_Parameter(bip)
    if p is None or p.IsReadOnly:
        return False
    p.Set(value)
    return True


def get_param_text(element, name):
    """Read a parameter by name as text, empty string when absent."""
    p = element.LookupParameter(name)
    if p is None:
        return ""
    try:
        return p.AsString() or p.AsValueString() or ""
    except Exception:
        return ""


def set_param_text(element, name, value):
    """Write a text parameter by name. Returns True / False."""
    p = element.LookupParameter(name)
    if p is None or p.IsReadOnly:
        return False
    p.Set(value)
    return True
