# EZTable — design notes

Draw an Excel worksheet into a Revit drafting view with its styling intact,
reproducing borders, shading and text with DetailLine + FilledRegion + TextNote.

Scope implemented: phases **1 + 2 + 3** of the spec. All four reference sheets
(`Summary` / `Part1` / `Building High` / `Print A4`) pass on real files.

> Module paths in this document (`lib/eztable/...`) are relative to
> `pyrevit/EZbuild.extension/`. The three measured Revit traps and the text size
> calibration are properties of the Revit API, not of the host language, so they
> apply equally to the C# add-in in `revit-addin/EZTable/` — its
> `Utils/Geometry.cs` is a port of `geometry.py` with the constants matching one
> for one. The two sides are mirrored by hand: change one, change the other.

## Important: engine choice — no CPython, no openpyxl

The original spec assumed pyRevit's CPython engine plus openpyxl. **That route
does not work on Revit 2025+.**

Measured on pyRevit 6.4.0 + Revit 2026 (.NET 8), the log says:

```
cpython engines dict: {
  CPY3123 (netfx) | Kernel: CPython | Version: 3123 | Runtime: False
  | Path: "...\bin\cengines\CPY3123\python312.dll"
}
Building on IronPython engine: 2712
```

`bin\netcore\engines\` contains only `IPY2712PR` and `IPY342` — **no CPython
engine at all**. The registered `CPY3123` is the .NET Framework build, with
`Runtime: False`. A script carrying `#! python3` throws during engine startup:

```
The input string '3.12.3' was not in a correct format.
```

What appears is Revit's native "Command Failure for External Command" dialog,
not pyRevit's traceback window — which says it died before Python ever started.

**Every script in this extension therefore carries no shebang and runs on the
default IronPython 2.7.12 engine**, with the parsing layer handled by the
bundled `xlsxlite.py` (a zero-dependency OOXML reader) instead of openpyxl. As a
side effect `lib` dropped from 3MB to 140KB, and future Revit or pyRevit version
changes will not get stuck on engine problems again.

## Installation

