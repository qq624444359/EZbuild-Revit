# EZbuild for Revit — 仓库合并与命名收敛

**日期：** 2026-08-29
**状态：** 已批准，实施中
**范围：** 项目 1（合并仓库 + 命名收敛）与项目 2（网站插件落地页）。Live Audit 明确不在本次范围内。

---

## 背景

三个仓库同时在用三套名字，用户在 Revit 里会看到两个互不相干的选项卡
（`EZTable` 和 `Pitaya`），没有任何东西表明它们出自同一个作者。同时
`EZbuild` 一词既是母品牌又是审图网站的产品名。

此刻做收敛的成本接近于零：EZbuild 网站零用户零推广，EZTable 上周才上架
Autodesk App Store，EZDrawing 一个 commit 都没有。每推迟一天成本都更高。

## 决策

### D1 — 品牌层级

| 层 | 名字 | 用户在哪看到 |
|---|---|---|
| 品牌 / 公司 | **EZbuild** | 域名 ezbuild.co.nz、LICENSE、邮箱、App Store publisher |
| 网页产品 | **EZbuild** | 网站本身（不改名） |
| Revit 产品 | **EZbuild for Revit** | Revit 里一个选项卡，名为 `EZbuild` |
| 功能（非产品） | Table · Sheets · Audit | 该选项卡下的各个面板 |

`Pitaya` 退场，仅保留为个人/法律署名。

### D2 — 合并成一个仓库

`EZbuild-Revit` 同时容纳 pyRevit extension 与 C# add-in。
`EZTable` 与 `EZDrawing` 归档，README 指向此处。

理由：pyRevit extension 必须是**一个**用户可安装的文件夹，才能保证多个面板
合并进同一个选项卡；跨 extension 的同名 tab 合并行为不确定，不值得赌。

### D3 — C# 程序集名保持 `EZTable`

程序集是 Table **功能**的实现，名字是准确的。品牌属于 ribbon tab，不属于 dll。
以后 Audit 的 C# 版就是 `revit-addin/EZAudit/`，一个功能一个程序集，
各自往 `EZbuild` 选项卡挂 panel。

`App.cs` 现有的 `CreateRibbonTab` try/catch 已经支持这种共用：

```csharp
try { application.CreateRibbonTab(tabName); }
catch (Autodesk.Revit.Exceptions.ArgumentException) { /* 已存在，忽略 */ }
```

改程序集名需触碰 csproj、.addin 三个字段、18 个 .cs 的命名空间、
`App.cs:82` 的资源路径与 `EZTable.config` 文件名，而用户屏幕上不会有任何变化。
**明确不做。**

### D4 — v1 只发布 Table 面板

Live Audit 尚未开发。现有的 `Audit.pushbutton` 是排版项目的开发脚手架
（read-only sheet scan），且绑死作者事务所的 A3 标准
（`config.py` 中 `TITLEBLOCK_X = 370` 等数值量自其自有的 6 个项目、296 页图纸），
他人运行会产生大量假错。

更重要的是：叫 `Audit` 会让用户误以为那就是 EZbuild 的 NZBC 合规审查，
从而损伤尚未推广的主产品叙事。**`Audit` 一词保留给引擎，等 Live Audit 落地再启用。**

未发布的代码进 `wip/`，位于 `.extension` 之外，因此 pyRevit 不会加载。

### D5 — App Store listing 名保持 `EZTable`

这是功能名，用户搜索的是 "excel table revit"。publisher 写 EZbuild 即可。
`ClientId` (`B8454D13-4015-4D78-9842-8EE553D0DB01`) **不得更改**——Revit 靠它识别插件。

---

## 目标结构

```
EZbuild-Revit/
  .gitignore                       挡住 *.pdf *.rvt 与构建产物
  README.md / README.zh-CN.md
  LICENSE                          MIT © 2026 EZbuild
  pyrevit/
    EZbuild.extension/
      EZbuild.tab/
        bundle.yaml                title: EZbuild
        A_Table.panel/             ← EZTable/pyrevit 的 Table.panel
      lib/eztable/
  revit-addin/
    EZTable/                       C# 程序集（名字不变）
  wip/                             pyRevit 不加载
    sheets/                        ← EZDrawing B_Sheets + C_Layout
    audit/                         ← 现有 Sheet Audit 脚本
    lib/ezsheets/                  ← 原 lib/pitaya
  docs/
```

## 改名清单

| 位置 | 现在 | 改成 |
|---|---|---|
| `revit-addin/EZTable/App.cs:13` | `tabName = "EZTable"` | `"EZbuild"` |
| pyRevit extension 目录 | `EZTable.extension` | `EZbuild.extension` |
| pyRevit tab 目录 | `EZTable.tab` | `EZbuild.tab` |
| pyRevit tab bundle | （无） | 新建 `bundle.yaml` → `title: EZbuild` |
| Table 面板目录 | `Table.panel` | `A_Table.panel` |
| wip 库 | `lib/pitaya` | `lib/ezsheets`（含 import 改写） |
| `audit-system/frontend/spec-viewer.html:280` | `pitayadesign.ezbuild@gmail.com` | `…@ezbuild.co.nz` |

