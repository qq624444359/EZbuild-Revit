# -*- coding: utf-8 -*-
"""Clone standard detail sheets.

Copies detail sheets from a Standard Detail Library .rvt into the current
project, together with their drafting views and viewport positions.

Why this is step one:
    Across 5 complete BC sets, sheets A501-A543 (17 sheet numbers) are
    identical. Together with the project-specific extras (A510, A513-A520,
    A534, A544) that is 30-45% of a typical set. Pure reuse, no layout
    judgement required, fully deterministic.

How it works:
    1. ElementTransformUtils.CopyElements(srcDoc, [draftingViewIds], dstDoc, ...)
       -- the same mechanism as Revit's "Insert Views from File". It brings the
       drafting view across with all its elements.
    2. ViewSheet.Create(dstDoc, titleBlockTypeId) makes the new sheet.
    3. Viewport.Create(...) places it, then SetBoxCenter puts it exactly where
       it sat in the source. In a clone the coordinates are copied, not computed,
       so reading them straight off the source is correct here.

Safety:
    - The source file is opened detached and closed without saving.
    - All writes sit inside one TransactionGroup; any error rolls everything back.
    - Sheet numbers that already exist are skipped, never overwritten.
"""

from __future__ import unicode_literals

import traceback

from System.Collections.Generic import List

from Autodesk.Revit.DB import (
    BuiltInParameter,
    CopyPasteOptions,
    DetachFromCentralOption,
    DuplicateTypeAction,
    ElementId,
    ElementTransformUtils,
    IDuplicateTypeNamesHandler,
    ModelPathUtils,
    OpenOptions,
    Transaction,
    TransactionGroup,
    Transform,
    ViewDrafting,
    ViewSheet,
    Viewport,
    WorksetConfiguration,
    WorksetConfigurationOption,
    XYZ,
)

from pyrevit import forms, revit, script

from ezsheets import config, sheetutils as su

doc = revit.doc
uiapp = __revit__  # noqa: F821  (injected by pyRevit)
app = uiapp.Application
output = script.get_output()
output.set_title("EZbuild - Clone Details")

logger = script.get_logger()


class UseDestinationTypes(IDuplicateTypeNamesHandler):
    """On a type-name clash, keep the destination project's type."""

    def OnDuplicateTypeNamesFound(self, args):
        return DuplicateTypeAction.UseDestinationTypes


def open_source_document(path):
    """Open the library file detached, without touching the original."""
    model_path = ModelPathUtils.ConvertUserVisiblePathToModelPath(path)
    opts = OpenOptions()
    opts.DetachFromCentralOption = DetachFromCentralOption.DetachAndPreserveWorksets
    opts.Audit = False
    try:
        wc = WorksetConfiguration(WorksetConfigurationOption.CloseAllWorksets)
        opts.SetOpenWorksetsConfiguration(wc)
    except Exception:
        pass  # raises on non-workshared files; harmless
    return app.OpenDocumentFile(model_path, opts)


def detail_sheets_of(src_doc):
    """Sheets whose viewports are all drafting views, i.e. pure detail sheets."""
    result = []
    for sheet in su.all_sheets(src_doc):
        vps = su.viewports_on(src_doc, sheet)
        if not vps:
            continue
        views = [src_doc.GetElement(vp.ViewId) for vp in vps]
        if all(isinstance(v, ViewDrafting) for v in views if v is not None):
            result.append(sheet)
    return result


def pick_titleblock_type(dst_doc):
    """Ask which title block type to use. Auto-picks when there is only one."""
    tb_types = su.titleblock_types(dst_doc)
    if not tb_types:
        forms.alert("This project has no title block family loaded. "
                    "Load one first.", exitscript=True)
    if len(tb_types) == 1:
        return tb_types[0].Id

    options = {}
    for t in tb_types:
        fam = t.Family.Name if t.Family else "?"
        p = t.get_Parameter(BuiltInParameter.SYMBOL_NAME_PARAM)
        tname = p.AsString() if p else "?"
        options["{0} : {1}".format(fam, tname)] = t.Id
    picked = forms.SelectFromList.show(
        sorted(options.keys()), title="Select the title block type",
        multiselect=False)
    if not picked:
        script.exit()
    return options[picked]


