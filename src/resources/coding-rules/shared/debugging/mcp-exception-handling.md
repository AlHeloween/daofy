<!-- @when: Developing an MCP tool or troubleshooting a tool anomaly -->
<!-- @chain: after=collaboration-workflow.md -->

### 8.6 MCP Tool Exception-Handling Conventions

| Layer | Handling |
|------|---------|
| `tools/*.py` handler | Catch concrete exceptions, return `{"error":"..."}` + log with `exc_info=True`; do not throw |
| `server.py call_tool` | Top-level catch-all for every exception, formatted as `CallToolResult(isError=True)`; bare throws are forbidden |
| `services/*.py` | Business exceptions use custom exception classes, keeping the call chain; log but do not swallow |
| `utils/*.py` | Usually no catching — let the upper layer handle it uniformly |