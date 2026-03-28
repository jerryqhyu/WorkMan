# Claude Desktop connector

Run AgentPM MCP in stdio mode:

```bash
cd backend
uv run agentpm-server mcp --transport stdio
```

If you prefer an HTTP transport, expose `http://127.0.0.1:8766/mcp` through a local reverse proxy or tunneling tool supported by your MCP client.
