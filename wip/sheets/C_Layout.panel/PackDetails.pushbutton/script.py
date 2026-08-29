# -*- coding: utf-8 -*-
"""Pack Details -- re-lay the viewports on a detail sheet into a column grid.

Runs the measured layout model:
  - column pitch 42 mm, compressing to 31 mm only when a sheet is tight
  - vertical space shared evenly down each column, because the measured gaps
    showed no convention to aim at
  - viewport outlines used directly, since outline = printed extent + title bar
    + 6.096 mm holds for every view type measured

Preview first. Nothing moves until you confirm, and the whole run sits in one
transaction so a single Undo puts everything back.

Scope: sheets whose viewports are all drafting views. Model views are excluded
because their placement interacts with note regions and view titles that this
version does not model yet.
"""

from __future__ import unicode_literals

from Autodesk.Revit.DB import Transaction, ViewDrafting

from pyrevit import forms, revit, script

from ezsheets import config, packing, sheetutils as su

doc = revit.doc
output = script.get_output()
output.set_title("EZbuild - Pack Details")


def detail_sheets():
    """Sheets where every viewport holds a drafting view."""
    result = []
    for sheet in su.all_sheets(doc):
        vps = su.viewports_on(doc, sheet)
        if not vps:
            continue
        views = [doc.GetElement(vp.ViewId) for vp in vps]
        if all(isinstance(v, ViewDrafting) for v in views if v is not None):
            result.append(sheet)
    return result


def read_sheet(sheet):
    """Current viewports with their FULL footprint, in reading order.

    The footprint packed is the view outline union its title bar. The title
    hangs below the view and belongs to the space the viewport occupies; packing
    the view outline alone pushes every title off the bottom of the paper.

    `bx0`/`by0` keep the view outline's own corner, because SetBoxCenter moves
    the view outline, not the footprint. The offset between the two is fixed, so
    the target footprint corner converts back to a box centre exactly.

    Reading order is column-major - down the left column, then the next - which
    is how the measured sheets read.
    """
    origin = su.titleblock_origin_mm(doc, sheet)
    if origin is None:
        return None, None
    entries = []
    for vp in su.viewports_on(doc, sheet):
        v = doc.GetElement(vp.ViewId)
        name = v.Name if v is not None else "?"
        bx0, by0, bx1, by1 = su.viewport_box_mm(vp, origin)
        tx0, ty0, tx1, ty1 = su.viewport_total_box_mm(vp, origin)
        lbox = su.viewport_label_box_mm(vp, origin)
        entries.append({
            "lw": (lbox[2] - lbox[0]) if lbox else 0.0,
            "lh": (lbox[3] - lbox[1]) if lbox else 0.0,
            # key by element id, never by view name - a name is a display
            # label, and matching on it is what silently broke this before
            "vp": vp, "key": su.id_value(vp.Id), "name": name,
            "x0": tx0, "y0": ty0,                # footprint, what we pack
            "w": tx1 - tx0, "h": ty1 - ty0,
            "bw": bx1 - bx0, "bh": by1 - by0,    # view outline, what we move
            "off_x": bx0 - tx0, "off_y": by0 - ty0,
            "has_label": (tx1 - tx0) - (bx1 - bx0) > 0.5
                         or (ty1 - ty0) - (by1 - by0) > 0.5,
        })
    entries.sort(key=lambda e: (round(e["x0"] / 50.0), -e["y0"]))
    return entries, origin


# A viewport moving less than this is treated as already in place.
NO_CHANGE_MM = 2.0


def plan_sheet(sheet):
    """Work out what would happen to one sheet. Returns a dict, never raises."""
    info = {"sheet": sheet, "status": "", "note": "", "entries": None,
            "by_key": None, "origin": None, "columns": 0, "gap_x": 0.0,
            "moved": 0, "max_delta": 0.0}

    entries, origin = read_sheet(sheet)
    if entries is None:
        info["status"] = "skipped"
        info["note"] = "no title block, so there is no reliable paper origin"
        return info

    info["entries"] = entries
    info["origin"] = origin

    items = [(e["key"], e["w"], e["h"]) for e in entries]
    result = packing.pack_grid(items)

    if result.overflow:
        # A sheet holding one viewport has no layout to arrange, whatever its
        # size. Reporting the full-page schedule sheets as failures was a
        # classification mistake, not a packing one - there was never anything
        # for the packer to do on them.
        if len(entries) == 1:
            info["status"] = "single view"
            info["note"] = ("one full-page view, nothing to arrange ({0})"
                            .format(result.reason))
        else:
            info["status"] = "does not fit"
            info["note"] = result.reason
        return info

    bad = packing.overlaps(result)
    if bad or not packing.fits(result):
        info["status"] = "check failed"
        info["note"] = "overlaps={0}".format(bad)
        return info

    by_key = dict((p.key, p) for p in result.placements)

    # Every viewport must come back from the packer. Skipping unmatched ones
    # quietly reported "already tidy, max delta 0.0" for a dozen sheets that had
    # in fact never been compared at all - the worst kind of wrong answer, since
    # it looks like a clean bill of health.
    missing = [e for e in entries if e["key"] not in by_key]
    if missing:
        info["status"] = "check failed"
        info["note"] = ("{0} of {1} viewports were not matched to a placement"
                        .format(len(missing), len(entries)))
        return info

    moved, max_delta = 0, 0.0
    for e in entries:
        p = by_key[e["key"]]
        d = max(abs(p.x0 - e["x0"]), abs(p.y0 - e["y0"]))
        max_delta = max(max_delta, d)
        if d > NO_CHANGE_MM:
            moved += 1

    info.update({"entries": entries, "by_key": by_key, "origin": origin,
                 "columns": result.columns, "gap_x": result.gap_x,
                 "moved": moved, "max_delta": max_delta})
    info["status"] = "ready" if moved else "already tidy"
    return info


