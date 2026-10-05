# 只读路径（REST + PAT）与官方远程 MCP 的探测记录

本文件覆盖 `cyx-mcp-figma` 的路径 A 细节，以及路径 B 为什么封死的完整证据。
将来 Figma 政策变化时，按第 4 节重跑即可复检。

## 1. 路径 A：figma-developer-mcp（只读）

**能力边界**：通过 Figma REST API 读设计稿，转成结构化数据交给 AI 分析、写代码、导出图片。
**不能修改画布** —— 这是它和 TalkToFigma 的本质区别。

**典型适用场景**：
- 「把这个设计稿转成 React 组件」
- 「分析这个页面的图层结构，告诉我用了哪些颜色和字号」
- 「把这些图标导出成 SVG」

### 1.1 本机现状（2026-10-05）

| 项 | 值 |
|---|---|
| 安装位置 | `~/.workbuddy/mcp-servers/figma/` |
| 包名 | `figma-developer-mcp` |
| 暴露工具 | 2 个：`get_figma_data`、`download_figma_images` |
| 配置 | `~/.workbuddy/mcp.json` → `figma` 条目 |

### 1.2 Token 的获取与验证

Figma → Settings → Security → Personal access tokens，创建后形如 `figd_xxxxx`。

**先独立验证 token，再查 MCP** —— 能把问题域一刀切开：

```bash
curl -s -k -m 20 -o /tmp/figma_me.json -w "HTTP=%{http_code}\n" \
  -H "X-Figma-Token: figd_xxxxx" https://api.figma.com/v1/me
head -c 300 /tmp/figma_me.json
```

| 返回 | 含义 | 处置 |
|---|---|---|
| `200` | token 有效 | 继续查 MCP 配置 |
| `403` + `Invalid scope` | **token 有效**，只是缺某个权限（如 `current_user:read`） | 不影响读设计稿，可忽略 |
| `401` + `Invalid token` | token 真的错了 | 重新生成 |

> 实测坑：本机 token 因为缺 `current_user:read` 返回 403，很容易被误判成「token 失效」。
> 看报错正文里列出的 scope 名字，再决定要不要去 Figma 补勾选。

### 1.3 配置要点

```json
"figma": {
  "command": "/usr/local/bin/node",
  "args": ["/Users/lulu/.workbuddy/mcp-servers/figma/node_modules/figma-developer-mcp/dist/bin.js", "--stdio"],
  "env": {
    "HOME": "/Users/lulu",
    "FIGMA_API_KEY": "figd_xxxxx",
    "IMAGE_DIR": "/Users/lulu/.workbuddy/mcp-servers/figma/images",
    "DO_NOT_TRACK": "1",
    "NODE_OPTIONS": ""
  }
}
```

- `IMAGE_DIR` —— 不指定的话 `download_figma_images` 会把图片落到进程 cwd，到处散
- `DO_NOT_TRACK` —— 关闭遥测；涉及设计稿这类敏感数据时值得加
- `NODE_OPTIONS: ""` —— 见 `mcp-install-cn` 里的沙箱 shim 坑

### 1.4 用法

丢一个 Figma 文件/节点链接给 Agent：

- `get_figma_data` —— 拉结构化数据（图层树、样式、文本、布局）
- `download_figma_images` —— 导出指定节点为图片

## 2. 路径 B：Figma 官方远程 MCP —— 封死

**端点**：`https://mcp.figma.com/mcp`
**宣称能力**：带 `use_figma` / `generate_figma_design`，AI 能直接在画布上建 frame、组件、变量。
**它支持**：Claude、ChatGPT、Codex、Cursor、VS Code、Xcode、Kiro、Warp 等 —— 见
[figma.com/mcp-catalog](https://www.figma.com/mcp-catalog/)，**共 24 个，没有 WorkBuddy / CodeBuddy**。

## 3. 探测证据（2026-10-05 实测）

三条独立路径全部失败，说明这不是配置问题，而是 Figma 的准入策略。

### 3.1 裸握手 → 401，只认 OAuth

```bash
curl -s -k -i -m 25 -X POST https://mcp.figma.com/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"WorkBuddy","version":"1.0"}}}'
```

响应头 `WWW-Authenticate` 指向 OAuth 元数据，scope 为 `mcp:connect`。

### 3.2 拿 PAT 冒充 → 均 401

`X-Figma-Token: figd_xxx` 和 `Authorization: Bearer figd_xxx` 两种头都试过，
Figma 明确回绝 —— 大意是「`figd_` 开头的令牌不能用于 Authorization」。

### 3.3 自助注册 OAuth 客户端（DCR） → 403

```bash
curl -s -k -m 25 -X POST https://api.figma.com/v1/oauth/mcp/register \
  -H "Content-Type: application/json" \
  -d '{"client_name":"WorkBuddy","redirect_uris":["http://127.0.0.1:8765/callback"],"grant_types":["authorization_code","refresh_token"],"response_types":["code"],"token_endpoint_auth_method":"client_secret_basic"}'
```

返回 `403 Forbidden` —— 拿不到 `client_id`，OAuth 流程根本没法起步。

### 3.4 顺带确认：WorkBuddy 客户端没实现 MCP OAuth

在 `/Applications/WorkBuddy.app/Contents/Resources/app.asar` 里检索
`oauth-protected-resource`、`authorization_endpoint`、`code_challenge` 等标识，均无命中。
所以即便 Figma 开放 DCR，客户端侧也还需要补 OAuth 能力。

## 4. 复检方法（政策变化时跑这一套）

三条命令按顺序跑，全部通过才说明这条路打开了：

1. 3.1 的握手返回 `200` + `serverInfo`（而非 401）
2. `POST https://api.figma.com/v1/oauth/mcp/register` 返回 200/201 并给出 `client_id`
   （若仍 403，去看 catalog 页面有没有把 WorkBuddy 加进白名单）
3. 客户端侧检索 `oauth-protected-resource` 有命中（说明 WorkBuddy 支持远程 MCP 的 OAuth 流程）

**在此之前，需要「能画」一律走 TalkToFigma**，见本技能 SKILL.md 与
`references/talktofigma-deploy.md`。

## 5. 三条路径取舍一览

| | A. REST + PAT | B. 官方远程 MCP | C. TalkToFigma |
|---|---|---|---|
| 读设计稿 | 支持 | 支持 | 支持（要插件在线） |
| 改画布 | 不支持 | 支持 | 支持 |
| 需要 OAuth | 否 | **是（且需白名单）** | 否 |
| 需要付费席位 | 否 | 需要 Full seat | 否 |
| 需要 Figma 桌面端 | 否 | 否 | **是** |
| 需要插件常驻 | 否 | 否 | **是** |
| 本机可用性 | 可用 | **封死** | 可用 |
