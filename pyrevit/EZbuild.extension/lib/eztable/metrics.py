# -*- coding: utf-8 -*-
"""
metrics.py -- Arial character width table, used to decide whether text fits

Revit will not tell you that a string overflowed its cell, and horizontal
overflow is something the centring maths cannot rescue -- it has to be computed
and warned about up front. The numbers here are Liberation Sans advance widths
(in 1/1000 em), whose metrics match Arial exactly.

Coverage is printable ASCII plus a handful of common symbols (deg, superscripts,
multiplication and plus-minus signs). Characters absent from the table are
estimated at 0.55 em (close to the average of digits and lowercase letters), and
CJK at 1.0 em. Entries are grouped by width, which saves space and saves writing
117 separate lines.
"""

from __future__ import division, unicode_literals

from .compat import to_text

_REG = {
    191: "'",
    222: 'ijl‘’',
    260: '|',
    278: ' !,./:;I[\\]ft',
    333: '()-`r²³·“”',
    334: '{}',
    355: '"',
    389: '*',
    400: '°',
    469: '^',
    500: 'Jcksvxyz',
    549: '±÷≈≠≤≥',
    556: '#$0123456789?L_abdeghnopqu–€',
    576: 'µ',
    584: '+<=>~×',
    611: 'FTZ',
    667: '&ABEKPSVXY',
    722: 'CDHNRUw',
    778: 'GOQ',
    833: 'Mm',
    889: '%',
    944: 'W',
    1000: '—…™',
    1015: '@',
    1073: '№',
}

_BOLD = {
    238: "'",
    278: ' ,./I\\ijl‘’',
    280: '|',
    333: '!()-:;[]`ft²³·',
    389: '*r{}',
    400: '°',
    474: '"',
    500: 'z“”',
    549: '±÷≈≠≤≥',
    556: '#$0123456789J_aceksvxy–€',
    576: 'µ',
    584: '+<=>^~×',
    611: '?FLTZbdghnopqu',
    667: 'EPSVXY',
    722: '&ABCDHKNRU',
    778: 'GOQw',
    833: 'M',
    889: '%m',
    944: 'W',
    975: '@',
    1000: '—…™',
    1115: '№',
}


def _expand(groups):
    out = {}
    for width, chars in groups.items():
        for ch in chars:
            out[ch] = width / 1000.0
    return out


WIDTHS_REGULAR = _expand(_REG)
WIDTHS_BOLD = _expand(_BOLD)

FALLBACK_WIDTH = 0.55          # characters absent from the table
CJK_WIDTH = 1.0                # full-width CJK
ITALIC_FACTOR = 1.0            # italic advance widths match upright closely enough


def _is_wide(ch):
    o = ord(ch)
    return (0x1100 <= o <= 0x115F or 0x2E80 <= o <= 0xA4CF
            or 0xAC00 <= o <= 0xD7A3 or 0xF900 <= o <= 0xFAFF
            or 0xFE30 <= o <= 0xFE6F or 0xFF00 <= o <= 0xFF60
            or 0xFFE0 <= o <= 0xFFE6)


def string_width_em(text, bold=False):
    """Width of a string, in em."""
    if not text:
        return 0.0
    table = WIDTHS_BOLD if bold else WIDTHS_REGULAR
    total = 0.0
    for ch in to_text(text):
        w = table.get(ch)
        if w is None:
            w = CJK_WIDTH if _is_wide(ch) else FALLBACK_WIDTH
        total += w
    return total


def text_width_feet(text, em_ft, bold=False, italic=False):
    """
    em_ft: the em size in feet -- note this is NOT Revit's TEXT_SIZE, which is
    a cap height; convert it back to em with geometry.font_metrics first.
    """
    factor = ITALIC_FACTOR if italic else 1.0
    return string_width_em(text, bold) * float(em_ft) * factor


def widest_line(text):
    """The widest line of a multi-line string, in em."""
    if not text:
        return ''
    lines = to_text(text).split('\n')
    return max(lines, key=lambda l: string_width_em(l))


def wrap_line(line, max_width_em, bold=False):
    """
    Greedy wrap against a width in em. Breaks on spaces; a single word wider
    than the limit is left to overflow rather than split, because a hard-broken
    word looks worse on a drawing and the fit-to-text pass will widen the column
    for it anyway.
    """
    line = to_text(line)
    if max_width_em <= 0 or string_width_em(line, bold) <= max_width_em:
        return [line]

    words = line.split(' ')
    out = []
    cur = ''
    for w in words:
        candidate = w if not cur else cur + ' ' + w
        if string_width_em(candidate, bold) <= max_width_em or not cur:
            cur = candidate
        else:
            out.append(cur)
            cur = w
    if cur:
        out.append(cur)
    return out or ['']


def wrap_text(text, max_width_em, bold=False):
    """Keep the existing hard line breaks, then wrap each of them to width."""
    if not text:
        return ['']
    out = []
    for seg in to_text(text).split('\n'):
        out.extend(wrap_line(seg, max_width_em, bold))
    return out


def longest_word_em(text, bold=False):
    """The longest unbreakable run, which sets the minimum useful column width."""
    widest = 0.0
    for seg in to_text(text or '').replace('\n', ' ').split(' '):
        w = string_width_em(seg, bold)
        if w > widest:
            widest = w
    return widest
