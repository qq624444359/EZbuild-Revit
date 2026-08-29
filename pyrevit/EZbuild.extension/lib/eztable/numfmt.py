# -*- coding: utf-8 -*-
"""
numfmt.py -- Excel number format rendering

openpyxl hands back a value and a format string but does not render them. What
follows is a deliberately "good enough" format engine covering General / 0 /
0.0 / 0.0% / #,##0 / #,##0.00 / sectioned positive-negative-zero formats and
simple dates and times. A format it genuinely has not seen falls back to str(v)
and raises a warning.

Deliberately not implemented: fractions, scientific notation, conditional
sections such as [<100], actual padding for the * fill character, and mixed
formatting within one cell. Spec section 3.5 excludes these explicitly.
"""

from __future__ import division, unicode_literals

import datetime
import re

from .compat import is_number, is_string, to_text

# Significant digits kept when rendering General (desktop Excel shows 11
# characters of width; 10 is used here)
GENERAL_SIG_DIGITS = 10

_COLOR_NAMES = {
    'BLACK': '000000', 'WHITE': 'FFFFFF', 'RED': 'FF0000',
    'GREEN': '008000', 'BLUE': '0000FF', 'YELLOW': 'FFFF00',
    'MAGENTA': 'FF00FF', 'CYAN': '00FFFF',
}

_DATE_TOKEN_RE = re.compile(r'(y+|m+|d+|h+|s+|AM/PM|A/P)', re.IGNORECASE)


# ---------------------------------------------------------------- format helpers
# IronPython's support for '%.*f' (star precision) and '{:,.2f}' (thousands
# grouping) is unverified, so everything here uses the plainest possible form:
# '%.<N>f' and commas inserted by hand.

def _fixed(num, decimals):
    """num -> '1035.4'; rounded to `decimals` decimal places."""
    return ('%%.%df' % int(decimals)) % float(num)


def _group_thousands(digits):
    """'1234567' -> '1,234,567'"""
    out = []
    n = len(digits)
    for i, ch in enumerate(digits):
        if i and (n - i) % 3 == 0:
            out.append(',')
        out.append(ch)
    return ''.join(out)


def _fixed_grouped(num, decimals):
    body = _fixed(num, decimals)
    neg = body.startswith('-')
    if neg:
        body = body[1:]
    if '.' in body:
        ip, dp = body.split('.', 1)
        dp = '.' + dp
    else:
        ip, dp = body, ''
    return ('-' if neg else '') + _group_thousands(ip) + dp


# ---------------------------------------------------------------- public entry point

def render(value, fmt, warnings=None):
    """
    -> (text, color_hex_or_None)

    color is non-None only when the format string spells out a colour such as
    [Red]; a caller may use it to override the font colour (the first version
    is free to ignore it).
    """
    if value is None:
        return '', None

    if isinstance(value, bool):
        return ('TRUE' if value else 'FALSE'), None

    # Non-numeric values pass straight through: '8+1m', 'Refer to Plan',
    # '2.5m+45' and so on
    if is_string(value):
        return value, None

    if isinstance(value, (datetime.datetime, datetime.date, datetime.time)):
        return _render_datetime(value, fmt, warnings)

    if not is_number(value):
        return text_of(value), None

    fmt = (fmt or 'General').strip()
    if not fmt or fmt.lower() == 'general':
        return format_general(value), None

    try:
        return _render_number(float(value), fmt, warnings)
    except Exception as exc:
        _warn(warnings, 'Number format %r failed (%s) - fell back to plain text' % (fmt, exc))
        return format_general(value), None


def text_of(value):
    from .compat import to_text
    return to_text(value)


def format_general(value):
    """General: integers carry no decimal point, floats lose trailing zeros."""
    if not isinstance(value, float):
        return text_of(value)
    f = float(value)
    if f == int(f) and abs(f) < 1e15:
        return to_text(int(f))
    s = ('%%.%dg' % GENERAL_SIG_DIGITS) % f
    if 'e' in s or 'E' in s:
        return s
    if '.' in s:
        s = s.rstrip('0').rstrip('.')
    return s


# ---------------------------------------------------------------- sections

