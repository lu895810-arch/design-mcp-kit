#!/usr/bin/env bash
# verify_modao_mcp.sh —— 校验墨刀（modao）MCP 的凭据是否真的有效
#
# 用法：
#   ./verify_modao_mcp.sh                          # 从 ~/.workbuddy/mcp.json 读 modao 令牌
#   ./verify_modao_mcp.sh /path/to/mcp.json        # 指定配置文件
#   MODAO_TOKEN=modao_xxx ./verify_modao_mcp.sh    # 直接测一个令牌
#
# 只做三件只读的事：MCP 握手 → 列工具 → 查账号状态。
# 不创建生成任务、不消耗积分（生成类工具才是付费的）。

set -uo pipefail

CONF="${1:-$HOME/.workbuddy/mcp.json}"
URL="${MODAO_MCP_URL:-https://modao.cc/agent-py/ai/mcp}"
PY="$(command -v python3 || echo /usr/bin/python3)"

TOKEN="${MODAO_TOKEN:-}"
if [ -z "$TOKEN" ]; then
  if [ ! -f "$CONF" ]; then
    echo "找不到配置文件：$CONF" >&2
    exit 2
  fi
  TOKEN="$("$PY" - "$CONF" <<'PYEOF'
import json, sys
try:
    cfg = json.load(open(sys.argv[1], encoding="utf-8"))
except Exception as e:
    print("", end="")
    sys.stderr.write("配置文件不是合法 JSON：%s\n" % e)
    sys.exit(0)
srv = (cfg.get("mcpServers") or {}).get("modao") or {}
print(((srv.get("headers") or {}).get("modao-token") or "").strip())
PYEOF
)"
fi

if [ -z "$TOKEN" ]; then
  echo "在 $CONF 里没找到 mcpServers.modao.headers['modao-token']。" >&2
  echo "要么先按 SKILL.md 第二节写好配置，要么用 MODAO_TOKEN=... 直接指定。" >&2
  exit 3
fi

echo "配置文件 : $CONF"
echo "服务地址 : $URL"
echo "令牌前缀 : ${TOKEN:0:16}…（共 ${#TOKEN} 字符）"
echo

# 服务端返回的是 SSE（event: message / data: {...}），这里剥掉 data: 前缀
call() {
  curl -sS -m 30 -X POST "$URL" \
    -H 'Content-Type: application/json' \
    -H 'Accept: application/json, text/event-stream' \
    -H "modao-token: $TOKEN" \
    -d "$1" | sed -n 's/^data: //p'
}

echo "-- 1/3 握手 initialize"
call '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"WorkBuddy","version":"1.0"}}}' \
  | "$PY" -c '
import sys, json
for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    try:
        d = json.loads(line)
    except Exception:
        continue
    if "result" in d:
        si = d["result"].get("serverInfo", {})
        print("   OK   serverInfo = %s %s" % (si.get("name"), si.get("version")))
        break
else:
    print("   FAIL 没有拿到 initialize 结果")
'

echo "-- 2/3 列工具 tools/list（此步不校验鉴权）"
call '{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}' \
  | "$PY" -c '
import sys, json
for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    try:
        d = json.loads(line)
    except Exception:
        continue
    tools = (d.get("result") or {}).get("tools")
    if tools is not None:
        print("   OK   %d 个工具：%s" % (len(tools), ", ".join(t["name"] for t in tools)))
        break
else:
    print("   FAIL 没有拿到工具列表")
'

echo "-- 3/3 查账号状态 get_account_status（此步才会真正校验令牌）"
call '{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"get_account_status","arguments":{"client":"WorkBuddy"}}}' \
  | "$PY" -c '
import sys, json
for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    try:
        d = json.loads(line)
    except Exception:
        continue
    r = d.get("result") or d.get("error")
    if r is None:
        continue
    if "error" in d:
        print("   FAIL %s" % json.dumps(d["error"], ensure_ascii=False))
        break
    sc = r.get("structuredContent") or {}
    if not sc:
        txt = (r.get("content") or [{}])[0].get("text", "")
        try:
            sc = json.loads(txt)
        except Exception:
            print("   ?    %s" % txt[:200])
            break
    if sc.get("success"):
        print("   OK   令牌有效 —— 空间类型=%s，积分=%s，账号=%s"
              % (sc.get("org_type"), sc.get("points"), sc.get("user_cid")))
        print()
        print("结论：令牌有效，链路通畅。（若连接器列表里还没有 modao，⌘Q 完全退出 WorkBuddy 再重开）")
    else:
        print("   FAIL %s" % json.dumps(sc, ensure_ascii=False))
    break
else:
    print("   FAIL 没有拿到响应")
'
