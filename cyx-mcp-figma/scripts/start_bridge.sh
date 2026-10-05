#!/bin/sh
# TalkToFigma 桥启动脚本
#
# 起一个本地 WebSocket 桥，监听 3055，等 Figma 插件接入。
#
# 用法:
#   sh start_bridge.sh             前台运行（关窗口 = 停桥，适合人工看守）
#   sh start_bridge.sh --detach    脱离会话常驻（推荐给 agent / 自动化）
#
# 注意：用 agent 的后台任务或 `nohup ... &` 起的桥，会随会话结束被回收，
#       表现为「跑几分钟突然没了」。要长期存活请用 --detach。
#
# 环境变量覆盖:
#   TTF_REPO   仓库根目录（默认 ~/.workbuddy/mcp-servers/talktofigma）
#   BUN_BIN    Bun 可执行文件（默认 ~/.bun/bin/bun）
#   PYTHON_BIN Python（--detach 时用，默认 /usr/bin/python3）

set -e

REPO="${TTF_REPO:-$HOME/.workbuddy/mcp-servers/talktofigma}"
BUN="${BUN_BIN:-$HOME/.bun/bin/bun}"
PY="${PYTHON_BIN:-/usr/bin/python3}"
SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)

if [ ! -x "$BUN" ]; then
  echo "找不到 Bun: $BUN"
  echo "安装步骤见 cyx-mcp-figma 技能的 references/talktofigma-deploy.md"
  exit 1
fi

if [ ! -f "$REPO/src/socket.ts" ]; then
  echo "找不到仓库: $REPO"
  echo "设置 TTF_REPO 指向 TalkToFigma 仓库根目录"
  exit 1
fi

case "$1" in
  --detach|-d)
    TTF_REPO="$REPO" BUN_BIN="$BUN" "$PY" "$SCRIPT_DIR/daemonize_bridge.py"
    exit $?
    ;;
esac

cd "$REPO"
echo "TalkToFigma 桥启动中，监听 3055 …（关掉本窗口即停止）"
echo "想让它常驻不随窗口关闭：sh start_bridge.sh --detach"
exec "$BUN" run src/socket.ts
