# -*- coding: utf-8 -*-
"""Measure Layout -- read-only, changes nothing.

Turns sheets a designer laid out by hand into numbers, so the packing
parameters in config.PACK can be calibrated against real work.

Three things this script learned the hard way, all of them still load-bearing:

1. A sheet's own (0,0) is arbitrary. Coordinates are reported relative to the
   title block instance, the only reliable anchor for real paper coordinates.

2. Gaps only mean something between viewports that actually face each other.
   An earlier row-band approach reported -14.8 mm between two viewports sitting
   diagonally opposite, which never touch.

3. Gaps between different kinds of neighbour are different parameters. The
   distance between two details in a grid and the distance from a legend to the
   main view are unrelated numbers; pooling them buried a clean 42 mm column
   pitch under unrelated samples. Statistics are therefore reported per pair
   type, and only same-type non-legend pairs feed GAP_X / GAP_Y.

On the viewport outline itself: Viewport.GetBoxOutline() equals the printed
extent plus exactly 6.096 mm (0.01 ft padding per side), for every view type
measured. The outline is trustworthy, so place -> measure -> reposition needs no
correction. The "Measure delta" column below exists to verify that claim on new
projects, not to discount any measurement.
"""

from __future__ import unicode_literals

from pyrevit import forms, revit, script

from ezsheets import config, sheetutils as su

doc = revit.doc
output = script.get_output()
output.set_title("EZbuild - Measure Layout")

# Pair types that describe a note/legend block rather than a view grid.
NOTE_TYPES = ("Legend",)


