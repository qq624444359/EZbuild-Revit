> **这是什么**：给 Claude Design 用的设计说明，用来出 EZbuild 官网的 Revit 插件
> 落地页 `for-revit.html` 的视觉稿。对应
> [合并设计文档](../superpowers/specs/2026-08-29-ezbuild-revit-consolidation-design.md)
> 的「项目 2 — 网站插件落地页」，决策见该文档 D9 / D10。
>
> **落地页不在本仓库**——它属于网站仓库 `qq624444359/ezbuild` 的 `frontend/`。
> 下面的设计 token（颜色、字体、玻璃拟态、卡片悬停、氛围层）是从那边的
> `frontend/index.html` 和 `tailwind.config.js` 实读出来的，不是拟定值；页面文案
> 由本仓库 README 提炼。
>
> 流程：整份粘进 Claude Design → 出稿 → 稿子交回，落成 `frontend/for-revit.html`
> 并同步改 `index.html` 的导航 / footer / 首页 section 三处。

---

# 粘贴给 Claude Design 的说明 —— EZbuild `for-revit.html` 落地页

设计一个名为 **for-revit.html** 的落地页，它要无缝并入一个已存在的深色 SaaS 网站
（EZbuild，新西兰建筑合规审图平台）。这是该网站新增的一个子页面，用来介绍它的
Revit 插件产品「EZbuild for Revit」。这一页的 URL 会被填进 Autodesk App Store
listing 的 Homepage 字段，所以它必须**独立成立**——从 App Store 点进来的人此前
可能完全没听说过 EZbuild。

全站文案是英文，**页面上所有可见文字必须用英文**（下面给出的 copy 请逐字使用，
不要改写、不要翻译）。

---

## 一、必须严格复用的设计系统

这一页要和现有首页看上去像同一天做出来的。以下 token 是硬约束：

**颜色**
- 页面主底色 `#09090b`（近黑）
- 次级分段底色 `#18181b`（用于交替 section，制造节奏）
- 品牌主色 `#1978e5`（蓝）
- 正文次要文字 `#A1A1AA`
- 标题/正文主色 纯白 `#FFFFFF`
- 语义色：绿 `#10b981`（通过 / 支持）、紫 `#a855f7`（AI / 处理中）、红 `#ef4444`（不支持）
- 分隔线一律用极低透明度白：`rgba(255,255,255,0.05)` ~ `0.06`

**字体**
- 全站 Inter（weights 400/500/600/700/800/900）
- 大标题用 `font-black`（900），字距收紧（tracking-tight），行高 1.07–1.15
- 小标题上方常配一行「kicker」：`#1978e5` 色、12–14px、bold、全大写、字距放宽
  （uppercase tracking-widest）

**圆角**：小元件 8px，卡片 12px，大图标块 16px，徽章/pill 全圆角

**三个必须复用的视觉效果**
1. `glass-panel`（玻璃拟态）：背景 `rgba(24,24,27,0.5)` + `backdrop-blur(14px)` +
   1px `rgba(255,255,255,0.06)` 边框。用于顶部导航条、次级按钮、徽章。
2. `card-hover`（卡片悬停）：默认 1px `rgba(255,255,255,0.06)` 边框；hover 时边框变
   `rgba(25,120,229,0.35)`、外发光 `0 0 30px -8px rgba(25,120,229,0.2)`、
   整体上移 3px。
3. `grad-text`（渐变标题字）：`linear-gradient(135deg,#1978e5,#60b0ff)` 裁进文字。
   **每页只用一次**，用在 H1 的最后一行关键词上。

**氛围层**（不要省略，这是这个站的调性所在）
- Hero 顶部一层径向渐变光晕：`radial-gradient(ellipse at 50% 0%,
  rgba(25,120,229,0.18) 0%, rgba(9,9,11,1) 65%)`
- Hero 满铺一层 60×60px 的网格线（白色，透明度仅 0.035），像蓝图纸
- 底部 CTA 区：一团 `#1978e5` 10% 的大面积模糊光斑（blur 120px）+ 两圈
  极淡的同心圆环缓慢反向旋转
- 所有 section 进入视口时淡入上移（opacity 0→1，translateY 28px→0，0.7s）

