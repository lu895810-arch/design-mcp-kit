---
name: cyx-mcp-cloudstudio
description: 把腾讯云 Cloud Studio（cloudstudio.net）接入 WorkBuddy —— 让 AI 把本地项目上传到云端工作空间、跑 npm install / 起服务，并拿到一个可直接分享的预览链接。当用户说「接入 Cloud Studio」「链接 Cloud Studio」「cloudstudio mcp」「云 IDE 接入」「把项目部署到 Cloud Studio」「云端预览」「cloudstudio 连不上 / MCP 列表里没有 cloudstudio」「我的 Cloud Studio 令牌」「cloudstudio.club」时使用，先读本技能再回答，不要凭印象答。含官方 PyPI 包参数（cloudstudio-mcp-server / cloudstudio-mcp-deploy）、独立 venv 安装法、JWT 令牌的离线校验方式、5 个工具的选择决策树，以及两个必踩的坑（initialize/tools/list 不校验鉴权、FASTMCP_CHECK_FOR_UPDATES 写 "0" 会让服务直接崩）。
agent_created: true
display_name: "Cloud Studio MCP 接入器"
display_name_en: "Cloud Studio MCP Connector"
buddy-adapted: "2026-10-05"
owner: "Buddy（Lulu 的数字搭子）"
---

# cyx-mcp-cloudstudio：把 Cloud Studio 接进 WorkBuddy

腾讯云 Cloud Studio 官方提供的是 **stdio 型本地 MCP**（PyPI 上的 Python 包），
与墨刀的远程 Streamable HTTP、Figma 的 npx / 桥接插件都不同。

**先澄清一件事**：WorkBuddy 的**连接器市场里没有** Cloud Studio 连接器。
搜 `search_plugins` 只能搜到「腾讯云 CloudBase」——那是另一个产品（云开发后端），不是云 IDE。
所以这条路只能走**自定义本地 MCP**，写 `~/.workbuddy/mcp.json`，
然后到连接器管理页右上角「自定义连接器」手动「信任」。

## 一、官方参数（照抄即可）

| 项 | 值 |
|---|---|
| PyPI 包名 | `cloudstudio-mcp-server`（非 npm！作者邮箱 `@tencent.com`） |
| console script | `cloudstudio-mcp-deploy` → `mcp_deploy.__main__:main` |
| Python 要求 | `>=3.10` |
| 传输类型 | stdio |
| 服务端标识 | `serverInfo.name = mcp-deploy`（实测 2026-10 为 fastmcp 4.0.11） |
| 必需环境变量 | `API_TOKEN`（**缺失时 import 期直接抛 `ValueError`**） |
| 可选环境变量 | `region`（默认 `ap-shanghai`） |
| 令牌获取 | https://cloudstudio.net/settings/tokens （Cloud Studio 控制台 → 设置 → 访问令牌） |
| 令牌形态 | **JWT**，`iat`/`exp` 可直接 base64 解出来看剩余天数（实测约 30 天，到期日是下月初零点） |

依赖：`fastapi` / `fastmcp>=2.11.3` / `mcp` / `pydantic` / `httpx` / `requests` / `uvicorn`。

## 二、安装：不要用 uvx，用独立 venv

官方文档推荐 `uvx`，**但本机没装 uv**，而且 `uvx` 每次启动要检查/拉包，
不如一次装到独立 venv 稳。沿用本机 `~/.workbuddy/mcp-servers/<name>/` 的既有惯例：

```bash
mkdir -p ~/.workbuddy/mcp-servers/cloudstudio
cd ~/.workbuddy/mcp-servers/cloudstudio
/Users/lulu/.workbuddy/binaries/python/versions/3.13.12/bin/python3 -m venv venv
./venv/bin/pip install -i https://pypi.tuna.tsinghua.edu.cn/simple cloudstudio-mcp-server
```

装完的可执行文件就是 `~/.workbuddy/mcp-servers/cloudstudio/venv/bin/cloudstudio-mcp-deploy`。
**不要**用 `pip install --user` 或全局装，会污染环境且路径不稳定。

