<p align="center">
  <a href="README.md">English</a> &nbsp;|&nbsp; <b>中文</b>
</p>

<h1 align="center">EZbuild for Revit</h1>

<p align="center">
  <b>把 Excel 表格搬进 Revit —— 原样式、矢量、可刷新。</b><br>
  选一个 xlsx → 选一张工作表 → Revit 里出现一张 1:1 的表格。<br>
  边框、底色、字体、合并单元格全部复刻。
</p>

---

> **EZbuild for Revit** 是 [EZbuild](https://ezbuild.co.nz) 在 Revit 这一侧的部分，
> 所有功能都装在同一个 **EZbuild** 选项卡下。
>
> 目前发布的只有一个面板：**Table**。图纸排版和模型级合规检查放在
> [`wip/`](wip/) 里，刻意不加载 —— 原因见该目录的 README。

## 这个插件解决什么问题

做施工图的时候，面积统计表、材料表、房间明细这些东西都在 Excel 里算。
要放到图纸上，常见做法是：

| 旧做法 | 问题 |
|---|---|
| 截图贴进去 | 一放大就糊，改一个数字要重截一遍 |
| 链接 OLE 对象 | 换台电脑就断链，打印经常出问题 |
| 在 Revit 里手工画一遍 | 画一次两小时，Excel 改一个数又要重来 |

EZTable 走第四条路：**把 Excel 直接画成 Revit 原生图元**（详图线 + 填充区域 + 文字）。
矢量、可打印、可标注、不断链。

## 两个版本，选一个装

| | **pyRevit 扩展版** | **原生插件版** |
|---|---|---|
| 目录 | [`pyrevit/`](pyrevit/) | [`revit-addin/`](revit-addin/) |
| 语言 | Python（IronPython 2.7） | C# / .NET |
| 前提 | **要先装 pyRevit** | 不用，装完就能用 |
| Revit 版本 | 2021+（实测 2026） | 2022–2026（双目标编译） |
| 功能 | Import + Refresh + **Cleanup** | Import + Refresh |
| 第三方依赖 | 无 | ClosedXML |
| 改配置 | 改 `config.py`，重启 Revit | 改 `EZTable.config`，重开 Revit |
| 安装 | 注册一个文件夹 | 目前要自己编译 |

**怎么选：**

- **已经在用 pyRevit → 选 pyRevit 版。** 装起来最省事，还多一个 Cleanup。
- **不想装 pyRevit → 选原生版。** 功能上只差一个 Cleanup。
- 两个版本的**几何算法完全一致**（同一套单位换算、文字标定值、边框合并、
  列宽自适应），画出来的表格是一样的。
- **两版共用同一个来源戳**（Extensible Storage Schema GUID 相同），所以
  A 版导入的表，B 版也能刷新。

> 📌 两个版本的按钮都挂在同一个 **EZbuild** 选项卡下，同时安装会在这个名字下出现两个面板
> （也可能是两个同名选项卡，取决于谁先加载 —— 这一点没实测过，需要两个版本
> 同时装在一个 Revit 里才能验证）。通常只装一个。

## 能做什么 / 不能做什么

两版通用：

| ✅ 支持 | ❌ 不支持 |
|---|---|
| 边框（细 / 中 / 粗 / 虚线） | 图片、图表、形状 |
| 单元格底色（含主题色 theme + tint） | 条件格式 |
| 字体、字号、粗体、斜体、颜色 | 文字旋转（按水平画） |
| 合并单元格 | 单元格内混合格式（一格里两种字体） |
| 数字格式（千分位、百分比、小数位、日期） | 数据透视表 |
| 对齐方式、自动换行 | 公式重算（读的是 Excel 存下的结果值） |
| 隐藏行列（自动跳过，不留空） | `.xls` 老格式（只支持 `.xlsx`） |
| 超宽表自动按列切块、往下堆叠 | |
| 文字放不下时自动撑宽列 / 撑高行 | |

---

# 安装

## A. pyRevit 扩展版

**需要**：Revit + [pyRevit](https://github.com/pyrevitlabs/pyRevit)。
不需要装 Python，不需要 pip，不需要任何第三方库。

> 实测环境：Revit 2026 + pyRevit 6.4.0。走 pyRevit 自带的 IronPython 引擎。

**第一步 · 拿到代码**

```
git clone https://github.com/qq624444359/EZbuild-Revit.git
```

不用 git 的话，`Code` → `Download ZIP`，解压到一个固定位置（比如 `D:\EZbuild-Revit`）。

**第二步 · 把 `pyrevit` 子目录注册给 pyRevit**

注意注册的是仓库里的 **`pyrevit` 文件夹**，不是仓库根目录，也不是
`EZbuild.extension` 本身：

```
D:\EZbuild-Revit\
├── pyrevit\                     ← 注册这一层
│   └── EZbuild.extension\
├── revit-addin\
└── docs\
```

命令行：

```
pyrevit extend D:\EZbuild-Revit\pyrevit
pyrevit reload
```

或者界面操作：pyRevit → Settings → Custom Extension Directories → Add Folder →
选 `D:\EZbuild-Revit\pyrevit` → Save Settings and Reload。

**第三步 · 重开 Revit**，功能区上会多出一个 **EZbuild** 选项卡。

> 💡 以后更新一句 `git pull` 就行，不用重新下载解压。

## B. 原生插件版

目前**需要自己编译**（还没有提供打包好的安装程序）。

**需要**：Visual Studio 2022 + .NET SDK，本机装有对应版本的 Revit。

```
git clone https://github.com/qq624444359/EZbuild-Revit.git
cd EZbuild-Revit/revit-addin/EZTable
dotnet build -c Release
```

工程是**双目标**编译的：

| 目标框架 | 对应 Revit |
|---|---|
| `net8.0-windows` | 2025 / 2026 |
| `net48` | 2022 – 2024 |

Revit API 的路径默认取标准安装位置。装在别处、或者只装了一个版本，
**不用改工程文件**，命令行覆盖就行：

```
# 只编 Revit 2025/2026 那个目标
dotnet build -c Release -p:TargetFrameworks=net8.0-windows

# Revit 装在别的盘
dotnet build -c Release -p:RevitApiDir="D:\Autodesk\Revit 2026"

# 换一个 Revit 版本
dotnet build -c Release -p:RevitVersion=2025
```

找不到 `RevitAPI.dll` 时会直接报一句人话告诉你该传什么参数，
而不是甩一屏「找不到类型 Document」。

编译成功后，`net8.0-windows` 目标会**自动**把 `.addin` 和所有 `.dll` 复制到
`%AppData%\Autodesk\Revit\Addins\2026\`。重开 Revit 即可看到 **EZbuild** 选项卡。

手工安装的话，把下面这些一起丢进 `%AppData%\Autodesk\Revit\Addins\<版本号>\`：

```
EZTable.addin
EZTable.dll
ClosedXML.dll  DocumentFormat.OpenXml.dll  ExcelNumberFormat.dll
Irony.dll      SixLabors.Fonts.dll         XLParser.dll
```

---

# 使用说明

两个版本的按钮行为一致，**Cleanup 只有 pyRevit 版有**。

### 📥 Import Excel — 导入

1. 选一个 `.xlsx` 文件
2. 选一张工作表（只有一张就直接跳过这步）
3. 插件新建一个 1:1 的 Drafting View（绘图视图），把表画进去，然后自动切过去

画完就可以像用普通视图一样，把它拖到图纸上。

### 🔄 Refresh — 刷新

Excel 改了之后按这个。插件会列出项目里所有导入过的视图，并标出状态：

```
[changed]         Table       <-  面积统计.xlsx / Summary
[up to date]      Table (1)   <-  面积统计.xlsx / Part1
[source missing]  Table (2)   <-  D:\已删除.xlsx / Sheet1
```

可以多选，也可以全选一次刷完。没变的会自动跳过，不做无谓的重画。

**关键：刷新不会删掉视图本身。** 视图编号保住，已经放到图纸上的视口不会失效，
位置也不动 —— 只是把视图里的内容擦掉重画一遍。

> ⚠️ **请把导入出来的视图当成只读的生成物。**
> 刷新会把视图里的详图线、填充、文字**全部**删掉重画，包括你手工加的。
> 要写批注、加引线，请加在**图纸上**，不要加在这个视图里面。

### 🧹 Cleanup — 清理（仅 pyRevit 版）

项目用久了会积下一堆自动生成的文字类型、填充类型、线样式。
这个按钮把**没有任何图元在用的**那些扫出来删掉。

**两个前缀都扫**：`EZ_` 是现在生成的，`XL_` 是这个扩展还叫 XLTable 时留下的 ——
后者正是这个按钮存在的意义。

正在使用中的会列出来给你看，但**绝对不碰** —— 不会连带删掉你的图元。

按你自己的标准生成的类型（`2.1mm Arial BOLD`、`Fill Grey 242`）也认得出来，
所以基准类型本身和 `PROTECTED_TEXT_TYPE_NAMES` 里列的名字会被排除在扫描之外：
基准类型从 `2.0mm Arial` 换成 `2.1mm Arial` 之后，你的 `2.0mm Arial`
看上去就和一个改过字号的副本一模一样，绝不能拿去删。

---

# 常见需求怎么调

两个版本都是改一个文本文件，改完**重开 Revit** 生效，不用重新编译：

| 版本 | 改哪个文件 |
|---|---|
| pyRevit 版 | `pyrevit/EZbuild.extension/lib/eztable/config.py` |
| 原生版 | `EZTable.dll` 旁边的 `EZTable.config`（通常在 `%AppData%\Autodesk\Revit\Addins\2026\`） |

原生版的配置文件**默认不存在** —— 编译产物里有一个 `EZTable.config.sample`，
改名成 `EZTable.config` 就生效。必须改名：`.sample` 会被下一次编译覆盖，
`.config` 不会。

格式是 `键 = 值`，`#` 开头是注释，删掉某一行就用回默认值：

```ini
GreyFillTypeName = Fill Grey 192
MaxTableWidthMm  = 380
FitColumns       = true
```

下面的例子用 pyRevit 版的写法（`config.py`），原生版把 `PascalCase` 的同名键
写进 `EZTable.config` 即可，含义一样。

<details>
<summary><b>表格太宽，A3 图纸放不下</b></summary>

<br>

不要去改视图比例 —— 文字尺寸是**纸面固定**的，视图一缩放，字和格子的比例就对不上，
版式全乱。

正确做法是**按列切块、往下堆叠**，每一块都保持 1:1。插件默认就这么干：

```python
MAX_TABLE_WIDTH_MM = 380.0     # 每块最大宽度；A3 横放去掉图签的可用宽度
BLOCK_GAP_MM = 10.0            # 块与块的垂直间距
REPEAT_LEADING_COLS = 1        # 每块开头重复前 N 列（行标题），0 = 不重复
```

一张 549mm 宽的表，在 380mm 上限下会切成两块（A–U 和 A+V–AD），
堆起来变成 376 × 192mm，A3 就放得下了。

切点会**优先避开合并单元格** —— 从中间劈开一个合并区会把那格文字切成两半。
重复的行标题如果和原表头内容一样，会自动去掉，不会出现两个并排的相同表头。

设成 `0` 就不分块，多宽都画成一整张。
</details>

<details>
<summary><b>文字放不下，撑出格子了</b></summary>

<br>

默认策略是**让表格适应文字**，而不是把字缩小 —— 字号固定在图纸上看着舒服的大小，
放不下就把列撑宽、把行撑高：

```python
SCALE_TEXT_TO_EXCEL = True   # 按每格 Excel 字号等比缩放文字
BASE_TEXT_SIZE_PT   = 7.0    # 基准文字类型代表「Excel 的这个字号」

WRAP_TEXT   = True      # Excel 里勾了自动换行的格子，按格宽自己折行
FIT_COLUMNS = True      # 不折行的文字放不下时把列撑宽
FIT_ROWS    = True      # 折行后高度不够时把行撑高
MAX_COL_GROWTH = 4.0    # 单列最多撑到原宽的几倍，防止极端内容把表撑爆
```

三个开关全关掉，就是严格 1:1 复刻 Excel 的行列尺寸，文字放不下就压边。

不管开不开，**放不下的格子都会在报告里列出来**，告诉你是哪一格。
</details>

<details>
<summary><b>想用项目自己的线型和文字样式</b></summary>

<br>

插件默认就是复用你项目里已有的出图标准，而不是自己建一堆新类型：

```python
LINE_STYLE_NAMES = {
    'thin':   '<Thin Lines>',      # Excel 的细线 / 虚线都走这个
    'medium': '<Medium Lines>',
    'thick':  '<Wide Lines>',
}
GREY_FILL_TYPE_NAME = 'Fill Grey 192'    # 灰色底纹一律用这个已有类型
BASE_TEXT_TYPE_NAME = '2.1mm Arial'      # 文字基准类型
```

`GREY_SNAP_TOLERANCE`（默认 16）决定 Excel 的灰要离 `GREY_FILL_TYPE_NAME` 名字里那个
灰度多近，才会用你的标准类型来画。差得远就单独建一个忠实的 `Fill Grey <灰度>`，
免得浅灰被画深。调大它可以把更多灰并到你的标准类型；设 `GREY_FILL_TYPE_NAME = None`
则永远忠实还原。

改成你项目里的类型名就行。**已经存在的类型一律只读不改** ——
你维护的 `Fill Grey 192`、`2.1mm Arial` 只会被读取和复制，永远不会被这个工具改写。

需要粗体、红字这些的时候，插件会**复制**基准类型派生一个子类型出来，
命名跟着你的写法走（`2.1mm Arial BOLD`、`2.1mm Arial RED`）。派生出来的类型背景
一律设成**透明**；普通黑字直接用基准类型本身，不作任何改动，所以基准类型的背景
也要设成透明 —— 不透明的背景会把文字后面的底纹和边框挡掉。

三个都设成 `None`，就回到全自动模式：完全按 Excel 的原始字体字号建 `EZ_*` 类型。
</details>

<details>
<summary><b>视图名字想自己定</b></summary>

<br>

```python
VIEW_NAME_TEMPLATE = 'Table'              # -> Table、Table (1)、Table (2) ...
# VIEW_NAME_TEMPLATE = 'Table - {sheet}'  # -> Table - Summary
# VIEW_NAME_TEMPLATE = '{file} {sheet}'   # -> 面积统计 Summary
```

`{sheet}` 是工作表名，`{file}` 是不含扩展名的文件名。重名会自动加 `(1)` `(2)` 后缀。
</details>

<details>
<summary><b>每次导入都弹一个报告窗口，很烦</b></summary>

<br>

```python
REPORT_MODE = 'auto'     # 默认：只在有警告或有文字放不下时才弹
# REPORT_MODE = 'always' # 每次都弹，带完整报告
# REPORT_MODE = 'off'    # 永远不弹
```

`auto` 模式下，导入成功的确认信号是**视图自动切过去了**，一切正常就不打扰你。

注意「跳过了隐藏行」「范围取自打印区域」这类只是**提示**，不算警告，不会因此弹窗；
`#DIV/0!`、认不出的边框样式、找不到指定类型这些才算。
</details>

# 常见问题

**Q：导入后提示 "has formulas but no cached values"，怎么办？**
你的 xlsx 是某个程序生成的，从来没在 Excel 里打开保存过，所以公式格里只有公式没有结果。
插件读的是 Excel 存下来的**结果值**，不重算公式。用 Excel 打开这个文件，
按一下保存，再导入就好了。

**Q：表格里出现了空格子，Excel 里明明有数？**
如果那格是 `#DIV/0!`、`#REF!` 这类错误值，插件会画成空白并在报告里列出来 ——
先把 Excel 里的错误修掉。

**Q：Refresh 认不出我以前导入的视图？**
来源戳是导入时盖上去的，早期版本没有这个机制。pyRevit 版 v0.7.0 之前、
原生版加入 Refresh 之前导入的视图都认不出来，重新导入一次即可。

**Q：能反过来吗？Revit 明细表导出到 Excel？**
不能，这个插件是单向的。

**Q：改了配置没反应？**
重开 Revit。pyRevit 版的 rocketmode 会把模块缓存在内存里；原生版的配置文件
是在插件加载时读一次的。另外确认原生版的文件名是 `EZTable.config` 而不是
`EZTable.config.sample`。

**Q：会不会弄乱我项目里已有的线型 / 文字样式？**
不会。已存在的类型只被读取和复制，永远不会被改写。插件新建的类型都有明确的命名
（`Fill Orange EE822F` 这种形式），pyRevit 版还有 Cleanup 按钮可以把不用的清掉。

# 已知限制

- **双线边框**按中粗线画（会记一条警告）
- **图案填充**（斜纹、网格那些）按前景色近似成实色
- **文字旋转**不支持，遇到按水平画
- 底色是**纯白**的格子不画填充 —— 图纸背景本来就是白的
- 文字类型的背景被设为透明，否则文字的白底会盖掉单元格底色

---

## 仓库结构

```
EZbuild-Revit/
├── pyrevit/
│   └── EZbuild.extension/       pyRevit 扩展（注册它的上一层目录）
│       ├── EZbuild.tab/             EZbuild 选项卡
│       │   └── A_Table.panel/           Import Excel · Refresh · Cleanup
│       └── lib/eztable/             全部逻辑，14 个模块
├── revit-addin/
│   └── EZTable/                 C# 原生插件 —— Table 功能的程序集
│       ├── EZTable.csproj           双目标：net48 / net8.0-windows
│       ├── EZTable.addin            Revit 清单（VendorId com.ezbuild）
│       ├── Core/ Models/ Utils/     解析与排版，不碰 Revit API
│       └── Revit/ Commands/ UI/     Revit API 与界面
├── wip/                         pyRevit 不加载 —— 见 wip/README.md
│   ├── sheets/                      图纸排版工具，未完成
│   ├── audit/                       只读图纸扫描，绑事务所标准
│   └── lib/ezsheets/                上面两者的共用库
├── docs/
│   ├── DESIGN.md                设计笔记：算法、实测标定、API 陷阱
│   └── superpowers/specs/       设计决策，按日期
├── README.md                    英文手册
└── README.zh-CN.md              本文件
```

> 代码注释、提交信息和设计文档一律英文；说明书有中英两份。

## 给开发者

代码结构、三个核心算法、Revit API 的实测坑、以及和原始规格文档不一致的地方，
都在 **[docs/DESIGN.md](docs/DESIGN.md)** 里。**两个版本都适用** ——
那些坑是 Revit API 的性质，跟用什么语言写无关：

- `TEXT_SIZE` 参数是**大写字母高度**，不是字号（直接填字号会大 40%）
- `FilledRegionType` 上没有 `LineStyleId`，要在**实例**上 `SetLineStyleId()`
- `Category.GetCategory(doc, OST_InvisibleLines)` 返回 `null`

pyRevit 版还有一条额外约束：整个包跑在 **IronPython 2.7** 上（Revit 2025+ 的
pyRevit 没有可用的 CPython 引擎），所以**不能有任何第三方依赖** —— xlsx 解析用的是
自带的零依赖 OOXML 读取器 `xlsxlite.py`，不是 openpyxl。原生版没这个限制，
用的是 ClosedXML。

pyRevit 版除 `styles.py` / `renderer.py` / `job.py` / `storage.py` 外的模块都不碰
Revit API，可以直接在电脑上跑：

```bash
cd pyrevit/EZbuild.extension
python3 -c "import sys; sys.path.insert(0,'lib'); from eztable import plan, xlreader; print('ok')"
```

## 待办

- [ ] **提供编译好的安装包**，省得用户自己装 Visual Studio。
      卡在一个现实问题上：GitHub 的构建机器上没有装 Revit，也就没有
      `RevitAPI.dll`，所以现在这套编译方式在 CI 上跑不起来。要么改用
      NuGet 上的 Revit API 包，要么自己找一台装了 Revit 的机器打包。
- [ ] 原生版补 **Cleanup**（清理没人用的 `EZ_*` / `XL_*` 类型）
- [ ] 原生版的功能区按钮还没有图标（pyRevit 版有）
- [ ] **原生版从未编译过**，更没在 Revit 里跑过。pyRevit 版已用真实图纸验证，这个还没有。
- [ ] 原生版的 `FitToText` 用 `System.Drawing` 量文字，pyRevit 版用的是自带的
      Arial 字宽表。两边结果应该一致，但没有逐格比对过

## 许可

[MIT](LICENSE) © 2026 EZbuild

可以自由使用、修改、商用，改完不用开源，只要保留版权声明就行。

> 原生插件版依赖 [ClosedXML](https://github.com/ClosedXML/ClosedXML)（MIT）及其
> 传递依赖 DocumentFormat.OpenXml、SixLabors.Fonts、XLParser、Irony、
> ExcelNumberFormat，分发编译产物时这些库各自的许可证也要一并带上。
> pyRevit 扩展版零依赖，不涉及这个问题。
