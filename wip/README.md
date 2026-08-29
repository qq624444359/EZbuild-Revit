# wip — 未发布的代码

这个目录**不在** `pyrevit/EZbuild.extension/` 里面，所以 pyRevit 不会加载它。
里面的东西都能跑，但还不该出现在用户的 ribbon 上。

| 目录 | 内容 | 为什么还没发布 |
|---|---|---|
| `sheets/` | Clone Details · Update Titleblock · Measure Layout · Pack Details | 排版功能尚未完成 |
| `audit/` | Sheet Audit（只读扫描） | 见下 |
| `lib/ezsheets/` | 上面两者共用的库（原 `lib/pitaya`） | 随之 |

## audit/ 为什么按住不发

两个原因，都不是技术问题：

1. **它绑死作者事务所的标准。** `lib/ezsheets/config.py` 里的数值
   （`SHEET_W=420` `SHEET_H=297` `TITLEBLOCK_X=370` 以及标准图纸清单）
   是从自有的 6 个项目、296 页已提交 BC 图纸量出来的。别人的标题栏不在
   X=370，跑出来就是一堆假错。
2. **`Audit` 这个词留给 EZbuild 引擎。** 网站上 `Audit` 指的是 23 条 NZBC
   合规检查。这个脚本查的是标题栏、图幅、缺哪几张图——是文档体检，不是合规审查。
   两者同名会让用户以为这就是 EZbuild 的全部能力。

要发布它，得先做两件事：把事务所专用的判定（A3 判定、标准图纸清单）改成
可配置且检测不到就跳过；然后换一个不叫 Audit 的名字。
