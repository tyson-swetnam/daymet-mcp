---
title: "Hosted HTTP deployment"
description: "Run the daymet-mcp container as a stateless HTTP service behind a TLS reverse proxy, with health checks and host settings."
type: Guide
tags:
  - deploy
  - docker
  - http
generated:
  by: "claude/opus-5.5"
  at: "2026-11-15T00:00:00Z"
sources:
  - id: design
    resource: "DESIGN.md"
    title: "daymet-mcp design"
    author: "team:daymet-mcp"
status: stable
---

# Hosted HTTP deployment

The image listens on `0.0.0.0:8080` inside the container, runs as uid 10001 and has a
`HEALTHCHECK` on `/healthz`. `docker-compose.yml` publishes it on `127.0.0.1:8080` only.

```bash
docker compose up -d
curl -s http://127.0.0.1:8080/healthz
```

Behind a reverse proxy, set the public URL so Host/Origin checks accept it:

```bash
DAYMET_MCP_SERVER__PUBLIC_BASE_URL=https://daymet-mcp.example.org
```

The server is stateless: run several replicas behind a load balancer without session affinity.
Each replica keeps its own in-memory cache; set `cache.disk_dir` to a volume to share cached
cell-years across restarts.
