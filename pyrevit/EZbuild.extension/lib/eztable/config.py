# -*- coding: utf-8 -*-
"""
config.py -- drafting standards

This is the file you are meant to edit. To change line styles, fill types or
text types, change them here; no other module needs touching. Restart Revit
afterwards -- under rocketmode the modules are cached.
"""

from __future__ import division, unicode_literals

import re

# ---------------------------------------------------------------- line styles
#
# True  = use the line styles already in the project (found by name below)
# False = create our own EZ_Thin / EZ_Medium / ... subcategories
USE_EXISTING_LINE_STYLES = True

# Excel border weight -> Revit line style name. A name that cannot be found
# falls back to creating an EZ_* subcategory, with a warning.
LINE_STYLE_NAMES = {
    'hair':   '<Thin Lines>',
    'thin':   '<Thin Lines>',
    'dashed': '<Thin Lines>',
    'medium': '<Medium Lines>',
    'thick':  '<Wide Lines>',
}

# ---------------------------------------------------------------- fills
#
# Grey shading always uses this existing type. Set to None to create types
# automatically by colour instead.
GREY_FILL_TYPE_NAME = 'Fill Grey 192'

# A colour counts as "grey" when the spread across R/G/B is no more than this
GREY_TOLERANCE = 12

# How far an Excel grey may sit from the level named in GREY_FILL_TYPE_NAME and
# still be drawn with it. Beyond this, a faithful `Fill Grey <level>` type is
# created instead.
#
# Without this every grey collapsed on to the one standard type: Excel's 230 and
# 242 greys were drawn at 192, which reads as noticeably darker than the source.
GREY_SNAP_TOLERANCE = 16

# Name prefix for automatically created fill types, following the same form as
# GREY_FILL_TYPE_NAME:
#   Fill Grey 217        grey
#   Fill Orange EE822F   coloured
FILL_TYPE_PREFIX = 'Fill'

# White shading is not drawn -- the sheet background is white anyway
SKIP_WHITE_FILL = True

# ---------------------------------------------------------------- text
#
# Derive from this existing type. Bold, italic and coloured variants are copies
# of it, inheriting font and size exactly and changing only weight, slant and
# colour:
#   2.0mm Arial              plain black text
#   2.0mm Arial Bold         bold
#   2.0mm Arial Red E24D4E   red
# Set to None to build EZ_* types purely from Excel's own font and size.
BASE_TEXT_TYPE_NAME = '2.0mm Arial'

# The base type above represents Excel text at this point size. Text at any other
# size is drawn proportionally larger or smaller, so a sheet set in 9pt keeps the
# same text-to-cell ratio as one set in 7pt.
#
# Without this, every sheet is forced to one fixed size: a 7pt sheet looks right
# while a 9-10pt sheet ends up with small text floating in tall cells. Measured on
# Planing_plan.xlsx, cap height filled 42% of the row on Summary (7pt) but only
# 32% on Part1 (9pt) -- in Excel both sit at about 36%.
#
# Set SCALE_TEXT_TO_EXCEL = False to force every cell to the base size.
SCALE_TEXT_TO_EXCEL = True
BASE_TEXT_SIZE_PT = 7.0

# ---------------------------------------------------------------- view naming
#
# Two placeholders are supported: {sheet} (worksheet name) and {file}
# (file name without extension):
#   'Table'                 -> Table、Table (1)、Table (2) ...
#   'Table - {sheet}'       -> Table - Summary
#   '{file} {sheet}'        -> Planing plan Summary
# A name already in use gets a (1) (2) suffix automatically.
VIEW_NAME_TEMPLATE = 'Table'

# ---------------------------------------------------------------- splitting wide tables
#
# An A3 sheet cannot hold an over-long table. Changing the view scale wrecks the
# layout -- text size is fixed on paper, so any scaling desynchronises text from
# cells. Instead the table is **split by column and stacked downwards**, every
# block staying 1:1.
#
# Set to 0 or None to disable splitting.
MAX_TABLE_WIDTH_MM = 380.0     # usable width of a landscape A3 minus the title block
BLOCK_GAP_MM = 10.0            # vertical gap between blocks
REPEAT_LEADING_COLS = 1        # repeat the first N columns (row headers) at the
                               # start of each block; 0 = do not repeat

