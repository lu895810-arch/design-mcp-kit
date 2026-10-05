# design-mcp-kit

把设计工具与云端开发环境接入 AI 编程助手的技能集。

每个目录是一个独立的技能包，可直接复制到 `~/.workbuddy/skills/` 使用。内容来自实际接入过程的完整记录，包含验证方法、失败原因与对应处理，而非文档的转述。

## 技能清单

| 技能 | 适用场景 | 主要内容 |
|---|---|---|
| [`cyx-mcp-figma`](cyx-mcp-figma/) | 接入 Figma；读取设计稿或在画布上直接绘制；排查桥连接故障 | 三条技术路径的选择依据、桥的常驻方案与自检脚本 |
| [`cyx-mcp-modao`](cyx-mcp-modao/) | 接入墨刀；从一句需求生成原型 / PRD / 配图，并把生成的 HTML 导成可编辑原型 | Streamable HTTP 配置写法、凭据探针脚本、13 个工具的取舍、重启才生效的坑 |
| [`cyx-mcp-cloudstudio`](cyx-mcp-cloudstudio/) | 接入腾讯云 Cloud Studio；把本地项目传到云端工作空间里跑起来，并拿到可分享的预览链接 | stdio 型本地 MCP 的配置写法、JWT 令牌校验脚本、5 个工具的串联方式、两个必踩的坑 |
| [`mcp-install-cn`](mcp-install-cn/) | 在网络受限环境下接入第三方 MCP server | 解决包源不可达、代理拦截本地连接等问题 |
| [`connect-figma-mcp`](connect-figma-mcp/) | 同上，早期实现 | 暂时保留，新场景建议优先使用 `cyx-mcp-figma` |

## 快速开始

```bash
git clone https://github.com/lu895810-arch/design-mcp-kit.git
cp -r design-mcp-kit/cyx-mcp-figma ~/.workbuddy/skills/
cp -r design-mcp-kit/cyx-mcp-modao ~/.workbuddy/skills/
cp -r design-mcp-kit/cyx-mcp-cloudstudio ~/.workbuddy/skills/
cp -r design-mcp-kit/mcp-install-cn ~/.workbuddy/skills/
```

复制后刷新即可生效，无需额外安装步骤。带脚本的技能（如 `cyx-mcp-figma/scripts/`、`cyx-mcp-modao/scripts/`、`cyx-mcp-cloudstudio/scripts/`）请保持目录结构一并复制。

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

### cyx-mcp-modao —— 把墨刀接入 WorkBuddy

墨刀和别的工具不一样：**官方直接给了 Streamable HTTP 型 MCP** —— 不用 npx、不用装包、不走 OAuth、不用桥接插件。配置里只写两个字段：

```json
{
  "mcpServers": {
    "modao": {
      "url": "https://modao.cc/agent-py/ai/mcp",
      "headers": { "modao-token": "modao_xxxxxxxxxxxxxxxx" }
    }
  }
}
```

代价是**不热加载**：改完 `mcp.json` 必须 **⌘Q 完全退出 WorkBuddy 再重开**，新条目才会出现在「连接器 → MCP 服务管理 → 我的 MCP」里。这是本仓库里唯一一个「配置全对但就是不生效」的坑 —— 列表里看不到，不代表配置写错了。

技能包含以下内容：

- 官方参数表：服务地址、`modao-token` 请求头、令牌获取路径（头像菜单 → 令牌设置）、个人空间归属；服务端无状态，不需要维护会话
- **为什么不能只看 `tools/list` 就认为配好了** —— 握手层不校验鉴权，令牌错了照样返回 `200`；必须调用业务工具 `get_account_status` 拿到 `success: true` 才算验过
- `scripts/verify_modao_mcp.sh`：一条命令跑完 握手 → 列工具 → 查账号状态，只读、不消耗积分，也可用 `MODAO_TOKEN=...` 直接测一个令牌
- 13 个工具的取用决策表（生成 / 续改 / 查状态 / 暂停 / 导入原型），以及服务端写在工具描述里的三条强约束：**有旧任务就不许新建、工具报错不许自动重试、`generate_*` 是付费操作必须用户明确同意**
- 能力边界：`import_to_proto` 只吃 HTML（不支持 React / Vue / 外链）、下载链接只能在已登录墨刀的浏览器里打开、生成类工具最多等 100 秒，超时后用 `get_task_result` 轮询
- 与 Figma 的分工：Figma 读和改既有设计稿，墨刀从零生成原型与 PRD

### cyx-mcp-cloudstudio —— 把 Cloud Studio 接入 WorkBuddy

Cloud Studio 是腾讯云的云端 IDE。它和上面两个都不一样：**官方给的是 stdio 型本地 MCP**，发布在 PyPI 上（`cloudstudio-mcp-server`，可执行文件为 `cloudstudio-mcp-deploy`），需要装在本地、由客户端拉起进程。接上之后可以把本地项目传到云端工作空间、在里面跑 `npm install` 并启动服务，再拿到形如 `https://{space_key}--{port}.{region}.cloudstudio.club` 的预览链接。

