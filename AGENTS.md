# browser_automation

Misc automation tasks on PJ's local macbook, driving the user's real Chrome browser to perform jobs on the web.

## Goal

A small collection of scripts/agents that automate everyday browser work (form filling, scraping, account chores, multi-step web flows) by connecting to the user's **local Chrome** over the Chrome DevTools Protocol (CDP). Not a cloud project — everything runs on this machine against the user's logged-in browser session.

## Toolbox

Pick the best tool per job:

1. **[Stagehand](https://github.com/browserbase/stagehand)** — primary. AI-first browser automation built on Playwright (TypeScript/Node). Use over local Chrome via CDP. Good when natural-language `act` / `extract` / `observe` beats hand-written selectors.
2. **[chrome-devtools-mcp](https://github.com/ChromeDevTools/chrome-devtools-mcp/blob/main/skills/chrome-devtools-cli/SKILL.md)** — when an MCP-driven Claude Code session needs direct CDP control (DOM, network, perf, console) without writing a script.
3. **[browser-use](https://github.com/browser-use/browser-use)** — Python alternative when the task is better expressed as an agent loop, or when Python is more convenient (data libs, existing scripts).

Rules of thumb:
- Deterministic flow with stable selectors → plain Playwright/Stagehand `page.*` calls.
- Flow that needs LLM reasoning on the page → Stagehand `act`/`extract`.
- One-off interactive browser control from Claude Code → chrome-devtools-mcp.
- Python ecosystem fits better → browser-use.

## Connecting to local Chrome (CDP)

Launch Chrome with a remote debugging port, then attach to it instead of spawning a fresh browser. This preserves logged-in sessions, extensions, and profile state.

```bash
# macOS — launch Chrome with CDP enabled (dedicated profile to avoid conflicts with daily browsing)
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome \
  --remote-debugging-port=9222 \
  --user-data-dir="$HOME/.chrome-automation-profile"
```

Stagehand: set `env: "LOCAL"` and pass `localBrowserLaunchOptions.cdpUrl: "http://localhost:9222"`.

## Tooling conventions (this machine)

Per `~/.claude/CLAUDE.md`:

- **Node/TS**: `pnpm` only (no `npm` / `yarn` / `npx` — use `pnpm dlx`). `bun run` for fast one-shot TS execution.
- **Python**: `uv` only (`uv add`, `uv run`, `uv sync`).
- **Versions**: `mise` only. Add a `mise.toml` when a project pins versions.
- **Env**: `mise.toml [env]` + `.env`. No `direnv`.
- **Secrets**: never commit `.env`. LLM API keys (OpenAI / Anthropic for Stagehand) go in `.env`.

Stagehand is a Node package (`pnpm add @browserbasehq/stagehand`). browser-use is a Python package (`uv add browser-use`).

## Repo layout (evolving)

```
/                    # root
  AGENTS.md          # this file (also symlinked to .claude/CLAUDE.md)
  tasks/             # individual automation scripts, one folder per task
  lib/               # shared helpers (CDP connection, Chrome launcher, etc.)
```

Each task in `tasks/<name>/` should be self-contained with its own README explaining what it does and how to run it.

## Working agreements for AI agents

- Confirm before any destructive web action (deleting accounts, sending messages, posting publicly, money movement). Read-only / data-extraction tasks can proceed.
- Default to attaching to the existing Chrome over CDP rather than spawning a fresh Playwright browser, so the user's logins are reused.
- When a script needs credentials or 2FA, prompt the user — do not attempt to bypass.
- Prefer the smallest tool that works. Don't pull in Stagehand+LLM if a 5-line Playwright script does the job.