See the [README](../README.md#installation) — register the repository's
`pyrevit/` directory, i.e. the **parent** of `EZbuild.extension`.

No third-party dependencies, no pip, no CPython engine.

## Branding — the EZbuild design language

Icon colours are taken from the EZbuild Design System
(`claude.ai/design/p/88b2eaa2…`):

| Role | Value | Use |
|---|---|---|
| Primary blue | `#0F76F5` | logo square, emphasis text, icon ground |
| Ink black | `#050B1C` | headings |
| Body grey | `#4C5156` | body text |
| Background | `#F8F9FB` | page ground |
| Blueprint lines | `#4B7DB9` / `#D9DFEB` | line-art motif |

The visual language follows the logo: **a blue rounded square with white line
art inset**. All three buttons share the same table body and are distinguished
by a white badge at the lower right (arrow / circular arrow / broom).

Icons are drawn on the principle that they must still read at 32px — large
blocks of colour, thick strokes, at most three elements. `dev/mkicons2.py` is
the generator script; change the colours and re-run it.

## Buttons

| Button | What it does |
|---|---|
| **Import Excel** | pick an xlsx, pick a sheet, create a 1:1 drafting view, draw it, stamp the view with its source |
| **Refresh** | compare the source file's MD5 and redraw the tables that changed; view ids are preserved so sheet viewports stay valid |
| **Cleanup** | delete the unused `EZ_*` / `XL_*` types older versions left behind |

**All UI strings are English.**

### View naming

`VIEW_NAME_TEMPLATE` in `config.py`, default `'Table'`. Two placeholders are
supported:

```python
VIEW_NAME_TEMPLATE = 'Table'              # -> Table, Table (1), Table (2) ...
# VIEW_NAME_TEMPLATE = 'Table - {sheet}'  # -> Table - Summary
# VIEW_NAME_TEMPLATE = '{file} {sheet}'   # -> Planing plan Summary
```

A name already in use gets a `(1)` `(2)` suffix automatically.

### Fitting an over-wide table on to A3

Changing the view scale is the wrong move — text size is **fixed on paper**, so
as soon as the view scales, text and cells stop matching and the layout falls
apart. The right move is to **split by column and stack downwards**, keeping
every block at 1:1.

```python
MAX_TABLE_WIDTH_MM = 380.0     # usable width of a landscape A3 minus the title block; 0 = no splitting
BLOCK_GAP_MM = 10.0            # vertical gap between blocks
REPEAT_LEADING_COLS = 1        # repeat the first N columns (row headers) in each block
```

Cut points **prefer column boundaries not crossed by a merged cell** —
splitting through the middle of a merged region cuts that cell's text in half.
Only when no clean cut point exists is one forced, with a warning recorded.

**Repeated row headers are dropped automatically.** Some sheets already carry a
second copy of the row headers partway across (column V of `Part1` is a second
`LOT RC.`), and repeating them again would produce two identical headers side by
side. The test is "no conflict and some overlap": no row where both columns hold
a value and the values differ, and at least one row where both hold the same
value. An exact-match test is too strict — column V only fills in LOT1~LOT3 and
Pre-Construction, leaving the other rows blank.

How `Part1` (549mm) splits at different limits:

| Limit | Result |
|---|---|
| off | 1 block, A–AD, 549mm — will not fit A3 |
| **380mm** | **2 blocks: A–U (376mm) / A+V–AD (198mm)** |
| 260mm | 3 blocks: A–J / A+K–U / A+V–AD |
| 190mm | 4 blocks |

`A+` marks the repeated row-header column. Stacked, Part1 becomes
376 × 192mm and fits A3.

### When the output window appears

`REPORT_MODE` in `config.py`:

| Value | Behaviour |
|---|---|
| `'auto'` (default) | only when there are **warnings** or **text that does not fit** |
| `'always'` | every time, with the full report |
| `'off'` | never |

A finished import already announces itself by switching to the new view, so
normally no window is needed. Notes such as "skipped hidden rows" or "range
taken from print_area" are **informational** and do not open the window;
`#DIV/0!`, unrecognised border styles and missing types count as warnings.

Measured on this project's four sheets, `Summary` / `Building High` /
`Print A4` import in **complete silence**; only `Part1` opens the window,
because its source really does contain 20 `#DIV/0!` cells.

### What Cleanup deletes

It scans every text type, filled region type, line style subcategory and line
pattern whose name starts with `EZ_` or `XL_`, and **deletes only those no
element uses**.
Anything still in use is listed but never touched, so no elements are taken down
with it.

`EZ_` is the current prefix; `XL_` dates from when the extension was called
XLTable. Both are scanned, because clearing out those legacy types is the whole
point of the button — this is how the `XL_Arial_7_000000`, `XL_Fill_D9D9D9` and
`XL_Thin` types left by versions before v0.4 get removed.

The prefixes only cover fully-automatic mode. When the config points at existing
project standards the generated names follow those instead, so
`config.is_derived_text_name()` / `is_generated_fill_name()` are consulted as
well: a name is "ours" when it is the base name carrying a different size token,
uppercase modifiers, or both (`2.6mm Arial`, `2.1mm Arial BOLD RED`).
`GREY_FILL_TYPE_NAME`, `BASE_TEXT_TYPE_NAME` and every name in
`PROTECTED_TEXT_TYPE_NAMES` are excluded — the last of these because a type that
differs from the base only in its size token is indistinguishable from a resized
copy, which is exactly what the project's own `2.0mm Arial` became when the base
moved to `2.1mm Arial`.

## Drafting standards — `lib/eztable/config.py`

This file is the one you edit; no other module needs touching. **Restart Revit**
afterwards — under rocketmode the modules are cached.

```python
USE_EXISTING_LINE_STYLES = True
LINE_STYLE_NAMES = {
    'thin':   '<Thin Lines>',      # Excel thin / hair / dashed all map here
    'medium': '<Medium Lines>',
    'thick':  '<Wide Lines>',
}

GREY_FILL_TYPE_NAME = 'Fill Grey 192'   # grey shading always uses this
GREY_TOLERANCE = 12                     # RGB spread <= 12 counts as grey

BASE_TEXT_TYPE_NAME = '2.1mm Arial'     # base text type
```

**Types that already exist are never modified.** The `Fill Grey 192` and
`2.1mm Arial` you maintain are only read and copied, never overwritten by this
tool.

Automatically created types follow the same naming form as your own standards:

| Case | Type name |
|---|---|
| Grey shading | `Fill Grey 192` (the one you already have) |
| Coloured shading | `Fill Orange EE822F`, `Fill Blue D9E1F2` |
| Plain black text | `2.1mm Arial` (yours, used directly rather than derived) |
| Bold | `2.1mm Arial Bold` |
| Red | `2.1mm Arial Red E24D4E` |

Derived types have `TEXT_BACKGROUND` forced to Transparent as they are created.
The base type is used as-is for plain black text at the base size, so it is the
one place where the project's own background setting reaches the drawing: an
opaque base type masks the fill and borders under every plain cell while the
derived ones stay transparent. `BASE_TEXT_TYPE_NAME` therefore has to name a
type whose background is Transparent — the reason the default moved from
`2.0mm Arial` to `2.1mm Arial`, the 2.0mm standard being opaque and not ours to
modify.

Set these to `None` for fully automatic behaviour: `EZ_*` types built from
Excel's own fonts, sizes and colours.

### Fit to text — the table adapts to the text

Font size stays fixed at 2.1mm (the most comfortable size on A3); anything that
does not fit **expands the table** rather than shrinking the text. Three steps,
in this order:

1. **Grow columns** — a non-wrapping cell that does not fit widens the columns
   it occupies; a spanning cell shares out the shortfall evenly
2. **Wrap** — cells with `wrapText` set in Excel are wrapped against the final
   column width (using the width table in `metrics.py`, not Revit's automatic
   wrapping, whose width is not controllable precisely enough)
3. **Grow rows** — rows too short for the wrapped result are heightened

```python
WRAP_TEXT = True
FIT_COLUMNS = True
FIT_ROWS = True
MAX_COL_GROWTH = 4.0        # how many times its original width one column may grow
CELL_PADDING_H_MM = 0.8
```

Measured (2.0mm cap height -- the base size at the time these were taken):

| Sheet | Strict 1:1 | After fitting | Grown | Overflow |
|---|---|---|---|---|
| Summary | 78.1 x 97.9 mm, 4 overflows | **84.5 x 97.9** | A +3.94, B +1.24, E +1.26 mm | 0 |
| Part1 | 545.6 x 91.0 mm, 21 overflows | **548.8 x 91.0** | 2 columns | 0 |
| Building High | — | 376.6 x 413.5 | 1 column | 0 |
| Print A4 | — | 189.3 x 414.8 | 6 columns | 0 |

The header row of `Part1` used to squeeze into one long line; it now wraps to
2–4 lines according to column width. `OTHER BUILDING COVERAGE (sqm)` wraps to
four lines, and because that row was already 28.3mm high in Excel, the row
height did not change at all.

Turning all three switches off gives a strict 1:1 copy of Excel's row and column
sizes, with text that does not fit running up to the border. Either way, cells
whose text does not fit are listed in the report.

## Refresh — what to do when the workbook changes

An import stamps the view via **Extensible Storage** with the absolute source
path, worksheet name, file MD5, import time and EZTable version. **Refresh**
compares against that stamp:

```
[changed]         Table        <-  Planing plan.xlsx / Summary
[up to date]      Table (1)    <-  Planing plan.xlsx / Part1
[source missing]  Table (2)    <-  D:\gone.xlsx / Sheet1
```

Multi-select and select-all are both supported. Unchanged tables are skipped
automatically rather than pointlessly redrawn.

**The key point: the view itself is never deleted.** Its id survives, so
viewports already placed on sheets stay valid and do not move — only the
`CurveElement` / `FilledRegion` / `TextNote` inside the view are deleted and
redrawn.

The strategy is clear-and-redraw with no incremental diffing. Inserting a row or
deleting a column in Excel throws every cell mapping out of alignment, which
makes incremental updates a poor trade.

> **Treat an EZTable view as a read-only artifact.** A refresh deletes **every**
> detail line, filled region and text note in the view, including anything you
> added by hand. Put annotation on the sheet, not inside this view.

Views imported before v0.7.0 carry no source stamp, so Refresh cannot recognise
them; they need importing again.

## Modules

| File | Responsibility | Uses Revit API |
|---|---|---|
| `compat.py` | Py2.7 / Py3 compatibility shims | no |
| `xlsxlite.py` | zero-dependency OOXML reader (zip + ElementTree, with a .NET ZipArchive fallback) | no |
| `geometry.py` | unit conversion, row/column default fallbacks, visible grid coordinates, text placement | no |
| `theme.py` | theme1.xml palette parsing, openpyxl-style index mapping `[1,0,2,…]`, tint, indexed palette | no |
| `numfmt.py` | number format rendering (sections, colour markers, percentages, thousands, dates) | no |
| `xlreader.py` | single-pass parse -> list of `CellModel` + warnings | no |
| `plan.py` | `CellModel` -> drawing instructions: border de-duplication and run merging, fill scanline merging, text anchors | no |
| `styles.py` | lookup, creation and caching of LineStyle / FilledRegionType / TextNoteType | yes |
| `renderer.py` | drawing instructions -> DetailLine / FilledRegion / TextNote; view creation | yes |

The first seven modules import neither the Revit API nor any third-party
library, so the geometry and merging algorithms can be validated under plain
CPython without opening Revit.

## Notes on the three algorithms

**Border de-duplication** does not use a coordinate `set`. Borders are
registered on the *edges of the visible grid*: `h_edges[(row_boundary, col)]`
and `v_edges[(col_boundary, row)]`. Each grid edge has exactly one slot, so an
edge shared by two neighbouring cells is naturally only written once; when both
sides define it, the heavier one wins. Inner cells of a merged range never take
part in registration at all, so interior lines are automatically not drawn — no
extra suppression logic needed.

**Run merging** joins consecutive segments of the same style along one boundary
line into a single `Line.CreateBound`.

**Fill merging** is a standard scanline: merge horizontally into strips first,
then merge strips of equal colour and width vertically into blocks.

**Detecting cached values** is more direct than the openpyxl approach: a single
xlsxlite parse yields both `<f>` (the formula) and `<v>` (the cached value), so
cells with a formula but no cached value can simply be counted — no `data_only`
second pass required.

## Where the spec disagrees with reality (verified against the real Planing_plan.xlsx)

**1. Section 8.2 gets the total table height wrong by a unit.** The visible row
heights of Summary in the file: every row is the default 15.0pt except row 2
(18.0pt) and row 17 (19.5pt), for a total of **277.5 pt**.

```
277.5 pt / 72 = 3.854 inches = 0.3212 ft = 97.90 mm
```

The document's `0.3854 ft ≈ 117.5mm` treats inches as feet (one division by 12
missing). **The acceptance criterion in 8.4 should read 78.0mm × 97.9mm.**