## 项目 2 — 网站插件落地页

* 新增 `audit-system/frontend/for-revit.html`，复用 index 的 nav / footer /
  主题初始化脚本
* `index.html:186` 导航增加 `For Revit`
* `index.html:698` footer Platform 区增加同一条
* 首页 `#how-it-works` 之后插入一个小 section（一句话 + 一个按钮）。
  **不动 hero**——审图 SaaS 的主叙事不稀释

落地页需承载 App Store listing 的 Homepage 字段，因此必须在作者登录
Autodesk 修改 listing **之前**上线。

## 执行顺序

1. `EZDrawing/.gitignore` — 堵住客户图纸外泄（已完成）
2. 建 `EZbuild-Revit` 仓库骨架 + 本设计文档（已完成）
3. 搬入 EZTable（pyrevit + revit-addin），改 tab 名
4. 搬入 EZDrawing 代码到 `wip/`，`lib/pitaya` → `lib/ezsheets`
5. README / LICENSE；EZTable 与 EZDrawing 仓库加归档提示
6. 网站：`for-revit.html` + 导航 + footer + 首页 section
7. （作者执行）Revit 构建、重拍截图、一次性提交 App Store 更新

## 明确不做

* 不改 C# 程序集 / 命名空间 / 目录名（D3）
* 不改 App Store listing 名（D5）
* 不发布 Sheets / Layout / Audit 面板（D4）
* 不做 Live Audit — 单独立项，需另写 spec：API 认证、user_id 获取、
  计费路径、以及从 23 条中挑出适合模型级检查的子集

---

## 实施期修订

### D6 — wip 库命名为 `ezsheets` 而非 `ezbuild`（2026-08-29）

原文写的是 `lib/pitaya` → `lib/ezbuild`。实施时改为 **`lib/ezsheets`**，理由：

* 与 `lib/eztable` 形成对仗——一个功能一个库，`eztable` / `ezsheets`
* `ezbuild` 是**品牌**，不该被占用为某一个功能的模块名。将来真有跨功能的共享
  代码时，`ezbuild` 这个名字还留着

影响面为零：这些代码在 `wip/` 内，未发布，无外部引用。

### D7 — 两条安装路线的 ribbon 对齐（2026-08-29）

C# add-in 原本把面板命名为 `Excel Tools`，pyRevit 那边则是 `Table`。
已统一为 **`Table`**（`App.cs:24`），使两条安装路线在 ribbon 上完全一致：

```
EZbuild ▸ Table ▸ Import Excel · Refresh · Cleanup
```

### D8 — 邮箱暂不更改（2026-08-29）

原计划把 `pitayadesign.ezbuild@gmail.com` 换成 `…@ezbuild.co.nz`。
**未执行**，因为 `@ezbuild.co.nz` 的邮箱尚未建立，改了会让一个**能收信的**
联系方式变成收不到信的——网站上的 "Request Access" 按钮正指向它。

待办（需先建信箱，再一次性替换）：

* `frontend/index.html` 的 `mailto:` CTA
* `frontend/spec-viewer.html:280` 报告页脚的 `companySub`
* Autodesk App Store listing 的 support email

### D9 — 联系邮箱定为 `pitayadesign.nz@gmail.com`（2026-09-02，取代 D8）

D8 把邮箱替换整件事挂起了，理由是 `@ezbuild.co.nz` 还没建信箱。现在作者拍板：
**不等自有域名信箱，改用另一个已经在收信的 gmail** —— `pitayadesign.nz@gmail.com`。

D8 的顾虑因此消失：新地址是能收信的，替换不会把一个活的联系方式改死。

三处一次性替换（随落地页一起提交，尚未执行）：

* `frontend/index.html:671` 的 "Request Access" `mailto:` CTA
* `frontend/spec-viewer.html:280` 报告页脚的 `companySub`
* 新建的 `frontend/for-revit.html` 直接用新地址，不要再写 `pitayadesign.ezbuild@gmail.com`

Autodesk App Store listing 的 support email 由作者手工改。

### D10 — 落地页先在 Claude Design 出稿，再落成 HTML（2026-09-02）

执行顺序第 6 步（网站落地页）不直接写 HTML。作者先在 Claude Desktop 的 Design
里出视觉稿，再把稿子交回来落成 `frontend/for-revit.html`。

配套的设计说明见 [`docs/design-briefs/for-revit-landing-page.md`](../../design-briefs/for-revit-landing-page.md)
—— 其中的设计 token 是从 `qq624444359/ezbuild` 仓库的 `frontend/index.html`
与 `tailwind.config.js` 实读出来的，页面文案由本仓库 README 提炼。