def split_sections(fmt):
    """Split on ';', ignoring semicolons inside quotes, inside square brackets,
    or escaped with a backslash."""
    out, buf = [], []
    i, n = 0, len(fmt)
    while i < n:
        ch = fmt[i]
        if ch == '\\' and i + 1 < n:
            buf.append(ch)
            buf.append(fmt[i + 1])
            i += 2
            continue
        if ch == '"':
            j = fmt.find('"', i + 1)
            j = n if j < 0 else j
            buf.append(fmt[i:j + 1])
            i = j + 1
            continue
        if ch == '[':
            j = fmt.find(']', i + 1)
            j = n if j < 0 else j
            buf.append(fmt[i:j + 1])
            i = j + 1
            continue
        if ch == ';':
            out.append(''.join(buf))
            buf = []
            i += 1
            continue
        buf.append(ch)
        i += 1
    out.append(''.join(buf))
    return out


def pick_section(sections, value):
    """Excel's rule: positive / negative / zero / text. When sections are
    missing, fall back in Excel's own order."""
    n = len(sections)
    if n == 1:
        return sections[0], False
    if value < 0:
        if n >= 2 and sections[1].strip():
            return sections[1], True          # negative section: format the absolute value
        return sections[0], False
    if value == 0 and n >= 3 and sections[2].strip():
        return sections[2], False
    return sections[0], False


# ---------------------------------------------------------------- lexer

def _tokenize(section):
    """
    -> (tokens, color, has_percent)
    token elements: ('lit', s) literal / ('num', c) digit placeholder (# 0 ? , .)
    """
    tokens = []
    color = None
    has_percent = False
    i, n = 0, len(section)
    while i < n:
        ch = section[i]
        if ch == '\\' and i + 1 < n:
            tokens.append(('lit', section[i + 1]))
            i += 2
        elif ch == '"':
            j = section.find('"', i + 1)
            j = n if j < 0 else j
            tokens.append(('lit', section[i + 1:j]))
            i = j + 1
        elif ch == '[':
            j = section.find(']', i + 1)
            j = n if j < 0 else j
            inner = section[i + 1:j].strip()
            up = inner.upper()
            if up in _COLOR_NAMES:
                color = _COLOR_NAMES[up]
            elif up.startswith('COLOR'):
                color = None                  # indexed colours like [Color15] are unsupported
            i = j + 1
        elif ch == '_':
            tokens.append(('lit', ' '))       # width placeholder, rendered as a space
            i += 2
        elif ch == '*':
            i += 2                            # fill character, not implemented
        elif ch == '%':
            has_percent = True
            tokens.append(('lit', '%'))
            i += 1
        elif ch in '#0?,.':
            tokens.append(('num', ch))
            i += 1
        else:
            tokens.append(('lit', ch))
            i += 1
    return tokens, color, has_percent


def _render_number(value, fmt, warnings):
    sections = split_sections(fmt)
    section, use_abs = pick_section(sections, value)

    if _looks_like_date(section):
        _warn(warnings, 'Value %r uses date format %r - converted from serial number' % (value, fmt))
        return _render_datetime(_serial_to_datetime(value), fmt, warnings)

    tokens, color, has_percent = _tokenize(section)

    num_positions = [i for i, (k, _) in enumerate(tokens) if k == 'num']
    if not num_positions:
        # A section of pure literals, e.g. ";;;" to hide the value
        return ''.join(t for k, t in tokens if k == 'lit'), color

    first, last = num_positions[0], num_positions[-1]
    prefix = ''.join(t for k, t in tokens[:first] if k == 'lit')
    suffix = ''.join(t for k, t in tokens[last + 1:] if k == 'lit')
    pattern = ''.join(t for k, t in tokens[first:last + 1] if k == 'num')

    num = abs(value) if use_abs else value
    if has_percent:
        num *= 100.0

    # Trailing commas: each one scales the value down by a thousand
    trailing = len(pattern) - len(pattern.rstrip(','))
    if trailing:
        num /= (1000.0 ** trailing)
        pattern = pattern[:-trailing]

    if '.' in pattern:
        int_part, dec_part = pattern.split('.', 1)
    else:
        int_part, dec_part = pattern, ''

    decimals = len([c for c in dec_part if c in '0#?'])
    min_int_digits = len([c for c in int_part if c in '0?'])
    thousands = ',' in int_part

    if thousands:
        body = _fixed_grouped(num, decimals)
    else:
        body = _fixed(num, decimals)

    body = _pad_int_digits(body, min_int_digits, thousands)

    if decimals and set(dec_part) <= set('#?.'):
        # Decimal places that are all #: drop the surplus zeros
        body = body.rstrip('0').rstrip('.')

    return prefix + body + suffix, color


