# ChatGPT connector

ChatGPT works with remote MCP servers.

For local development:

1. Run the AgentPM MCP server:

```bash
cd backend
uv run agentpm-server mcp --port 8766
```

2. Expose `http://127.0.0.1:8766/mcp` over HTTPS using your preferred tunnel or deployment target.
3. Add the resulting MCP server URL in ChatGPT connector / developer settings.

This repository includes the MCP tool/resource surface. A production ChatGPT app would typically add authentication, a stable HTTPS endpoint, and optionally an MCP Apps widget.
