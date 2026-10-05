---
name: cyx-mcp-figma
description: 把 Figma 接入 WorkBuddy —— 既能读设计稿，也能让 AI 直接在画布上画图/改稿，并系统排查连不上的原因。当用户说「接入 figma 的 mcp」「让 AI 画 figma」「figma mcp 连不上 / 不生效」「figma 插件连不上桥」「3055 端口没反应」「桥跑一会儿就断 / 桥进程没了」「figma 插件一直显示未连接」「在 figma 里生成一份设计稿」时使用；即使只说「figma 能不能接入」「figma 和 workbuddy 打通」「figma 网页版能不能用」也要先读本技能再回答，不要凭印象答。含三条路径的决策树（REST 只读 / 官方远程 MCP 白名单 / TalkToFigma 本地桥）、Bun 安装与 npm 镜像、桥的报文协议与自检探针脚本、让桥脱离会话常驻的守护脚本，以及「必须桌面端 + 必须先打开设计文件 + 隐藏目录找不到 manifest」这三个必踩的坑。
agent_created: true
display_name: "Figma MCP 接入器"
display_name_en: "Figma MCP Connector"
buddy-adapted: "2026-10-05"
owner: "Buddy（Lulu 的数字搭子）"
---

# cyx-mcp-figma：把 Figma 接进 WorkBuddy

Figma 接入有三个岔路口，能力差别很大。**先问清用户要「读」还是「画」，再动手** —— 选错路会浪费大量时间，尤其是官方远程 MCP 那条，它在本机一定连不上。

## 第一步：决策

| 用户想要 | 走哪条 | 结论 |
|---|---|---|
| 读设计稿：拉图层数据、导出图片、转代码 | **A. figma-developer-mcp**（REST API + Personal Access Token） | 可用 |
| 在画布上画/改：建 frame、写文字、改颜色、自动布局 | **B. Figma 官方远程 MCP**（`mcp.figma.com/mcp`） | **封死，不要尝试** |
| 同上 | **C. TalkToFigma**（本地 WebSocket 桥 + Figma 插件） | 可用 |

**一句话规则：只读走 A，要画走 C，B 直接跳过。**

用户说的是「接入 figma 的 mcp」这种含糊说法时，用这两句问清楚：
1. 「你是想把设计稿拿给 AI 分析／生成代码吗？」→ A
2. 「你是想让 AI 直接在画布上画东西吗？」→ C（顺便提醒他：**必须用 Figma 桌面端**，网页版不行）

## 路径 A：只读版

REST 接口 + PAT，能力是「把设计稿变成结构化数据 / 导出图片」，**不能改画布**。

```bash
# 验证 token 是否有效（独立于 MCP 先测，能把问题域缩小）
curl -s -k -m 20 -o /tmp/figma_me.json -w "HTTP=%{http_code}\n" \
  -H "X-Figma-Token: <figd_...>" https://api.figma.com/v1/me
```

判读：`401 Invalid token` 才是 token 错；**`403 Invalid scope` 说明 token 有效**，只是缺 `current_user:read` 这类与读设计稿无关的权限，不影响使用。

要求用户给出 Figma 文件链接，然后用它自带的两个工具：
- `get_figma_data` —— 拉取文件/节点的结构化数据
- `download_figma_images` —— 导出图片

配置要点：
- 输出目录用 `IMAGE_DIR` 环境变量显式指定，否则图片会散落到进程 cwd
- 加 `DO_NOT_TRACK: "1"` 关闭遥测（涉及设计稿这类敏感数据时尤其值得）

细节与验证记录见 `references/figma-readonly.md`。

## 路径 B：官方远程 MCP —— 为什么封死

