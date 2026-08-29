# -*- coding: utf-8 -*-
"""
storage.py -- records which Excel a view came from, via Extensible Storage

Four things are stored: absolute source path, worksheet name, MD5 of the source
file, and the import time. Refresh compares the MD5 to tell whether the workbook
has changed.

The schema GUID must never change once published -- changing it orphans every
view imported so far. It is the sole identity of the stamp: schemas are looked
up by GUID, so the name and vendor id below are cosmetic. They still have to
match Revit/Storage.cs in the C# add-in, so that the two implementations agree
on what they create in a document that has no stamp yet.
"""

from __future__ import division, unicode_literals

import System
from Autodesk.Revit.DB import FilteredElementCollector, ViewDrafting
from Autodesk.Revit.DB.ExtensibleStorage import (
    AccessLevel, Entity, Schema, SchemaBuilder,
)

SCHEMA_GUID = System.Guid('7b2f1a54-3c9d-4e6b-8a11-5f0d2c9e4a77')
SCHEMA_NAME = 'EZTableSource'
VENDOR_ID = 'EZTB'

FIELDS = ('SourcePath', 'SheetName', 'SourceHash', 'ImportTime', 'Version')


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


def write_stamp(view, source_path, sheet_name, source_hash, version=''):
    """Must be called inside a transaction."""
    schema = get_schema()
    entity = Entity(schema)
    values = {
        'SourcePath': source_path or '',
        'SheetName': sheet_name or '',
        'SourceHash': source_hash or '',
        'ImportTime': System.DateTime.Now.ToString('yyyy-MM-dd HH:mm:ss'),
        'Version': version or '',
    }
    for name in FIELDS:
        entity.Set[System.String](schema.GetField(name), values[name])
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
            out[name] = entity.Get[System.String](schema.GetField(name))
        return out
    except Exception:
        return None


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