def print_sheet_detail(info):
    """Full numbers for one sheet.

    Printed for tidy sheets as well as ones that would move. A dozen sheets
    reporting "max delta 0.0" is either a genuine no-op or a broken measurement,
    and the summary alone cannot tell those apart - the view / label / footprint
    widths side by side can.
    """
    sheet = info["sheet"]
    output.print_md("### {0}  {1}   [{2}]"
                    .format(sheet.SheetNumber, sheet.Name, info["status"]))
    planned = info["by_key"] is not None
    rows = []
    for e in info["entries"]:
        p = info["by_key"][e["key"]] if planned else None
        row = [
            e["name"],
            "{0:.1f} x {1:.1f}".format(e["bw"], e["bh"]),
            "{0:.1f} x {1:.1f}".format(e["lw"], e["lh"]) if e["lw"] else "none",
            "{0:.1f} x {1:.1f}".format(e["w"], e["h"]),
            "{0:.1f} - {1:.1f}".format(e["x0"], e["x0"] + e["w"]),
            "{0:.1f} - {1:.1f}".format(e["y0"], e["y0"] + e["h"]),
        ]
        if planned:
            row += ["({0:.1f}, {1:.1f})".format(p.x0, p.y0),
                    "{0:+.1f}, {1:+.1f}".format(p.x0 - e["x0"], p.y0 - e["y0"]),
                    "c{0} r{1}".format(p.col, p.row)]
        else:
            row += ["-", "-", "-"]
        rows.append(row)
    output.print_table(rows, columns=["View", "View box", "Title box",
                                      "Footprint", "Now X span", "Now Y span",
                                      "Proposed", "Delta", "Cell"])
    if not planned:
        output.print_md("Usable area is X {0:.1f}-{1:.1f}, Y {2:.1f}-{3:.1f}. "
                        "Compare the spans above against it to see how far past "
                        "the edge the content actually runs."
                        .format(config.CONTENT_X0, config.CONTENT_X1,
                                config.CONTENT_Y0, config.CONTENT_Y1))
        return
    widest = max(e["w"] for e in info["entries"])
    tallest = max(e["h"] for e in info["entries"])
    output.print_md("{0} column(s) at {1:.1f} mm pitch, {2} of {3} viewports move. "
                    "Widest footprint {4:.1f} mm of {5:.1f} usable, tallest {6:.1f} "
                    "of {7:.1f}."
                    .format(info["columns"], info["gap_x"], info["moved"],
                            len(info["entries"]), widest, config.CONTENT_W,
                            tallest, config.CONTENT_H))
    dominated = [e["name"] for e in info["entries"]
                 if e["lw"] > e["bw"] + 0.5]
    if dominated:
        output.print_md("> **Title wider than the view** on {0} of {1}: {2}. "
                        "The footprint is set by the title rule, not the drawing, "
                        "which inflates how much room the viewport appears to need."
                        .format(len(dominated), len(info["entries"]),
                                ", ".join(dominated)))


def apply_plans(plans):
    applied = 0
    t = Transaction(doc, "Pack detail sheets")
    t.Start()
    try:
        for info in plans:
            origin = info["origin"]
            for e in info["entries"]:
                p = info["by_key"][e["key"]]
                # p is the target FOOTPRINT corner; SetBoxCenter moves the view
                # outline, so shift by the fixed offset between the two first
                box_x0 = p.x0 + e["off_x"]
                box_y0 = p.y0 + e["off_y"]
                cx = origin[0] + box_x0 + e["bw"] / 2.0
                cy = origin[1] + box_y0 + e["bh"] / 2.0
                su.set_viewport_center_mm(e["vp"], cx, cy)
                applied += 1
        t.Commit()
    except Exception:
        t.RollBack()
        raise
    return applied