注意落地页所在的仓库是 **`qq624444359/ezbuild`**（网站），不是本仓库。

### D11 — 落地页已落地，四处事实性修正（2026-09-03）

执行顺序第 6 步完成。设计稿经 Claude Design 出稿、handoff bundle 导出后，落成
`frontend/for-revit.html`（388 行），并按计划改了 `index.html` 三处（导航、footer
的 Platform 栏、`#how-it-works` 之后的窄横幅）。提交在网站仓库
`qq624444359/ezbuild` 的 `claude/ezbuild-revit-new-website-5yhkzg` 分支。

设计稿里有四处说法与插件源码不符，落地时已改正——**记在这里是因为设计稿本身
仍是错的**，将来若从 Design 项目重新导出，同样的四处会再回来：

| 设计稿写的 | 实际 | 依据 |
|---|---|---|
| standalone 支持 Revit `2026 – 2027` | `2022 – 2026` | `EZTable.csproj` 双目标 net48（2022–2024）+ net8.0-windows（2025/2026） |
| hero 版本行 `2021 – 2027` | `2021 – 2026` | 仓库中无任何 2027 支持 |
| standalone「面板在 Add-Ins 选项卡下」 | 自建 `EZbuild` 选项卡 + `Table` 面板 | `App.cs:13`、`App.cs:24` |
| GitHub 链接指向 `qq624444359/EZTable` | `qq624444359/EZbuild-Revit` | 合并后 EZTable 仓库已归档 |

明暗主题的疑虑不成立：设计稿自己引了 `css/unified-theme.css` 作为覆盖层，并补了
一组 `html[data-theme="light"]` 的修正（hero 光晕、蓝图网格、CTA 圆环在浅色底下
会消失，白色 hero 按钮在近白页面上没有边缘），另加载 `js/theme-toggle.js`。
无头验证：`for-revit.html` 与 `index.html` 的本地资源全部 200，主题开关
（`#ezbuild-theme-toggle`）在两页上都正常挂载，无横向溢出，控制台报错与首页完全
一致（均为沙箱拦截 CDN 所致）。

D9 的替换清单少列了一处：`frontend/privacy.html:54` 也有旧邮箱。三处已一并替换。

#### 两个悬而未决的问题（需作者确认）

1. **Autodesk App Store 链接仍是占位符。** 页面上两个 "Get it on the Autodesk App
   Store" 按钮指向 `https://apps.autodesk.com/` 首页，而非实际 listing。上线前必须
   替换成真实 URL。
2. **standalone 的安装路径自相矛盾。** 落地页照设计稿写的是「从 App Store 下载对应
   Revit 版本的安装包并运行」，但本仓库 `README.md:133` 写的是「For now this **has
   to be built yourself**; there is no packaged installer yet」。而本设计文档开头又
   称 EZTable 已上架 App Store。三者需对齐：要么 README 过时，要么落地页那张卡片
   要改写成自行构建的流程。

顺带发现：`README.md:139` 的克隆地址仍是 `qq624444359/EZTable.git`，合并后已过时。

### D12 — App Store 审核期间落地页改指 GitHub（2026-09-03）

D11 留的两个问题有答案了：**Autodesk App Store 的 listing 还在审核**，尚未真正上线。
因此没有「真实 listing URL」可填，README 的说法（无打包安装程序，需自行构建）是
对的，落地页照设计稿写的那套「从 App Store 下载安装包并运行」是错的。

落地页已改（网站仓库 `687f555`）：

* hero 与底部 CTA 的主按钮从 "Get it on the Autodesk App Store" 改为
  **"Get it on GitHub →"**，副按钮改为跳转到 `#install` 而不是重复同一个链接
* 按钮下方加一句说明：listing 审核中，暂时从 GitHub 安装
* standalone 安装卡三步改写为仓库实际记录的构建流程（`dotnet build -c Release`、
  构建后自动拷贝进 Revit Addins 目录、单版本 Revit 用 `-p:TargetFrameworks=` 只构建
  一个目标）。被替换掉的那条「Windows 拦截了下载的安装包 → 右键解除锁定」对自行
  编译出来的 DLL 根本不适用

**listing 通过审核后要做的**：把两个主按钮的 href 换回 App Store 实际地址，删掉
hero 那句 "listing is in review"，并回头确认 standalone 卡片是否该改回安装包流程。

同时修正了两份 README 里合并后过时的引用（4 处克隆地址 + 示例路径）：

* `git clone …/EZTable.git` → `…/EZbuild-Revit.git`
* `cd EZTable/revit-addin/EZTable` → `cd EZbuild-Revit/…`
* 示例解压路径 `D:\EZTable` → `D:\EZbuild-Revit`

保留未改的 `EZTable` 是**功能名与程序集名**（`revit-addin/EZTable/`、
`EZTable.csproj`、`EZTable.config`），按 D3 不动。
