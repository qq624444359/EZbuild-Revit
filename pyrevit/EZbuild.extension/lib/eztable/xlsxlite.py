# -*- coding: utf-8 -*-
"""
xlsxlite.py -- a minimal, zero-dependency xlsx reader

Why not openpyxl: the netcore build of pyRevit 6.4.0 ships no CPython engine
that runs under .NET 8 (bin\\netcore\\engines contains only IPY2712PR and
IPY342), so `#! python3` scripts never start on Revit 2025+. The parsing layer
therefore has to run on IronPython 2.7, which rules openpyxl out.

Only the part of OOXML this project needs is parsed:
    xl/workbook.xml              worksheet list + print area
    xl/_rels/workbook.xml.rels   r:id -> file path
    xl/sharedStrings.xml         shared strings
    xl/styles.xml                numFmt / font / fill / border / alignment
    xl/worksheets/sheetN.xml     row and column sizes, cells, merged ranges
    xl/theme/theme1.xml          handed to theme.py

Not parsed: images, charts, conditional formatting, data validation, pivot
tables, and per-run formatting inside rich text.

The objects exposed here deliberately duck-type openpyxl (Color has
.type/.rgb/.theme/.tint, Side has .style/.color), which means
theme.ThemePalette.resolve() needs no changes.
"""

from __future__ import division, unicode_literals

import datetime
import re
import xml.etree.ElementTree as ET

from .compat import safe_float, safe_int, to_text

NS_MAIN = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
NS_REL = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
NS_PKG_REL = 'http://schemas.openxmlformats.org/package/2006/relationships'

ERROR_VALUES = frozenset([
    '#REF!', '#DIV/0!', '#N/A', '#NAME?', '#NULL!', '#NUM!', '#VALUE!',
    '#SPILL!', '#CALC!', '#GETTING_DATA',
])

BUILTIN_FORMATS = {
    0: 'General', 1: '0', 2: '0.00', 3: '#,##0', 4: '#,##0.00',
    9: '0%', 10: '0.00%', 11: '0.00E+00', 12: '# ?/?', 13: '# ??/??',
    14: 'mm-dd-yy', 15: 'd-mmm-yy', 16: 'd-mmm', 17: 'mmm-yy',
    18: 'h:mm AM/PM', 19: 'h:mm:ss AM/PM', 20: 'h:mm', 21: 'h:mm:ss',
    22: 'm/d/yy h:mm',
    37: '#,##0 ;(#,##0)', 38: '#,##0 ;[Red](#,##0)',
    39: '#,##0.00;(#,##0.00)', 40: '#,##0.00;[Red](#,##0.00)',
    45: 'mm:ss', 46: '[h]:mm:ss', 47: 'mmss.0', 48: '##0.0E+0', 49: '@',
}


def M(tag):
    return '{%s}%s' % (NS_MAIN, tag)


# ---------------------------------------------------------------- cell references

_REF_RE = re.compile(r'^\$?([A-Za-z]+)\$?(\d+)$')


def column_index(letters):
    """'A' -> 1, 'AA' -> 27"""
    idx = 0
    for ch in letters.upper():
        idx = idx * 26 + (ord(ch) - 64)
    return idx


def column_letter(index):
    """1 -> 'A', 27 -> 'AA'"""
    letters = ''
    while index > 0:
        index, rem = divmod(index - 1, 26)
        letters = chr(65 + rem) + letters
    return letters


def parse_ref(ref):
    """'B3' / '$B$3' -> (3, 2)"""
    m = _REF_RE.match(ref.strip())
    if not m:
        raise ValueError('Cannot parse cell reference: %r' % ref)
    return safe_int(m.group(2), 0), column_index(m.group(1))


def parse_range(ref):
    """'A1:E20' / "'Sheet 1'!$A$1:$E$20" -> (min_row, min_col, max_row, max_col)"""
    ref = ref.strip()
    if '!' in ref:
        ref = ref.rsplit('!', 1)[-1]
    ref = ref.replace('$', '')
    if ':' in ref:
        a, b = ref.split(':', 1)
        r1, c1 = parse_ref(a)
        r2, c2 = parse_ref(b)
        return min(r1, r2), min(c1, c2), max(r1, r2), max(c1, c2)
    r, c = parse_ref(ref)
    return r, c, r, c


# ---------------------------------------------------------------- the archive

