---
name: cyx-mcp-modao
description: 把墨刀（modao.cc）接入 WorkBuddy —— 一句话从文字生成 HTML 原型 / React / Vue 应用 / PRD / 图片，并把生成的 HTML 导回墨刀变成可编辑原型。当用户说「接入墨刀」「墨刀 mcp」「链接墨刀」「磨刀」（同音误写）「墨刀能不能接入」「墨刀连不上 / 不生效 / MCP 列表里没有墨刀」「在墨刀里生成原型 / PRD / 海报」「把生成的原型导进墨刀」「墨刀还剩多少积分」时使用，先读本技能再回答，不要凭印象答。含配置写法（远程 Streamable HTTP + modao-token，只写 url / headers 两个字段）、用 get_account_status 验凭据的探针脚本、13 个工具的选择决策树，以及「新条目必须 ⌘Q 完全退出重开才会出现在 MCP 服务管理列表」这个必踩的坑。
agent_created: true
display_name: "墨刀 MCP 接入器"
display_name_en: "Modao MCP Connector"
buddy-adapted: "2026-10-05"
owner: "Buddy（Lulu 的数字搭子）"
---

# cyx-mcp-modao：把墨刀接进 WorkBuddy

墨刀（modao.cc）官方提供的是 **Streamable HTTP 型 MCP**。这一条与 Figma 的三种路径都不同：
**不用 npx、不用装包、不走 OAuth、不用桥接插件**，配置里只写 `url` + `headers` 两个字段，凭据就是你自己的个人令牌。

代价是它**不热加载**：改完 `mcp.json` 必须 **⌘Q 完全退出 WorkBuddy 再重开**，新条目才会出现在
「连接器 → MCP 服务管理 → 我的 MCP」里。这是本技能唯一一个「配置没错但就是不生效」的原因。

## 一、官方参数（照抄即可）

| 项 | 值 |
|---|---|
| 传输类型 | Streamable HTTP |
| 服务地址 | `https://modao.cc/agent-py/ai/mcp` |
| 认证方式 | 请求头 `modao-token: <个人访问令牌>` |
| 令牌获取 | 墨刀 → 头像菜单 → **令牌设置** → 复制个人访问令牌 |
| 归属空间 | 个人空间（所有 MCP 调用都记在令牌绑定的账号下） |
| 服务端标识 | `serverInfo.name = modao-agent-py`（2026-10 实测版本 3.4.2） |

服务端**无状态**：响应头里不带 `Mcp-Session-Id`，每次请求独立带令牌即可，不需要维护会话。

## 二、配置写法

写到 `~/.workbuddy/mcp.json` 的 `mcpServers` 下：

```json
{
  "mcpServers": {
    "modao": {
      "url": "https://modao.cc/agent-py/ai/mcp",
      "headers": {
        "modao-token": "modao_xxxxxxxxxxxxxxxx"
      }
    }
  }
}
```

要点：

- **远程型只写 `url` + `headers`**。不要写 `command` / `args` / `env` —— 那是 stdio 型专用字段，
  混写会让连接器以错误方式启动。
- 令牌写**真实值**，不要写 `"${MODAO_TOKEN}"` 占位（部分客户端不展开环境变量，等于空值）。
- 改前先备份：`cp ~/.workbuddy/mcp.json ~/.workbuddy/mcp.json.bak-$(date +%Y%m%d)`。
- 改后校验 JSON：`python3 -c "import json;json.load(open('$HOME/.workbuddy/mcp.json'))"`。
- 一个 server 一个 key，不要把过期条目留着。

## 三、首次接入流程（五步）

1. **拿令牌** —— 让用户去墨刀「头像菜单 → 令牌设置」复制，粘贴给你。
2. **写配置** —— 备份后合并进 `mcp.json`，不动其它 server；用 `json.load` 校验一遍。
3. **验凭据** —— 跑 `scripts/verify_modao_mcp.sh`（见下），确认令牌真的有效。**这一步不能省**，
   因为 `initialize` / `tools/list` 不校验鉴权，跳过它很可能把无效令牌当成配好了。
4. **⌘Q 完全退出 WorkBuddy 再重开** —— 只关窗口无效。
5. **启用** —— 重开后进「连接器 → MCP 服务管理 → 我的 MCP」，找到 `modao`，打开右侧开关（即「信任」）。

## 四、验证凭据：为什么必须真调一个工具

`initialize` 和 `tools/list` 是**协议层握手，面向所有人开放**，令牌错了它们照样返回 `200`。
只有真正调用一个**业务工具**才会过鉴权。官方给的验凭据入口是 `get_account_status`：

```
tools/call get_account_status { "client": "WorkBuddy" }
→ {"success":true,"message":"连接成功","org_type":"personal","points":1318,...}
```

`success: true` + `points` 就是令牌有效的确证；失败会明确回传错误信息。

脚本 `scripts/verify_modao_mcp.sh` 把这三步串起来了：读 `mcp.json` 里的令牌 →
`initialize` → `tools/list`（打印工具数）→ `get_account_status`（打印账号与积分）。
不带参数用默认配置路径，也可以 `MODAO_TOKEN=... ./verify_modao_mcp.sh` 直接测一个令牌。

**响应格式坑**：返回体是 SSE，不是纯 JSON —— 每行形如

