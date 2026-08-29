# -*- coding: utf-8 -*-
"""
theme.py -- theme palette parsing, tint arithmetic, one colour resolution entry point

An Excel fill or font colour may be theme + tint rather than a direct RGB.
openpyxl only hands back the index and the tint value; the palette itself has to
be parsed out of xl/theme/theme1.xml.

The trap: the theme indices used in styles.xml do not follow the element order
of <a:clrScheme> in theme1.xml. Excel presents the palette as Background/Text
pairs, and **both pairs are swapped** relative to the XML:

    styles.xml theme=  Excel calls it   clrScheme child
        0              Background 1     lt1   (white)
        1              Text 1           dk1   (black)
        2              Background 2     lt2   (light grey)
        3              Text 2           dk2   (dark navy)
        4..11          Accent 1-6,      accent1..folHlink, in XML order
                       hyperlinks

Getting only the first pair swapped is a subtle and nasty bug: a theme=2 fill
renders dark navy instead of light grey, and theme=3 text renders near-white
instead of dark -- invisible on a white sheet. OPENPYXL_THEME_ORDER does the
conversion.
"""

from __future__ import division, unicode_literals

import re
import zipfile
import xml.etree.ElementTree as ET

from .compat import binary_type, text_type

DRAWINGML_NS = 'http://schemas.openxmlformats.org/drawingml/2006/main'

# Child element order of <a:clrScheme> in theme1.xml
CLR_SCHEME_ORDER = ['dk1', 'lt1', 'dk2', 'lt2',
                    'accent1', 'accent2', 'accent3', 'accent4',
                    'accent5', 'accent6', 'hlink', 'folHlink']

# styles.xml theme index -> subscript into CLR_SCHEME_ORDER.
# Both Background/Text pairs are swapped: 0<->1 (lt1/dk1) and 2<->3 (lt2/dk2).
OPENPYXL_THEME_ORDER = [1, 0, 3, 2, 4, 5, 6, 7, 8, 9, 10, 11]

# Office default palette used when theme1.xml is missing (in CLR_SCHEME_ORDER)
FALLBACK_PALETTE = ['000000', 'FFFFFF', '44546A', 'E7E6E6',
                    '4472C4', 'ED7D31', 'A5A5A5', 'FFC000',
                    '5B9BD5', '70AD47', '0563C1', '954F72']

# Legacy indexed colour table (OOXML's traditional 56-colour palette plus
# system foreground/background)
INDEXED_COLORS = (
    '000000', 'FFFFFF', 'FF0000', '00FF00', '0000FF', 'FFFF00', 'FF00FF', '00FFFF',
    '000000', 'FFFFFF', 'FF0000', '00FF00', '0000FF', 'FFFF00', 'FF00FF', '00FFFF',
    '800000', '008000', '000080', '808000', '800080', '008080', 'C0C0C0', '808080',
    '9999FF', '993366', 'FFFFCC', 'CCFFFF', '660066', 'FF8080', '0066CC', 'CCCCFF',
    '000080', 'FF00FF', 'FFFF00', '00FFFF', '800080', '800000', '008080', '0000FF',
    '00CCFF', 'CCFFFF', 'CCFFCC', 'FFFF99', '99CCFF', 'FF99CC', 'CC99FF', 'FFCC99',
    '3366FF', '33CCCC', '99CC00', 'FFCC00', 'FF9900', 'FF6600', '666699', '969696',
    '003366', '339966', '003300', '333300', '993300', '993366', '333399', '333333',
    '000000', 'FFFFFF',          # 64 = system foreground, 65 = system background
)


# ---------------------------------------------------------------- tint

def apply_tint(rgb_hex, tint):
    """
    Excel's tint: positive moves towards white, negative towards black.

    Check: theme0 (=FFFFFF) + tint -0.15 -> 255 x 0.85 = 216.75 ~ 217 -> D9D9D9
    """
    if not tint:
        return rgb_hex
    r, g, b = (int(rgb_hex[i:i + 2], 16) for i in (0, 2, 4))

    def adj(v):
        if tint < 0:
            n = int(round(v * (1 + tint)))              # darken
        else:
            n = int(round(v * (1 - tint) + 255 * tint))  # lighten
        return max(0, min(255, n))

    return '%02X%02X%02X' % (adj(r), adj(g), adj(b))


# ---------------------------------------------------------------- palette

def _extract_srgb(node):
    for child in node:
        tag = child.tag.split('}')[-1]
        if tag == 'srgbClr':
            return child.get('val', '000000').upper()
        if tag == 'sysClr':
            return (child.get('lastClr') or '000000').upper()
    return None