def main():
    sheets = detail_sheets()
    if not sheets:
        forms.alert("No detail sheets found - this tool only handles sheets "
                    "whose viewports are all drafting views.", exitscript=True)

    labels = dict(("{0}  {1}".format(s.SheetNumber, s.Name), s)
                  for s in sorted(sheets, key=lambda x: x.SheetNumber))
    picked = forms.SelectFromList.show(
        sorted(labels.keys()),
        title="Select detail sheets to preview  ({0} found - Ctrl+A selects all)"
              .format(len(labels)),
        multiselect=True, button_name="Preview")
    if not picked:
        script.exit()

    output.print_md("# Pack Details - preview")
    output.print_md("Region X {0}-{1}, Y {2}-{3} mm. **Nothing has been moved yet.**"
                    .format(config.CONTENT_X0, config.CONTENT_X1,
                            config.CONTENT_Y0, config.CONTENT_Y1))

    infos = [plan_sheet(labels[label]) for label in sorted(picked)]

    # summary first - with 25 sheets this is the part worth reading
    output.print_md("## Summary")
    rows = []
    for i in infos:
        rows.append([
            i["sheet"].SheetNumber,
            i["sheet"].Name,
            len(i["entries"]) if i["entries"] else "-",
            i["columns"] or "-",
            i["moved"] or "-",
            "{0:.1f}".format(i["max_delta"]) if i["entries"] else "-",
            i["status"],
            i["note"],
        ])
    output.print_table(rows, columns=["Sheet", "Name", "Views", "Cols", "Moves",
                                      "Max delta", "Status", "Note"])

    ready = [i for i in infos if i["status"] == "ready"]
    tidy = [i for i in infos if i["status"] == "already tidy"]
    single = [i for i in infos if i["status"] == "single view"]
    problem = [i for i in infos if i["status"] in ("does not fit", "check failed",
                                                   "skipped")]
    output.print_md("**{0} ready, {1} already tidy, {2} single-view, "
                    "{3} cannot be arranged.**"
                    .format(len(ready), len(tidy), len(single), len(problem)))
    if tidy:
        output.print_md("*Already tidy* means every viewport is within {0:.0f} mm "
                        "of where the packer would put it - usually because a "
                        "previous run already packed the sheet."
                        .format(NO_CHANGE_MM))
    if single:
        output.print_md("*Single view* sheets hold one full-page view. There is no "
                        "layout to arrange on them, so they are left alone rather "
                        "than counted as failures.")
    if problem:
        output.print_md("*Cannot be arranged* sheets are never touched. Fitting them "
                        "would need a smaller view scale, which is a design decision "
                        "rather than a layout one. Where a note names a gap, lowering "
                        "`PACK['GAP_X_MIN']` in `config.py` to that value would let "
                        "the sheet pack.")

    # Incidental QA: viewports whose footprint runs into the title block strip or
    # off the paper. Found while investigating why sheets would not pack, but it
    # matters on its own - content sitting under the title block is a drafting
    # problem regardless of how the sheet is arranged.
    intruders = []
    for i in infos:
        for e in (i["entries"] or []):
            x1, y1 = e["x0"] + e["w"], e["y0"] + e["h"]
            if x1 > config.TITLEBLOCK_X + 0.5:
                intruders.append([i["sheet"].SheetNumber, e["name"], "title block",
                                  "{0:.1f} mm past X {1:.0f}"
                                  .format(x1 - config.TITLEBLOCK_X,
                                          config.TITLEBLOCK_X)])
            if e["x0"] < -0.5 or y1 > config.SHEET_H + 0.5 or e["y0"] < -0.5:
                intruders.append([i["sheet"].SheetNumber, e["name"], "paper edge",
                                  "X {0:.1f}-{1:.1f}  Y {2:.1f}-{3:.1f}"
                                  .format(e["x0"], x1, e["y0"], y1)])
    if intruders:
        output.print_md("## Content outside the drawing area")
        output.print_table(intruders,
                           columns=["Sheet", "View", "Crosses", "By how much"])
        output.print_md("These are flagged for review, not touched. Packing cannot "
                        "fix them - the views are larger than the space, so the "
                        "remedy is a smaller view scale or a redrawn detail.")

    measurable = ready + tidy
    if measurable:
        output.print_md("## Per-sheet numbers")
        for i in measurable:
            print_sheet_detail(i)

    if problem:
        output.print_md("## Sheets that cannot be arranged - current geometry")
        for i in problem:
            if i["entries"]:
                print_sheet_detail(i)

    if not ready:
        output.print_md("Nothing to apply.")
        script.exit()

    # let the user drop any sheet that looks wrong, rather than all-or-nothing
    apply_labels = dict(
        ("{0}  {1}   ({2} moves, max {3:.0f} mm)".format(
            i["sheet"].SheetNumber, i["sheet"].Name, i["moved"], i["max_delta"]), i)
        for i in ready)
    chosen = forms.SelectFromList.show(
        sorted(apply_labels.keys()),
        title="Which sheets should be applied?  (Ctrl+A selects all)",
        multiselect=True, button_name="Apply")
    if not chosen:
        output.print_md("Cancelled - nothing was changed.")
        script.exit()

    plans = [apply_labels[c] for c in chosen]
    applied = apply_plans(plans)

    output.print_md("## Applied")
    output.print_md("{0} viewport(s) repositioned across {1} sheet(s). "
                    "One transaction - a single Undo reverses the whole run."
                    .format(applied, len(plans)))
    output.print_md("Spot-check a few sheets before saving: `{0}`"
                    .format(", ".join(i["sheet"].SheetNumber for i in plans[:8])))


if __name__ == "__main__":
    main()