def main():
    src_path = forms.pick_file(
        file_ext="rvt", title="Select the Standard Detail Library .rvt")
    if not src_path:
        script.exit()

    output.print_md("# Clone Standard Details")
    output.print_md("**Source:** `{0}`".format(src_path))
    output.print_md("**Target project:** `{0}`".format(doc.Title))

    src_doc = None
    try:
        src_doc = open_source_document(src_path)

        candidates = detail_sheets_of(src_doc)
        if not candidates:
            forms.alert("No pure detail sheets found in the source file "
                        "(sheets where every viewport is a drafting view).",
                        exitscript=True)

        existing_numbers = set(su.sheets_by_number(doc).keys())
        std_set = set(config.STANDARD_SHEET_NUMBERS + config.OPTIONAL_SHEET_NUMBERS)

        labels = {}
        for s in sorted(candidates, key=lambda x: x.SheetNumber):
            if s.SheetNumber in existing_numbers:
                flag = "   [already in project - will be skipped]"
            elif s.SheetNumber in std_set:
                flag = "   * standard"
            else:
                flag = ""
            labels["{0}  {1}{2}".format(s.SheetNumber, s.Name, flag)] = s

        picked = forms.SelectFromList.show(
            sorted(labels.keys()),
            title="Select detail sheets to clone  (* standard = shared by all 5 sets)",
            multiselect=True,
            button_name="Clone",
        )
        if not picked:
            script.exit()

        selected = [labels[p] for p in picked
                    if labels[p].SheetNumber not in existing_numbers]
        skipped = [labels[p].SheetNumber for p in picked
                   if labels[p].SheetNumber in existing_numbers]

        if not selected:
            forms.alert("Every selected sheet number already exists in this "
                        "project - nothing to clone.", exitscript=True)

        tb_type_id = pick_titleblock_type(doc)

        copy_opts = CopyPasteOptions()
        copy_opts.SetDuplicateTypeNamesHandler(UseDestinationTypes())

        done, failed = [], []
        tg = TransactionGroup(doc, "Clone standard details")
        tg.Start()
        try:
            for sheet in selected:
                try:
                    clone_one_sheet(src_doc, doc, sheet, tb_type_id, copy_opts)
                    done.append((sheet.SheetNumber, sheet.Name))
                except Exception as ex:
                    logger.error(traceback.format_exc())
                    failed.append((sheet.SheetNumber, str(ex)))
            tg.Assimilate()
        except Exception:
            tg.RollBack()
            raise

        output.print_md("---")
        if done:
            output.print_md("## Cloned {0} sheet(s)".format(len(done)))
            output.print_table([[n, nm] for n, nm in done],
                               columns=["Sheet no.", "Name"])
        if skipped:
            output.print_md("## Skipped {0} (already present)".format(len(skipped)))
            output.print_md("`{0}`".format(", ".join(sorted(skipped))))
        if failed:
            output.print_md("## Failed {0}".format(len(failed)))
            output.print_table([[n, e] for n, e in failed],
                               columns=["Sheet no.", "Error"])
        output.print_md("---")
        output.print_md("Next: run **2 Sheets > Update Titleblock** to write the "
                        "project number, date and drafter names into the new sheets.")

    finally:
        if src_doc is not None:
            try:
                src_doc.Close(False)   # False = do not save
            except Exception:
                logger.warn("Could not close the source document - close it manually.")


def clone_one_sheet(src_doc, dst_doc, src_sheet, tb_type_id, copy_opts):
    """Clone a single detail sheet. Must be called inside a TransactionGroup."""
    src_vps = su.viewports_on(src_doc, src_sheet)

    plan = []
    view_ids = List[ElementId]()
    for vp in src_vps:
        v = src_doc.GetElement(vp.ViewId)
        if not isinstance(v, ViewDrafting):
            continue
        center = vp.GetBoxCenter()
        plan.append({"name": v.Name, "center": XYZ(center.X, center.Y, 0.0)})
        view_ids.Add(v.Id)

    if view_ids.Count == 0:
        raise Exception("no drafting views on this sheet")

    # 1. copy the drafting views across, with all their elements
    t = Transaction(dst_doc, "Copy views for {0}".format(src_sheet.SheetNumber))
    t.Start()
    new_view_ids = ElementTransformUtils.CopyElements(
        src_doc, view_ids, dst_doc, Transform.Identity, copy_opts)
    t.Commit()

    # match old to new by name - CopyElements does not guarantee return order
    new_views = {}
    for vid in new_view_ids:
        v = dst_doc.GetElement(vid)
        if isinstance(v, ViewDrafting):
            new_views[v.Name] = v.Id

    # 2. create the sheet, place viewports, restore exact positions
    t = Transaction(dst_doc, "Create sheet {0}".format(src_sheet.SheetNumber))
    t.Start()
    new_sheet = ViewSheet.Create(dst_doc, tb_type_id)
    new_sheet.SheetNumber = src_sheet.SheetNumber
    new_sheet.Name = src_sheet.Name

    for item in plan:
        vid = new_views.get(item["name"])
        if vid is None:
            # a copied view may get a suffix on a name clash - loose match
            for nm, i in new_views.items():
                if nm.startswith(item["name"]):
                    vid = i
                    break
        if vid is None:
            continue
        vp = Viewport.Create(dst_doc, new_sheet.Id, vid, XYZ(0, 0, 0))
        vp.SetBoxCenter(item["center"])   # copied 1:1 from the source
    t.Commit()


if __name__ == "__main__":
    main()