另需澄清一点：**WorkBuddy 的连接器市场里没有 Cloud Studio**（搜到的「腾讯云 CloudBase」是云开发后端，不是云 IDE），所以这条路只能走自定义本地 MCP，配置完还要在连接器管理页手动「信任」。

技能包含以下内容：

- 为什么不用官方推荐的 `uvx`，改走 `~/.workbuddy/mcp-servers/<name>/venv` 独立虚拟环境：不污染全局解释器，也避开每次启动的拉包检查
- `scripts/verify_cloudstudio_mcp.py`：一条命令跑完「解 JWT 有效期 → 打鉴权端点 → stdio 握手 → 列工具」，只读，不创建任何云端资源
- 两个必踩的坑：**`initialize` / `tools/list` 不校验鉴权**（令牌错了照样返回，所以「握手成功」不等于「配好了」）；**`FASTMCP_CHECK_FOR_UPDATES` 只接受 `stable` / `prerelease` / `off`**，写 `"0"` 会让服务在 import 期直接崩溃，表现为「完全起不来、列表里看不到它」
- 5 个工具（建工作空间 / 传文件 / 执行命令 / 生成分享链接 / 查运行日志）的串联顺序与各自约束
- 一处源码里的暗改：`region` 传 `ap-shanghai` 会被静默改写成 `ap-shanghai2`，排查域名解析问题时先想到它

> `create_workspace` 会创建**真实的云端资源**并占用每月赠送时长。验链路不要拿它试，用只读的鉴权接口。

### mcp-install-cn —— 网络受限环境下的 MCP 接入

本技能针对下列网络特征，环境相同可直接沿用：

| 现象 | 具体表现 | 处理方式 |
|---|---|---|
| `registry.npmjs.org` 被拦截 | 返回 `302 → m.baidu.com`；npm 报 `FETCH_ERROR` | 改用 `registry.npmmirror.com` |
| 出网经代理并存在 TLS 中间人 | 自签证书，curl exit 60 | curl 加 `-k`；npm 加 `--strict-ssl=false` |
| 本机设有 HTTP 代理 | 会把 `localhost` 的 MCP 连接一并带走 | 在 server 的 env 中加 `NO_PROXY` |
| macOS 缺少 `timeout` 命令 | 探针误判为「server 无输出」 | 用 `{ printf ...; sleep N; } \| server` 保活 stdin |

核心结论：**`command: "npx"` 形式的配置在此类网络环境下无法运行**，必须改为「本地安装 + 绝对路径调用」。

该技能也覆盖了远程型 MCP 的两条路：**自定义 Header 型**（只写 `url` + `headers`，本仓库的墨刀即属此类）与 **OAuth 型**（须先确认客户端在服务方白名单内）。

> 文中出现的 `127.0.0.1:7890`、`npmmirror` 属于作者本机环境，迁移到其他环境时请按实际情况替换。

### connect-figma-mcp —— 早期实现

2026-09 的初版实现，覆盖三种连接方式（token-based stdio / Figma Desktop MCP / TalkToFigma）的对比与配置流程。新场景建议优先使用 `cyx-mcp-figma`；此处保留，是因为其中关于 `~/.workbuddy/mcp.json` 合并写法、OAuth 故障排查（`ECONNRESET`）的部分仍有参考价值。

## 安装到 WorkBuddy

每个技能目录下都有 `SKILL.md`，其 frontmatter 中的 `description` 决定技能在什么场景下被触发。安装方式：

1. 将目录整体复制到 `~/.workbuddy/skills/`
2. 刷新后，技能会按 `description` 描述的适用场景自动加载

> 配置类技能（`cyx-mcp-figma` / `cyx-mcp-modao` / `cyx-mcp-cloudstudio`）除了复制技能目录，还需要把凭据写入 `~/.workbuddy/mcp.json`；改完该文件后 **⌘Q 完全退出 WorkBuddy 再重开**，新连接器才会出现在「MCP 服务管理」列表里。其中 `cyx-mcp-cloudstudio` 还需先把 Python 包装进独立虚拟环境（见该技能 `SKILL.md` 第二节）。

## Third-party notices

本仓库不包含任何第三方源代码。文中的部署流程会引导你安装以下项目，它们各自遵循自己的许可证：

- [TalkToFigma](https://github.com/grab/cursor-talk-to-figma-mcp) —— MIT
- [figma-developer-mcp (Framelink)](https://github.com/GLips/Figma-Context-MCP) —— MIT
- [cloudstudio-mcp-server](https://pypi.org/project/cloudstudio-mcp-server/) —— MIT（由腾讯云 Cloud Studio 团队发布）

若需在自己的项目中再分发上述组件，请保留其版权声明与许可证原文。

本项目与 Figma, Inc.、墨刀（modao.cc）、腾讯云均无隶属或背书关系。Figma 是 Figma, Inc. 的商标；墨刀是墨刀团队的商标；Cloud Studio 是腾讯云的商标。

## License

[MIT](LICENSE)
