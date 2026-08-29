# -*- coding: utf-8 -*-
"""
compat.py -- small helpers that work on both Python 2.7 (IronPython) and Python 3

The netcore build of pyRevit 6.4.0 ships no CPython engine that runs under
.NET 8, so IronPython is the only option on Revit 2025+ and the whole package
has to keep working on IronPython 2.7.
"""

from __future__ import division

import sys

PY2 = sys.version_info[0] == 2

if PY2:                                        # pragma: no cover
    string_types = (str, unicode)              # noqa: F821
    text_type = unicode                        # noqa: F821
    binary_type = str
    integer_types = (int, long)                # noqa: F821
else:
    string_types = (str,)
    text_type = str
    binary_type = bytes
    integer_types = (int,)

number_types = tuple(list(integer_types) + [float])


def to_text(value, encoding='utf-8'):
    """bytes/str -> unicode text"""
    if value is None:
        return None
    if isinstance(value, text_type):
        return value
    if isinstance(value, binary_type):
        return value.decode(encoding, 'replace')
    return text_type(value)


def is_number(value):
    """bool does not count as a number -- Excel TRUE/FALSE renders down another path"""
    return isinstance(value, number_types) and not isinstance(value, bool)


def is_string(value):
    return isinstance(value, string_types)


def safe_float(value, default=None):
    """
    An IronPython trap: float(None) raises the .NET
    SystemError: Object reference not set to an instance of an object,
    not CPython's TypeError. Every conversion coming out of an XML attribute
    has to go through here, and the except clause has to catch broad Exception
    rather than a specific type.
    """
    if value is None:
        return default
    try:
        return float(value)
    except Exception:
        return default


def safe_int(value, default=None):
    """Same contract as safe_float."""
    if value is None:
        return default
    try:
        return int(value)
    except Exception:
        return default
