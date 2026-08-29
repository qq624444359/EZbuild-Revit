# -*- coding: utf-8 -*-
"""Update Titleblock -- batch-write the fields that are identical on every sheet.

Measured against the real drawings: of the 9 information bands inside the title
block, only DRAWING NAME / DRAWING NUMBER differ per sheet and the logo is an
image. The other six are constant across a project:
    PROJECT, PROJECT NUMBER, REV, DATE, DRAWN BY, CHECKED BY

Fields left blank are skipped - existing values are never cleared.
"""

from __future__ import unicode_literals

from Autodesk.Revit.DB import Transaction

from pyrevit import forms, revit, script

from ezsheets import sheetutils as su

doc = revit.doc
output = script.get_output()
output.set_title("EZbuild - Update Titleblock")


# Shared/custom parameter name for the revision field.
# If your title block family calls it something else, change this.
REV_PARAM_NAME = "REV"


def main():
    form = forms.FlexForm("Update Titleblock", [
        forms.Label("Blank fields are left untouched."),
        forms.Separator(),
        forms.Label("PROJECT NUMBER"),
        forms.TextBox("project_number"),
        forms.Label("PROJECT"),
        forms.TextBox("project_name"),
        forms.Label("ADDRESS"),
        forms.TextBox("project_address"),
        forms.Separator(),
        forms.Label("DATE  (e.g. 31/12/24)"),
        forms.TextBox("date"),
        forms.Label("DRAWN BY"),
        forms.TextBox("drawn_by"),
        forms.Label("CHECKED BY"),
        forms.TextBox("checked_by"),
        forms.Label("REV"),
        forms.TextBox("rev"),
        forms.Separator(),
        forms.CheckBox("only_selected", "Only update currently selected sheets"),
        forms.Button("Apply"),
    ])
    if not form.show():
        script.exit()
    values = form.values

    def val(key):
        v = (values.get(key) or "").strip()
        return v if v else None

    sheets = su.all_sheets(doc)
    if values.get("only_selected"):
        sel_ids = set(su.id_value(i) for i in revit.get_selection().element_ids)
        sheets = [s for s in sheets if su.id_value(s.Id) in sel_ids]
        if not sheets:
            forms.alert("No sheets are selected.", exitscript=True)

    output.print_md("# Update Titleblock")
    output.print_md("**Target sheets:** {0}".format(len(sheets)))

    project_fields = {
        "project_number": val("project_number"),
        "project_name": val("project_name"),
        "project_address": val("project_address"),
    }
    sheet_fields = {
        "date": val("date"),
        "drawn_by": val("drawn_by"),
        "checked_by": val("checked_by"),
    }
    rev_value = val("rev")

    if not any(project_fields.values()) and not any(sheet_fields.values()) \
            and rev_value is None:
        forms.alert("Every field is empty - nothing to write.", exitscript=True)

    written_project, failed_project = [], []
    counts = dict((k, 0) for k in sheet_fields)
    rev_ok, rev_fail = 0, 0

    t = Transaction(doc, "Update titleblock info")
    t.Start()
    try:
        for field, value in project_fields.items():
            if value is None:
                continue
            if su.set_project_field(doc, field, value):
                written_project.append(field)
            else:
                failed_project.append(field)

        for s in sheets:
            for field, value in sheet_fields.items():
                if value is None:
                    continue
                if su.set_sheet_field(s, field, value):
                    counts[field] += 1
            if rev_value is not None:
                if su.set_param_text(s, REV_PARAM_NAME, rev_value):
                    rev_ok += 1
                else:
                    rev_fail += 1
        t.Commit()
    except Exception:
        t.RollBack()
        raise

    output.print_md("## Project information")
    if written_project:
        output.print_md("Written: `{0}`".format(", ".join(written_project)))
    if failed_project:
        output.print_md("Failed (parameter read-only or missing): `{0}`"
                        .format(", ".join(failed_project)))

    output.print_md("## Sheet parameters")
    rows = [[k, v] for k, v in counts.items() if v]
    if rows:
        output.print_table(rows, columns=["Field", "Sheets written"])
    else:
        output.print_md("(no sheet-level parameters written this run)")

    if rev_value is not None:
        output.print_md("**{0}**: {1} written, {2} failed"
                        .format(REV_PARAM_NAME, rev_ok, rev_fail))
        if rev_fail:
            output.print_md("> Failures usually mean your title block family calls this "
                            "parameter something other than `{0}`. Check the real name on "
                            "a title block instance, then edit `REV_PARAM_NAME` at the top "
                            "of this script.".format(REV_PARAM_NAME))


if __name__ == "__main__":
    main()
