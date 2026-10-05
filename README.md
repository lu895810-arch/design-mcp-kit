# design-mcp-kit

把设计工具接进 AI 编程助手的实战技能集。

每个目录是一个**独立的 skill**，可以直接复制到 `~/.workbuddy/skills/` 使用。内容全部来自真实接入过程的踩坑记录，不是从文档抄的教程——凡是写"封死""不要试"的地方，都是实测撞过南墙的。

## 技能清单

| 技能 | 适用场景 | 一句话 |
|---|---|---|
| [`cyx-mcp-figma`](cyx-mcp-figma/) | 接入 Figma、AI 读设计稿 / 直接改画布、桥连不上 | 主力技能。三条路径决策树 + 桥的守护与自检 |
| [`mcp-install-cn`](mcp-install-cn/) | 国内网络下接任何第三方 MCP server | 绕开 npmjs 被拦、代理劫持 localhost 等问题 |
| [`connect-figma-mcp`](connect-figma-mcp/) | 同上，早期版本 | 保留备查，新场景请优先用 `cyx-mcp-figma` |

## 快速开始

```bash
git clone https://github.com/lu895810-arch/design-mcp-kit.git
cp -r design-mcp-kit/cyx-mcp-figma ~/.workbuddy/skills/
cp -r design-mcp-kit/mcp-install-cn ~/.workbuddy/skills/
```

复制完刷新即可，无需额外安装步骤。带脚本的技能（如 `cyx-mcp-figma/scripts/`）保持目录结构一起复制。

## 技能详情

### cyx-mcp-figma —— 把 Figma 接进 WorkBuddy

Figma 接入有三个岔路口，能力差别很大，**先问清要"读"还是"画"再动手**：

| 你想要的 | 走哪条 | 结论 |
|---|---|---|
| 读设计稿：拉图层数据、导出图片、转代码 | A. `figma-developer-mcp`（REST API + Personal Access Token） | 可用 |
| 在画布上画 / 改：建 frame、写文字、改颜色、自动布局 | B. Figma 官方远程 MCP（`mcp.figma.com/mcp`） | 封死，不要尝试 |
| 同上 | C. TalkToFigma（本地 WebSocket 桥 + Figma 插件） | 可用 |

一句话规则：**只读走 A，要画走 C，B 直接跳过。**

技能里包含：

- 路径 B 被封的三条实测证据（裸握手 401 / PAT 冒充 401 / DCR 403），省掉你重复验证的几小时
- TalkToFigma 三段式架构与 44 个工具说明
- `scripts/daemonize_bridge.py`、`scripts/start_bridge.sh` —— 用 `setsid` 让桥脱离会话常驻（普通 `nohup &` 起的桥会被回收，实测一次活 11 小时、一次只活 3 分钟）
- `scripts/probe_bridge.mjs` —— 绕过客户端直连桥的端到端自检探针，不用等新会话加载 MCP 工具
- 三个必踩的坑：必须用桌面端（网页版不行）、必须先打开设计文件、隐藏目录找不到 manifest

### mcp-install-cn —— 国内网络给 WorkBuddy 接 MCP

这份技能的前提是本机网络有下列特征，遇到同类环境可直接套用：

| 事实 | 表现 | 对策 |
|---|---|---|
| `registry.npmjs.org` 被拦截 | 返回 `302 → m.baidu.com`；npm 报 `FETCH_ERROR` | 换 `registry.npmmirror.com` |
| 出网走代理并做 TLS MITM | 自签证书，curl exit 60 | curl 加 `-k`；npm 加 `--strict-ssl=false` |
| 本机有 HTTP 代理 | 会把 `localhost` 的 MCP 连接也带走 | server 的 env 里加 `NO_PROXY` |
| macOS 无 `timeout` 命令 | 探针误判成「server 没输出」 | 用 `{ printf ...; sleep N; } \| server` 保活 stdin |

核心结论：**`command: "npx"` 的配置在国内网络一定跑不起来**，必须改成「本地安装 + 绝对路径调用」。

> 技能里出现的 `127.0.0.1:7890`、`npmmirror` 属于作者本机环境，换环境时按自己情况替换。

### connect-figma-mcp —— 早期版本

2026-09 的初版实现，覆盖三种连接方式（token-based stdio / Figma Desktop MCP / TalkToFigma）的对比与配置流程。新场景请优先用 `cyx-mcp-figma`，这里保留是因为里面关于 `~/.workbuddy/mcp.json` 合并写法、OAuth 故障排查（`ECONNRESET`）的部分仍有参考价值。

## 安装到 WorkBuddy

每个技能目录下都有 `SKILL.md`，其 frontmatter 里的 `description` 决定了什么时候被触发。安装方式：

1. 把目录整个复制到 `~/.workbuddy/skills/`
2. 刷新后，技能会按 `description` 里描述的场景自动加载

## License

[MIT](LICENSE)
