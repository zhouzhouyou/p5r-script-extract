# 整理工具

从 P5R 原始二进制脚本，到这个仓库里的成品（纯文本剧本 + 阅读器数据）的全部管线。
所有脚本都可重复执行，除反编译两步外均为纯 Python 标准库。

> **前置条件**：需要自备两样东西，本仓库不包含——
> 1. 用 [CriFsV2Lib](https://github.com/Sewer56/CriFsV2Lib) 从正版游戏解包出的脚本目录
>    （`P5RScript`，内含 `.BF` / `.BMD` / `.MSG`），步骤见
>    [Persona Modding Docs](https://animatedswine37.github.io/persona-modding-docs/docs/getting-started/extracting-files/)；
> 2. [Atlus Script Tools](https://github.com/tge-was-taken/Atlus-Script-Tools) 的 Release，
>    解压后把两个 `Program.cs` 里的 `toolDir` 改成该目录。
>
> 详细出处与许可证见仓库根目录的 [SOURCES.md](../SOURCES.md)。

---

## 管线总览

```
P5RScript（原始 .BF/.BMD/.MSG）
      │
      │  batch_msg        —— 反编译对话
      ▼
_staging/decompiled/*.msg + *.msg.h          消息文本 + 索引表
      │
      │  batch_flow       —— 反编译流程脚本
      ▼
_staging/flow/*.flow                         流程与分支结构
      │
      ├─ build_script.py   → P5R_对话脚本/*.txt
      ├─ build_timeline.py → _staging/timeline.json
      └─ build_reader.py   → reader/data/*.json
```

`_staging/` 已在 `.gitignore` 中排除：它是中间产物，体积大（约 144 MB）且可由上述
工具重新生成。

---

## 各工具说明

### 反编译（C#，需要 .NET 8）

| 工具 | 作用 | 产出 |
| --- | --- | --- |
| `batch_msg/` | 批量反编译**对话** | `_staging/decompiled/**/*.msg` + `.msg.h` |
| `batch_flow/` | 批量反编译**流程脚本** | `_staging/flow/**/*.flow` |

两者都通过反射直接调用上游的 `AtlusScriptLibrary.dll`，
**输出与官方 `AtlusScriptCompiler -Decompile -Library P5R -Encoding P5R_CHS` 逐字节一致**，
但省去了每个文件启动一次进程的开销（7000 个文件由数小时降到几分钟）。

```powershell
# 对话
cd batch_msg && dotnet build -c Release
.\bin\Release\net8.0\batch_msg.exe $P5R ..\..\_staging\decompiled P5R_CHS P5R

# 流程
cd ..\batch_flow && dotnet build -c Release
.\bin\Release\net8.0\batch_flow.exe $P5R ..\..\_staging\flow P5R
```

参数：`<输入目录> <输出目录> <字符集> <游戏库>`。
字符集 `P5R_CHS`（简中）/ `P5R_CHT`（繁中）；游戏库 `P5R`。

### 结构化（Python）

| 脚本 | 作用 | 产出 |
| --- | --- | --- |
| `build_script.py` | 把 `.msg` 结构化成可读剧本；清理排版/立绘/语音标签；定义 `SPEAKER_FIXES` 译名修正表 | `P5R_对话脚本/` |
| `build_timeline.py` | 从 `.flow` 解析出选项分支与汇合点 | `_staging/timeline.json` |
| `build_reader.py` | 把 `.msg` + timeline 组织成「分类 → 章节 → 场景」，并**保留每条消息**（否则索引会错位） | `reader/data/` |

**执行顺序有要求**：`build_timeline.py` 必须在 `build_reader.py` 之前，
因为后者要读 `_staging/timeline.json` 生成 `reader/data/timeline/`。

`build_reader.py` 会 import `build_script.py`，两者共用同一份 `SPEAKER_FIXES`，
所以纯文本剧本与阅读器的译名修正规则不会走样。

### 译名修正（幂等，可重复跑）

| 脚本 | 作用 |
| --- | --- |
| `apply_corrections.py` | 修正纯文本剧本与 `_staging` 里的「礼司 → 龙司」 |
| `fix_reader_name.py` | 修正阅读器数据里的同一处错字，并校验 JSON 仍合法 |

中文版把**坂本龙司**误写成「礼司」。这不是解码问题——回原始二进制核对，
`92 9D 99 F4` 正是「礼司」在 `P5R_CHS` 字库中的编码，而「龙司」是 `93 84 99 F4`。
详见 [SOURCES.md](../SOURCES.md) 第 5 节。

### 辅助

| 文件 | 作用 |
| --- | --- |
| `find_speaker_anomalies.py` | 排查说话人标签的异常（当初就是靠它发现「礼司」的） |
| `reference/` | 为理解格式而收录的上游文档与关键源码（版权属上游） |

### 发布后的验证

`verify_published.js` 用来检查**部署出去的那份**是否真的能渲染：

```powershell
# 先把部署站的 reader 目录抓下来（含 data/），再本地验证
node tools/verify_published.js <下载目录>
```

它会用下载下来的 `index.html` 里的真实渲染函数，去跑下载下来的数据，
断言「解析出的场景数 > 0」「渲染出非空对话」「没有隐藏选项」「没有假选择」。
网络抓取不放进这个脚本，是因为它不该依赖任何代理设置。

---

## 自检

改完阅读器或数据后建议跑一遍，四条都是无依赖的 Node 脚本：

```powershell
node test_nav_toggle.js       # 左侧导航展开/收起逻辑（26 项）
node test_timeline_render.js  # 时间线渲染逻辑：分支、折叠、索引对齐（71 项）
node test_scene_load.js       # 真实执行 boot() + openScene()（13 项）
node verify_timeline_e2e.js   # 用真实数据全量验证
```

**`test_scene_load.js` 值得单独说明。** 它会用一套 mock DOM 与读本地文件的
`fetch`，去**真正执行**页面里的 `boot()` 与 `openScene()`，断言：

- 整个页面脚本能求值不抛错
- 导航构建出与 `index.json` 一致的分类数
- **每个分类都能打开一个场景、并渲染出非空对话文本**
- 载入进度回调会报告字节数与总量（进度条的数据来源）
- `fetch` 失败时显示错误信息，而不是静默空白

它存在的理由是一个真实教训：给阅读器加「载入中转圈」时，我把
`fetchJSON` / `buildLoading` / `updateLoading` 写在 `boot()` 之后，
而 `boot()` 在脚本末尾立即调用——`node --check` 只验语法，完全看不出问题，
但页面一打开就抛 `ReferenceError`，阅读器彻底空白。这类「声明顺序 / 未定义引用 /
路径写错」的 bug 只有真正跑一遍才抓得到。

`verify_timeline_e2e.js` 则是正确性的一道闸，它会断言：

- 引用的对话索引**都存在**
- **没有任何选项被折叠隐藏**
- **没有任何「选择 1 项」这种假选择**
- `{sel: n}` 引用必须落在真的是 `sel` 的对话上（编号对齐判据）

这几条都是实际踩过的坑：曾经因为「按比例判断编号是否对齐」，
导致 682 个场景的时间线**指向了完全无关的台词**——引用碰巧落在数组范围内，
比例很高但内容全错。现在改用结构性判据。

---

## 数据格式备注

- **`.BF`** 是 flow script 二进制，对话文本**内嵌**在其 `MessageScriptSection` 里，
  所以一个 `.BF` 反编译后同时产出 `.flow`（流程）与 `.msg`（对话）。
- **`.msg`** 是 MessageScript 文本：`[msg 名字 说话人]` / `[sel 名字 top]` 开头，
  其后每个 `[s]…[e]` 是一屏；行内的 `[n]` `[w]` `[clr]` `[bup]` `[vp]` `[f]`
  是排版/立绘/语音/函数控制码，**不是台词**。
- **flow 里的消息参数直接就是 `.msg.h` 的索引**：`MSG(3, 0)` 即第 3 条。
  全量验证过（3624/3625 个文件成立），唯一例外是
  `EVENT_DATA\SCRIPT\E700\E700_300.BF`，其引用指向外部消息池。