def parse_theme_palette(xlsx_path=None, theme_xml=None):
    """
    Parse the 12-colour palette and return RGB hex values in CLR_SCHEME_ORDER.

    theme_xml may be passed directly as bytes or a string (openpyxl's
    wb.loaded_theme); otherwise xl/theme/theme1.xml is read out of the xlsx
    archive. A failed parse falls back to the Office default palette.
    """
    raw = theme_xml
    if raw is None and xlsx_path is not None:
        try:
            with zipfile.ZipFile(xlsx_path) as zf:
                name = None
                for n in zf.namelist():
                    if re.match(r'xl/theme/theme\d*\.xml$', n):
                        name = n
                        break
                if name:
                    raw = zf.read(name)
        except Exception:
            raw = None
    if raw is None:
        return list(FALLBACK_PALETTE)

    try:
        if isinstance(raw, binary_type):
            root = ET.fromstring(raw)
        elif isinstance(raw, text_type):
            root = ET.fromstring(raw.encode('utf-8'))
        else:
            root = ET.fromstring(raw)
        scheme = root.find('.//{%s}clrScheme' % DRAWINGML_NS)
        if scheme is None:
            return list(FALLBACK_PALETTE)
        found = {}
        for child in scheme:
            found[child.tag.split('}')[-1]] = _extract_srgb(child)
        palette = []
        for i, key in enumerate(CLR_SCHEME_ORDER):
            palette.append(found.get(key) or FALLBACK_PALETTE[i])
        return palette
    except Exception:
        return list(FALLBACK_PALETTE)


class ThemePalette(object):
    """Palette, index mapping and tint bundled into one resolver."""

    __slots__ = ('palette', 'warnings')

    def __init__(self, palette=None, warnings=None):
        self.palette = palette or list(FALLBACK_PALETTE)
        self.warnings = warnings if warnings is not None else []

    @classmethod
    def from_workbook(cls, wb, xlsx_path=None, warnings=None):
        raw = getattr(wb, 'loaded_theme', None)
        return cls(parse_theme_palette(xlsx_path=xlsx_path, theme_xml=raw),
                   warnings)

    def theme_rgb(self, theme_index):
        """openpyxl theme index -> RGB hex."""
        try:
            idx = OPENPYXL_THEME_ORDER[int(theme_index)]
            return self.palette[idx]
        except Exception:
            self._warn('Theme colour index out of range: %r - fell back to white' % (theme_index,))
            return 'FFFFFF'

    def resolve(self, color, default=None):
        """
        openpyxl Color object -> 'RRGGBB'; returns default when unresolvable.

        Handles type = rgb / theme / indexed / auto. Tint is always applied last.
        """
        if color is None:
            return default

        ctype = getattr(color, 'type', None)
        try:
            tint = float(getattr(color, 'tint', 0.0) or 0.0)
        except Exception:
            tint = 0.0
        base = None

        if ctype == 'rgb':
            base = _normalize_rgb(getattr(color, 'rgb', None))
        elif ctype == 'theme':
            base = self.theme_rgb(getattr(color, 'theme', None))
        elif ctype == 'indexed':
            base = self._indexed_rgb(getattr(color, 'indexed', None))
        elif ctype == 'auto':
            base = None                                  # automatic colour: the caller decides
        else:
            base = _normalize_rgb(getattr(color, 'rgb', None))

        if base is None:
            return default
        return apply_tint(base, tint)

    def _indexed_rgb(self, idx):
        try:
            return _normalize_rgb(INDEXED_COLORS[int(idx)])
        except Exception:
            self._warn('Indexed colour out of range: %r - fell back to black' % (idx,))
            return '000000'

    def _warn(self, msg):
        if self.warnings is not None and msg not in self.warnings:
            self.warnings.append(msg)


def _normalize_rgb(value):
    """'FFD9D9D9' / 'D9D9D9' / a Values object -> 'D9D9D9'."""
    if value is None:
        return None
    s = str(value).strip().upper()
    if not re.match(r'^[0-9A-F]{6}([0-9A-F]{2})?$', s) and len(s) != 8:
        return None
    if len(s) == 8:
        s = s[2:]
    if len(s) != 6 or not re.match(r'^[0-9A-F]{6}$', s):
        return None
    return s


def rgb_to_revit_int(rgb_hex):
    """
    Revit's colour parameters (LINE_COLOR on a TextNoteType, for instance) store
    an integer:
        r + g*256 + b*65536
    """
    r = int(rgb_hex[0:2], 16)
    g = int(rgb_hex[2:4], 16)
    b = int(rgb_hex[4:6], 16)
    return r + g * 256 + b * 65536


def is_white(rgb_hex):
    return rgb_hex is not None and rgb_hex.upper() == 'FFFFFF'