**根因**：Figma 只允许它自家 [MCP Catalog](https://www.figma.com/mcp-catalog/) 白名单里的客户端连，WorkBuddy / CodeBuddy 不在名单里。三条实测证据：

| 测试 | 做法 | 结果 |
|---|---|---|
| 裸握手 | POST `https://mcp.figma.com/mcp` 发 `initialize` | `401`，`WWW-Authenticate` 要求 OAuth，scope 是 `mcp:connect` |
| 拿 PAT 冒充 | `X-Figma-Token` 与 `Authorization: Bearer` 两种头都试 | 均 `401`，Figma 明确回绝 `figd_` 令牌走 Authorization |
| 自助注册 OAuth 客户端 | POST `https://api.figma.com/v1/oauth/mcp/register`（DCR） | `403 Forbidden` → 拿不到 client_id |

白名单当时是 24 个客户端：Claude、ChatGPT、Codex、Cursor、VS Code、Xcode、Kiro、Warp 等，**没有 WorkBuddy**。

所以别在 OAuth 上耗时间。将来若 Figma 开放自助注册或把 WorkBuddy 加进名单，重跑上面三条即可确认 —— 原始命令见 `references/figma-readonly.md`。

## 路径 C：TalkToFigma —— 能画

架构是三段式，缺一不可：

```
WorkBuddy ──stdio──> MCP server ──ws://localhost:3055──> 桥 ──> Figma 插件 ──> 画布
  (44 个工具)      (bun run server.ts)                (bun run socket.ts)
```

### ⚠️ 头号坑：桥不能由 agent 的后台任务起

**症状**：桥跑了几分钟突然消失，探针报「无法连接桥」，用户正在画的图卡住。

**原因**：用 agent 的后台任务、或 `nohup ... &` 起的进程，仍属于调用方的会话 / 进程组，
会话一结束就被一起回收。实测同一条命令：一次活了 11 小时（会话空闲），一次只活 3 分钟。

**正解**：用 `setsid` 让它自成会话（父进程变 launchd），与调用方彻底解耦。

```bash
# 常驻启动（已在监听则跳过，幂等）
/usr/bin/python3 ~/.workbuddy/skills/cyx-mcp-figma/scripts/daemonize_bridge.py
# 或
sh ~/.workbuddy/skills/cyx-mcp-figma/scripts/start_bridge.sh --detach
```

原理与可调参数见脚本头部注释（`TTF_REPO` / `BUN_BIN` / `--force`）。

**已验证不可行的两条路**（别重复试）：

| 做法 | 结果 |
|---|---|
| `nohup bun run socket.ts &` | 拉起瞬间 `lsof` 能看到监听，但进程随后被回收 → 探测 `ECONNREFUSED` |
| `launchctl bootstrap/load`（含自建 LaunchAgent） | 在 agent 沙箱内报 `Bootstrap failed: 5: Input/output error` |

关于 LaunchAgent：**在 agent 里装不进去，但在用户自己的终端里可以**。
`~/Library/LaunchAgents/` 下的 plist 会在**下次登录时被 launchd 自动加载**，所以
「写好 plist + 让用户重新登录」也能达到开机自启 + 崩溃自拉（`KeepAlive`）的效果。

### 插件没有自动重连（上游原版）

桥一重启，插件的 WS 就断了，而原版 `ui.html` 的 `onclose` 只置灰状态、**不重连**，
所以每次桥重启后都要用户手动再点一次 Connect。

本机已打补丁（`ui.html` + 桌面副本，备份 `ui.html.bak.prereconnect`）：
`onclose` 里带退避重试（1s 起、上限 5s），手动点 Disconnect 不触发重连。
**补丁只在插件重新运行时生效** —— Figma 每次运行开发插件都会重读磁盘上的 `ui.html`，
所以关掉面板重开即可，不必重新 Import。

### 每次开工的前置检查

```bash
lsof -nP -iTCP:3055 -sTCP:LISTEN              # 桥在不在
~/.bun/bin/bun --version                      # Bun 在不在
ls ~/.workbuddy/mcp-servers/talktofigma/src/talk_to_figma_mcp/server.ts   # 仓库在不在
ls -d /Applications/Figma.app                 # 桌面端在不在（网页版不行）
```

### 端到端自检（最有价值的一招）

不用等新会话加载 MCP 工具，直接用本技能带的探针绕过客户端直连桥：

```bash
node ~/.workbuddy/skills/cyx-mcp-figma/scripts/probe_bridge.mjs get_document_info
```

| 输出 | 含义 |
|---|---|
| `[3/3] 插件已连接且正常响应:` + 文档结构 | **三段全通**，可以画了 |
| `超时：频道 "workbuddy" 里没有 Figma 插件` | 插件没运行，或没点 Connect |
| `超时：频道里检测到有客户端加入了，但对方没回应命令` | 连上了但插件卡死，关掉面板重开 |
| `无法连接桥` | 桥没起，先起桥 |

探针也是**命令执行器** —— 在用户还没开新会话时，可以用它直接往画布上发指令：

```bash
node ~/.workbuddy/skills/cyx-mcp-figma/scripts/probe_bridge.mjs \
  create_frame '{"name":"iPhone","x":0,"y":0,"width":375,"height":812}'
```

### 谁做什么

**agent 可以自己做的：**

1. **起桥**（常驻）：`python3 scripts/daemonize_bridge.py`，然后 `lsof -nP -iTCP:3055 -sTCP:LISTEN` 确认
2. **自检**：跑探针确认「插件 → 桥」这一段通不通

**必须用户亲自做的（agent 碰不到 Figma 的界面）：**

1. **装插件**（仅一次，**必须桌面端**）：进入一个设计文件 → `Plugins → Development → Import plugin from manifest…` → 选 `~/Desktop/TalkToFigma插件/manifest.json`
2. **连接**：面板端口填 `3055` → Connect → 看到绿色 `Connected to WorkBuddy bridge in channel: workbuddy`

> 桥重启后插件**不会自动恢复**（补丁版会自动重连；未打补丁的老版本必须手动再点一次 Connect）。

### 能干什么（44 个工具）

| 类别 | 代表工具 |
|---|---|
| 读画布 | `get_document_info` `get_selection` `get_node_info` `read_my_design` |
| 创建图形 | `create_frame` `create_rectangle` `create_text` `create_section` |
| 改样式 | `set_fill_color` `set_stroke_color` `set_corner_radius` `set_image_fill` |
| 排版布局 | `set_layout_mode` `set_padding` `set_axis_align` `set_item_spacing` |
| 文本 | `set_text_content` `set_multiple_text_contents` `scan_text_nodes` |
| 结构 | `move_node` `clone_node` `resize_node` `delete_node` `set_parent` |
| 组件 | `get_local_components` `create_component_instance` `set_instance_overrides` |
| 导出 / 标注 | `export_node_as_image` `set_annotation` `get_annotations` |

### 从零部署（换机器或重装时）

见 `references/talktofigma-deploy.md` —— 含 Bun 安装（GitHub Releases 慢时的 npmmirror 备选）、bunfig 镜像源、mcp.json 条目、桥的报文协议、插件的固定频道补丁与本地改名。

## 坑（都是实测踩过的）

### ⚠️ 用脚本批量绘图的 5 个静默失败（最高频，先看这条）

用 Node 脚本连桥批量画图时，下面几类错误**不会报错、只在导出的预览图上才看得出来**，而且一次就毁掉整页观感。踩全过一遍，照这条清：

| # | 现象 | 真因 | 正确写法 |
|---|---|---|---|
| 1 | 某些矩形变成**浅灰 `#D9D9D9` 实心块**（输入框、图标、分割线发白） | `create_rectangle` **不接受** `fillColor` 参数，不设置就保留 Figma 默认灰底 | 创建后单独 `set_fill_color`；**不传填充的必须显式清掉** |
| 2 | 图标变成 **100×100 的巨圆**，糊住半个画布 | 封装函数参数名和调用方不一致（如签名写 `w/h`、传参写 `width/height`）→ 解构出 `undefined` → 插件回退**默认尺寸 100×100** | 参数名与 `create_ellipse` 原生一致（`width/height`），或封装里写 `width ?? w` 双兼容 |
| 3 | `set_stroke_color` / `set_corner_radius` 报错或无效 | 参数是**嵌套**结构且名字不同：描边是 `{nodeId, color:{r,g,b,a}, weight}`（不是 `strokeColor`/`strokeWeight`），圆角是 `{nodeId, radius}`（不是 `cornerRadius`） | 先把参数名 grep 一遍再写封装 |
| 4 | 坐标探针判断反了，**子元素全被丢到父级外面裁掉**，卡片一片空白 | `get_node_info` 返回的是 **REST 格式，顶层没有 `x/y/width/height`**，只有 `absoluteBoundingBox` | 用 `absoluteBoundingBox` 实测，别读 `x/y` |
| 5 | 背景光斑/网格边缘出现**生硬直角** | 节点超出父 Frame 边界被 `clipsContent` 裁掉，或模糊半径不够 | 装饰元素让父 Frame 溢出可见，或把模糊半径调大 |

**插件没有的命令要提前认命**：没有「清除填充」（用全透明渐变等效：`set_gradient_fill` + 两个 `alpha=0` 的 stop）、没有旋转、没有线段、没有路径/多边形。所以**信封的 V 形折线、斜线、六边形都画不出来** —— 别硬凑，改成能表达同样语义的基础图形（圆角矩形轮廓、圆环）。

**收尾必须加三层自检**（写进脚本，每次跑完打印）：

```js
// 1) 父容器绝对框对不对
// 2) 抽查一个文字节点的绝对坐标与期望值比对
// 3) 图标尺寸守卫：凡是 name 含 icon 的节点，宽高 > 26 就是漏传尺寸了
```

第 3 条能一眼抓出上面第 2 类静默失败，性价比最高。

### 三个「找不到入口」的坑，按发生频率排

1. **必须桌面端**。本地开发插件（`Import plugin from manifest`）只有 Figma 桌面端能导入，浏览器版整个 `Plugins → Development` 菜单都不存在（Figma 官方论坛确认）。
2. **必须先打开设计文件**。插件菜单是上下文相关的，停在文件列表首页时菜单栏只有 `Figma / File / Edit / View / Window / Help`；打开设计文件后才出现 `Plugins`。判断「真的进去了」的标准是：左侧有图层/资源面板、中间是画布。
3. **隐藏目录里翻不到 manifest**。插件在 `~/.workbuddy/...`，点开头的目录在 macOS 文件选择框里默认隐藏。解法：在弹窗里按 `⌘⇧G` 粘贴绝对路径，或从桌面副本 `~/Desktop/TalkToFigma插件/` 进。

### 别点错导入入口

右上角 `More → Import` 是导入 `.fig` 设计文件的，选 `manifest.json` 会报 `Unsupported file format`。必须走 `Plugins → Development`。

### 本机代理会拦掉本地连接

本机有 `127.0.0.1:7890` 代理，MCP 的 `env` 里必须加 `NO_PROXY: "localhost,127.0.0.1,::1"`，否则桥的 WS 连接会被代理带走，表现为「明明在监听却连不上」。

### MCP 工具不会热加载

新写入的 server 在**当前对话里调不到**（工具是会话启动时加载的），必须新开一个对话。在那之前用探针脚本兜底。另外别忘了提醒用户去连接器管理页右上角的「自定义连接器」点**信任**，否则开关是关的。

### 插件是「第二套代码」，改动要两份同步

`manifest.json` / `ui.html` 不在 `mcp.json` 里。改完后：

- **两份都要改**：源目录 + 桌面副本（Figma 实际加载的是桌面那份）
- `manifest.json` 的 `id` **绝不能改**，否则 Figma 会当成全新插件
- 改完要在 Figma 里**重新 Import + 关掉重开插件面板**（UI 是启动时加载的）
- 想改名去掉原仓库的 `Cursor` 品牌：改 `manifest.name` + `ui.html` 文案。**不能动** CSS 的 `cursor: pointer`、About 页指向原仓库的 GitHub 链接（改了会 404）、以及目录名（被路径引用）

### 网页版相关（用户常问，别答错）

- 本地开发插件**只能桌面端**；但同一个插件若已发布到社区（`figma.com/community/plugin/<manifest.id>`，id 一致即同一个），**网页版可以安装并运行**
- 代价：社区版带不上任何本地补丁（改名、固定频道都不生效），频道名是随机的
- `ws://localhost:<port>` 在 https 页面能连（浏览器把 localhost 视作 secure context），但 Figma 侧还要求 manifest `networkAccess.allowedDomains` 里有该地址
- **数据是互通的**：桌面端与网页版访问同一个云端文件，改动双向实时同步；但**插件只运行在启动它的那个客户端**，不跟随文件

## 排错速查

| 症状 | 最可能的原因 | 处置 |
|---|---|---|
| 探针报「频道里没有插件」 | 面板没开 / 没点 Connect | 让用户重开面板点 Connect |
| 探针报「有客户端但没回应」 | 那个客户端是 MCP server 不是插件（两者同频道） | 别误判；确认插件面板的绿色状态行 |
| 探针报「无法连接桥」 | 桥没起，或**被会话回收了** | `python3 scripts/daemonize_bridge.py` 常驻起桥 |
| 桥跑几分钟就消失 | 用了后台任务 / `nohup &` 起桥 | 改用 `--detach`（setsid 脱离会话） |
| `launchctl bootstrap` 报 I/O error 5 | agent 沙箱不允许写 gui 域 | 交给用户在自己终端执行；或重登让 plist 自动加载 |
| 桥重启后面板一直灰 | 原版插件不会自动重连 | 关掉面板重开（已打重连补丁则自动恢复） |
| 面板 Connect 一直转圈 | 桥没起 / 代理拦了 localhost | 查 3055 监听；确认 `NO_PROXY` |
| 菜单栏没有 `Plugins` | 停在文件列表首页 | 先打开一个设计文件 |
| 文件框里翻不到 manifest | 目录以点开头，被隐藏 | `⌘⇧G` 粘贴绝对路径 |
| 新对话里调不到工具 | 没重启对话 / 没点信任 | 新开会话；连接器管理点信任 |
| 插件名/界面文案还是旧的 | 改了文件但没重装插件 | 重新 Import + 重开面板 |
| 报「需要 Full seat」 | 误用了官方远程 MCP | 改走路径 C |

## 关键路径（本机）

| 用途 | 路径 |
|---|---|
| MCP 配置 | `~/.workbuddy/mcp.json` |
| 只读 server | `~/.workbuddy/mcp-servers/figma/` |
| 可画 server + 桥 | `~/.workbuddy/mcp-servers/talktofigma/` |
| Bun | `~/.bun/bin/bun` |
| 插件源目录 | `~/.workbuddy/mcp-servers/talktofigma/src/cursor_mcp_plugin/` |
| 插件桌面副本（Figma 加载这个） | `~/Desktop/TalkToFigma插件/` |
| 起桥脚本（人工双击） | `~/.workbuddy/mcp-servers/talktofigma/启动Figma桥.command` |
| 起桥（常驻，给 agent 用） | `~/.workbuddy/skills/cyx-mcp-figma/scripts/daemonize_bridge.py` |
| 排错经验记录 | `~/.workbuddy/mcp-servers/talktofigma/使用说明.md` |
| 探针 | `~/.workbuddy/skills/cyx-mcp-figma/scripts/probe_bridge.mjs` |
| 自建 LaunchAgent（重登后生效） | `~/Library/LaunchAgents/com.workbuddy.talktofigma-bridge.plist` |

## 相关技能

- **`mcp-install-cn`** —— 通用 MCP 接入（本机网络环境、npx 型改造、`NODE_OPTIONS` shim 拖慢启动的坑、握手验证）。本技能是它在 Figma 场景的专精版，通用手法以那边为准。
- **`cyx-github-skill`** —— 若要安装的其他 MCP 来自 GitHub 仓库，先走那边的安全审查。
