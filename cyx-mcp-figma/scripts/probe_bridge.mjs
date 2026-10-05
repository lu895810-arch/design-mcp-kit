#!/usr/bin/env node
// TalkToFigma 端到端探针 / 通用命令执行器
//
// 作用：绕过 MCP 客户端，直连本地 WebSocket 桥，验证
//       「Figma 插件 → 桥 → 调用方」这条链路是否真的通。
//       用户还没开新会话、MCP 工具没挂上时，也能用它直接往画布发命令。
//
// 用法：
//   node probe_bridge.mjs [命令名] [参数JSON] [频道名]
//
// 例：
//   node probe_bridge.mjs
//   node probe_bridge.mjs get_document_info
//   node probe_bridge.mjs create_frame '{"name":"iPhone","x":0,"y":0,"width":375,"height":812}'
//
// 环境变量：
//   TTF_REPO  仓库根目录（默认 ~/.workbuddy/mcp-servers/talktofigma）
//   TTF_PORT  桥端口（默认 3055）
//
// 退出码：0 成功 / 1 插件返回错误 / 2 用法或依赖问题 / 3 超时无响应 / 4 连不上桥

import os from 'node:os';
import path from 'node:path';
import { pathToFileURL } from 'node:url';

const PORT = process.env.TTF_PORT || '3055';
const REPO = process.env.TTF_REPO
  || path.join(os.homedir(), '.workbuddy', 'mcp-servers', 'talktofigma');
const WS_ENTRY = path.join(REPO, 'node_modules', 'ws', 'index.js');

if (process.argv.includes('--help') || process.argv.includes('-h')) {
  console.log('');
  console.log('TalkToFigma 探针 / 命令执行器');
  console.log('');
  console.log('用法: node probe_bridge.mjs [命令名] [参数JSON] [频道名]');
  console.log('');
  console.log('参数默认值: get_document_info / {} / workbuddy');
  console.log('环境变量:   TTF_REPO 仓库根目录   TTF_PORT 桥端口（默认 3055）');
  console.log('');
  console.log('例:');
  console.log('  node probe_bridge.mjs');
  console.log('  node probe_bridge.mjs create_frame \'{"name":"iPhone","width":375,"height":812}\'');
  console.log('');
  console.log('退出码: 0 成功 / 1 插件返回错误 / 2 用法或依赖问题 / 3 超时无响应 / 4 连不上桥');
  console.log('');
  process.exit(0);
}

const CMD = process.argv[2] || 'get_document_info';
let PARAMS = {};
if (process.argv[3]) {
  try {
    PARAMS = JSON.parse(process.argv[3]);
  } catch {
    console.error(`参数不是合法 JSON: ${process.argv[3]}`);
    process.exit(2);
  }
}
const CHANNEL = process.argv[4] || 'workbuddy';

let WebSocket;
try {
  ({ default: WebSocket } = await import(pathToFileURL(WS_ENTRY).href));
} catch {
  console.error(`找不到 ws 模块: ${WS_ENTRY}`);
  console.error('设置 TTF_REPO 指向 TalkToFigma 仓库根目录，或先在该仓库执行 bun install。');
  process.exit(2);
}

const id = `probe-${Date.now()}`;
let joined = false;
let sawPeer = false;

const ws = new WebSocket(`ws://localhost:${PORT}`);

const finish = (code, msg) => {
  if (msg) console.log(msg);
  try { ws.close(); } catch {}
  process.exit(code);
};

ws.on('open', () => {
  ws.send(JSON.stringify({ type: 'join', channel: CHANNEL }));
});

ws.on('message', (d) => {
  let j;
  try { j = JSON.parse(d.toString()); } catch { return; }

  // 入频道回执：桥发来的 system 消息，message 是个带 result 的对象
  if (j.type === 'system' && j.message && typeof j.message === 'object' && j.message.result && !joined) {
    joined = true;
    console.log(`[1/3] 已加入频道 "${CHANNEL}"`);
    ws.send(JSON.stringify({
      id, type: 'message', channel: CHANNEL,
      message: { id, command: CMD, params: PARAMS },
    }));
    console.log(`[2/3] 已发送命令 "${CMD}"，参数 ${JSON.stringify(PARAMS)}，等待插件响应…`);
    return;
  }

  // 桥的成员变动通知：用来区分「频道里没人」和「有人但不回应」
  if (j.type === 'system' && typeof j.message === 'string') {
    if (j.message.includes('new user has joined')) sawPeer = true;
    return;
  }

  if (j.type === 'broadcast' && j.message && j.message.id === id) {
    if (j.message.error) {
      finish(1, `[3/3] 插件返回错误: ${j.message.error}`);
    }
    const out = JSON.stringify(j.message.result, null, 2);
    finish(0, `[3/3] 插件已连接且正常响应:\n${out.slice(0, 1400)}`);
  }
});

ws.on('error', (e) => {
  finish(4, `无法连接桥 (ws://localhost:${PORT}): ${e.message}\n`
    + `先确认桥在监听: lsof -nP -iTCP:${PORT} -sTCP:LISTEN`);
});

setTimeout(() => {
  if (!joined) {
    finish(4, `超时：没收到入频道回执，桥可能异常。检查 lsof -nP -iTCP:${PORT} -sTCP:LISTEN`);
  }
  finish(3, sawPeer
    ? '超时：频道里检测到有客户端加入了，但对方没回应命令。插件可能卡死，关掉面板重开。'
    : `超时：频道 "${CHANNEL}" 里没有 Figma 插件。请确认插件已运行并点了 Connect。`);
}, 12000);
