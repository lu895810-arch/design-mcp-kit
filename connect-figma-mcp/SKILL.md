---
name: connect-figma-mcp
agent_created: true
display_name: "Figma MCP 连接"
display_name_en: "Connect Figma MCP"
buddy-adapted: "2026-09-24"
owner: "Buddy（Lulu 的数字搭子）"
description: Connect Figma to WorkBuddy via MCP. Use when the user asks to connect Figma, use Figma designs, or troubleshoots a Figma MCP connection error (e.g., ECONNRESET, OAuth failure).
---

# Connect Figma MCP

## Overview

Figma has no built-in WorkBuddy connector. This skill wires Figma into WorkBuddy through an MCP server so the agent can read frames, components, variables, and generate code or design tokens from Figma files.

## Workflow

### 1. Inspect the current MCP config

Read `~/.workbuddy/mcp.json` if it exists. Merge the Figma server into the existing `mcpServers` object; do not overwrite other servers.

### 2. Choose a connection method

There are three ways to connect Figma. Prefer the token-based stdio method because it does not require interactive OAuth in WorkBuddy.

| Method | Transport | Prerequisites | Notes |
|---|---|---|---|
| Token-based `figma-developer-mcp` | stdio | Figma Personal Access Token with `file:read` scope | Most reliable in WorkBuddy |
| Figma Desktop MCP | streamableHttp | Figma desktop app v116.3+ with Dev/Full seat, MCP enabled | No token, but app must stay running |
| Figma Remote MCP | streamableHttp / http | Figma account OAuth | Often fails in WorkBuddy with `ECONNRESET` because WorkBuddy cannot complete the browser OAuth handshake |

### 3. Recommended: token-based configuration

Generate a token:

1. Open Figma in a browser and go to **Settings → Security → Personal access tokens**.
2. Click **Generate new token**, name it (e.g., `workbuddy-mcp`).
3. Scope: at minimum `file:read`.
4. Copy the token immediately (it is shown only once).

Write or update `~/.workbuddy/mcp.json`:

```json
{
  "mcpServers": {
    "figma": {
      "command": "npx",
      "args": ["-y", "figma-developer-mcp", "--stdio"],
      "env": {
        "FIGMA_API_KEY": "${FIGMA_API_KEY}"
      }
    }
  }
}
```

If the user pastes the token directly, replace `"${FIGMA_API_KEY}"` with the real token string.

### 4. Enable the server in WorkBuddy

1. Open **MCP 服务管理 / MCP Service Management** from the connector management page.
2. Find the `figma` server.
3. Toggle it on or click **信任 / Trust** if prompted.
4. Wait for the status to show connected (green dot).

### 5. Verify and use

Test with a prompt like:

- "读取这个 Figma 链接里的设计稿并生成 React 组件：`<Figma frame URL>`"
- "从这个 Figma 文件提取设计 token 并生成 CSS 变量：`<Figma file URL>`"
- "把这个 Figma 帧转换成 HTML + Tailwind"

When pasting a Figma link, prefer links to a specific frame or component (select it in Figma and press `Cmd/Ctrl + L`) rather than the whole file, because large files may exceed context limits.

## Troubleshooting

- **Error: `streamableHttp connect failed: fetch failed; sse connect failed: SSE error: TypeError: fetch failed: read ECONNRESET`**
  - Cause: the official Figma remote MCP server (`https://mcp.figma.com/mcp`) requires OAuth and rejects unauthenticated connections.
  - Fix: switch to the token-based `figma-developer-mcp` stdio configuration above.

- **Error: `FIGMA_API_KEY is required` or 401**
  - The token is missing or invalid. Regenerate the token in Figma settings and update `~/.workbuddy/mcp.json`.

- **Tools do not appear after enabling**
  - Restart the MCP server in the MCP service management panel, or close and reopen the WorkBuddy conversation.

## Alternative: Figma Desktop MCP

If the user cannot or does not want to use a token:

1. Open Figma desktop app v116.3+.
2. Open a design file, switch to **Dev Mode**.
3. Enable **MCP Server** in the right sidebar.
4. Copy the local server URL, usually `http://127.0.0.1:3845/mcp`.
5. Update `~/.workbuddy/mcp.json`:

```json
{
  "mcpServers": {
    "figma": {
      "type": "streamableHttp",
      "url": "http://127.0.0.1:3845/mcp",
      "timeout": 30000
    }
  }
}
```

Keep the Figma desktop app running while using the MCP.