# ---------------------------------------------------------------- the report window
#
# 'auto'   open the output window only when there are warnings or text that
#          does not fit (the default)
# 'always' open it every time, with the full report
# 'off'    never open it
#
# A finished import already announces itself by switching to the new view, so
# normally there is no need for a second window.
REPORT_MODE = 'auto'

# ---------------------------------------------------------------- fit to text
#
# The default is to fit the table to its text, not to make the text put up with
# the table. Font size stays at a comfortable 2.0mm (on A3); anything that does
# not fit widens the column and heightens the row.
#
# Turn all of them off for a strict 1:1 copy of Excel's row and column sizes,
# where text that does not fit simply runs up to the border.

WRAP_TEXT = True            # wrap cells that have wrapText set in Excel, to cell width
FIT_COLUMNS = True          # widen columns when non-wrapping text does not fit
FIT_ROWS = True             # heighten rows when wrapping leaves them too short

MAX_COL_GROWTH = 4.0        # how many times its original width one column may grow,
                            # so extreme content cannot blow the table apart
MAX_ROW_GROWTH = 6.0

CELL_PADDING_H_MM = 0.8     # padding left and right of the text
CELL_PADDING_V_MM = 0.4     # padding above and below the text

# ---------------------------------------------------------------- colour naming

_HUE_NAMES = (
    (15, 'Red'), (45, 'Orange'), (70, 'Yellow'), (160, 'Green'),
    (200, 'Cyan'), (260, 'Blue'), (290, 'Purple'), (345, 'Pink'),
    (360, 'Red'),
)


def rgb_parts(rgb_hex):
    h = (rgb_hex or '000000').upper()
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def is_grey(rgb_hex, tolerance=None):
    r, g, b = rgb_parts(rgb_hex)
    tol = GREY_TOLERANCE if tolerance is None else tolerance
    return (max(r, g, b) - min(r, g, b)) <= tol


def grey_level(rgb_hex):
    r, g, b = rgb_parts(rgb_hex)
    return int(round((r + g + b) / 3.0))


def colour_name(rgb_hex):
    """Rough hue naming, purely to keep type names readable."""
    r, g, b = rgb_parts(rgb_hex)
    mx, mn = max(r, g, b), min(r, g, b)
    if mx - mn <= GREY_TOLERANCE:
        return 'Grey'
    d = float(mx - mn)
    if mx == r:
        hue = 60.0 * (((g - b) / d) % 6.0)
    elif mx == g:
        hue = 60.0 * (((b - r) / d) + 2.0)
    else:
        hue = 60.0 * (((r - g) / d) + 4.0)
    hue = hue % 360.0
    for limit, name in _HUE_NAMES:
        if hue < limit:
            return name
    return 'Red'


def colour_label(rgb_hex):
    """
    'D9D9D9' -> 'Grey 217'
    'EE822F' -> 'Orange EE822F'

    Grey needs only a number (grey is one-dimensional); colours carry the hex
    to stay unique.
    """
    if is_grey(rgb_hex):
        return 'Grey %d' % grey_level(rgb_hex)
    return '%s %s' % (colour_name(rgb_hex), (rgb_hex or '').upper())


def fill_type_name(rgb_hex):
    return '%s %s' % (FILL_TYPE_PREFIX, colour_label(rgb_hex))


def text_type_name(base_name, bold, italic, rgb_hex, disambiguate=False):
    """
    Name for a derived text type, following the project's existing convention
    of uppercase modifiers:
        2.0mm Arial
        2.0mm Arial BOLD
        2.0mm Arial RED
        2.0mm Arial BOLD RED

    disambiguate=True appends the hex after the colour name. It is only needed
    when a type of that name already exists in a different colour, to stop two
    different reds colliding:
        2.0mm Arial RED E24D4E
    """
    parts = [base_name]
    if bold:
        parts.append('BOLD')
    if italic:
        parts.append('ITALIC')
    if rgb_hex and rgb_hex.upper() != '000000':
        label = colour_name(rgb_hex).upper()
        if is_grey(rgb_hex):
            label = 'GREY %d' % grey_level(rgb_hex)
        elif disambiguate:
            label = '%s %s' % (label, rgb_hex.upper())
        parts.append(label)
    return ' '.join(parts)