def main():
    sheets = su.all_sheets(doc)
    if not sheets:
        forms.alert("This project has no sheets.", exitscript=True)

    labels = dict(("{0}  {1}".format(s.SheetNumber, s.Name), s)
                  for s in sorted(sheets, key=lambda x: x.SheetNumber))
    picked = forms.SelectFromList.show(
        sorted(labels.keys()), title="Select sheets to measure (multi-select)",
        multiselect=True, button_name="Measure")
    if not picked:
        script.exit()

    output.print_md("# Layout Measurements")
    output.print_md("Coordinates are millimetres from the **bottom-left corner of "
                    "the title block**. Usable area X {0}-{1}, Y {2}-{3}."
                    .format(config.CONTENT_X0, config.CONTENT_X1,
                            config.CONTENT_Y0, config.CONTENT_Y1))

    gaps_x = {}     # pair-type key -> [gap, ...]
    gaps_y = {}
    no_anchor = []
    padding_samples = []

    for label in sorted(picked):
        sheet = labels[label]
        vps = su.viewports_on(doc, sheet)
        output.print_md("---")
        output.print_md("## {0}  {1}   ({2} viewport(s))"
                        .format(sheet.SheetNumber, sheet.Name, len(vps)))
        if not vps:
            continue

        origin = su.titleblock_origin_mm(doc, sheet)
        if origin is None:
            no_anchor.append(sheet.SheetNumber)
            output.print_md("> No title block on this sheet - coordinates below are "
                            "raw sheet space and cannot be compared across sheets.")
            origin = (0.0, 0.0)

        boxes = []
        for vp in vps:
            v = doc.GetElement(vp.ViewId)
            name = v.Name if v is not None else "?"
            vtype = str(v.ViewType) if v is not None else "?"
            x0, y0, x1, y1 = su.viewport_box_mm(vp, origin)
            cw, ch = su.viewport_content_size_mm(doc, vp)
            lw, lh = su.viewport_label_size_mm(vp)
            delta = None
            if cw is not None and ch is not None:
                # subtract the title bar before comparing - it lives in the
                # outline but in no crop box
                delta = max((x1 - x0) - max(cw, lw), (y1 - y0) - ch - lh)
                if lw <= 0.01 and lh <= 0.01:
                    padding_samples.append(delta)
            boxes.append({
                "name": name, "type": vtype,
                "x0": x0, "y0": y0, "x1": x1, "y1": y1,
                "cw": cw, "ch": ch, "lw": lw, "lh": lh, "delta": delta,
            })

        rows = []
        for b in sorted(boxes, key=lambda b: (-b["y1"], b["x0"])):
            rows.append([
                b["name"], b["type"],
                "{0:.1f}".format(b["x0"]), "{0:.1f}".format(b["y0"]),
                "{0:.1f}".format(b["x1"]), "{0:.1f}".format(b["y1"]),
                "{0:.1f} x {1:.1f}".format(b["x1"] - b["x0"], b["y1"] - b["y0"]),
                "{0:.1f} x {1:.1f}".format(b["cw"], b["ch"])
                if b["cw"] is not None else "-",
                "{0:.1f} x {1:.1f}".format(b["lw"], b["lh"])
                if b["lw"] else "none",
                "{0:.1f}".format(b["delta"]) if b["delta"] is not None else "-",
            ])
        output.print_table(
            rows,
            columns=["View name", "Type", "X0", "Y0", "X1", "Y1",
                     "Outline W x H", "Printed W x H", "Title bar", "Residual"])

        off_paper = [b["name"] for b in boxes
                     if b["x0"] < -1 or b["y0"] < -1
                     or b["x1"] > config.SHEET_W + 1
                     or b["y1"] > config.SHEET_H + 1]
        if off_paper:
            output.print_md("> **{0} outline(s) fall outside the {1} x {2} mm paper**: "
                            "{3}."
                            .format(len(off_paper), config.SHEET_W, config.SHEET_H,
                                    ", ".join(off_paper)))

        h_gaps, v_gaps = su_neighbour_gaps(boxes)
        for gaps, axis, bucket in ((h_gaps, "Horizontal", gaps_x),
                                   (v_gaps, "Vertical", gaps_y)):
            if not gaps:
                continue
            output.print_md("  {0} gaps between adjacent viewports:".format(axis))
            for g, pair, key in sorted(gaps):
                output.print_md("    {0:.1f} mm   [{1}]   {2}".format(g, key, pair))
                bucket.setdefault(key, []).append(g)

    # -- summary ------------------------------------------------
    output.print_md("---")
    output.print_md("## Suggested parameter values")

    if no_anchor:
        output.print_md("**{0} sheet(s) had no title block**: `{1}`"
                        .format(len(no_anchor), ", ".join(no_anchor)))

    expected = config.VIEWPORT_OUTLINE_PADDING_MM
    if padding_samples:
        lo, hi = min(padding_samples), max(padding_samples)
        if hi - lo <= 2.5 and abs(median(padding_samples) - expected) <= 2.5:
            output.print_md("**Outline model check: passed.** Across {0} title-less "
                            "viewports the residual held at {1:.1f}-{2:.1f} mm against "
                            "an expected {3:.1f}. So `outline = printed extent + title "
                            "bar + {3:.1f} mm` holds, and GetBoxOutline is a reliable "
                            "footprint to pack against."
                            .format(len(padding_samples), lo, hi, expected))
        else:
            output.print_md("**Outline model check: residual {0:.1f}-{1:.1f} mm** across "
                            "{2} title-less viewports, expected {3:.1f}. Worth a look, "
                            "though the gap numbers are unaffected - they come from the "
                            "outlines directly."
                            .format(lo, hi, len(padding_samples), expected))
    else:
        output.print_md("Every viewport measured carries a view title, so the outline "
                        "padding constant could not be isolated on these sheets.")
    output.print_md("The **Title bar** column shows why outline and printed extent "
                    "differ: the view title sits inside the outline but inside no crop "
                    "box, and its rule can be set wider than the view. Viewports reading "
                    "`none` have the title switched off - on detail sheets here the "
                    "titles are ordinary text drawn inside the drafting view instead.")

    output.print_md("### Horizontal gaps by pair type")
    report_by_type("GAP_X", gaps_x)
    output.print_md("### Vertical gaps by pair type")
    report_by_type("GAP_Y", gaps_y)

    output.print_md("Only same-type, non-legend pairs should feed `PACK['GAP_X']` and "
                    "`PACK['GAP_Y']` in `lib/ezsheets/config.py`. Legend pairs describe "
                    "the note region instead - record those in the region rules.")


