# Browser Automation Project

A local browser automation agent that uses Chrome via Chrome DevTools Protocol (CDP) to perform tasks on the web.

## Tools & Frameworks

### Primary
- **[Stagehand](https://github.com/browserbase/stagehand)** — High-level agent framework for browser automation. Best for complex multi-step workflows, reasoning, and natural language instructions.
- **[Chrome DevTools MCP](https://github.com/ChromeDevTools/chrome-devtools-mcp)** — Direct Chrome DevTools access via MCP skill. Best for low-level control, debugging, and DevTools-specific operations.
- **[browser-use](https://github.com/browser-use/browser-use)** — Alternative agent framework. Use if stagehand doesn't fit the task.

### Local Chrome
All automation runs against local Chrome via CDP. No remote browsers or BrowserBase cloud.

## When to Use Each Tool

| Tool | Use When |
|------|----------|
| **Stagehand** | Multi-step tasks, natural language reasoning, high-level workflows, when you need the agent to reason about what to do next |
| **Chrome DevTools MCP** | Direct element inspection, network interception, performance profiling, debugging, low-level browser control |
| **browser-use** | Stagehand doesn't fit the use case, or you need a different agent architecture |

## Global Tooling Rules

See parent CLAUDE.md for:
- Python: `uv` only
- Node/JS: `pnpm` only
- Versions: `mise` only
- Env vars: `mise.toml` + `.env`
- Docker: `colima` runtime

## Getting Started

1. Install Stagehand: `uv add stagehand`
2. Ensure Chrome is available locally
3. Create agents that use CDP to control local Chrome

## Example Task Structure

```
Task: [High-level goal]
Tool: [stagehand/chrome-devtools-mcp/browser-use]
Steps:
  1. Navigate to [URL]
  2. Locate [element via CSS/XPath]
  3. Perform [action]
  4. Verify [result]
```
