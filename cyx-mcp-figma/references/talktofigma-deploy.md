# TalkToFigma 从零部署手册

本文是 `cyx-mcp-figma` 路径 C 的完整部署流程。换机器、重装、或上游大版本更新后照此重做。
所有数据来自 2026-10-05 在 macOS 上的实测。

## 0. 前置条件

- macOS（本机 arm64）
- **Figma 桌面端**已安装 —— 本地开发插件不支持网页版
- 能出网（要下载 Bun ~24MB、npm 依赖 ~167 个包）
- 本机有 HTTP 代理 `127.0.0.1:7890`，联网命令都需要 `dangerouslyDisableSandbox: true`

## 1. 安装 Bun

官方一键脚本 `curl -fsSL https://bun.sh/install | bash` 走 GitHub Releases，
本机实测只有 ~430KB/s，且**管道方式容易被中断**。改成分步执行更稳：

```bash
# 1) 先确认架构：arm64 → darwin-aarch64；x64 → darwin-x64
uname -m

# 2) 下载二进制包（24MB）
curl --fail --location --progress-bar -o /tmp/bun.zip \
  https://github.com/oven-sh/bun/releases/latest/download/bun-darwin-aarch64.zip

# 3) 解压并装到用户目录（不碰系统）
cd /tmp && rm -rf bunx && mkdir bunx && unzip -oqd bunx bun.zip
mkdir -p ~/.bun/bin
cp "$(find /tmp/bunx -type f -name bun | head -1)" ~/.bun/bin/bun
chmod +x ~/.bun/bin/bun

# 4) 验证（实测装到 1.4.2）
~/.bun/bin/bun --version
```

**备选源**（GitHub 太慢时的第二条线）：npmmirror 上有 `@oven/bun-darwin-aarch64`
这个 npm 包，里面就是同一份二进制：

```bash
curl -sL -o /tmp/bun-npm.tgz \
  https://registry.npmmirror.com/@oven/bun-darwin-aarch64/-/bun-darwin-aarch64-<版本>.tgz
```

用哪个版本先去 `https://registry.npmmirror.com/@oven/bun-darwin-aarch64` 查 `dist-tags.latest`。

## 2. 配置 npm 镜像

本机 `registry.npmjs.org` 被拦截（跳转 baidu），写一份全局 bunfig：

`~/.bunfig.toml`
```toml
[install]
registry = "https://registry.npmmirror.com"
```

## 3. 部署仓库

```bash
DEST="$HOME/.workbuddy/mcp-servers/talktofigma"
mkdir -p "$DEST"

# 用 codeload 拉 tarball（本机比 git clone 稳）
curl -sL -m 60 -o /tmp/ttf.tgz \
  https://codeload.github.com/grab/cursor-talk-to-figma-mcp/tar.gz/refs/heads/main
tar xzf /tmp/ttf.tgz -C /tmp
cp -R /tmp/cursor-talk-to-figma-mcp-main/. "$DEST/"

# 装依赖（实测 167 个包、7.4 秒）
cd "$DEST" && ~/.bun/bin/bun install
```

关键文件校验：

```bash
for f in src/socket.ts src/talk_to_figma_mcp/server.ts \
         src/cursor_mcp_plugin/manifest.json src/cursor_mcp_plugin/code.js \
         src/cursor_mcp_plugin/ui.html; do
  [ -f "$DEST/$f" ] && echo "OK  $f" || echo "缺失 $f"
done
```

> 上游 `src/socket.ts` **写死依赖 Bun**（`import { Server } from "bun"`），所以桥只能用 Bun 跑，
> 换 Node 需要重写。好在 Bun 安装成本不高，不值得移植。

## 4. 写入 mcp.json

`~/.workbuddy/mcp.json` → `mcpServers.talktofigma`：

```json
"talktofigma": {
  "command": "/Users/lulu/.bun/bin/bun",
  "args": [
    "run",
    "/Users/lulu/.workbuddy/mcp-servers/talktofigma/src/talk_to_figma_mcp/server.ts"
  ],
  "env": {
    "HOME": "/Users/lulu",
    "NODE_OPTIONS": "",
    "NO_PROXY": "localhost,127.0.0.1,::1"
  }
}
```

三个 `env` 都不是可选的：

| 变量 | 为什么必须 |
|---|---|
| `NODE_OPTIONS: ""` | WorkBuddy 会注入沙箱 shim，加载后阻塞 3–5 秒才响应。置空后实测从 4.7s 降到 0.28s |
| `NO_PROXY` | 本机 7890 代理会把 `localhost` 的 WS 连接也带走，表现为「桥明明在监听却连不上」 |
| `HOME` | 让 server 能找到用户的配置 |

## 5. 桥启动脚本

`~/.workbuddy/mcp-servers/talktofigma/启动Figma桥.command`（双击运行，中文名方便用户找）：

```sh
#!/bin/sh
cd "$HOME/.workbuddy/mcp-servers/talktofigma"
exec "$HOME/.bun/bin/bun" run src/socket.ts
```

```bash
chmod +x "启动Figma桥.command"
```

通用模板见本技能 `scripts/start_bridge.sh`。

## 6. 验证 MCP 服务端能起来

注意 **macOS 没有 `timeout` 命令**，要用「printf + sleep」保活 stdin：

