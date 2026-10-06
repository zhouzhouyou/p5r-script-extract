# P5R Script Extract

把 **Persona 5 Royal（女神异闻录5 皇家版）中文版**的游戏脚本，整理成可阅读、可检索、
可追溯的对话剧本，并做成一个纯前端的剧本阅读器。

- **在线阅读器**：<https://zhouzhouyou.github.io/p5r-script-extract/>
  （GitHub Pages，默认打开阅读器；`t` 键可切换「时间线／原序」两种模式）
- **纯文本剧本**：`P5R_对话脚本/` —— 15 万条对话，按来源目录与章节归档
- **整理工具**：`tools/` —— 从原始脚本到成品的完整可复现管线

---

## 这是什么，为什么需要它

P5R 的脚本在游戏里是**二进制**的，玩家看到的中文原文并不以文本形式存在：

| 游戏内文件 | 实际内容 |
| --- | --- |
| `.BF` | flow script（流程脚本）二进制，**对话文本内嵌在其 `MessageScriptSection` 里** |
| `.BMD` / `.MSG` | 独立的 message script 二进制 |

所以「拿到对话」这件事本身需要两步：**反编译**，再把反编译出的
MessageScript 文本（`.msg`）**结构化成可读剧本**。

游戏里并没有一个叫 `P5RScript` 的文件夹——那是**从游戏本体提取出来的**（见下节）。
本仓库不包含完整的游戏素材，只包含整理成果、工具，以及少量用于说明格式的样本。

---

## 数据来源与工具链（重要）

### 1. 从游戏本体提取原始脚本

`P5RScript` 目录（`.BF` / `.BMD` 等）是用 **CriFsV2Lib** 解包 CPK 得到的：

- CriFsV2Lib：<https://github.com/Sewer56/CriFsV2Lib>
- 提取步骤参考：<https://animatedswine37.github.io/persona-modding-docs/docs/getting-started/extracting-files/>
  （Persona Modding Docs —— Extracting Files）

> 本仓库**不包含**这些原始文件（版权属于 Atlus）。想复现请自备正版游戏，
> 用上面的工具自行提取。
>
> 唯一的例外是 `samples/`：少量 `.BF` 及其反编译结果，**仅用于说明文件格式**，
> 覆盖「协助人剧情」与「日常与城镇」两类。完整数据需自行提取。

### 2. 反编译：Atlus Script Tools

- 仓库：<https://github.com/tge-was-taken/Atlus-Script-Tools>
- 作者：TGE · 许可：GNU GPL
- 用途：读取 `.BF`（flow script）与 `.BMD`/`.MSG`（message script），
  反编译成 `.flow` / `.msg` 文本

它支持 P5R，命令行形如：

```powershell
AtlusScriptCompiler -Decompile -In "script.bf" -Library P5R -Encoding P5R_CHS
```

**字符集**：P5R 中文版用的是游戏自定义字符集（不是常见编码），
对应工具里的 `Charsets\P5R_CHS.tsv`（繁体为 `P5R_CHT`）。

### 3. 本仓库的整理管线

`tools/` 里的工具按顺序做四件事，全部可重复执行：

```
P5RScript（原始）          用 CriFsV2Lib 从游戏提取
      │
      ├─ batch_msg/        → _staging/decompiled/*.msg + *.h      （对话文本）
      └─ batch_flow/       → _staging/flow/*.flow                 （流程与分支）
      │
      ├─ build_script.py   → P5R_对话脚本/*.txt                    （纯文本剧本）
      ├─ build_timeline.py → _staging/timeline.json                （选项分支）
      └─ build_reader.py   → reader/data/*.json                    （阅读器数据）
```

`batch_msg` 与 `batch_flow` 都是**直接调用 `AtlusScriptLibrary.dll`**（反射），
输出与官方 `AtlusScriptCompiler -Decompile -Library P5R -Encoding P5R_CHS`
**逐字节一致**，但省去了每个文件启动一次进程的开销（7000 个文件从数小时降到几分钟）。

---

## 目录说明