**2. Section 8.2 gets the feet values for columns C and D wrong.** The raw
widths stored in the file, against the document's own formula
`px = width×7 + 5`:

| Col | Stored in xlsx | Effective width | Pixels | Actual ft | Document says | |
|---|---|---|---|---|---|---|
| A | 11.42578125 | 11.43 | 84.98 → 85 | 0.0738 | 0.0738 | ✓ |
| B | 9.42578125 | 9.43 | 70.98 → 71 | 0.0616 | 0.0616 | ✓ |
| C | 5.5703125 | 5.57 | 43.99 → 44 | **0.0382** | 0.0378 | ✗ |
| D | 4.7109375 | 4.71 | 37.98 → 38 | **0.0330** | 0.0325 | ✗ |
| E | 7.42578125 | 7.43 | 56.98 → 57 | 0.0495 | 0.0495 | ✓ |

A, B and E agree exactly; C and D do not. Working the document's 0.0378 /
0.0325 backwards gives 43.55px / 37.44px, which are not whole pixels — most
likely a rounding slip during hand calculation. The total width is
**295 px = 0.2561 ft = 78.0 mm**; the document's 0.2552 ft (294 px) is one pixel
short.

The code implements the document's formula but applies `round()` to the pixel
count. The xlsx stores values like `11.42578125`, which work out to 84.98px,
whereas Excel renders a whole 85px. Without rounding, every column is off by a
fraction of a percent and the error accumulates into the total width.

