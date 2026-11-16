---
title: "Connect an MCP client"
description: "Register daymet-mcp with Claude Code, Claude Desktop or any MCP client over stdio, or point a client at the HTTP endpoint."
type: Guide
tags:
  - clients
  - stdio
  - http
generated:
  by: "claude/opus-5.5"
  at: "2026-11-15T00:00:00Z"
sources:
  - id: mcp-spec
    resource: "https://modelcontextprotocol.io/specification/2026-07-28"
    title: "Model Context Protocol specification 2026-07-28"
    author: "team:modelcontextprotocol"
status: stable
---

# Connect an MCP client

## stdio (local)

Claude Code:

```bash
claude mcp add daymet -s user -- uv --directory /path/to/daymet-mcp run daymet-mcp
```

Claude Desktop and other clients that read a JSON configuration:

```json
{
  "mcpServers": {
    "daymet": {
      "command": "uv",
      "args": ["--directory", "/path/to/daymet-mcp", "run", "daymet-mcp"],
      "env": {"DAYMET_MCP_DOWNLOADS__DIR": "/path/to/daymet-downloads"}
    }
  }
}
```

Over stdio every tool is available, including `daymet_download_area`, which writes files under
`downloads.dir`.

## Streamable HTTP

Start the server with `daymet-mcp --transport http` (default `127.0.0.1:8080`) and point the client
at `http://127.0.0.1:8080/mcp`. Over HTTP the download tool is not offered and the Earthdata backend
is off unless the operator enables it (see [Security](../deploy/security.md)).

## From Python

```python
from mcp import Client, StdioServerParameters

params = StdioServerParameters(command="uv", args=["run", "daymet-mcp"])
async with Client(params) as client:
    result = await client.call_tool("daymet_locate_cell", {"lat": 35.8, "lon": -106.6})
```
