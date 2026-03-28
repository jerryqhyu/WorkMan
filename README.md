# AgentPM

A local-first macOS desktop control plane for feature planning and parallel Claude Code execution.

## What this starter includes

- Tauri 2 desktop shell with a React/TypeScript UI styled to feel like a native macOS app.
- Local Python control plane with FastAPI, SQLite, and a background master-agent event loop.
- First-class **Feature → Task → Run** data model.
- Internal feature chat that asks a master agent to maintain a task graph.
- Parallel child-agent execution for implementation tasks, each in its own Git worktree/branch.
- Claude Code integration through the official non-interactive CLI workflow.
- Repo living docs support:
  - `CHANGELOG.md`
  - `.agentpm/memory/PROJECT_MEMORY.md`
  - `.agentpm/features/<feature-id>.md`
- Draft PR creation for GitHub remotes when `GITHUB_TOKEN` is set.
- A built-in MCP server so Cursor, VS Code, Claude Desktop, and ChatGPT can connect to the same board/task model.

## Architecture

```text
apps/desktop/        Tauri shell + React UI
backend/             FastAPI, SQLite, master loop, Claude executor, MCP server
connectors/          Example MCP configurations for Cursor / VS Code / Claude Desktop / ChatGPT
templates/           Repo bootstrap files for managed projects
scripts/             Development and packaging helpers
```

## Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/)
- Node.js 20+
- Rust toolchain when you want to build the Tauri desktop bundle
- Git
- Claude Code CLI on your `PATH`
- `ANTHROPIC_API_KEY` exported in your shell

Optional:

- `GITHUB_TOKEN` for draft PR creation

## Quick start (web/dev mode)

```bash
git clone <your-copy>
cd agentpm
./scripts/dev.sh
```

That starts:

- FastAPI on `http://127.0.0.1:8765`
- Vite on `http://127.0.0.1:3000`

## Desktop app flow

1. Install Rust.
2. Build the Python sidecar:

```bash
./scripts/build_sidecar.sh
```

3. Start Tauri:

```bash
cd apps/desktop
npm install
npm run tauri:dev
```

## Claude Code integration

The planner and all child agents are Claude Code runs.

- Planner calls `claude --bare -p ... --output-format json --json-schema ...`
- Executors call `claude --bare -p ... --output-format stream-json --verbose --include-partial-messages`
- AgentPM handles worktree creation, commit/push, PR creation, and document sync around those runs.

## Managed repo bootstrap

Importing a repository through the UI automatically creates these files if they do not exist:

- `AGENTS.md`
- `CLAUDE.md`
- `.agentpm/project.yaml`
- `.agentpm/memory/PROJECT_MEMORY.md`
- `CHANGELOG.md`

You can also do it manually:

```bash
cd backend
uv run agentpm-server bootstrap-repo /path/to/repo --name "My Project"
```

## Local storage

The backend stores persistent state under your user application data directory via `platformdirs`:

- SQLite database
- worktree roots
- logs
- content blobs

The app does **not** store its database in the repo.

## MCP server

Run the MCP server over Streamable HTTP:

```bash
cd backend
uv run agentpm-server mcp --port 8766
```

Or stdio for local clients:

```bash
cd backend
uv run agentpm-server mcp --transport stdio
```

See `connectors/` for client examples.

## Known limitations in this starter

This is intentionally opinionated and local-first. It is a strong implementation starting point, but you will still want to extend it with:

- richer approvals / review workflows
- GitHub App auth + webhooks instead of token-only PR creation
- stronger retry / cancel / resume semantics
- more polished MCP Apps UI for ChatGPT
- packaging, notarization, auto-update, and keychain storage for production macOS distribution