def _pad_int_digits(body, min_digits, thousands):
    neg = body.startswith('-')
    if neg:
        body = body[1:]
    if '.' in body:
        ip, dp = body.split('.', 1)
        dp = '.' + dp
    else:
        ip, dp = body, ''
    digits = ip.replace(',', '')
    if min_digits == 0 and digits == '0':
        ip = ip[1:] if not thousands else ip.lstrip('0')
    elif len(digits) < min_digits:
        ip = '0' * (min_digits - len(digits)) + ip
    return ('-' if neg else '') + ip + dp


# ---------------------------------------------------------------- dates

def _looks_like_date(section):
    stripped = re.sub(r'\[[^\]]*\]|"[^"]*"|\\.', '', section)
    return bool(re.search(r'[yYdD]', stripped)) or \
        bool(re.search(r'(?<![#0?])[mM]+/', stripped))


def _serial_to_datetime(serial):
    base = datetime.datetime(1899, 12, 30)
    return base + datetime.timedelta(days=float(serial))


def _render_datetime(value, fmt, warnings):
    if isinstance(value, datetime.time):
        value = datetime.datetime(1899, 12, 30, value.hour,
                                  value.minute, value.second)
    elif isinstance(value, datetime.date) and not isinstance(value, datetime.datetime):
        value = datetime.datetime(value.year, value.month, value.day)

    fmt = (fmt or '').strip()
    if not fmt or fmt.lower() == 'general':
        return value.strftime('%Y-%m-%d'), None

    section = split_sections(fmt)[0]
    section = re.sub(r'\[[^\]]*\]', '', section)
    out = []
    i, n = 0, len(section)
    seen_hour = False
    while i < n:
        ch = section[i]
        if ch == '\\' and i + 1 < n:
            out.append(section[i + 1])
            i += 2
            continue
        if ch == '"':
            j = section.find('"', i + 1)
            j = n if j < 0 else j
            out.append(section[i + 1:j])
            i = j + 1
            continue
        m = _DATE_TOKEN_RE.match(section, i)
        if m:
            tok = m.group(0)
            low = tok.lower()
            if low.startswith('h'):
                seen_hour = True
            out.append(_date_token(value, low, seen_hour))
            i = m.end()
            continue
        out.append(ch)
        i += 1
    return ''.join(out), None


def _date_token(dt, tok, seen_hour):
    if tok.startswith('y'):
        return '%04d' % dt.year if len(tok) > 2 else '%02d' % (dt.year % 100)
    if tok.startswith('d'):
        if len(tok) >= 4:
            return dt.strftime('%A')
        if len(tok) == 3:
            return dt.strftime('%a')
        return '%02d' % dt.day if len(tok) == 2 else str(dt.day)
    if tok.startswith('h'):
        return '%02d' % dt.hour if len(tok) == 2 else str(dt.hour)
    if tok.startswith('s'):
        return '%02d' % dt.second if len(tok) == 2 else str(dt.second)
    if tok.startswith('m'):
        if seen_hour:                                    # an m right after an hour is minutes
            return '%02d' % dt.minute if len(tok) == 2 else str(dt.minute)
        if len(tok) >= 4:
            return dt.strftime('%B')
        if len(tok) == 3:
            return dt.strftime('%b')
        return '%02d' % dt.month if len(tok) == 2 else str(dt.month)
    if tok.upper() in ('AM/PM', 'A/P'):
        return dt.strftime('%p')
    return tok


def _warn(warnings, msg):
    if warnings is not None and msg not in warnings:
        warnings.append(msg)
