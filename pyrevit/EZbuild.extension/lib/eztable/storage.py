# -*- coding: utf-8 -*-
"""
storage.py -- records which Excel a view came from, via Extensible Storage

What is stored: absolute source path, worksheet name, MD5 of the source file,
the import time, and -- for a table too tall for one sheet -- which part of it
this view holds. Refresh compares the MD5 to tell whether the workbook has
changed, and groups a table's parts by path + worksheet so they are redrawn
together.

The schema GUID must never change once published -- changing it orphans every
view imported so far. It is the sole identity of the stamp: schemas are looked
up by GUID, so the name and vendor id below are cosmetic. They still have to
match Revit/Storage.cs in the C# add-in, so that the two implementations agree
on what they create in a document that has no stamp yet.

**Adding a field is not retroactive.** A document stamped before Part/PartCount
existed already holds the five-field schema, and Schema.Lookup returns that one;
the GUID cannot change, so the new fields are simply absent there. Every read
and write below therefore skips a field the document's schema does not have, and
a missing part reads as part 1 of 1 -- which is what those views are.
"""

from __future__ import division, unicode_literals

import os

import System
from Autodesk.Revit.DB import FilteredElementCollector, ViewDrafting
from Autodesk.Revit.DB.ExtensibleStorage import (
    AccessLevel, Entity, Schema, SchemaBuilder,
)

SCHEMA_GUID = System.Guid('7b2f1a54-3c9d-4e6b-8a11-5f0d2c9e4a77')
SCHEMA_NAME = 'EZTableSource'
VENDOR_ID = 'EZTB'

FIELDS = ('SourcePath', 'SheetName', 'SourceHash', 'ImportTime', 'Version',
          'Part', 'PartCount')

# Defaults for a stamp written before a field existed
DEFAULTS = {'Part': '1', 'PartCount': '1'}


def get_schema():
    """Look it up, create it if absent. Building a schema does not modify the
    document, so no transaction is needed."""
    schema = Schema.Lookup(SCHEMA_GUID)
    if schema is not None:
        return schema
    builder = SchemaBuilder(SCHEMA_GUID)
    builder.SetSchemaName(SCHEMA_NAME)
    builder.SetVendorId(VENDOR_ID)
    builder.SetReadAccessLevel(AccessLevel.Public)
    builder.SetWriteAccessLevel(AccessLevel.Public)
    for name in FIELDS:
        builder.AddSimpleField(name, System.String)
    return builder.Finish()


def write_stamp(view, source_path, sheet_name, source_hash, version='',
                part=1, part_count=1):
    """Must be called inside a transaction."""
    schema = get_schema()
    entity = Entity(schema)
    values = {
        'SourcePath': source_path or '',
        'SheetName': sheet_name or '',
        'SourceHash': source_hash or '',
        'ImportTime': System.DateTime.Now.ToString('yyyy-MM-dd HH:mm:ss'),
        'Version': version or '',
        'Part': str(part or 1),
        'PartCount': str(part_count or 1),
    }
    for name in FIELDS:
        field = schema.GetField(name)
        if field is None:
            continue              # older schema in this document; see the header
        entity.Set[System.String](field, values[name])
    view.SetEntity(entity)


def read_stamp(view):
    """-> dict, or None when the view carries no stamp."""
    try:
        schema = get_schema()
        entity = view.GetEntity(schema)
        if entity is None or not entity.IsValid():
            return None
        out = {}
        for name in FIELDS:
            field = schema.GetField(name)
            out[name] = (entity.Get[System.String](field) if field is not None
                         else DEFAULTS.get(name, ''))
        return out
    except Exception:
        return None


def clear_stamp(view):
    """Un-stamp a view, so Refresh stops offering it. Must be called inside a
    transaction. Used when a table shrinks and a part is left with no content."""
    try:
        view.DeleteEntity(get_schema())
        return True
    except Exception:
        return False


def part_of(stamp):
    """(part, part count) of a stamp, both 1 when it predates the fields."""
    def number(key):
        try:
            return max(1, int(stamp.get(key) or 1))
        except Exception:
            return 1
    return number('Part'), number('PartCount')


def table_key(stamp):
    """
    What makes two views parts of the same table: the source file and the
    worksheet. Paths are compared case-insensitively and normalised, because
    Windows hands back the same file under more than one spelling.
    """
    path = stamp.get('SourcePath') or ''
    try:
        path = os.path.normcase(os.path.abspath(path))
    except Exception:
        pass
    return (path, stamp.get('SheetName') or '')


def find_stamped_views(doc):
    """-> [(view, stamp)], sorted by view name."""
    out = []
    for view in FilteredElementCollector(doc).OfClass(ViewDrafting):
        if view.IsTemplate:
            continue
        stamp = read_stamp(view)
        if stamp:
            out.append((view, stamp))
    out.sort(key=lambda pair: pair[0].Name)
    return out


def find_tables(doc):
    """
    The stamped views grouped into the tables they belong to.
    -> [(table key, [(view, stamp)] in part order)], sorted by the first view's
    name.

    A table split across several sheets is refreshed as a unit -- redrawing one
    part on its own would leave the others showing a different revision of the
    same workbook.
    """
    groups = {}
    for view, stamp in find_stamped_views(doc):
        groups.setdefault(table_key(stamp), []).append((view, stamp))
    tables = []
    for key, members in groups.items():
        # By recorded part, with the view name to settle stamps that predate
        # the Part field (all of which read as part 1)
        members.sort(key=lambda pair: (part_of(pair[1])[0], pair[0].Name))
        tables.append((key, members))
    tables.sort(key=lambda t: t[1][0][0].Name)
    return tables
