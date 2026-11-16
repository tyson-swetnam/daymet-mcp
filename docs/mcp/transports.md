---
title: "Transports"
description: "daymet-mcp speaks stdio for local clients and stateless Streamable HTTP at /mcp, with health and readiness endpoints."
type: Reference
tags:
  - transports
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
  - id: design
    resource: "DESIGN.md"
    title: "daymet-mcp design"
    author: "team:daymet-mcp"
status: stable
---

# Transports

## stdio (default)

`daymet-mcp` with no arguments serves MCP over stdin/stdout. Logs go to stderr; stdout carries
only protocol messages (a test checks this). All eight tools are available.

## Stateless Streamable HTTP

`daymet-mcp --transport http [--host 127.0.0.1] [--port 8080]` serves:

| Path | Behaviour |
| --- | --- |
| `POST /mcp` | MCP JSON-RPC, stateless (no session header), JSON responses, 1 MiB body cap |
| `GET`, `DELETE /mcp` | 405 with `Allow: POST` |
| `GET /healthz` | `{"status":"ok","version","protocolVersion","transport":"http"}` |
| `GET /readyz` | 503 while the CMR latest-year lookup warms up, then `{"status":"ready","degraded":false}` (`degraded: true` if CMR failed) |

Host and Origin headers are checked against `127.0.0.1`, `localhost`, the bind host and any
`server.allowed_hosts` / `server.allowed_origins` / `server.public_base_url` (DNS-rebinding
protection). Every response carries `x-request-id`.

Over HTTP `daymet_download_area` is not listed and a call to it returns
`not_available_in_http_mode`; the Earthdata backend is off unless
`earthdata.allow_in_http_mode=true`.