## 三、配置写法

写到 `~/.workbuddy/mcp.json` 的 `mcpServers` 下：

```json
{
  "mcpServers": {
    "cloudstudio": {
      "command": "/Users/lulu/.workbuddy/mcp-servers/cloudstudio/venv/bin/cloudstudio-mcp-deploy",
      "args": [],
      "env": {
        "API_TOKEN": "<JWT>",
        "region": "ap-shanghai",
        "HOME": "/Users/lulu",
        "FASTMCP_CHECK_FOR_UPDATES": "off"
      }
    }
  }
}
```

要点：

- **本地 stdio 型写 `command` + `args` + `env`**，用**绝对路径**（WorkBuddy 启动子进程时 cwd 不一定是家目录）。
- 改前先备份：`cp ~/.workbuddy/mcp.json ~/.workbuddy/mcp.json.bak-$(date +%Y%m%d-%H%M)`。
- 改后必须回读校验：`python3 -c "import json;json.load(open('$HOME/.workbuddy/mcp.json'))"`。
  合并而不是覆盖 —— 本机 `mcp.json` 里同时挂着 figma / talktofigma / modao / vercel，写错会连带搞坏。
- `FASTMCP_CHECK_FOR_UPDATES: "off"` 是**建议加**的：不加的话每次启动这个服务都会去连
  `pypi.org` 做版本检查（实测启动日志里能看到 `CONNECT pypi.org:443`），
  无网或代理不通时会拖慢甚至卡住启动。**取值只能是 `stable` / `prerelease` / `off`**（见坑 2）。

## 四、区域参数有个暗改

`server.py` 里有一行：

```python
region = os.environ.get("region", "ap-shanghai")
if region == "ap-shanghai":
    region = "ap-shanghai2"
```

也就是说**传 `ap-shanghai` 会被静默改写成 `ap-shanghai2`**。
工作空间域名是 `<space_key>--api.<region>.cloudstudio.club`，
所以最终实际用的是 `ap-shanghai2`。排查 404 / 域名解析问题时先想到这一点。
默认值就是对的，**不用主动改**。

## 五、首次接入流程（五步）

1. **拿令牌** —— 让用户去 https://cloudstudio.net/settings/tokens 生成并粘贴给你。
2. **验令牌** —— 先离线验一把（见第六节），**这一步不能省**。
3. **写配置** —— 备份后合并进 `mcp.json`，不动其它 server，回读校验。
4. **握手自检** —— 跑 `scripts/verify_cloudstudio_mcp.py`，确认服务能起、工具数=5。
5. **信任 + 重启** —— 连接器管理页右上角「自定义连接器」里给 `cloudstudio` 点「信任」，
   然后 **⌘Q 完全退出 WorkBuddy 再重开**（关窗口无效）。

## 六、验令牌：initialize / tools/list 验不出来

**这两个方法是协议层握手，面向所有人开放，令牌错了照样返回结果。**
唯一的验法是打一个**需要鉴权的 HTTP 端点**：

```
GET https://api.cloudstudio.net/user
Authorization: Bearer <JWT>
```

| 结果 | 含义 |
|---|---|
| `200` + `{"code":0,...,"data":{"id":545002,"nickname":"雨露","idp":"wechat"}}` | ✅ 令牌有效，`data.id` 就是账号 userId |
| `401` + `{"code":1001,"semanticization":"leak_auth_params","msg":"Leak Auth Params"}` | ❌ 令牌无效 / 已过期 / 签名错 |

**解码 JWT 看有效期**（比调接口还快，能提前发现「还有 1 小时就过期」）：

```bash
python3 -c "
import base64,json,datetime,sys
p='<JWT载荷段>'
d=json.loads(base64.urlsafe_b64decode(p+'='*(-len(p)%4)))
print('userId:',d['userId'],'exp:',datetime.datetime.fromtimestamp(d['exp']))
"
```

`scripts/verify_cloudstudio_mcp.py` 把「解 JWT → 打 /user 验鉴权 → stdio 握手 → 列工具」串成一条命令，
只读、不创建任何云端资源。