def su_neighbour_gaps(boxes, overlap_ratio=0.5, tol=0.5):
    """Gaps between genuinely adjacent viewports, tagged with the pair type.

    Returns (horizontal, vertical); each entry is (gap_mm, "a -> b", pair_key).
    Two boxes are neighbours only when they overlap on the perpendicular axis by
    more than overlap_ratio of the smaller extent AND nothing sits between them.
    """
    h_gaps, v_gaps = [], []
    n = len(boxes)
    for i in range(n):
        for j in range(n):
            if i == j:
                continue
            a, b = boxes[i], boxes[j]
            key = pair_key(a["type"], b["type"])
            pair = "{0} -> {1}".format(a["name"], b["name"])

            ov = span_overlap(a["y0"], a["y1"], b["y0"], b["y1"])
            shorter = min(a["y1"] - a["y0"], b["y1"] - b["y0"])
            if shorter > 0 and ov / shorter >= overlap_ratio \
                    and b["x0"] >= a["x1"] - tol:
                if not blocked_between(boxes, i, j, "x", tol):
                    h_gaps.append((round(b["x0"] - a["x1"], 1), pair, key))

            ov = span_overlap(a["x0"], a["x1"], b["x0"], b["x1"])
            narrower = min(a["x1"] - a["x0"], b["x1"] - b["x0"])
            if narrower > 0 and ov / narrower >= overlap_ratio \
                    and b["y0"] >= a["y1"] - tol:
                if not blocked_between(boxes, i, j, "y", tol):
                    v_gaps.append((round(b["y0"] - a["y1"], 1), pair, key))

    return h_gaps, v_gaps


def span_overlap(a0, a1, b0, b1):
    return min(a1, b1) - max(a0, b0)


def blocked_between(boxes, i, j, axis, tol):
    """True when a third viewport sits in the corridor between boxes i and j."""
    a, b = boxes[i], boxes[j]
    lo, hi = (axis + "1", axis + "0")
    other = "y" if axis == "x" else "x"
    for k in range(len(boxes)):
        if k == i or k == j:
            continue
        c = boxes[k]
        if c[axis + "0"] >= a[lo] - tol and c[axis + "1"] <= b[hi] + tol \
                and span_overlap(a[other + "0"], a[other + "1"],
                                 c[other + "0"], c[other + "1"]) > 0:
            return True
    return False


def pair_key(type_a, type_b):
    """Order-independent label for a neighbour pair, e.g. 'Drafting-Drafting'."""
    a = type_a.replace("View", "") or type_a
    b = type_b.replace("View", "") or type_b
    return "-".join(sorted((a, b)))


def report_by_type(name, buckets):
    if not buckets:
        output.print_md("No samples.")
        return
    for key in sorted(buckets, key=lambda k: -len(buckets[k])):
        values = sorted(buckets[key])
        is_note = any(t in key for t in NOTE_TYPES)
        same_type = len(set(key.split("-"))) == 1
        output.print_md("**{0}** - {1} sample(s): {2}".format(key, len(values), values))

        if is_note:
            output.print_md("   -> Note/legend pair. This is a region boundary, not a "
                            "grid gap. Do not feed it into {0}.".format(name))
            continue
        if not same_type:
            output.print_md("   -> Mixed view types. Treat with care; grid spacing "
                            "conventions usually apply within one view type.")

        lo, hi, members = dominant_cluster(values, tolerance=6.0)
        if len(members) >= 3 and len(members) < len(values):
            output.print_md("   -> **{0} = {1:.0f} mm.** {2} of {3} cluster in "
                            "{4:.1f}-{5:.1f}; the rest are outliers. A habitual spacing "
                            "shows up as a cluster, not as the minimum."
                            .format(name, median(members), len(members),
                                    len(values), lo, hi))
        elif len(members) >= 3:
            output.print_md("   -> **{0} = {1:.0f} mm** (all samples within {2:.1f} mm)."
                            .format(name, median(members), hi - lo))
        else:
            output.print_md("   -> No cluster: {0:.1f}-{1:.1f} mm with no repeated "
                            "value. This spacing is leftover space, not a convention - "
                            "the packer should distribute it rather than target it."
                            .format(min(values), max(values)))


def dominant_cluster(sorted_values, tolerance):
    """Largest run of values spanning no more than `tolerance`."""
    best = (sorted_values[0], sorted_values[-1], sorted_values)
    best_n = 0
    for i in range(len(sorted_values)):
        j = i
        while j + 1 < len(sorted_values) and \
                sorted_values[j + 1] - sorted_values[i] <= tolerance:
            j += 1
        if j - i + 1 > best_n:
            best_n = j - i + 1
            best = (sorted_values[i], sorted_values[j], sorted_values[i:j + 1])
    return best


def median(values):
    s = sorted(values)
    n = len(s)
    if n == 0:
        return 0.0
    if n % 2:
        return s[n // 2]
    return (s[n // 2 - 1] + s[n // 2]) / 2.0


if __name__ == "__main__":
    main()
