# -*- coding: utf-8 -*-
"""
styles.py -- lookup / creation / caching of Revit type elements

Existing drafting standards in the project are reused wherever possible
(see config.py):
    line styles  <Thin Lines> / <Medium Lines> / <Wide Lines>
    fills        grey always uses Fill Grey 192; other colours are created
                 automatically under the same naming scheme
    text         derived from 2.0mm Arial; bold, italic and coloured variants
                 are copies of it

**Types that already exist are never modified.** The Fill Grey 192 and
2.0mm Arial you maintain are only read and copied; this tool will never
overwrite them.

Three traps found by measurement, none of them mentioned in the spec:
  * TEXT_SIZE is a cap height, not a font size, and its unit is feet -- see
    geometry.py
  * FilledRegionType has no LineStyleId; the boundary line style goes on the
    instance
  * NewSubcategory must run inside a Transaction, followed by doc.Regenerate()
"""

from __future__ import division, unicode_literals

from Autodesk.Revit.DB import (
    BuiltInCategory, BuiltInParameter, Category, Color, ElementId,
    FillPatternElement, FillPatternTarget, FilledRegionType,
    FilteredElementCollector, GraphicsStyle, GraphicsStyleType, LinePattern,
    LinePatternElement, LinePatternSegment, LinePatternSegmentType,
    TextNoteType,
)
from Autodesk.Revit.DB import Element

from System.Collections.Generic import List

from . import config as cfg
from .theme import rgb_to_revit_int

# Revit line weights used when creating our own line styles
LINE_WEIGHTS = {'hair': 1, 'thin': 1, 'dashed': 1, 'medium': 3, 'thick': 5}
DASHED_STYLES = frozenset(['dashed'])

DASH_PATTERN_NAME = 'EZ_Dash'
DASH_LEN_FT = 1.0 / 32.0
GAP_LEN_FT = 1.0 / 64.0


def elem_name(el):
    """Element.Name is an ambiguous property on some classes; always go
    through this helper."""
    try:
        return Element.Name.GetValue(el)
    except Exception:
        try:
            return el.Name
        except Exception:
            return ''


def hex_to_color(rgb_hex):
    r, g, b = cfg.rgb_parts(rgb_hex)
    return Color(r, g, b)