```
README.md                 本文档
SOURCES.md                数据与工具出处、许可证、复现所需的全部外链
LICENSE                   本仓库代码的许可（MIT；游戏素材与工具另见 SOURCES.md）
index.html                重定向到 reader/（供 GitHub Pages 作为默认入口）

reader/                   ★ 前端剧本阅读器（GitHub Pages 就是它）
├── index.html            阅读器本体，纯前端无依赖
└── data/
    ├── index.json        2514 个场景的索引 + 说话人/变量词表
    ├── scenes/*.json     对话正文，按分类拆分、按需加载
    └── timeline/*.json   选项分支时间线，按分类拆分

P5R_对话脚本/              ★ 纯文本剧本，按来源文件归档
├── 00_总目录.md          分类 → 文件 → 条数 的索引
├── FIELD/                NPC 对话、大宅日常、门/场景描写
├── EVENT_DATA/E000..E900 主线与支线剧情事件（按章节分）
├── SCRIPT_FIELD/         早期流程脚本对话
├── CAMP/                 同伴聊天
├── BATTLE/               战斗前后与敌人对白
├── FACILITY/             天鹅绒房间等
└── MYPALACE/             我的宫殿（第三学期追加）

samples/                  少量原始文件与其反编译结果，仅供说明格式
├── raw/                  .BF 原始二进制
└── decompiled/           对应的 .msg / .msg.h（可读文本）

tools/                    可复现的整理工具（详见 tools/README.md）
```

---

## 阅读器

纯前端、无构建、无依赖，一个 `index.html` + 几个 JSON。

### 两种模式

右上角按钮切换（快捷键 `t`）：

| 模式 | 内容 |
| --- | --- |
| **时间线**（默认） | 按流程脚本的先后顺序显示，选项后面直接画出各分支走向 |
| **原序** | 按 `.msg` 文件里的原始顺序平铺 |

时间线模式下，一个选项长这样：

```
选择 2 项
  1  你讨厌课长吗？
  2  课长是怎样的人？

⎇ var3 == 0 / else
  → 选「你讨厌课长吗？」  (var3 == 0)
      【系长机器人】那种家伙有谁会喜欢啊！……
  → 其他选择
      【系长机器人】他就是个讨人厌的家伙啦！……

↓ 各分支在此汇合，后续相同
  【系长机器人】什么！？
```

其他行为：

- **各分支末尾相同的内容会合并**，只显示一次
- **无法静态求解的条件原样展示**（`BIT_CHK(...)` / `CHK_DAYS(...)` 等）
- **游戏状态分支默认折叠**（它们占全部分支的 96%），点击展开，内容不丢
- **选项永不折叠**，且只要分支通向选项就保持展开
- **单项 `[sel]` 不当成选择**（游戏里只是按一下确认），按普通文本行显示
- **流程与文本编号对不上的场景自动退回原序**，避免指向错误台词

### 本地运行

浏览器不允许 `file://` 页面读取本地 JSON，需要一个本地服务器：

```powershell
cd reader
python -m http.server 8777 --bind 127.0.0.1
# 打开 http://127.0.0.1:8777/
```

---

## 统计

| 项目 | 数量 |
| --- | ---: |
| 处理的源文件 | 7217（`.BF` 5182 / `.BMD` 2019 / `.MSG` 12） |
| 成功反编译的对话 | 7200 |
| 成功反编译的流程脚本 | 5181 |
| 提取出的对话条目 | 154504 |
| 纯文本剧本文件 | 5581 |
| 阅读器场景数 | 2514 |
| 其中按时间线渲染 | 1132 |
| `[sel]` 选项块 | 10414（含 607 个单项确认） |

---

## 已知限制

- **流程与文本编号并不总能对齐。** 一个场景可能由多个源文件拼成，各自的消息编号
  从 0 重新开始。阅读器用「`{sel: n}` 必须落在一条真的是 `sel` 的对话上」作为
  结构性判据，对不上就整篇退回原序——实测 1814 个有流程数据的场景中 682 个如此。
  想把这些也救回来，需要还原多文件偏移规则，目前没做。
- **部分条件无法静态求值**，如 `SEL((19 + sVar2))`、`MSG(sVar1, 0)`，只能原样展示。
- **未纳入**战斗 UI、教程、系统公告、存档/网络等非剧情文本。
- **译名修正**：中文版把「坂本龙司」误写成「礼司」，本仓库已统一修正
  （见 `tools/apply_corrections.py`，记录在阅读器的 `dataFixes` 字段里）。

---

## 版权与免责

- 游戏脚本、角色名、台词等**版权归 Atlus / SEGA 所有**。本仓库对脚本的整理
  仅供**学习、检索与无障碍阅读**之用，不得用于商业用途。
- `samples/` 内的原始文件同样是游戏素材，仅为说明格式而收录极少量。
- 本仓库自有的整理代码以 MIT 许可发布，详见 [LICENSE](LICENSE)。
- 第三方工具与数据的出处、许可证见 [SOURCES.md](SOURCES.md)。

如果版权方认为本仓库有不当之处，请提 issue，会立即处理。