```bash
cd /tmp && {
  printf '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"wb-verify","version":"1.0"}}}\n'
  sleep 3
  printf '{"jsonrpc":"2.0","method":"notifications/initialized"}\n'
  printf '{"jsonrpc":"2.0","id":2,"method":"tools/list"}\n'
  sleep 6
} | HOME=/Users/lulu NO_PROXY="localhost,127.0.0.1,::1" NODE_OPTIONS="" \
    ~/.bun/bin/bun run "$HOME/.workbuddy/mcp-servers/talktofigma/src/talk_to_figma_mcp/server.ts" \
    2>/tmp/tt_err.log | /Users/lulu/.workbuddy/binaries/python/versions/3.13.12/bin/python3 -c "
import sys, json
for line in sys.stdin:
    line = line.strip()
    if not line: continue
    try: j = json.loads(line)
    except Exception: continue
    r = j.get('result')
    if isinstance(r, dict):
        if 'tools' in r:
            print('工具总数:', len(r['tools']))
            for t in r['tools']: print('  -', t['name'])
        elif 'serverInfo' in r:
            print('SERVER:', json.dumps(r['serverInfo'], ensure_ascii=False))
"
```

预期：`SERVER: {"name":"TalkToFigmaMCP","version":"1.0.0"}` + 工具总数 44。

**要完整、实时的工具清单就用这个命令取**，不要凭记忆背工具名——版本更新后会变。

## 7. 加载 Figma 插件

用户必须在 Figma 桌面端**手动**操作（Agent 无法代劳）：

1. 打开 Figma 桌面端，**进入一个设计文件**（停在文件列表首页时菜单栏没有 `Plugins`）
2. `Plugins → Development → Import plugin from manifest…`
3. 选择 manifest.json：
   - 源路径 `~/.workbuddy/mcp-servers/talktofigma/src/cursor_mcp_plugin/manifest.json`
   - 但 `~/.workbuddy` 是隐藏目录，文件选择框里翻不到 → 按 `⌘⇧G` 粘贴绝对路径，
     或从桌面副本 `~/Desktop/TalkToFigma插件/manifest.json` 进
4. 之后每次从 `Plugins → Development → <插件名>` 启动面板
5. 面板里端口填 `3055` → Connect

> **为什么要放桌面副本**：`~/.workbuddy` 以点开头，macOS 文件选择框默认不显示隐藏目录，
> 用户手动翻一定找不到。本机 iCloud 桌面同步开着，**符号链接会显示异常，必须用实体副本**。
> 代价是副本是快照 —— 更新源插件后要重新复制并重新 Import。

## 8. 固定频道补丁（可选但强烈建议）

上游 `ui.html` 的 `generateChannelName()` 每次连接生成 **8 位随机频道名**，
意味着每开一次面板都要人工把频道名抄给 Agent。改成固定值可以省掉这一步：

```js
function generateChannelName() {
  return "workbuddy";
}
```

改动前备份 `ui.html.bak.orig`。**两份副本都要改**（源目录 + 桌面副本）。

## 9. 本地改名（去掉上游的 Cursor 品牌）

上游是为 Cursor 写的，`manifest.json` 的 `name` 和面板文案全是 Cursor，容易让用户困惑。

改动范围：`manifest.json`（`name` + `networkAccess.reasoning`）、`ui.html`（title、正文文案、
断线提示里的启动命令、`updateMcpConfig()` 生成的示例 JSON）、`code.js` 首行注释。

**不能动**：
- CSS 的 `cursor: pointer`（鼠标样式，与品牌无关）
- About 页指向原仓库的 GitHub 链接（改了会 404）
- `manifest.json` 的 `id`（改了 Figma 会当成全新插件）
- 目录名 `cursor_mcp_plugin`（被 Figma 按路径引用，改了要重新导入，收益为零）

改完要在 Figma 里 `Manage plugins in development` 移除旧条目 → 重新 Import → 重开面板。

## 10. 报文协议（写探针、排查时必备）

`src/socket.ts` 是个纯转发器，协议很简单：

| 方向 | 报文 |
|---|---|
| 入频道 | `{ type: "join", channel }` |
| 发命令 | `{ id, type: "message", channel, message: { id, command, params } }` |
| 插件回包 | `{ id, type: "message", channel, message: { id, result } }` |
| 桥转发给同频道**其他人** | `{ type: "broadcast", message: { id, result }, sender: "peer", channel }` |
| 桥的成员变动通知 | `{ type: "system", message: "..." }`（字符串，含 `new user has joined`） |
| 入频道回执 | `{ type: "system", message: { result: ... } }`（对象） |

关键点：
- 桥**只转发给发送者以外**的同频道成员；频道里没有对端时日志打 `No other clients`
- 所以探针必须**先 join、等回执、再发命令**，否则会被自己的消息绕晕
- 判断「频道里有没有插件」不能靠 `broadcast` 是否到达，要靠**是否收到过
  `new user has joined`** —— 这正是探针脚本区分两种超时的依据

本技能 `scripts/probe_bridge.mjs` 就是按这套协议实现的，可直接复用。

## 11. 部署后的验收清单

```bash
~/.bun/bin/bun --version                                       # Bun 可用
lsof -nP -iTCP:3055 -sTCP:LISTEN                               # 桥在监听
python3 -c "import json;print(list(json.load(open('$HOME/.workbuddy/mcp.json'))['mcpServers']))"  # 配置已写入
node ~/.workbuddy/skills/cyx-mcp-figma/scripts/probe_bridge.mjs get_document_info   # 端到端通
```

最后一条返回 Figma 文档结构 = 插件 → 桥 → 调用方三段全通，**可以开始画图了**。

别忘了提醒用户：新写入的 MCP **不会自动生效**，要去连接器管理页右上角的「自定义连接器」
对 `talktofigma` 点**信任**；MCP 工具在**新开对话**里才会挂上。