class Package(object):
    """Prefer Python's zipfile; fall back to .NET ZipArchive should it be
    unavailable under IronPython."""

    def __init__(self, path):
        self.path = path
        self._zip = None
        self._netzip = None
        try:
            import zipfile
            self._zip = zipfile.ZipFile(path)
            self.names = list(self._zip.namelist())
        except Exception:
            self._open_dotnet(path)

    def _open_dotnet(self, path):                        # pragma: no cover
        import clr
        try:
            clr.AddReference('System.IO.Compression.FileSystem')
        except Exception:
            pass
        from System.IO.Compression import ZipFile as NetZipFile
        self._netzip = NetZipFile.OpenRead(path)
        self.names = [e.FullName for e in self._netzip.Entries]

    def has(self, name):
        return name in self.names

    def read(self, name):
        """-> bytes on py3 / str on py2, ready to feed straight to ElementTree."""
        if self._zip is not None:
            return self._zip.read(name)
        return self._read_dotnet(name)

    def _read_dotnet(self, name):                        # pragma: no cover
        from System.IO import StreamReader
        entry = None
        for e in self._netzip.Entries:
            if e.FullName == name:
                entry = e
                break
        if entry is None:
            raise KeyError(name)
        stream = entry.Open()
        try:
            reader = StreamReader(stream)
            text = reader.ReadToEnd()
        finally:
            stream.Close()
        return to_text(text).encode('utf-8')

    def xml(self, name):
        if not self.has(name):
            return None
        return ET.fromstring(self.read(name))

    def close(self):
        try:
            if self._zip is not None:
                self._zip.close()
            elif self._netzip is not None:               # pragma: no cover
                self._netzip.Dispose()
        except Exception:
            pass


# ---------------------------------------------------------------- style objects
# Deliberately duck-typed against openpyxl so theme.ThemePalette.resolve()
# needs no changes.

class ColorRef(object):
    __slots__ = ('type', 'rgb', 'theme', 'indexed', 'tint')

    def __init__(self, el=None):
        self.type = None
        self.rgb = None
        self.theme = None
        self.indexed = None
        self.tint = 0.0
        if el is None:
            return
        self.tint = safe_float(el.get('tint'), 0.0) or 0.0
        if el.get('rgb'):
            self.type = 'rgb'
            self.rgb = el.get('rgb')
        elif el.get('theme') is not None:
            self.type = 'theme'
            self.theme = safe_int(el.get('theme'))
        elif el.get('indexed') is not None:
            self.type = 'indexed'
            self.indexed = safe_int(el.get('indexed'))
        elif el.get('auto'):
            self.type = 'auto'

    def __repr__(self):
        return '<Color %s rgb=%s theme=%s tint=%s>' % (
            self.type, self.rgb, self.theme, self.tint)


class SideRef(object):
    __slots__ = ('style', 'color')

    def __init__(self, el=None):
        self.style = el.get('style') if el is not None else None
        self.color = None
        if el is not None:
            c = el.find(M('color'))
            if c is not None:
                self.color = ColorRef(c)


class BorderRef(object):
    __slots__ = ('left', 'right', 'top', 'bottom')

    def __init__(self, el=None):
        for name in ('left', 'right', 'top', 'bottom'):
            sub = el.find(M(name)) if el is not None else None
            setattr(self, name, SideRef(sub) if sub is not None else SideRef())


class FillRef(object):
    __slots__ = ('patternType', 'fgColor', 'bgColor')

    def __init__(self, el=None):
        self.patternType = None
        self.fgColor = None
        self.bgColor = None
        if el is None:
            return
        pf = el.find(M('patternFill'))
        if pf is None:
            return
        self.patternType = pf.get('patternType')
        fg = pf.find(M('fgColor'))
        bg = pf.find(M('bgColor'))
        if fg is not None:
            self.fgColor = ColorRef(fg)
        if bg is not None:
            self.bgColor = ColorRef(bg)


class FontRef(object):
    __slots__ = ('name', 'sz', 'b', 'i', 'u', 'color')

    def __init__(self, el=None):
        self.name = None
        self.sz = None
        self.b = False
        self.i = False
        self.u = None
        self.color = None
        if el is None:
            return
        n = el.find(M('name'))
        if n is None:
            n = el.find(M('rFont'))
        if n is not None:
            self.name = n.get('val')
        s = el.find(M('sz'))
        if s is not None:
            self.sz = safe_float(s.get('val'))
        self.b = _flag(el, 'b')
        self.i = _flag(el, 'i')
        u = el.find(M('u'))
        self.u = (u.get('val') or 'single') if u is not None else None
        c = el.find(M('color'))
        if c is not None:
            self.color = ColorRef(c)