```
event: message
data: {"jsonrpc":"2.0","id":1,"result":{...}}
```

解析前要先剥掉 `data: ` 前缀（脚本里用 `sed -n 's/^data: //p'`）。

## 五、13 个工具怎么选

先看服务端的**强约束**（写在每个工具的 description 里，客户端必须遵守）：

- 上文已有生成任务或 `task_id`、且用户**没有明确要求新建**时 → 用 `continue_task`，**不要**再调 `generate_*`。
- 运行中的任务**只能**用 `get_task_result` 查状态，不能暂停、不能继续。
- 工具返回失败或异常时：**禁止自动重试**、**禁止自动改调 `continue_task` 或 `generate_*`**，
  必须把错误原样展示给用户，只有用户明确要求后才能再调一次。
- `generate_*` 是**付费生成**，会消耗账号积分 —— 必须用户明确同意后才能调用。

| 工具 | 什么时候用 | 关键返回 |
|---|---|---|
| `generate` | 产物类型说不清（既不像页面也不像图片/文档）时的通用入口 | 任务链接 |
| `generate_html` | HTML 静态页面、可预览原型、高保真界面（未指定技术栈） | HTML 内容 + 预览链接 |
| `generate_react` | 用户明确要 React 的应用、后台系统、交互原型 | React 产物 + 预览链接 |
| `generate_vue` | 用户明确要 Vue / Vue 3 | Vue 产物 + 预览链接 |
| `generate_image` | 海报、插图、配图、商品图（**不能**用来生成可交互页面） | 图片链接 |
| `generate_prd` | 需求文档、产品方案、功能说明、验收标准 | Markdown 文档 |
| `continue_task` | 在已有 `task_id` 上继续改 / 优化 / 补页面 / 恢复暂停或失败的任务 | 新产物 |
| `get_task_result` | 查任务状态、进度、预览链接、错误信息；**只读** | 状态 |
| `paused_task` | 用户明确要求暂停或取消某个已有任务 | 状态 |
| `list_recent_tasks` | 用户要「看最近的任务」，或引用了旧任务但上下文里没有 `task_id` | 任务列表（默认 10、最多 20） |
| `download_generated_content` | 取某个任务的下载链接 | 下载链接 |
| `import_to_proto` | 把生成的 **HTML** 导入墨刀，变成可继续编辑的原型 | `prototype_url` |
| `get_account_status` | 验凭据 / 查积分 / 确认绑定的账号与空间 | 账号 + `points` |

**调用约定**：所有工具都有可选参数 `client`，填当前客户端名称（本机填 `WorkBuddy`）；
显式填写的名称优先于 `initialize` 的 `clientInfo.name`。

**超时与轮询**：生成类工具**最多等 100 秒**，超时返回 `running` + `task_id`，
之后用 `get_task_result` 轮询，不要重复发起新的生成。

## 六、能力边界（先讲清楚，别许愿）

- `import_to_proto` **只吃 HTML**：不支持 React、Vue、外部 URL，也不能指定目标空间（只进默认个人空间）。
  拿到 React/Vue 产物时要如实说明这个限制，让用户决定怎么处理，
  **不得**擅自改调 `generate_*` 转成 HTML（那是付费操作）。
- `download_generated_content` 返回的链接**只能在已登录墨刀的浏览器里打开**；
  客户端不要自己去访问、代下载或验证。
- 首次使用 `import_to_proto` 前，账号里得先有至少一个任务；没有的话提示用户先在墨刀 AI 里对话一次。
- 生成任务都记在令牌绑定的**个人空间**，与 MCP 调用同账号。

## 七、坑

1. **列表里看不到 `modao` = 还没重载**。`mcp.json` 改动不会热更新，MCP 列表是应用启动时扫描的；
   必须 ⌘Q 完全退出后重开（关窗口无效）。判断依据：列表条数没变 + 日志里没有该 server 的加载记录。
2. **不要按 stdio 的直觉写 `command` / `args`**。远程型多写这些字段会以错误方式启动。
3. **令牌明文**存在 `mcp.json` 里（与 Figma 那条一样），提醒用户别外发这个文件。
4. 首次接入后**不要**急着调 `generate_*` 试链路 —— 那是付费生成。
   验链路用 `get_account_status`，免费且直接。
5. 本机 `registry.npmjs.org` 被封的问题**与墨刀无关**（它不需要 npx）。
   如果看到有人给墨刀配 `npx`，那多半是早期非官方实现，优先用本文的官方 Streamable HTTP。

## 八、和 Figma 的分工

| 需求 | 用哪个 |
|---|---|
| 读已有设计稿：拉图层、导出图片、生成代码 | Figma（`cyx-mcp-figma` 路径 A） |
| 在画布上改稿 / 画图 | Figma（`cyx-mcp-figma` 路径 C，TalkToFigma 桥） |
| 从一句需求**生成**原型 / PRD / 配图，并落地成可编辑原型 | 墨刀（本技能） |

两者可以并存：Figma 负责「读与改既有设计」，墨刀负责「从零生成与交付文档」。

## 九、文件

- `scripts/verify_modao_mcp.sh` —— 一条命令验完握手、工具数与凭据，只读、不消耗积分。

> 本技能与本项目均与墨刀（modao.cc）无隶属或背书关系。墨刀是墨刀团队的商标。
