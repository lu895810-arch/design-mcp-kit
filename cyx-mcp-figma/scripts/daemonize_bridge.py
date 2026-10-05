#!/usr/bin/env python3
"""让 TalkToFigma 桥脱离当前会话常驻（double-fork + setsid）。

为什么需要它
------------
用 agent 的「后台任务」或 `nohup ... &` 起桥，进程仍属于当前 shell 的
进程组 / 会话。会话一结束就被回收，表现为：桥跑了几分钟突然没了，
探针报「无法连接桥」，用户那边正在画的图卡住。

setsid 之后进程自成会话、父进程变为 launchd，与调用方彻底解耦。

用法
----
    python3 daemonize_bridge.py            # 常驻启动（已在监听则跳过）
    python3 daemonize_bridge.py --force    # 忽略已有监听，强制再起一个

环境变量
--------
    TTF_REPO  仓库根目录（默认 ~/.workbuddy/mcp-servers/talktofigma）
    BUN_BIN   Bun 可执行文件（默认 ~/.bun/bin/bun）
    TTF_PORT  端口，仅用于「是否已在监听」的检查（默认 3055）

退出码：0 已启动或已在运行 / 1 前置条件不满足
"""
import os
import sys

REPO = os.environ.get("TTF_REPO") or os.path.expanduser(
    "~/.workbuddy/mcp-servers/talktofigma"
)
BUN = os.environ.get("BUN_BIN") or os.path.expanduser("~/.bun/bin/bun")
PORT = os.environ.get("TTF_PORT") or "3055"
ENTRY = os.path.join(REPO, "src", "socket.ts")
LOG = os.path.join(REPO, "bridge.log")
ERRLOG = os.path.join(REPO, "bridge.err.log")

FORCE = "--force" in sys.argv


def die(msg, code=1):
    print(msg)
    sys.exit(code)


if not os.path.isfile(ENTRY):
    die(f"找不到桥入口: {ENTRY}\n设置 TTF_REPO 指向仓库根目录。")
if not os.access(BUN, os.X_OK):
    die(f"找不到可执行的 Bun: {BUN}\n设置 BUN_BIN，或先安装 Bun。")

if not FORCE:
    # lsof 返回 0 表示端口已被监听
    if os.system(f"lsof -nP -iTCP:{PORT} -sTCP:LISTEN >/dev/null 2>&1") == 0:
        print(f"桥已在监听 {PORT}，跳过启动。（要强制再起用 --force）")
        sys.exit(0)

pid = os.fork()
if pid > 0:
    print(f"桥已脱离当前会话启动，中间进程 pid={pid}")
    sys.exit(0)

os.setsid()

pid = os.fork()
if pid > 0:
    os._exit(0)

os.chdir(REPO)

os.environ["NO_PROXY"] = "localhost,127.0.0.1,::1"
os.environ["no_proxy"] = "localhost,127.0.0.1,::1"
os.environ.setdefault("HOME", os.path.expanduser("~"))

fd_out = os.open(LOG, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
fd_err = os.open(ERRLOG, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
fd_in = os.open(os.devnull, os.O_RDONLY)

os.dup2(fd_in, 0)
os.dup2(fd_out, 1)
os.dup2(fd_err, 2)

os.execv(BUN, [BUN, "run", ENTRY])
