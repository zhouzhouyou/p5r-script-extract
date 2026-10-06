# 数据与工具出处

本文件记录本仓库所有**外部依赖、数据来源与许可证**，以及复现所需的全部外链。

---

## 1. 原始游戏脚本的来源

本仓库的输入是 `P5RScript` 目录下的 P5R 原始脚本文件
（`.BF` flow script / `.BMD`、`.MSG` message script）。

**这些文件不在游戏的文件系统里以这个目录形式存在**，它们是解包游戏 CPK 归档
之后得到的。提取方式：

| 步骤 | 工具／资料 | 链接 |
| --- | --- | --- |
| 解包 CPK（CriFs 归档） | **CriFsV2Lib**（Sewer56） | <https://github.com/Sewer56/CriFsV2Lib> |
| 提取流程说明 | Persona Modding Docs — Extracting Files | <https://animatedswine37.github.io/persona-modding-docs/docs/getting-started/extracting-files/> |

> **本仓库不包含**上述原始文件。`samples/` 下仅有极少量 `.BF` 及其反编译结果，
> 目的是**说明文件格式**（覆盖「协助人剧情」与「日常与城镇」两类），
> 不构成对游戏素材的分发。完整数据请自备正版游戏后自行提取。

### 版权

Persona 5 Royal 及其全部脚本、文本、角色、美术、音频等素材，
版权归 **Atlus / SEGA** 所有。本仓库对脚本的整理仅供学习、检索与无障碍阅读，
不得用于任何商业用途。

---

## 2. 反编译工具

把二进制脚本转成可读文本，使用的是：

| 项目 | 说明 |
| --- | --- |
| **Atlus Script Tools** | 作者 **TGE**，许可 **GNU GPL** |
| 仓库 | <https://github.com/tge-was-taken/Atlus-Script-Tools> |
| 用到的组件 | `AtlusScriptLibrary.dll`（核心库）、`AtlusScriptCompiler`（官方 CLI）、`Charsets/*.tsv`（字符集表） |
| 支持的 P5R 相关参数 | `-Library P5R`、`-Encoding P5R_CHS`（中文）、`P5R_CHT`（繁体） |

本仓库的 `_tools/batch_msg` 与 `_tools/batch_flow` 是**对该库的薄封装**：
通过 .NET 反射直接调用 `AtlusScriptLibrary.dll`，避免为 7000 个文件各启动一次进程。

> 使用前请自行从上游 Release 获取该工具，并把路径填入工具源码里的 `toolDir`
> （默认 `C:\Users\14453\Downloads\Atlus-Script-Tools`）。
> 本仓库**不重新分发**该工具的二进制，因为它以 GPL 授权，且并非本仓库的作品。

### 用到的上游源码参考

整理 `_tools/reference/` 下收录了为理解格式而引用的上游文件（同样来自 Atlus Script Tools）：

| 文件 | 用途 |
| --- | --- |
| `MessageScriptLanguageReference.txt` | `.msg` 文本格式的语法说明 |
| `FlowScriptBFFormatReference.txt` | `.BF` 容器与 section 的格式说明 |
| `MessageScriptDecompiler.cs` | 反编译输出规则（标签如何生成） |
| `FlowScriptDecompiler.cs` | flow 反编译规则（分支如何还原） |
| `AtlusEncoding.cs` | 自定义字符集的解码实现 |
| `Atlus-Script-Tools-README.md` | 上游 README 存档 |

这些文件的版权属上游作者，遵循其 GPL 许可。

---

## 3. 运行时依赖

| 用途 | 依赖 | 许可 |
| --- | --- | --- |
| 批量反编译（C#） | .NET 8 SDK | MIT |
| 整理脚本（Python） | Python 3.11+，**仅用标准库** | PSF |
| 阅读器 | 无依赖，纯前端（原生 JS + CSS） | — |
| 测试 | Node.js（运行 `_tools/*.js` 断言） | MIT |

---

## 4. 字符集与编码

P5R 中文版不使用常见编码（GBK / Shift-JIS / UTF-8 都不是），
而是**游戏自定义字符集**：字库按 0x80 大小的「glyph table」分块，
高位字节是表索引、低位字节是表内偏移。

因此必须用配套的字符集表才能正确解码：

```
Charsets/P5R_CHS.tsv   ← 简体中文（本仓库全程使用）
Charsets/P5R_CHT.tsv   ← 繁体中文
Charsets/P5R_Japanese.tsv
Charsets/P5R_EFIGS.tsv
```

这些表由 Atlus Script Tools 随发行版提供。若解码用错表，中文会变成乱码；
本仓库曾据此验证过一处游戏数据自身的错字（见下节）。

---

## 5. 已修正的游戏数据错字

中文版数据把 **坂本龙司** 的名字误写成 **`礼司`**（日文 リョウジ → 龙司）。
这不是解码问题：回原始二进制核对，字节序列 `92 9D 99 F4` 正是「礼司」在
`P5R_CHS` 字库中的编码，而「龙司」是 `93 84 99 F4`，两者只差第一个字。

修正范围与方式记录在：

- `_tools/apply_corrections.py` —— 纯文本剧本 + staging
- `_tools/fix_reader_name.py` —— 阅读器数据
- 阅读器 `reader/data/index.json` 的 `dataFixes` 字段保留了审计记录

---

## 6. 复现步骤（需要自备游戏与上游工具）

```powershell
# 0) 准备：从正版游戏解包出脚本目录（用 CriFsV2Lib，见第 1 节）
#    设该目录为  $P5R = "C:\path\to\P5RScript"

# 1) 从上游 Release 取 Atlus Script Tools，解压到某目录
#    并把 _tools/batch_msg/Program.cs 与 _tools/batch_flow/Program.cs
#    里的 toolDir 改成该目录

# 2) 反编译对话（产出 .msg / .msg.h）
cd _tools\batch_msg && dotnet build -c Release
.\bin\Release\net8.0\batch_msg.exe $P5R "..\..\_staging\decompiled" P5R_CHS P5R

# 3) 反编译流程脚本（产出 .flow）
cd ..\batch_flow && dotnet build -c Release
.\bin\Release\net8.0\batch_flow.exe $P5R "..\..\_staging\flow" P5R

# 4) 结构化成纯文本剧本
cd ..\.. && python _tools\build_script.py
python _tools\apply_corrections.py

# 5) 解析选项分支 → 阅读器数据
python _tools\build_timeline.py
python _tools\build_reader.py
python _tools\fix_reader_name.py

# 6) 自检
node _tools\test_nav_toggle.js
node _tools\test_timeline_render.js
node _tools\verify_timeline_e2e.js
```

---

## 7. 相关项目与延伸阅读

- **Atlus Script Tools** —— 本仓库赖以工作的反编译工具<br><https://github.com/tge-was-taken/Atlus-Script-Tools>
- **CriFsV2Lib** —— 解包 CriFs 归档（提取游戏文件）<br><https://github.com/Sewer56/CriFsV2Lib>
- **Persona Modding Docs** —— P5R 文件提取与修改的总入口<br><https://animatedswine37.github.io/persona-modding-docs/>
- **Amicitia** —— Persona 系列文件格式的社区文档<br><https://amicitia.miraheze.org/wiki/Persona_5>