**布局**：内容最大宽 1280px（max-w-7xl），左右 padding 24px；section 上下
padding 112px（py-28）。

---

## 二、页面结构（按顺序，共 8 段）

### 1. 顶部导航（固定，高 80px，glass-panel）
左：`EZbuild` 黑体大字 + 一枚 `BETA` 徽章（蓝色 15% 底、蓝边框、10px 全大写）。
中（桌面端才显示）：`Features` · `How It Works` · `Results` · **`For Revit`**
——最后这条是当前页，用白色高亮，其余为 `#A1A1AA` hover 变白。
右：主按钮 `Get Started →`（蓝底白字，圆角 8px）。
滚动超过 30px 时导航条背景加深为 `rgba(9,9,11,0.95)` 并出现底边线。

### 2. Hero（首屏，左文右图，约 70vh）

左侧文案：
- 徽章（glass-panel + 蓝边 + 一个脉冲小圆点）：`FREE REVIT PLUG-IN`
- H1（三行，最后一行用 grad-text）：
  ```
  Your Excel table,
  drawn into
  Revit.
  ```
  （`Revit.` 用渐变色）
- 副文案：
  `Pick an .xlsx, pick a worksheet, and a 1:1 table appears in Revit — borders, shading, fonts and merged cells all reproduced. Native geometry, not a screenshot.`
- 两个按钮并排：
  - 主：`Get it on the Autodesk App Store →`（白底黑字，大号，圆角 12px）
  - 次：`View on GitHub`（glass-panel + 白边框）
- 下方一行三个信任点（12px、`#A1A1AA`、每个配一枚小图标）：
  - ✔（绿）`Revit 2021 – 2026`
  - ⚡（蓝）`pyRevit or standalone add-in`
  - ◆（绿）`Free`

右侧视觉（这是整页最重要的一张图，请认真设计）：
一个「Excel → Revit」的转化示意。左半边是一小片 Excel 网格（灰白、带表头行、
几个合并单元格、一处黄色底纹），中间一个蓝色箭头/光束，右半边是同一张表在 Revit
里的样子——深色底、蓝色矢量线框、文字清晰。右半边可以叠一条自上而下缓慢扫描的
蓝色光线（scan line），暗示「正在绘制」。整体放在一个 glass-panel 卡片里。

### 3. The problem（`#18181b` 底）

kicker：`THE USUAL WAY` ／ H2：`Three bad options for one simple job`

三张并排卡片（card-hover），每张：一个图标 + 一个做法 + 它的问题。文案逐字使用：

| 标题 | 正文 |
|---|---|
| `Paste a screenshot` | `Blurry when zoomed. Change one number and you re-capture it.` |
| `Link an OLE object` | `Breaks on another machine, and prints unreliably.` |
| `Redraw it by hand` | `Two hours the first time — and again every time a number changes.` |

三张卡片下方居中一句转折，字号大一些、白色加粗：
`EZbuild takes a fourth route: it draws the Excel straight into native Revit elements — detail lines, filled regions and text notes. Vector, printable, annotatable, and nothing to break.`

### 4. How it works（三步，`#09090b` 底）

kicker：`PROCESS` ／ H2：`From spreadsheet to sheet in three clicks`

三个圆角方块图标（88×88px，深底 + 彩色边框 + 外发光），右上角挂一枚编号圆点。
配色沿用首页：第 1 步蓝、第 2 步紫、第 3 步绿。三者之间用一条水平渐变细线相连
（桌面端才显示）。

1. `Pick your .xlsx` — `Browse to the file and choose a worksheet. No export step, no CSV, no add-in inside Excel.`
2. `Place the table` — `Click once in the view. Column widths and row heights are measured from the real text, so nothing clips.`
3. `Refresh anytime` — `Numbers changed in Excel? Hit Refresh. The table redraws in place, keeping its position on the sheet.`

### 5. Two builds（对比表，`#18181b` 底）

kicker：`INSTALL` ／ H2：`Two builds. Pick one.`
副题：`The geometry is identical — same unit conversion, same text calibration, same border merging. A table made by one can be refreshed by the other.`

一个两列对比表（表格样式：极淡分隔线、行 hover 时底色微亮），列头分别是
**`pyRevit extension`** 和 **`Standalone add-in`**：