class StyleFactory(object):
    """One instance per import; the internal caches avoid repeated lookups."""

    def __init__(self, doc, warnings=None):
        self.doc = doc
        self.warnings = warnings if warnings is not None else []
        self._line_styles = {}
        self._fill_types = {}
        self._text_types = {}
        self._dash_pattern_id = None
        self._solid_pattern_id = None
        self._invisible_style_id = None
        self._base_text_type = None
        self._base_text_looked_up = False
        self._greys_seen = {}

    def warn(self, msg):
        if msg not in self.warnings:
            self.warnings.append(msg)

    # ------------------------------------------------------------ lookups

    def _lines_category(self):
        return self.doc.Settings.Categories.get_Item(BuiltInCategory.OST_Lines)

    def _find_subcategory(self, name):
        for sub in self._lines_category().SubCategories:
            if elem_name(sub) == name:
                return sub
        return None

    def _find_type(self, cls, name):
        for el in FilteredElementCollector(self.doc).OfClass(cls):
            if elem_name(el) == name:
                return el
        return None

    def _first_type(self, cls):
        return FilteredElementCollector(self.doc).OfClass(cls).FirstElement()

    # ------------------------------------------------------------ line styles

    def get_line_style(self, style, rgb='000000'):
        """-> GraphicsStyle. The first call must happen inside a transaction,
        because it may need to create a subcategory."""
        key = (style, (rgb or '000000').upper())
        if key in self._line_styles:
            return self._line_styles[key]

        sub = None
        if cfg.USE_EXISTING_LINE_STYLES:
            wanted = cfg.LINE_STYLE_NAMES.get(style)
            if wanted:
                sub = self._find_subcategory(wanted)
                if sub is None:
                    self.warn('Line style %s not found in this project - created an EZ_ subcategory instead' % wanted)
                elif rgb and rgb.upper() != '000000':
                    self.warn('Excel border colour #%s ignored - project line styles carry their own colour'
                              % rgb.upper())

        if sub is None:
            sub = self._create_subcategory(style, rgb)

        gs = sub.GetGraphicsStyle(GraphicsStyleType.Projection)
        if gs is None:
            self.doc.Regenerate()
            gs = sub.GetGraphicsStyle(GraphicsStyleType.Projection)
        self._line_styles[key] = gs
        return gs

    def _create_subcategory(self, style, rgb):
        name = 'EZ_%s' % style.capitalize()
        if rgb and rgb.upper() != '000000':
            name += '_%s' % rgb.upper()
        sub = self._find_subcategory(name)
        if sub is not None:
            return sub

        cats = self.doc.Settings.Categories
        sub = cats.NewSubcategory(self._lines_category(), name)
        try:
            sub.SetLineWeight(LINE_WEIGHTS.get(style, 1), GraphicsStyleType.Projection)
        except Exception as exc:
            self.warn('Line style %s: could not set line weight (%s)' % (name, exc))
        try:
            sub.LineColor = hex_to_color(rgb or '000000')
        except Exception as exc:
            self.warn('Line style %s: could not set colour (%s)' % (name, exc))
        if style in DASHED_STYLES:
            pid = self.dash_pattern_id()
            if pid is not None:
                try:
                    sub.SetLinePatternId(pid, GraphicsStyleType.Projection)
                except Exception as exc:
                    self.warn('Line style %s: could not set line pattern (%s)' % (name, exc))
        return sub

    def dash_pattern_id(self):
        if self._dash_pattern_id is not None:
            return self._dash_pattern_id
        existing = self._find_type(LinePatternElement, DASH_PATTERN_NAME)
        if existing is not None:
            self._dash_pattern_id = existing.Id
            return self._dash_pattern_id
        try:
            pattern = LinePattern(DASH_PATTERN_NAME)
            # SetSegments wants an IList<LinePatternSegment>; under IronPython
            # it has to be wrapped explicitly
            segments = List[LinePatternSegment]()
            segments.Add(LinePatternSegment(LinePatternSegmentType.Dash, DASH_LEN_FT))
            segments.Add(LinePatternSegment(LinePatternSegmentType.Space, GAP_LEN_FT))
            pattern.SetSegments(segments)
            self._dash_pattern_id = LinePatternElement.Create(self.doc, pattern).Id
        except Exception as exc:
            self.warn('Could not create the dash pattern - dashed borders drawn solid (%s)' % exc)
            self._dash_pattern_id = None
        return self._dash_pattern_id

    # ------------------------------------------------------------ fills

    def solid_pattern_id(self):
        if self._solid_pattern_id is not None:
            return self._solid_pattern_id
        for fpe in FilteredElementCollector(self.doc).OfClass(FillPatternElement):
            fp = fpe.GetFillPattern()
            if fp.IsSolidFill and fp.Target == FillPatternTarget.Drafting:
                self._solid_pattern_id = fpe.Id
                return self._solid_pattern_id
        raise RuntimeError('No Solid fill pattern in this project')

    def invisible_line_style_id(self):
        """
        Find the GraphicsStyle for <Invisible lines>.

        Category.GetCategory(OST_InvisibleLines) cannot be used -- measured on
        Revit 2026, it returns None. Iterating GraphicsStyle and matching on
        category Id is the reliable route, and it is also immune to Revit's UI
        language (searching by name breaks on a localised Revit).
        """
        if self._invisible_style_id is not None:
            return self._invisible_style_id

        target = ElementId(BuiltInCategory.OST_InvisibleLines)
        for gs in FilteredElementCollector(self.doc).OfClass(GraphicsStyle):
            try:
                cat = gs.GraphicsStyleCategory
            except Exception:
                continue
            if cat is not None and cat.Id == target:
                self._invisible_style_id = gs.Id
                return self._invisible_style_id

        cat = Category.GetCategory(self.doc, BuiltInCategory.OST_InvisibleLines)
        if cat is not None:
            gs = cat.GetGraphicsStyle(GraphicsStyleType.Projection)
            self._invisible_style_id = gs.Id if gs is not None else cat.Id
            return self._invisible_style_id

        self.warn('Invisible lines style not found - filled regions may show a double boundary')
        self._invisible_style_id = ElementId.InvalidElementId
        return self._invisible_style_id

    def get_filled_region_type(self, rgb_hex):
        rgb_hex = (rgb_hex or '000000').upper()
        if rgb_hex in self._fill_types:
            return self._fill_types[rgb_hex]

        frt = None
        if cfg.GREY_FILL_TYPE_NAME and cfg.is_grey(rgb_hex):
            # Only greys close to the standard type's own level are drawn with
            # it. Snapping every grey on to one type made light shading come out
            # far darker than the source -- Excel's 230 and 242 both rendered at
            # 192. Anything outside the tolerance gets a faithful type instead.
            if cfg.snaps_to_grey_type(rgb_hex, cfg.GREY_FILL_TYPE_NAME):
                self._greys_seen[rgb_hex] = cfg.grey_level(rgb_hex)
                frt = self._find_type(FilledRegionType, cfg.GREY_FILL_TYPE_NAME)
                if frt is None:
                    self.warn('Filled region type %s not found - creating one per colour instead'
                              % cfg.GREY_FILL_TYPE_NAME)

        if frt is None:
            frt = self._get_or_create_fill(rgb_hex)

        self._fill_types[rgb_hex] = frt
        return frt

    def _get_or_create_fill(self, rgb_hex):
        name = cfg.fill_type_name(rgb_hex)
        found = self._find_type(FilledRegionType, name)
        if found is not None:
            return found                       # the colour is already encoded in
                                               # the name, nothing to change

        base = self._first_type(FilledRegionType)
        if base is None:
            raise RuntimeError('No FilledRegionType in this project to duplicate')
        found = base.Duplicate(name)
        try:
            found.ForegroundPatternId = self.solid_pattern_id()
            found.ForegroundPatternColor = hex_to_color(rgb_hex)
            found.BackgroundPatternId = ElementId.InvalidElementId
        except Exception as exc:
            self.warn('Filled region type %s: could not set the pattern (%s)' % (name, exc))
        # FilledRegionType has no LineStyleId (measured on Revit 2026); the
        # boundary line style is set on the instance with
        # FilledRegion.SetLineStyleId -- see renderer.draw_fills
        if hasattr(found, 'LineStyleId'):
            try:
                found.LineStyleId = self.invisible_line_style_id()
            except Exception:
                pass
        try:
            found.IsMasking = False
        except Exception:
            pass
        return found

    # ------------------------------------------------------------ text

    def base_text_type(self):
        """The base text type named in the config; None when unset or not found."""
        if self._base_text_looked_up:
            return self._base_text_type
        self._base_text_looked_up = True
        self._base_text_type = None
        if cfg.BASE_TEXT_TYPE_NAME:
            found = self._find_type(TextNoteType, cfg.BASE_TEXT_TYPE_NAME)
            if found is None:
                self.warn('Text type %s not found - building EZ_ types from the Excel font sizes instead'
                          % cfg.BASE_TEXT_TYPE_NAME)
            self._base_text_type = found
        return self._base_text_type

    def base_text_cap_height_ft(self):
        """
        The base type's TEXT_SIZE, in feet. plan.py needs it for vertical
        centring: the height of a text block depends on the size actually in
        use, not the one written in Excel.
        """
        base = self.base_text_type()
        if base is None:
            return None
        try:
            p = base.get_Parameter(BuiltInParameter.TEXT_SIZE)
            return p.AsDouble() if p is not None else None
        except Exception:
            return None

    def get_text_type(self, font, size_pt, bold, italic, rgb):
        rgb = (rgb or '000000').upper()
        key = (font, round(float(size_pt), 3), bool(bold), bool(italic), rgb)
        if key in self._text_types:
            return self._text_types[key]

        base = self.base_text_type()
        if base is not None:
            result = self._derive_from_base(base, size_pt, bold, italic, rgb)
        else:
            result = self._build_from_excel(font, size_pt, bold, italic, rgb)
        self._text_types[key] = result
        return result

    def _colour_of(self, text_type):
        try:
            p = text_type.get_Parameter(BuiltInParameter.LINE_COLOR)
            return p.AsInteger() if p is not None else None
        except Exception:
            return None

    def _derive_from_base(self, base, size_pt, bold, italic, rgb):
        """Derive from a project type. Font is inherited exactly; weight, slant
        and colour change, and so does size when SCALE_TEXT_TO_EXCEL is on.

        The size scaling is what keeps two sheets consistent with each other: the
        base type stands for Excel text at cfg.BASE_TEXT_SIZE_PT, so a 9pt cell
        is drawn 9/7 as large rather than being flattened to the base size.
        """
        base_cap_ft = self.base_text_cap_height_ft() or 0.0
        scale = cfg.text_scale(size_pt)
        scaled = base_cap_ft > 0 and abs(scale - 1.0) > 1e-6

        stem = cfg.BASE_TEXT_TYPE_NAME
        if scaled:
            stem = cfg.resize_text_type_name(stem, base_cap_ft * scale * 304.8)

        name = cfg.text_type_name(stem, bold, italic, rgb)
        if name == cfg.BASE_TEXT_TYPE_NAME:
            return base                        # plain black text uses the original
                                               # type as-is, untouched

        found = self._find_type(TextNoteType, name)
        if found is not None:
            # Same name but a different colour -- the project may already have
            # its own idea of "red". Switch to a name carrying the hex rather
            # than touching someone else's type
            want = rgb_to_revit_int(rgb)
            got = self._colour_of(found)
            if got is not None and got != want:
                self.warn('Existing text type %s has a different colour than #%s - using a name with the hex'
                          % (name, rgb))
                name = cfg.text_type_name(stem, bold, italic,
                                          rgb, disambiguate=True)
                found = self._find_type(TextNoteType, name)

        if found is None:
            found = base.Duplicate(name)

        # Derived types are realigned with the base every time: if the base
        # changes size, the derived ones follow
        for bip in (BuiltInParameter.TEXT_FONT, BuiltInParameter.TEXT_SIZE,
                    BuiltInParameter.TEXT_WIDTH_SCALE):
            self._copy_param(base, found, bip, name)
        if scaled:
            # TEXT_SIZE is a cap height in feet -- see geometry.py
            self._set(found, BuiltInParameter.TEXT_SIZE, base_cap_ft * scale, name)
        self._set(found, BuiltInParameter.TEXT_STYLE_BOLD, 1 if bold else 0, name)
        self._set(found, BuiltInParameter.TEXT_STYLE_ITALIC, 1 if italic else 0, name)
        self._set(found, BuiltInParameter.LINE_COLOR, rgb_to_revit_int(rgb), name)
        self._set(found, BuiltInParameter.TEXT_BACKGROUND, 1, name, quiet=True)
        return found

    def _build_from_excel(self, font, size_pt, bold, italic, rgb):
        """Fallback when there is no base type: build EZ_ types straight from
        Excel's own font and size."""
        from .geometry import revit_text_size_feet

        size_txt = ('%g' % float(size_pt)).replace('.', 'p')
        name = 'EZ_%s_%s%s%s_%s' % (font.replace(' ', ''), size_txt,
                                    'B' if bold else '', 'I' if italic else '', rgb)
        found = self._find_type(TextNoteType, name)
        if found is None:
            base = self._first_type(TextNoteType)
            if base is None:
                raise RuntimeError('No TextNoteType in this project to duplicate')
            found = base.Duplicate(name)

        # Reapply every time: older EZTable versions created types under these
        # same names with a miscalculated TEXT_SIZE, and looking one up without
        # correcting it would inherit the bug
        self._set(found, BuiltInParameter.TEXT_FONT, font, name)
        # TEXT_SIZE has two traps: its unit is feet, and it is a cap height
        # rather than a font size
        self._set(found, BuiltInParameter.TEXT_SIZE,
                  revit_text_size_feet(size_pt, font), name)
        self._set(found, BuiltInParameter.TEXT_STYLE_BOLD, 1 if bold else 0, name)
        self._set(found, BuiltInParameter.TEXT_STYLE_ITALIC, 1 if italic else 0, name)
        self._set(found, BuiltInParameter.TEXT_STYLE_UNDERLINE, 0, name)
        self._set(found, BuiltInParameter.LINE_COLOR, rgb_to_revit_int(rgb), name)
        self._set(found, BuiltInParameter.TEXT_BACKGROUND, 1, name, quiet=True)
        self._set(found, BuiltInParameter.TEXT_WIDTH_SCALE, 1.0, name, quiet=True)
        return found

    # ------------------------------------------------------------ parameters

    def _copy_param(self, src, dst, bip, owner):
        try:
            sp = src.get_Parameter(bip)
            dp = dst.get_Parameter(bip)
            if sp is None or dp is None or dp.IsReadOnly:
                return
            st = sp.StorageType.ToString()
            if st == 'Double':
                dp.Set(sp.AsDouble())
            elif st == 'Integer':
                dp.Set(sp.AsInteger())
            elif st == 'String':
                dp.Set(sp.AsString())
        except Exception as exc:
            self.warn('Text type %s: could not inherit %s (%s)' % (owner, exc))

    def _set(self, el, bip, value, owner, quiet=False):
        try:
            p = el.get_Parameter(bip)
            if p is None or p.IsReadOnly:
                if not quiet:
                    self.warn('Type %s: parameter %s is read-only' % (owner, bip))
                return
            p.Set(value)
        except Exception as exc:
            if not quiet:
                self.warn('Type %s: failed to set %s (%s)' % (owner, bip, exc))

    # ------------------------------------------------------------ prebuild

    def prebuild(self, plan):
        """Create every type the plan needs, in one dedicated transaction."""
        for ln in plan.lines:
            self.get_line_style(ln.style, ln.rgb)
        for f in plan.fills:
            self.get_filled_region_type(f.rgb)
        for t in plan.texts:
            self.get_text_type(t.font_name, t.font_size, t.bold, t.italic, t.rgb)

    def describe(self):
        """For the output report: which types this run actually used."""
        lines = sorted(set(elem_name(gs) for gs in self._line_styles.values() if gs))
        fills = sorted(set(elem_name(f) for f in self._fill_types.values() if f))
        texts = sorted(set(elem_name(t) for t in self._text_types.values() if t))
        return {'lines': lines, 'fills': fills, 'texts': texts}
