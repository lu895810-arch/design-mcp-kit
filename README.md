# design-mcp-kit

把设计工具接入 AI 编程助手的技能集。

每个目录是一个独立的技能包，可直接复制到 `~/.workbuddy/skills/` 使用。内容来自实际接入过程的完整记录，包含验证方法、失败原因与对应处理，而非文档的转述。

## 技能清单

| 技能 | 适用场景 | 主要内容 |
|---|---|---|
| [`cyx-mcp-figma`](cyx-mcp-figma/) | 接入 Figma；读取设计稿或在画布上直接绘制；排查桥连接故障 | 三条技术路径的选择依据、桥的常驻方案与自检脚本 |
| [`mcp-install-cn`](mcp-install-cn/) | 在网络受限环境下接入第三方 MCP server | 解决包源不可达、代理拦截本地连接等问题 |
| [`connect-figma-mcp`](connect-figma-mcp/) | 同上，早期实现 | 暂时保留，新场景建议优先使用 `cyx-mcp-figma` |

## 快速开始

```bash
git clone https://github.com/lu895810-arch/design-mcp-kit.git
cp -r design-mcp-kit/cyx-mcp-figma ~/.workbuddy/skills/
cp -r design-mcp-kit/mcp-install-cn ~/.workbuddy/skills/
```

复制后刷新即可生效，无需额外安装步骤。带脚本的技能（如 `cyx-mcp-figma/scripts/`）请保持目录结构一并复制。

## 技能详情

### cyx-mcp-figma —— 把 Figma 接入 WorkBuddy

Figma 接入有三条技术路径，能力范围差异较大，**动手前应先明确需求是「读取」还是「绘制」**：

| 目标 | 路径 | 可用性 |
|---|---|---|
| 读取设计稿：获取图层数据、导出图片、生成代码 | A. `figma-developer-mcp`（REST API + Personal Access Token） | 可用 |
| 在画布上绘制或修改：创建 frame、写入文字、修改颜色、设置自动布局 | B. Figma 官方远程 MCP（`mcp.figma.com/mcp`） | 不可用，已经实测验证 |
| 同上 | C. TalkToFigma（本地 WebSocket 桥 + Figma 插件） | 可用 |

**选择依据：需要读取走路径 A，需要绘制走路径 C，路径 B 可以跳过。**

技能包含以下内容：

- 路径 B 不可用的实测依据与复检方法（裸握手返回 401、PAT 冒充返回 401、自助注册返回 403），便于日后政策变化时重新验证
- TalkToFigma 的三段式架构说明，以及 44 个工具的取用方式
- `scripts/daemonize_bridge.py`、`scripts/start_bridge.sh`：通过 `setsid` 让桥脱离调用会话独立常驻。直接用 `nohup &` 启动的进程会被回收，实测存活时间在 3 分钟到 11 小时之间大幅波动
- `scripts/probe_bridge.mjs`：不经客户端、直连桥的端到端自检脚本，无需重开会话加载 MCP 工具即可验证链路
- 三个高频阻碍：必须使用桌面端（网页版不支持）、必须先打开设计文件、插件包位于隐藏目录导致选不到 manifest

### mcp-install-cn —— 网络受限环境下的 MCP 接入

本技能针对下列网络特征，环境相同可直接沿用：

| 现象 | 具体表现 | 处理方式 |
|---|---|---|
| `registry.npmjs.org` 被拦截 | 返回 `302 → m.baidu.com`；npm 报 `FETCH_ERROR` | 改用 `registry.npmmirror.com` |
| 出网经代理并存在 TLS 中间人 | 自签证书，curl exit 60 | curl 加 `-k`；npm 加 `--strict-ssl=false` |
| 本机设有 HTTP 代理 | 会把 `localhost` 的 MCP 连接一并带走 | 在 server 的 env 中加 `NO_PROXY` |
| macOS 缺少 `timeout` 命令 | 探针误判为「server 无输出」 | 用 `{ printf ...; sleep N; } \| server` 保活 stdin |

核心结论：**`command: "npx"` 形式的配置在此类网络环境下无法运行**，必须改为「本地安装 + 绝对路径调用」。

> 文中出现的 `127.0.0.1:7890`、`npmmirror` 属于作者本机环境，迁移到其他环境时请按实际情况替换。

### connect-figma-mcp —— 早期实现

2026-09 的初版实现，覆盖三种连接方式（token-based stdio / Figma Desktop MCP / TalkToFigma）的对比与配置流程。新场景建议优先使用 `cyx-mcp-figma`；此处保留，是因为其中关于 `~/.workbuddy/mcp.json` 合并写法、OAuth 故障排查（`ECONNRESET`）的部分仍有参考价值。

## 安装到 WorkBuddy

每个技能目录下都有 `SKILL.md`，其 frontmatter 中的 `description` 决定技能在什么场景下被触发。安装方式：

1. 将目录整体复制到 `~/.workbuddy/skills/`
2. 刷新后，技能会按 `description` 描述的适用场景自动加载

## License

[MIT](LICENSE)
