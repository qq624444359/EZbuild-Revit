# -*- coding: utf-8 -*-
"""Sheet Audit -- read-only scan, modifies nothing.

Purpose: first runnable script of the automation project. It answers
questions Q-02 / Q-03 / Q-04 / Q-06 in the rules workbook, and verifies
that the A3 constants in config.py match the actual title block family.

Safety: no Transaction is opened anywhere, the model cannot be changed.
"""

from __future__ import unicode_literals

from collections import Counter

from Autodesk.Revit.DB import (
    BuiltInParameter,
    FilteredElementCollector,
    TextNote,
    ViewSchedule,
    ViewType,
)

from pyrevit import revit, script

from ezsheets import config, sheetutils as su

doc = revit.doc
output = script.get_output()
output.set_title("EZbuild - Sheet Audit")


def _type_name(symbol):
    """Safely read a FamilySymbol type name (.Name is ambiguous under IronPython)."""
    p = symbol.get_Parameter(BuiltInParameter.SYMBOL_NAME_PARAM)
    if p is not None:
        return p.AsString() or "?"
    try:
        return symbol.Name
    except Exception:
        return "?"


output.print_md("# Sheet Audit Report")
output.print_md("**Project file:** `{0}`".format(doc.Title))
output.print_md("---")


# ---------------------------------------------------------------
# 1. Title block family  -- answers Q-04
# ---------------------------------------------------------------
output.print_md("## 1. Title block family")

tb_types = su.titleblock_types(doc)
if not tb_types:
    output.print_md("> **No title block family found.** Load one before running this.")
else:
    rows = []
    for t in tb_types:
        fam = t.Family.Name if t.Family else "?"
        rows.append([fam, _type_name(t)])
    output.print_table(rows, columns=["Family name", "Type name"])
    output.print_md("-> Record the family name under **Q-04** in the rules workbook. "
                    "If all 6 projects share one family, the title block update script "
                    "can use a single set of parameter names.")


# ---------------------------------------------------------------
# 2. Sheet size  -- validates the A3 constants in config.py
# ---------------------------------------------------------------
output.print_md("## 2. Sheet size check (expecting A3, 420 x 297 mm)")

sheets = su.all_sheets(doc)
if not sheets:
    output.print_md("> This project has no sheets.")
else:
    size_counter = Counter()
    no_titleblock = []
    for s in sheets:
        w, h = su.sheet_size_mm(doc, s)
        if w is None:
            no_titleblock.append(s.SheetNumber)
            continue
        size_counter[(round(w, 1), round(h, 1))] += 1

    rows = []
    for (w, h), n in size_counter.most_common():
        rows.append([
            "{0} x {1} mm".format(w, h),
            n,
            "OK - A3" if su.is_a3(w, h) else "NOT A3",
        ])
    output.print_table(rows, columns=["Size", "Sheets", "Verdict"])

    if no_titleblock:
        output.print_md("> **No title block instance on:** `{0}`"
                        .format(", ".join(sorted(no_titleblock))))

    all_a3 = bool(size_counter) and all(su.is_a3(w, h) for (w, h) in size_counter.keys())
    if all_a3:
        output.print_md("-> All sheets are A3. The sheet constants in `config.py` "
                        "can be used as-is.")
    else:
        output.print_md("-> Non-A3 sheets present. **Update `SHEET_W` / `SHEET_H` in "
                        "`lib/ezsheets/config.py`** - every other script follows from there.")


# ---------------------------------------------------------------
# 3. Standard detail sheet coverage
# ---------------------------------------------------------------
output.print_md("## 3. Standard detail sheets (17 shared across 5 BC sets)")

existing = su.sheets_by_number(doc)
rows = []
missing = []
for num, name in config.STANDARD_DETAIL_SHEETS:
    if num in existing:
        rows.append([num, name, "present", existing[num].Name])
    else:
        rows.append([num, name, "MISSING", "-"])
        missing.append(num)
output.print_table(rows,
                   columns=["Sheet no.", "Standard name", "Status", "Name in this project"])

output.print_md("**{0} of {1} missing.**"
                .format(len(missing), len(config.STANDARD_DETAIL_SHEETS)))
if missing:
    output.print_md("Missing: `{0}`".format(", ".join(missing)))
    output.print_md("-> Use **2 Sheets > Clone Details** to bring them in from the library file.")