class AlignmentRef(object):
    __slots__ = ('horizontal', 'vertical', 'wrapText', 'textRotation', 'indent')

    def __init__(self, el=None):
        self.horizontal = el.get('horizontal') if el is not None else None
        self.vertical = el.get('vertical') if el is not None else None
        self.wrapText = _truthy(el.get('wrapText')) if el is not None else False
        self.textRotation = safe_int(el.get('textRotation'), 0) if el is not None else 0
        self.indent = safe_int(el.get('indent'), 0) if el is not None else 0


class CellStyle(object):
    __slots__ = ('number_format', 'font', 'fill', 'border', 'alignment')

    def __init__(self):
        self.number_format = 'General'
        self.font = FontRef()
        self.fill = FillRef()
        self.border = BorderRef()
        self.alignment = AlignmentRef()


def _flag(parent, tag):
    el = parent.find(M(tag))
    if el is None:
        return False
    return _truthy(el.get('val'), default=True)


def _truthy(value, default=False):
    if value is None:
        return default
    try:
        return to_text(value).strip().lower() in ('1', 'true', 'on')
    except Exception:
        return default


def _float(value):
    return safe_float(value)


def _int(value, default=None):
    return safe_int(value, default)


# ---------------------------------------------------------------- sheet structure

class ColDim(object):
    __slots__ = ('width', 'hidden', 'custom')

    def __init__(self, width=None, hidden=False, custom=False):
        self.width = width
        self.hidden = hidden
        self.custom = custom


class RowDim(object):
    __slots__ = ('height', 'hidden', 'custom')

    def __init__(self, height=None, hidden=False, custom=False):
        self.height = height
        self.hidden = hidden
        self.custom = custom


class Cell(object):
    __slots__ = ('row', 'column', 'value', 'formula', 'has_cached', 'style')

    def __init__(self, row, column, style):
        self.row = row
        self.column = column
        self.value = None
        self.formula = None
        self.has_cached = True
        self.style = style

    @property
    def coordinate(self):
        return '%s%d' % (column_letter(self.column), self.row)

    @property
    def number_format(self):
        return self.style.number_format

    def __repr__(self):
        return '<Cell %s %r>' % (self.coordinate, self.value)


class Worksheet(object):
    __slots__ = ('name', 'index', 'cells', 'col_dims', 'row_dims',
                 'default_col_width', 'default_row_height',
                 'merged_ranges', 'dimension', 'print_area', 'default_style')

    def __init__(self, name, index, default_style):
        self.name = name
        self.index = index
        self.cells = {}
        self.col_dims = {}
        self.row_dims = {}
        self.default_col_width = None
        self.default_row_height = None
        self.merged_ranges = []
        self.dimension = None
        self.print_area = []
        self.default_style = default_style

    def cell(self, row, column):
        """An empty cell still returns a Cell carrying default styling, so
        callers never have to check for None."""
        c = self.cells.get((row, column))
        if c is None:
            c = Cell(row, column, self.default_style)
        return c

    def hidden_rows(self):
        return set(r for r, d in self.row_dims.items() if d.hidden)

    def hidden_cols(self):
        return set(c for c, d in self.col_dims.items() if d.hidden)

    def used_range(self):
        """(min_row, min_col, max_row, max_col); inferred from the cells when
        dimension is missing."""
        if self.dimension:
            return self.dimension
        if not self.cells:
            return (1, 1, 1, 1)
        rows = [k[0] for k in self.cells]
        cols = [k[1] for k in self.cells]
        return (min(rows), min(cols), max(rows), max(cols))