## 七、5 个工具怎么选

| 工具 | 什么时候用 | 关键返回 |
|---|---|---|
| `create_workspace(title)` | 在云端新建一个工作空间。`title` ≤50 字符、无特殊字符 | `space_key` / `edit_url` / `webIDE` / `preview` / `lite_app_id` |
| `write_files(space_key, directory?, files?)` | 把本地项目传上去。**优先传 `directory`**（整个目录绝对路径，≤300MB，自动打包解压到 `/workspace`）；单个/少量文件或 >300MB 才用 `files` 列表，且本地文件优先给 `local_path` 而不是 `file_content` | `success_count` / `failed_count` / `details` |
| `execute_command(space_key, command)` | 在工作空间里跑 shell：`npm install`、起服务。超时 300s，输出上限 10MB | 命令输出 |
| `create_share_link_with_command(space_key, port)` | 给某个端口生成**对外可分享**的链接 | `host` / `scheme` / `expireAt` |
| `get_auto_run_log(space_key, ...)` | 查自动运行日志，服务起不来时用来排错 | 日志 |

**预览链接格式**：`https://{space_key}--{port}.{region}.cloudstudio.club`。

典型串法：`create_workspace` → `write_files(directory=...)` → `execute_command("npm install && npm run dev")`
→ 用 `preview` 拼预览链接（要给外部人看再调 `create_share_link_with_command`）。

## 八、坑

1. **`initialize` / `tools/list` 不校验鉴权**。跳过验令牌这一步，很可能把无效令牌当成功（见第六节）。
2. **`FASTMCP_CHECK_FOR_UPDATES` 写 `"0"` 会让服务直接崩**。这个字段是 pydantic 的 Literal，
   只接受 `stable` / `prerelease` / `off`，写 `0` 会在 import 期抛
   `ValidationError: Input should be 'stable', 'prerelease' or 'off'`，**表现为服务起不来、MCP 列表里看不到它**。
   要关就写 `"off"`。
3. **`create_workspace` 会创建真实云端资源**，占用每月赠送时长。
   验链路**优先用 `/user` 接口**；只在用户明确要求时才建工作空间，别为了「试试通不通」就建一个。
4. **`API_TOKEN` 缺失时是 import 期崩溃**，不是在调工具时才报错。
   所以「服务完全起不来」的第一反应应该是看 `env` 里有没有 `API_TOKEN`，
   而不是怀疑包装坏了。
5. **cmd 别在 argv 里传 JWT**（会进 `ps`）。验令牌用环境变量传，例如 `CS_TOKEN=... python verify_...py`。
6. 令牌**明文**存在 `mcp.json` 里（与 figma / modao 那几条一样），提醒用户别外发这个文件；
   到期后（约 30 天）要重新生成。
7. 配置改完**不热加载**：必须「信任」+ **⌘Q 完全退出重开**。判断依据是 MCP 列表条数没变、
   日志里没有该 server 的加载记录。

## 九、和本机其它 MCP 的分工

| 需求 | 用哪个 |
|---|---|
| 云端 IDE 跑项目、给可分享的预览链接 | Cloud Studio（本技能） |
| 部署静态站 / 小游戏成公开链接 | 「发布为应用」内置能力（`sites`） |
| 需要数据库 / 登录 / 文件存储 / 调大模型 | 「腾讯云 CloudBase」连接器或内置云服务 |
| 读改 Figma 设计稿 | `cyx-mcp-figma` |
| 生成原型 / PRD / 海报 | `cyx-mcp-modao` |

## 十、文件

- `scripts/verify_cloudstudio_mcp.py` —— 一条命令验完 JWT 有效期、HTTP 鉴权、stdio 握手与工具清单。
  默认读 `~/.workbuddy/mcp.json` 里的 `cloudstudio.env`，也可用 `CS_TOKEN=...` 直接测一个令牌。
  只读，不创建任何云端资源。

> 本技能与 Cloud Studio / 腾讯云无隶属或背书关系。Cloud Studio 是腾讯云的商标。
