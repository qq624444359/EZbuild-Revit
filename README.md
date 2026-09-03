<p align="center">
  <b>English</b> &nbsp;|&nbsp; <a href="README.zh-CN.md">中文</a>
</p>

<h1 align="center">EZbuild for Revit</h1>

<p align="center">
  <b>Excel tables into Revit — original styling, vector, refreshable.</b><br>
  Pick an xlsx, pick a worksheet, and a 1:1 table appears in Revit.<br>
  Borders, shading, fonts and merged cells all reproduced.
</p>

---

> **EZbuild for Revit** is the Revit-side half of [EZbuild](https://ezbuild.co.nz).
> Everything installs under a single **EZbuild** ribbon tab.
>
> Today one panel ships: **Table**. Sheet layout and a model-level compliance
> check are in [`wip/`](wip/) and are deliberately not loaded yet — see that
> folder's README for why.

## What this solves

Area schedules, material take-offs, room lists — all of it gets calculated in
Excel. Getting it on to a drawing usually means one of:

| The usual way | The problem |
|---|---|
| Paste a screenshot | Blurry when zoomed; change one number and you re-capture it |
| Link an OLE object | Breaks on another machine, and prints unreliably |
| Redraw it by hand in Revit | Two hours the first time, and again every time a number changes |

EZTable takes a fourth route: **it draws the Excel straight into native Revit
elements** — detail lines, filled regions and text notes. Vector, printable,
annotatable, and nothing to break.

## Two implementations, pick one

| | **pyRevit extension** | **Native add-in** |
|---|---|---|
| Directory | [`pyrevit/`](pyrevit/) | [`revit-addin/`](revit-addin/) |
| Language | Python (IronPython 2.7) | C# / .NET |
| Prerequisite | **pyRevit must be installed** | none, it just installs |
| Revit versions | 2026 – 2027 | 2026 – 2027 |
| Features | Import + Refresh + **Cleanup** | Import + Refresh |
| Third-party deps | none | ClosedXML |
| Changing settings | edit `config.py`, restart Revit | edit `EZTable.config`, restart Revit |
| Installing | register one folder | build it yourself, for now |

**How to choose:**

- **Already using pyRevit? Take the pyRevit build.** Easiest to install, and it
  has Cleanup as well.
- **Don't want pyRevit? Take the native build.** Cleanup is the only thing you
  give up.
- The **geometry is identical** in both (same unit conversion, same measured
  text calibration, same border merging, same fit-to-text), so the table they
  draw is the same table.
- **They share one source stamp** — the same Extensible Storage schema GUID — so
  a table imported by one can be refreshed by the other.

> 📌 Both builds put their buttons under the same **EZbuild** ribbon tab, so
> installing them side by side gives you two panels under that name (or two
> tabs sharing it, depending on which loads first — untested, as it needs both
> installed in one Revit). Installing just one is the ordinary case.

## What it does and doesn't handle

The same for both builds:

| ✅ Handled | ❌ Not handled |
|---|---|
| Borders (thin / medium / thick / dashed) | Images, charts, shapes |
| Cell shading, theme colours and tint included | Conditional formatting |
| Font, size, bold, italic, colour | Mixed formatting inside one cell |
| Merged cells | Pivot tables |
| Number formats (thousands, percent, decimals, dates) | Formula recalculation — the cached result is read |
| Alignment and text wrapping | Rotated text (drawn horizontally) |
| Hidden rows and columns (skipped, leaving no gap) | Legacy `.xls` (only `.xlsx`) |
| Over-wide tables split by column and stacked | |
| Columns widened and rows heightened so text fits | |

---

# Installation

## A. pyRevit extension

**Requires**: Revit and [pyRevit](https://github.com/pyrevitlabs/pyRevit).
No Python install, no pip, no third-party libraries.

> Measured on Revit 2026 + pyRevit 6.4.0, running on pyRevit's own IronPython
> engine.

**Step 1 — get the code**

```
git clone https://github.com/qq624444359/EZbuild-Revit.git
```

Or without git: `Code` → `Download ZIP`, and unpack somewhere permanent such as
`D:\EZbuild-Revit`.

**Step 2 — register the `pyrevit` subdirectory with pyRevit**

Register the **`pyrevit` folder inside the repository** — not the repository
root, and not `EZbuild.extension` itself:

```
D:\EZbuild-Revit\
├── pyrevit\                     <- register this level
│   └── EZbuild.extension\
├── revit-addin\
└── docs\
```

From the command line:

```
pyrevit extend D:\EZbuild-Revit\pyrevit
pyrevit reload
```

Or through the UI: pyRevit → Settings → Custom Extension Directories → Add
Folder → pick `D:\EZbuild-Revit\pyrevit` → Save Settings and Reload.

**Step 3 — restart Revit.** An **EZbuild** tab appears on the ribbon.

> 💡 Updating later is just `git pull` — no re-downloading and unpacking.

## B. Native add-in

For now this **has to be built yourself**; there is no packaged installer yet.

**Requires**: Visual Studio 2022 or the .NET SDK, plus the matching Revit
installed locally.

```
git clone https://github.com/qq624444359/EZbuild-Revit.git
cd EZbuild-Revit/revit-addin/EZTable
dotnet build -c Release
```

The project targets **`net8.0-windows`**, which covers both supported Revit
versions — 2026 and 2027 each run on .NET 8.

The Revit API path defaults to `C:\Program Files\Autodesk\Revit 2026`. If you
are building against 2027, or Revit lives elsewhere, **there is no need to edit
the project file** — override on the command line:

```
# build against Revit 2027
dotnet build -c Release -p:RevitVersion=2027

# Revit installed on another drive
dotnet build -c Release -p:RevitApiDir="D:\Autodesk\Revit 2027"
```

When `RevitAPI.dll` cannot be found, the build says so in plain language and
names the argument to pass, rather than emitting a screen of "the type Document
could not be found".

A successful `net8.0-windows` build **automatically** copies the `.addin` and
every `.dll` into `%AppData%\Autodesk\Revit\Addins\<RevitVersion>\`. Restart Revit and an
**EZbuild** tab appears.

To install by hand, drop all of these into
`%AppData%\Autodesk\Revit\Addins\<version>\`:

```
EZTable.addin
EZTable.dll
ClosedXML.dll  DocumentFormat.OpenXml.dll  ExcelNumberFormat.dll
Irony.dll      SixLabors.Fonts.dll         XLParser.dll
```

---

# Using it

The buttons behave the same in both builds. **Cleanup exists only in the pyRevit
build.**

### 📥 Import Excel

1. Pick an `.xlsx` file
2. Pick a worksheet (skipped when there is only one)
3. A 1:1 drafting view is created, the table drawn into it, and the view
   activated

From there it is an ordinary view — drag it on to a sheet like any other.

### 🔄 Refresh

Press this after the workbook changes. Every view imported by EZTable is listed
with its state:

```
[changed]         Table       <-  area schedule.xlsx / Summary
[up to date]      Table (1)   <-  area schedule.xlsx / Part1
[source missing]  Table (2)   <-  D:\deleted.xlsx / Sheet1
```

Select several, or all of them at once. Unchanged tables are skipped
automatically rather than pointlessly redrawn.

**The key point: refreshing does not delete the view.** Its id survives, so
viewports already placed on sheets stay valid and do not move — only the
contents of the view are erased and redrawn.

> ⚠️ **Treat an imported view as a read-only artifact.**
> A refresh deletes **every** detail line, filled region and text note in the
> view, including anything you added by hand. Put comments and leaders on the
> **sheet**, not inside this view.

### 🧹 Cleanup (pyRevit build only)

Generated text types, fill types and line styles pile up in a project over
time. This button finds the ones **no element uses** and deletes them.

It scans **both** prefixes: `EZ_`, which the tool creates now, and `XL_`, left
behind from when this extension was called XLTable. Those legacy types are
exactly what the button exists to clear out.

Anything still in use is listed for you to see but **never touched** — your
elements are never taken down with it.

It also recognises the types generated from your own standards (`2.1mm Arial
BOLD`, `Fill Grey 242`), which is why the base type and the names in
`PROTECTED_TEXT_TYPE_NAMES` are excluded from the scan: after the base moved
from `2.0mm Arial` to `2.1mm Arial`, your `2.0mm Arial` looks exactly like a
resized copy, and it must never be offered for deletion.

---

# Adjusting the common things

Both builds read a plain text file, and both pick up changes on the next Revit
restart — no rebuild required:

| Build | File to edit |
|---|---|
| pyRevit | `pyrevit/EZbuild.extension/lib/eztable/config.py` |
| Native | `EZTable.config`, next to `EZTable.dll` (normally `%AppData%\Autodesk\Revit\Addins\2026\`) |

The native build's config file **does not exist by default** — the build output
contains `EZTable.config.sample`; rename it to `EZTable.config` to activate it.
The rename matters: a `.sample` file is overwritten by the next build, a
`.config` file is not.

Its format is `key = value`, with `#` for comments. Delete a line to fall back
to its default:

```ini
GreyFillTypeName = Fill Grey 192
MaxTableWidthMm  = 380
FitColumns       = true
```

The examples below use the pyRevit form (`config.py`). For the native build,
write the same setting under its PascalCase name in `EZTable.config`; the
meanings are identical.

<details>
<summary><b>The table is too wide for an A3 sheet</b></summary>

<br>

Do not change the view scale. Text size is **fixed on paper**, so the moment the
view scales, text and cells stop matching and the layout falls apart.

The right move is to **split by column and stack downwards**, keeping every
block at 1:1. That is the default behaviour:

```python
MAX_TABLE_WIDTH_MM = 380.0     # max width per block; a landscape A3 minus the title block
BLOCK_GAP_MM = 10.0            # vertical gap between blocks
REPEAT_LEADING_COLS = 1        # repeat the first N columns (row headers); 0 = off
```

A 549mm-wide table splits into two blocks at a 380mm limit (A–U and A+V–AD),
which stack into 376 × 192mm and fit A3.

Cut points **avoid merged cells** where possible — splitting through the middle
of a merged region cuts that cell's text in half. If a repeated row header turns
out to duplicate content already there, it is dropped automatically, so you
never get two identical headers side by side.

Set it to `0` to disable splitting and draw the table full width.
</details>

<details>
<summary><b>Text doesn't fit and spills out of its cell</b></summary>

<br>

The default is to **fit the table to the text** rather than shrink the text:
font size stays at a comfortable size and columns widen, rows heighten.

```python
SCALE_TEXT_TO_EXCEL = True   # scale text by each cell's Excel font size
BASE_TEXT_SIZE_PT   = 7.0    # the base text type stands for Excel text at this size

WRAP_TEXT   = True      # wrap cells that have wrapping enabled in Excel
FIT_COLUMNS = True      # widen columns when non-wrapping text does not fit
FIT_ROWS    = True      # heighten rows when wrapping leaves them too short
MAX_COL_GROWTH = 4.0    # how many times its original width one column may grow
```

Turn all three off for a strict 1:1 copy of Excel's row and column sizes, where
text that does not fit simply runs up to the border.

Either way, **cells whose text does not fit are listed in the report**, so you
know exactly which ones they are.
</details>

<details>
<summary><b>Use the project's own line styles and text types</b></summary>

<br>

Reusing the drafting standards already in your project is the default, rather
than creating a pile of new types:

```python
LINE_STYLE_NAMES = {
    'thin':   '<Thin Lines>',      # Excel thin and dashed borders both map here
    'medium': '<Medium Lines>',
    'thick':  '<Wide Lines>',
}
GREY_FILL_TYPE_NAME = 'Fill Grey 192'    # grey shading always uses this existing type
BASE_TEXT_TYPE_NAME = '2.1mm Arial'      # base text type
```

`GREY_SNAP_TOLERANCE` (default 16) decides how close an Excel grey has to be to
the level in `GREY_FILL_TYPE_NAME` before it is drawn with that type. Further
away and a faithful `Fill Grey <level>` is created instead, so light shading does
not come out darker than the source. Raise it to force more greys on to your
standard type; set `GREY_FILL_TYPE_NAME = None` to always be faithful.

Put your own type names in. **Types that already exist are only ever read, never
modified** — the `Fill Grey 192` and `2.1mm Arial` you maintain are read and
copied, and this tool will never overwrite them.

When bold or red text is needed, the base type is **copied** into a derived one,
named the way you name things (`2.1mm Arial BOLD`, `2.1mm Arial RED`). Derived
types are always given a **transparent** background; plain black text is drawn
with the base type untouched, so give that type a transparent background too —
an opaque one hides the shading and borders behind the text.

Set all three to `None` for fully automatic behaviour: `EZ_*` types built
straight from Excel's own fonts and sizes.
</details>

<details>
<summary><b>Name the views differently</b></summary>

<br>

```python
VIEW_NAME_TEMPLATE = 'Table'              # -> Table, Table (1), Table (2) ...
# VIEW_NAME_TEMPLATE = 'Table - {sheet}'  # -> Table - Summary
# VIEW_NAME_TEMPLATE = '{file} {sheet}'   # -> Area Schedule Summary
```

`{sheet}` is the worksheet name, `{file}` the file name without its extension. A
name already in use gets a `(1)` `(2)` suffix automatically.
</details>

<details>
<summary><b>The report window opens on every import and it's annoying</b></summary>

<br>

```python
REPORT_MODE = 'auto'     # default: only when there are warnings or text that does not fit
# REPORT_MODE = 'always' # every time, with the full report
# REPORT_MODE = 'off'    # never
```

Under `auto`, a successful import announces itself by **switching to the new
view**, so nothing interrupts you when all is well.

Note that "skipped hidden rows" and "range taken from the print area" are
**informational** and never open the window; `#DIV/0!`, unrecognised border
styles and missing types do count as warnings.
</details>

# FAQ

**Q: The import says "has formulas but no cached values". Now what?**
Your xlsx was generated by some program and never opened and saved in Excel, so
its formula cells hold a formula but no result. EZTable reads the **result
values** Excel stored and does not recalculate formulas. Open the file in Excel,
save it once, and import again.

**Q: A cell is blank in Revit but has a number in Excel.**
If that cell is an error value such as `#DIV/0!` or `#REF!`, it is drawn blank
and listed in the report — fix the error in Excel first.

**Q: Refresh doesn't recognise a view I imported earlier.**
The source stamp is written at import time, and early versions had no such
mechanism. Views imported before v0.7.0 of the pyRevit build, or before the
native build gained Refresh, cannot be recognised; import them again.

**Q: Can it go the other way — a Revit schedule out to Excel?**
No. This is one-directional.

**Q: I changed the config and nothing happened.**
Restart Revit. The pyRevit build's rocketmode caches modules in memory, and the
native build reads its config file once when the add-in loads. Also check the
native build's file is named `EZTable.config` and not `EZTable.config.sample`.

**Q: Will it disturb the line styles and text types already in my project?**
No. Existing types are only read and copied, never overwritten. Types this tool
creates carry unambiguous names (`Fill Orange EE822F` and the like), and the
pyRevit build's Cleanup button can remove the unused ones.

# Known limitations

- **Double borders** are drawn as medium (with a warning)
- **Pattern fills** — hatches, grids and so on — are approximated as solid using
  the foreground colour
- **Rotated text** is unsupported and drawn horizontally
- Cells shaded **pure white** get no fill — the sheet background is white anyway
- Text type backgrounds are set to transparent; otherwise a text note's white
  background would cover the cell shading beneath it

---

## Repository layout

```
EZbuild-Revit/
├── pyrevit/
│   └── EZbuild.extension/       pyRevit extension (register the level above it)
│       ├── EZbuild.tab/             the EZbuild ribbon tab
│       │   └── A_Table.panel/           Import Excel · Refresh · Cleanup
│       └── lib/eztable/             all the logic, 14 modules
├── revit-addin/
│   └── EZTable/                 C# native add-in — the Table feature's assembly
│       ├── EZTable.csproj           net8.0-windows (Revit 2026 / 2027)
│       ├── EZTable.addin            Revit manifest (VendorId com.ezbuild)
│       ├── Core/ Models/ Utils/     parsing and layout, no Revit API
│       └── Revit/ Commands/ UI/     Revit API and interface
├── wip/                         NOT loaded by pyRevit — see wip/README.md
│   ├── sheets/                      sheet layout tools, unfinished
│   ├── audit/                       read-only sheet scan, office-specific
│   └── lib/ezsheets/                shared library for the two above
├── docs/
│   ├── DESIGN.md                design notes: algorithms, measured calibration, API traps
│   └── superpowers/specs/       design decisions, dated
├── README.md                    this file
└── README.zh-CN.md              Chinese manual
```

> Code comments, commit messages and the design notes are English throughout;
> the manual exists in English and Chinese.

## For developers

The code layout, the three core algorithms, the measured Revit API traps and the
places where the original spec disagrees with reality are all in
**[docs/DESIGN.md](docs/DESIGN.md)**. **It applies to both builds** — those traps
are properties of the Revit API, not of the language:

- `TEXT_SIZE` is a **cap height**, not a font size (feeding it a font size makes
  text 40% too large)
- `FilledRegionType` has no `LineStyleId`; call `SetLineStyleId()` on the
  **instance**
- `Category.GetCategory(doc, OST_InvisibleLines)` returns `null`

The pyRevit build carries one extra constraint: the whole package runs on
**IronPython 2.7** (pyRevit on Revit 2025+ has no usable CPython engine), so it
**can have no third-party dependencies** — xlsx parsing uses the bundled
zero-dependency OOXML reader `xlsxlite.py`, not openpyxl. The native build has no
such limit and uses ClosedXML.

Every pyRevit module except `styles.py`, `renderer.py`, `job.py` and `storage.py`
avoids the Revit API entirely and runs on a plain machine:

```bash
cd pyrevit/EZbuild.extension
python3 -c "import sys; sys.path.insert(0,'lib'); from eztable import plan, xlreader; print('ok')"
```

## To do

- [ ] **Ship a prebuilt installer** so nobody has to install Visual Studio.
      Blocked on something real: GitHub's build machines have no Revit
      installed and therefore no `RevitAPI.dll`, so the current reference
      scheme cannot run in CI. Either switch to the Revit API NuGet packages,
      or package from a machine that has Revit.
- [ ] Add **Cleanup** to the native build (removing unused `EZ_*` / `XL_*` types)
- [ ] Give the native build's ribbon buttons icons — the pyRevit build has them
- [ ] The native build's `FitToText` measures text with `System.Drawing`, while
      the pyRevit build uses its own Arial width table. Both now measure at the
      size the text is actually drawn at, but the two mechanisms have never been
      compared cell by cell.
- [ ] **Nothing in the native build has ever been compiled**, let alone run in
      Revit. The pyRevit build is verified against real drawings; this one is not.

## Licence

[MIT](LICENSE) © 2026 EZbuild

Free to use, modify and sell; derivative work need not be open sourced. Just
keep the copyright notice.

> The native add-in depends on [ClosedXML](https://github.com/ClosedXML/ClosedXML)
> (MIT) and, transitively, on DocumentFormat.OpenXml, SixLabors.Fonts, XLParser,
> Irony and ExcelNumberFormat. When distributing compiled output, their licences
> have to travel with it. The pyRevit build has no dependencies and is unaffected.