**3. The theme colour index is swapped in pairs, not just the first pair.**
`styles.xml` addresses the palette as Background/Text pairs, and **both** pairs
are transposed relative to the `<a:clrScheme>` element order in theme1.xml:
index 0=lt1, 1=dk1, **2=lt2, 3=dk2**, then the accents in XML order. Handling
only the first pair stays invisible until a workbook actually uses index 2 or 3:
on Planing_plan.xlsx a `theme="2"` fill rendered as `44546A` dark navy instead of
`E7E6E6` light grey, and `theme="3"` text would have rendered near-white on a
white sheet.

**4. The default vertical alignment.** Excel's real default when nothing is set
is **bottom**, not top, and the code implements bottom. Every cell in the
reference sheets is center/center, so this does not affect acceptance.

**Two more small discrepancies between document and file (no implementation
impact):**

- Section 8.3 says rows A9/A11 have "no fill"; in the file they carry an
  explicit white `FFFFFF`. White is skipped rather than turned into a
  FilledRegion anyway, so the result is the same.
- The Summary sheet has **no** print_area and uses dimension instead (which
  happens to be A1:E20). `Print A4` is the one with a print_area (A1:F90), and
  its `defaultColWidth` is `None` — so both fallback paths do get exercised on
  real files.

## Three measured Revit traps (none of them in the spec)