| | pyRevit extension | Standalone add-in |
|---|---|---|
| `Prerequisite` | `pyRevit must be installed` | `None — it just installs` |
| `Revit versions` | `2021+` | `2022 – 2026` |
| `Features` | `Import · Refresh · Cleanup` | `Import · Refresh` |
| `Language` | `Python (IronPython)` | `C# / .NET` |

表格下方两句选择建议，做成两个小提示条：
- `Already using pyRevit? Take the pyRevit build — easiest to install, and it has Cleanup as well.`
- `Don't want pyRevit? Take the standalone build. Cleanup is the only thing you give up.`

### 6. Fidelity（支持 / 不支持，`#09090b` 底）

kicker：`FIDELITY` ／ H2：`What comes across`

左右两栏。左栏标题 `Reproduced`，每条前面一枚绿色对勾；右栏标题 `Not supported`，
每条前面一枚红色叉。两栏用一条竖向淡线分隔。

左栏（8 条）：
`Borders — thin, medium, thick, dashed`
`Cell shading, theme colours and tints`
`Font, size, bold, italic, colour`
`Merged cells`
`Number formats — thousands, percent, decimals, dates`
`Alignment and text wrapping`
`Hidden rows and columns, skipped without leaving a gap`
`Over-wide tables split by column and stacked`

右栏（5 条）：
`Images, charts and shapes`
`Conditional formatting`
`Pivot tables`
`Rotated text — drawn horizontally`
`Legacy .xls — .xlsx only`

### 7. 底部 CTA（`#09090b` 底 + 光斑 + 旋转圆环）

- 徽章：`FREE · NO ACCOUNT REQUIRED`
- H2（两行）：`Stop redrawing tables.` / `Start refreshing them.`
- 副文案：`EZbuild for Revit is free. The web platform — AI compliance review against the NZBC — is in private beta.`
- 三个按钮：
  - 主：`Get it on the Autodesk App Store →`（蓝底白字）
  - 次：`View on GitHub`（glass-panel）
  - 次：`Request Beta Access`（glass-panel）→ 链接到
    `mailto:pitayadesign.nz@gmail.com`
- 底下一行小字：`Questions? pitayadesign.nz@gmail.com`

### 8. 页脚（与首页完全一致）

四栏网格：左侧两栏是 `EZbuild` + BETA 徽章 + 一句
`Ensuring the technical integrity of New Zealand's built environment through intelligent automation.`；
第三栏 `Platform`：`Features` / `How It Works` / **`For Revit`**；
第四栏 `Legal`：`Privacy Policy` / `Terms of Use`。
底部一条分隔线，左 `© 2026 EZbuild. All rights reserved. Registered in New Zealand.`，
右 `Built for Architects & Builders · Private Beta`。

---

## 三、硬性约束

1. **深色单一主题**。这一页是营销页，底色写死深色，不做浅色版。
2. **不要改首页的 hero**。这一页是子页，主叙事仍归审图 SaaS。
3. 邮箱一律 `pitayadesign.nz@gmail.com`。
4. 移动端要能用：导航在窄屏收起中间链接，Hero 变上下堆叠，三卡片变单列，
   对比表可横向滚动。
5. 语气：克制、工程化、有具体数字，不吹。不要出现 "revolutionary" /
   "game-changing" 这类词。参照首页已有的口吻。

---

## 四、顺带产出（如果 Design 支持多画板，请一并给我）

除主页面外，另外给两个小画板，是要插回**现有首页**的改动：

- **画板 A —— 首页新增 section**：放在首页 `How It Works` 之后、`Results` 之前的
  一条窄横幅（不是整屏）。左侧一行 kicker `ALSO FROM EZBUILD` + 一行标题
  `Working in Revit? Get our free plug-in.` + 一句
  `Excel tables drawn straight into native Revit geometry — vector, printable, refreshable.`；
  右侧一个按钮 `For Revit →`。整体用 glass-panel，高度控制在 200px 左右，
  不要抢首页主叙事的戏。
- **画板 B —— 导航与页脚的新条目**：把加了 `For Revit` 之后的导航条和页脚
  Platform 栏单独画出来，方便我核对位置。