def text_scale(size_pt):
    """
    How much larger than the base text type a cell's text should be drawn.

    The base type stands for Excel text at BASE_TEXT_SIZE_PT, so a 9pt cell in a
    7pt-anchored standard comes out at 9/7 of the base size.
    """
    if not SCALE_TEXT_TO_EXCEL or not BASE_TEXT_SIZE_PT:
        return 1.0
    try:
        size = float(size_pt)
    except Exception:
        return 1.0
    if size <= 0:
        return 1.0
    return size / float(BASE_TEXT_SIZE_PT)


_SIZE_TOKEN_RE = re.compile(r'^\s*\d+(?:\.\d+)?\s*mm\b', re.I)


def resize_text_type_name(base_name, cap_mm):
    """
    Name for a scaled copy of the base text type, following the project's own
    convention of leading the name with the size:

        '2.0mm Arial' at 2.57mm -> '2.6mm Arial'

    When the base name carries no size token there is nothing to substitute, so
    the size is appended instead:

        'Table Text' at 2.57mm -> 'Table Text 2.6mm'
    """
    token = '%.1fmm' % cap_mm
    name = base_name or ''
    if _SIZE_TOKEN_RE.match(name):
        return _SIZE_TOKEN_RE.sub(token, name, count=1)
    return ('%s %s' % (name, token)).strip()


_GREY_LEVEL_RE = re.compile(r'(\d{1,3})\s*$')


def grey_type_level(type_name):
    """
    The grey level encoded in a fill type name -- 'Fill Grey 192' -> 192.
    Returns None when the name carries no trailing number.
    """
    match = _GREY_LEVEL_RE.search(type_name or '')
    return int(match.group(1)) if match else None


def snaps_to_grey_type(rgb_hex, type_name, tolerance=None):
    """Is this Excel grey close enough to the standard type to be drawn with it?"""
    standard = grey_type_level(type_name)
    if standard is None:
        return True                    # no level in the name, nothing to compare
    tol = GREY_SNAP_TOLERANCE if tolerance is None else tolerance
    return abs(grey_level(rgb_hex) - standard) <= tol


# ---------------------------------------------------------------- generated names
#
# Cleanup needs to recognise what this tool created. The EZ_ / XL_ prefixes only
# cover the fully-automatic mode; when the config points at existing project
# standards the generated names follow those instead ('Fill Grey 242',
# '2.0mm Arial BOLD'), and a prefix scan finds nothing at all.

_MODIFIER_RE = re.compile(r'^(?:BOLD|ITALIC|GREY|[A-Z]+|\d{1,3}|[0-9A-F]{6})$')


def _strip_size_token(name):
    return _SIZE_TOKEN_RE.sub('', name or '', count=1).strip()


def is_generated_fill_name(name):
    """
    True for a fill type this tool would have created -- 'Fill Grey 242',
    'Fill Orange EE822F'. The standard type named in GREY_FILL_TYPE_NAME is
    excluded: it is the user's own and must never be offered for deletion.
    """
    if not name or name == GREY_FILL_TYPE_NAME:
        return False
    pattern = r'^%s\s+(?:Grey\s+\d{1,3}|[A-Za-z]+\s+[0-9A-Fa-f]{6})$' % re.escape(FILL_TYPE_PREFIX)
    return bool(re.match(pattern, name))


def is_derived_text_name(name):
    """
    True for a text type derived from BASE_TEXT_TYPE_NAME -- the base name, or a
    resized variant of it, plus uppercase modifiers: '2.0mm Arial BOLD',
    '2.6mm Arial', '2.6mm Arial BOLD RED'. The base type itself is excluded, and
    so is any name that merely happens to start the same way ('3.5mm Arial
    Titles' keeps its lowercase word and is left alone).
    """
    base = BASE_TEXT_TYPE_NAME
    if not base or not name or name == base:
        return False

    parts = name.split()
    while parts and _MODIFIER_RE.match(parts[-1]):
        parts.pop()
    stem = ' '.join(parts)
    if not stem:
        return False
    return _strip_size_token(stem) == _strip_size_token(base)


def view_name(sheet_name, file_path=None):
    """Build a view name from VIEW_NAME_TEMPLATE."""
    import os
    base = ''
    if file_path:
        base = os.path.splitext(os.path.basename(file_path))[0]
    try:
        return VIEW_NAME_TEMPLATE.format(sheet=sheet_name or '', file=base)
    except Exception:
        return VIEW_NAME_TEMPLATE