**1. `TEXT_SIZE` is a cap height, not a font size.** This is the worst of them.
Following the spec with `Set(points_to_feet(7))` makes Revit render text with a
**7pt cap height**, corresponding to a font size of 7 / 0.716 = **9.8pt** — 40%
larger than Excel, and the text visibly spills out of its cell.

How it was calibrated: a Revit export was aligned against the known
78.05 x 97.90mm table (measured at 5.561 px/mm horizontally, 5.567 vertically,
so the geometry itself is exact) and the ink height of a pure uppercase `RC`
came out at 2.70mm = 7.65pt (antialiasing included; the true value is about
7.1pt) — confirming TEXT_SIZE == cap height.

The correct call is `revit_text_size_feet(size_pt, font_name)`, which converts
via the font's cap height / em ratio (Arial = 0.7163, so a 7pt font needs
TEXT_SIZE set to 5.014pt).

Two more values calibrated at the same time:

| Quantity | Measured | Used for |
|---|---|---|
| Line pitch (top to top) | 1.60 x TEXT_SIZE (= 1.146 em) | vertical centring of multi-line text |
| Insertion point -> cap top | 0.267 x TEXT_SIZE | Arial's ascender/cap - 1 = 0.264, which agrees |

Vertical centring therefore centres the **block of capitals**, not a block of
font size: `block height = (line count - 1) x line pitch + cap height`, with the
insertion-point gap added once the cap top is known. Measured across all four
sheets — 831 text blocks — vertical overflow is 0.

**2. `FilledRegionType` has no `LineStyleId`.** The spec's
`new_frt.LineStyleId = invisible_lines_style_id` raises
`'FilledRegionType' object has no attribute 'LineStyleId'` on Revit 2026. It has
to be set on the **instance**: call `region.SetLineStyleId(id)` after
`FilledRegion.Create(...)`.

**3. `Category.GetCategory(doc, OST_InvisibleLines)` returns None.** It will not
hand back `<Invisible lines>`. The reliable route is to iterate `GraphicsStyle`
and match on `gs.GraphicsStyleCategory.Id ==
ElementId(BuiltInCategory.OST_InvisibleLines)` — which as a bonus is immune to
Revit's UI language (searching by name breaks on a localised Revit).

## Known trade-offs

- `double` borders are drawn as `medium`, with a warning (the spec permits this).
- Non-solid pattern fills are approximated as solid using the foreground colour,
  with a warning.
- Text rotation is unsupported; rotated text is drawn horizontally after a
  warning.
- `wrapText` does not enable Revit's automatic wrapping — lines break only where
  the cell genuinely contains `\n`.
- Text type backgrounds are set to Transparent; otherwise a TextNote's white
  background covers the cell shading beneath it.
- White (`FFFFFF`) shading creates no FilledRegion — the sheet background is
  already white.
- Greys are only drawn with `GREY_FILL_TYPE_NAME` when their level is within
  `GREY_SNAP_TOLERANCE` of the level in that type's own name. Collapsing every
  grey on to one standard type made light shading read far darker than the
  source: Excel's 230 and 242 both came out at 192.
- With a base text type in play, cap height is scaled by the cell's Excel font
  size relative to `BASE_TEXT_SIZE_PT`. One fixed size makes sheets inconsistent
  with each other — measured on Planing_plan.xlsx, cap height filled 42% of the
  row on Summary (7pt) against 23% on Part1 (9pt), where Excel itself sits near
  36% on both.
