#!/usr/bin/env python3
"""验 Cloud Studio MCP：JWT 有效期 -> HTTP 鉴权 -> stdio 握手 -> 工具清单。

只读，不创建任何云端资源。默认读 ~/.workbuddy/mcp.json 里 cloudstudio 条目的
command 与 env.API_TOKEN；也可以用环境变量覆盖：

    CS_TOKEN=<JWT>                    只验这个令牌，不碰 mcp.json
    CS_MCP_JSON=/path/to/mcp.json     换配置文件
    CS_SERVER_NAME=cloudstudio        换 mcpServers 下的 key

退出码 0 = 全绿；1 = 有一步没过。
"""

import base64
import datetime
import json
import os
import pathlib
import subprocess
import sys
import time
import urllib.error
import urllib.request

OK = "  \u2713"
NG = "  \u2717"
SERVER_NAME = os.environ.get("CS_SERVER_NAME", "cloudstudio")
CONFIG = pathlib.Path(
    os.environ.get("CS_MCP_JSON", str(pathlib.Path.home() / ".workbuddy" / "mcp.json"))
)
USER_ENDPOINT = "https://api.cloudstudio.net/user"

failures = []


def step(label):
    print(f"\n[{label}]")


def fail(msg):
    print(f"{NG} {msg}")
    failures.append(msg)


def ok(msg):
    print(f"{OK} {msg}")


def load_entry():
    """返回 (token, command)。CS_TOKEN 优先于配置文件。"""
    token = os.environ.get("CS_TOKEN")
    command = None
    if CONFIG.is_file():
        try:
            cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            fail(f"{CONFIG} 不是合法 JSON：{exc}")
            return token, command
        entry = (cfg.get("mcpServers") or {}).get(SERVER_NAME)
        if entry is None:
            print(f"  配置里没有 mcpServers.{SERVER_NAME}，只读到 {list((cfg.get('mcpServers') or {}).keys())}")
        else:
            command = entry.get("command")
            if token is None:
                token = (entry.get("env") or {}).get("API_TOKEN")
            region = (entry.get("env") or {}).get("region", "(未设置，默认 ap-shanghai)")
            print(f"  command = {command}")
            print(f"  region  = {region}")
    else:
        print(f"  找不到 {CONFIG}（可用 CS_MCP_JSON 指定）")
    return token, command


def check_jwt(token):
    step("1/4 解 JWT 看有效期")
    parts = token.split(".")
    if len(parts) != 3:
        fail("令牌不是 3 段式 JWT，形态可疑")
        return
    payload = parts[1] + "=" * (-len(parts[1]) % 4)
    try:
        data = json.loads(base64.urlsafe_b64decode(payload))
    except Exception as exc:  # noqa: BLE001
        fail(f"载荷解不开：{exc}")
        return
    exp = data.get("exp")
    print(f"  userId = {data.get('userId')}")
    if not exp:
        print("  载荷里没有 exp（长期令牌？）")
        return
    exp_dt = datetime.datetime.fromtimestamp(exp)
    now = datetime.datetime.now()
    days = (exp_dt - now).total_seconds() / 86400
    print(f"  exp    = {exp_dt:%Y-%m-%d %H:%M}（距今 {days:.1f} 天）")
    if days <= 0:
        fail("令牌已过期，去 https://cloudstudio.net/settings/tokens 重新生成")
    elif days <= 3:
        ok(f"令牌有效，但只剩 {days:.1f} 天，尽快续")
    else:
        ok("令牌未过期")


def check_auth(token):
    step("2/4 打鉴权端点（initialize 验不出令牌，只有这里能验）")
    req = urllib.request.Request(
        USER_ENDPOINT,
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            code = resp.status
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", "replace")[:200]
        fail(f"HTTP {exc.code} -> {raw}")
        if exc.code == 401:
            print("  401 + leak_auth_params = 令牌无效/过期/签名错")
        return
    except Exception as exc:  # noqa: BLE001
        fail(f"请求失败（网络或代理问题）：{exc}")
        return
    if code == 200 and body.get("code") == 0:
        info = body.get("data") or {}
        ok(f"鉴权通过：userId={info.get('id')} nickname={info.get('nickname')} idp={info.get('idp')}")
    else:
        fail(f"HTTP {code} -> {json.dumps(body, ensure_ascii=False)[:200]}")


def check_handshake(command, token):
    step("3/4 stdio 握手 + 列工具")
    if not command:
        fail("配置里没有 command，跳过握手")
        return
    if not pathlib.Path(command).exists():
        fail(f"可执行文件不存在：{command}（是不是 venv 被删了/换路径了）")
        return
    env = dict(os.environ)
    env.update(
        {
            "API_TOKEN": token,
            "HOME": str(pathlib.Path.home()),
            "FASTMCP_CHECK_FOR_UPDATES": "off",
        }
    )
    proc = subprocess.Popen(
        [command],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        text=True,
        bufsize=1,
    )

    def send(obj):
        proc.stdin.write(json.dumps(obj) + "\n")
        proc.stdin.flush()

    def read_reply(target_id, timeout=30):
        deadline = time.time() + timeout
        while time.time() < deadline:
            line = proc.stdout.readline()
            if not line:
                return None
            line = line.strip()
            if not line.startswith("{"):
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue
            if msg.get("id") == target_id:
                return msg
        return None

    try:
        send(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "cs-verify", "version": "1.0"},
                },
            }
        )
        init = read_reply(1)
        if init is None:
            fail("initialize 无响应。stderr 末尾：")
            print(proc.stderr.read()[-1200:])
            return
        info = init.get("result", {}).get("serverInfo", {})
        ok(f"initialize OK：{info.get('name')} {info.get('version')}")

        send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        send({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
        tools = read_reply(2)
        if tools is None:
            fail("tools/list 无响应")
            return
        names = [t["name"] for t in tools.get("result", {}).get("tools", [])]
        ok(f"工具 {len(names)} 个")
        for name in names:
            print(f"      - {name}")
    finally:
        try:
            proc.stdin.close()
            proc.terminate()
            proc.wait(timeout=5)
        except Exception:  # noqa: BLE001
            proc.kill()


def main():
    print(f"Cloud Studio MCP 自检  (配置：{CONFIG}, server：{SERVER_NAME})")
    token, command = load_entry()
    if not token:
        print("\n没有拿到 API_TOKEN。去 https://cloudstudio.net/settings/tokens 生成后：")
        print("  - 写进 mcp.json 的 env.API_TOKEN，或")
        print("  - 临时用 CS_TOKEN=<JWT> 跑本脚本")
        return 1
    check_jwt(token)
    check_auth(token)
    check_handshake(command, token)

    step("4/4 结论")
    if failures:
        print(f"{NG} 有 {len(failures)} 项没过：")
        for item in failures:
            print(f"      - {item}")
        return 1
    print(f"{OK} 全绿：令牌有效、服务可启动、工具可枚举")
    print("  别忘了：连接器管理页右上角「自定义连接器」→ 信任 → ⌘Q 完全退出重开")
    return 0


if __name__ == "__main__":
    sys.exit(main())
