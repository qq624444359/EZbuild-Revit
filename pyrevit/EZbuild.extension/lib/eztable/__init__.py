# -*- coding: utf-8 -*-
"""
eztable -- draw an Excel worksheet into a Revit drafting view, styling intact.

Module layout:
    compat.py     Python 2.7 (IronPython) / Python 3 compatibility shims
    xlsxlite.py   zero-dependency OOXML reader (replaces openpyxl)
    geometry.py   unit conversion + coordinate maths
    theme.py      theme palette + tint resolution
    numfmt.py     number format rendering
    config.py     drafting standards (line styles / fills / text types) -- edit this one
    metrics.py    Arial character width table, decides whether text fits
    xlreader.py   Excel parsing -> list of CellModel
    plan.py       CellModel -> Revit-free drawing instructions + fit-to-text layout
    styles.py     lookup / creation / caching of Revit type elements
    renderer.py   drawing instructions -> DetailLine / FilledRegion / TextNote
    storage.py    records the source of a view via Extensible Storage
    job.py        the pipeline shared by Import and Refresh
    report.py     the report printed in the output window

Everything except styles.py and renderer.py avoids the Revit API and any
third-party library, so those modules can be exercised directly under both
IronPython 2.7 and CPython 3.x.

Why not openpyxl: the netcore build of pyRevit 6.4.0 (Revit 2025+ / .NET 8)
ships no usable CPython engine, so `#! python3` scripts never start. The whole
package therefore has to run on IronPython 2.7, and openpyxl needs Python 3.8+.
"""

__version__ = '1.0.0'

from . import compat, config, geometry, metrics, numfmt, theme, xlsxlite  # noqa: F401

__all__ = ['compat', 'config', 'metrics', 'xlsxlite', 'geometry', 'numfmt',
           'theme', 'xlreader', 'plan', 'report', 'storage', 'job',
           'styles', 'renderer', '__version__']