class Workbook(object):
    __slots__ = ('path', 'package', 'sheetnames', '_sheet_meta',
                 'shared_strings', 'styles', 'theme_xml', '_cache')

    def __init__(self, path):
        self.path = path
        self.package = Package(path)
        self.sheetnames = []
        self._sheet_meta = []            # [(name, target_path, print_area_ref)]
        self.shared_strings = []
        self.styles = [CellStyle()]
        self.theme_xml = None
        self._cache = {}
        self._load()

    # -- loading --------------------------------------------------

    def _load(self):
        pkg = self.package
        rels = self._read_rels()
        self.shared_strings = self._read_shared_strings()
        self.styles = self._read_styles()
        for name in pkg.names:
            if re.match(r'xl/theme/theme\d*\.xml$', name):
                self.theme_xml = pkg.read(name)
                break

        root = pkg.xml('xl/workbook.xml')
        if root is None:
            raise ValueError('Not a valid xlsx: xl/workbook.xml is missing')

        sheets_el = root.find(M('sheets'))
        sheets = list(sheets_el) if sheets_el is not None else []

        print_areas = {}
        dn = root.find(M('definedNames'))
        if dn is not None:
            for el in dn.findall(M('definedName')):
                if el.get('name') == '_xlnm.Print_Area':
                    lsid = el.get('localSheetId')
                    lsi = safe_int(lsid)
                    if lsi is not None and el.text:
                        print_areas[lsi] = el.text

        for i, sh in enumerate(sheets):
            name = sh.get('name')
            rid = sh.get('{%s}id' % NS_REL)
            target = rels.get(rid)
            self.sheetnames.append(name)
            self._sheet_meta.append((name, target, print_areas.get(i)))

    def _read_rels(self):
        root = self.package.xml('xl/_rels/workbook.xml.rels')
        out = {}
        if root is None:
            return out
        for rel in root:
            target = rel.get('Target') or ''
            if target.startswith('/'):
                target = target[1:]
            elif not target.startswith('xl/'):
                target = 'xl/' + target
            out[rel.get('Id')] = target.replace('\\', '/')
        return out

    def _read_shared_strings(self):
        root = self.package.xml('xl/sharedStrings.xml')
        if root is None:
            return []
        out = []
        for si in root.findall(M('si')):
            parts = []
            for t in si.iter(M('t')):
                parts.append(t.text or '')
            out.append(''.join(parts))
        return out

    def _read_styles(self):
        root = self.package.xml('xl/styles.xml')
        if root is None:
            return [CellStyle()]

        fmt_codes = dict(BUILTIN_FORMATS)
        nf = root.find(M('numFmts'))
        if nf is not None:
            for el in nf.findall(M('numFmt')):
                nid = safe_int(el.get('numFmtId'))
                if nid is not None:
                    fmt_codes[nid] = el.get('formatCode') or 'General'

        fonts = [FontRef(el) for el in _children(root, 'fonts', 'font')]
        fills = [FillRef(el) for el in _children(root, 'fills', 'fill')]
        borders = [BorderRef(el) for el in _children(root, 'borders', 'border')]

        style_xfs = _children(root, 'cellStyleXfs', 'xf')
        cell_xfs = _children(root, 'cellXfs', 'xf')

        styles = []
        for xf in cell_xfs:
            st = CellStyle()
            st.number_format = fmt_codes.get(safe_int(xf.get('numFmtId'), 0), 'General')
            st.font = _pick(fonts, xf.get('fontId'))
            st.fill = _pick(fills, xf.get('fillId'))
            st.border = _pick(borders, xf.get('borderId'))

            al = xf.find(M('alignment'))
            if al is None and xf.get('xfId') is not None:
                # inherit the alignment from cellStyleXfs
                parent = _pick_el(style_xfs, xf.get('xfId'))
                if parent is not None:
                    al = parent.find(M('alignment'))
            st.alignment = AlignmentRef(al)
            styles.append(st)

        return styles or [CellStyle()]

    # -- worksheets -----------------------------------------------

    def worksheet(self, name):
        if name in self._cache:
            return self._cache[name]
        meta = None
        index = 0
        for i, (n, target, pa) in enumerate(self._sheet_meta):
            if n == name:
                meta, index = (n, target, pa), i
                break
        if meta is None:
            raise KeyError('Worksheet not found: %r (available: %s)'
                           % (name, ', '.join(self.sheetnames)))
        ws = self._parse_sheet(meta, index)
        self._cache[name] = ws
        return ws

    def _parse_sheet(self, meta, index):
        name, target, print_area_ref = meta
        default_style = self.styles[0] if self.styles else CellStyle()
        ws = Worksheet(name, index, default_style)

        if print_area_ref:
            for part in print_area_ref.split(','):
                part = part.strip()
                if part:
                    try:
                        ws.print_area.append(parse_range(part))
                    except ValueError:
                        pass

        root = self.package.xml(target) if target else None
        if root is None:
            return ws

        dim = root.find(M('dimension'))
        if dim is not None and dim.get('ref'):
            try:
                ws.dimension = parse_range(dim.get('ref'))
            except ValueError:
                ws.dimension = None

        fmt = root.find(M('sheetFormatPr'))
        if fmt is not None:
            ws.default_col_width = _float(fmt.get('defaultColWidth'))
            ws.default_row_height = _float(fmt.get('defaultRowHeight'))

        cols = root.find(M('cols'))
        if cols is not None:
            for el in cols.findall(M('col')):
                lo = safe_int(el.get('min'), 1)
                hi = safe_int(el.get('max'), lo)
                width = _float(el.get('width'))
                hidden = _truthy(el.get('hidden'))
                custom = _truthy(el.get('customWidth'))
                if hi - lo > 16384:
                    hi = lo
                for c in range(lo, hi + 1):
                    ws.col_dims[c] = ColDim(width, hidden, custom)

        data = root.find(M('sheetData'))
        if data is not None:
            for row_el in data.findall(M('row')):
                r = safe_int(row_el.get('r'), 0)
                if r:
                    ws.row_dims[r] = RowDim(_float(row_el.get('ht')),
                                            _truthy(row_el.get('hidden')),
                                            _truthy(row_el.get('customHeight')))
                for c_el in row_el.findall(M('c')):
                    cell = self._parse_cell(c_el, r)
                    if cell is not None:
                        ws.cells[(cell.row, cell.column)] = cell

        merges = root.find(M('mergeCells'))
        if merges is not None:
            for el in merges.findall(M('mergeCell')):
                ref = el.get('ref')
                if ref:
                    try:
                        ws.merged_ranges.append(parse_range(ref))
                    except ValueError:
                        pass

        return ws

    def _parse_cell(self, el, fallback_row):
        ref = el.get('r')
        if ref:
            row, col = parse_ref(ref)
        else:
            return None
        if not row:
            row = fallback_row

        s_idx = safe_int(el.get('s'))
        style = self.styles[0]
        if s_idx is not None and 0 <= s_idx < len(self.styles):
            style = self.styles[s_idx]

        cell = Cell(row, col, style)

        f_el = el.find(M('f'))
        if f_el is not None:
            cell.formula = '=' + (f_el.text or '')

        t = el.get('t') or 'n'
        v_el = el.find(M('v'))

        if t == 'inlineStr':
            is_el = el.find(M('is'))
            parts = [x.text or '' for x in is_el.iter(M('t'))] if is_el is not None else []
            cell.value = ''.join(parts)
            return cell

        if v_el is None or v_el.text is None:
            cell.has_cached = f_el is None
            cell.value = None
            return cell

        raw = v_el.text
        if t == 's':
            si = safe_int(raw)
            if si is not None and 0 <= si < len(self.shared_strings):
                cell.value = self.shared_strings[si]
            else:
                cell.value = ''
        elif t in ('str', 'e'):
            cell.value = raw
        elif t == 'b':
            cell.value = raw.strip() in ('1', 'true', 'TRUE')
        elif t == 'd':
            cell.value = _parse_iso(raw)
        else:
            cell.value = _parse_number(raw)
        return cell

    def close(self):
        self.package.close()


# ---------------------------------------------------------------- helpers

def _children(root, container_tag, item_tag):
    el = root.find(M(container_tag))
    return list(el.findall(M(item_tag))) if el is not None else []


def _pick(items, idx):
    i = safe_int(idx)
    if i is not None and 0 <= i < len(items):
        return items[i]
    return items[0] if items else None


def _pick_el(items, idx):
    i = safe_int(idx)
    if i is not None and 0 <= i < len(items):
        return items[i]
    return None


def _parse_number(raw):
    raw = (raw or '').strip()
    if '.' not in raw and 'e' not in raw.lower():
        v = safe_int(raw)
        if v is not None:
            return v
    v = safe_float(raw)
    return raw if v is None else v


def _parse_iso(raw):
    raw = raw.strip()
    for fmt in ('%Y-%m-%dT%H:%M:%S', '%Y-%m-%dT%H:%M', '%Y-%m-%d'):
        try:
            return datetime.datetime.strptime(raw.split('.')[0], fmt)
        except Exception:
            continue
    return raw


def load_workbook(path):
    return Workbook(path)