# ---------------------------------------------------------------
# 4. View type on detail sheets  -- answers Q-02
# ---------------------------------------------------------------
output.print_md("## 4. What view type sits on the standard detail sheets? (Q-02)")

type_counter = Counter()
sample = {}
for num, _ in config.STANDARD_DETAIL_SHEETS:
    sheet = existing.get(num)
    if sheet is None:
        continue
    for vp in su.viewports_on(doc, sheet):
        v = doc.GetElement(vp.ViewId)
        if v is None:
            continue
        vt = str(v.ViewType)
        type_counter[vt] += 1
        sample.setdefault(vt, "'{0}' on {1}".format(v.Name, num))

if not type_counter:
    output.print_md("> No standard detail sheets in this project - skipped.")
else:
    rows = [[vt, n, sample[vt]] for vt, n in type_counter.most_common()]
    output.print_table(rows, columns=["View type", "Count", "Example"])
    # ViewType enum reports "DraftingView", so match on a substring, not a key
    drafting = sum(n for vt, n in type_counter.items() if "Drafting" in vt)
    other = sum(type_counter.values()) - drafting
    if drafting and not other:
        output.print_md("-> All {0} are **Drafting Views**, so "
                        "`ElementTransformUtils.CopyElements` can clone them across "
                        "files (the same mechanism Revit's own 'Insert Views from "
                        "File' uses). The clone strategy holds.".format(drafting))
    elif drafting:
        output.print_md("-> {0} Drafting Views plus {1} of other types. Only the "
                        "drafting views can be cloned; the rest need a separate "
                        "strategy.".format(drafting, other))
    else:
        output.print_md("-> No Drafting Views found. The clone script needs a "
                        "different strategy - please report this result.")


# ---------------------------------------------------------------
# 5. What carries the note text?  -- answers Q-06
# ---------------------------------------------------------------
output.print_md("## 5. What carries the note text on sheets? (Q-06)")

note_stats = Counter()
for s in sheets:
    n_text = FilteredElementCollector(doc, s.Id) \
        .OfClass(TextNote).WhereElementIsNotElementType().GetElementCount()
    if n_text:
        note_stats["TextNote placed on sheet"] += n_text
    for vp in su.viewports_on(doc, s):
        v = doc.GetElement(vp.ViewId)
        if v is None:
            continue
        if v.ViewType == ViewType.Legend:
            note_stats["Legend view"] += 1
        elif isinstance(v, ViewSchedule):
            note_stats["Schedule"] += 1

if not note_stats:
    output.print_md("> No separate text carrier detected - the notes are most likely "
                    "embedded in the title block family. Click a note in Revit and check "
                    "the category shown in the status bar.")
else:
    rows = [[k, v] for k, v in note_stats.most_common()]
    output.print_table(rows, columns=["Carrier", "Count"])
    top = note_stats.most_common(1)[0][0]
    if top.startswith("Legend"):
        output.print_md("-> Notes are mostly **Legend views**. That is the easiest case "
                        "to automate: a legend can be placed on many sheets, so note "
                        "insertion becomes `Viewport.Create(sheet, legendViewId)` plus a "
                        "fixed position from the region rules - no text handling at all.")
    elif top.startswith("TextNote"):
        output.print_md("-> Notes are mostly **TextNotes placed on sheets**. Insertion "
                        "means creating TextNote elements, so the full note text has to "
                        "live in the rules workbook.")
    output.print_md("-> Record the dominant carrier under **Q-06**.")


# ---------------------------------------------------------------
# 6. Summary
# ---------------------------------------------------------------
output.print_md("---")
output.print_md("## Next steps")

steps = ["Copy the findings from sections 1, 4 and 5 into the 'Open questions' "
         "sheet of the rules workbook."]

if sheets and not all_a3:
    steps.append("**Section 2 found non-A3 sheets** - update `SHEET_W` / `SHEET_H` "
                 "in `lib/ezsheets/config.py` before running anything that writes.")

if missing:
    steps.append("Run **2. Sheets > Clone Details** to bring in the {0} missing "
                 "standard detail sheet(s).".format(len(missing)))
else:
    steps.append("All 17 standard detail sheets are present, so there is nothing "
                 "to clone here. This project can serve as the **source file** "
                 "when cloning into a new project.")

steps.append("Run **3. Layout > Measure Layout** on the elevation and detail sheets "
             "to calibrate GAP_X / GAP_Y in `config.py`.")

for i, s in enumerate(steps, start=1):
    output.print_md("{0}. {1}".format(i, s))
