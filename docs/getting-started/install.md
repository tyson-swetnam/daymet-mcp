---
title: "Install daymet-mcp"
description: "Install daymet-mcp from a checkout with uv, as a uv tool, or as the container image, and check that it runs."
type: Guide
tags:
  - install
  - uv
  - docker
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

# Install daymet-mcp

daymet-mcp needs Python 3.11 or newer. It has no GDAL or NumPy dependency unless you install the
optional `grid` extra (Earthdata backend and NetCDF output).

## From a checkout (development)

```bash
git clone <repository-url> daymet-mcp
cd daymet-mcp
uv sync                      # runtime + dev extras from the hashed uv.lock
uv run daymet-mcp --version
uv run daymet-mcp --check    # offline self-test: config and schemas
```

Add `--extra grid` to `uv sync` for the experimental Earthdata backend and NetCDF downloads.

## As a uv tool

```bash
uv tool install ./daymet-mcp          # or a git URL once the repository is published
daymet-mcp --check --live             # adds one tiny live single-pixel request
```

## Container image

The `Dockerfile` builds a two-stage image from a digest-pinned `python:3.13-slim`, installs the
locked dependencies with `uv sync --frozen --no-dev`, builds daymet-mcp with the hash-locked
hatchling from the `build` dependency group (`--no-build-isolation`), runs as uid 10001 and serves
Streamable HTTP on port 8080.

```bash
docker build -t daymet-mcp:local .
docker run --rm -p 127.0.0.1:8080:8080 daymet-mcp:local
curl -s http://127.0.0.1:8080/healthz
```

The image can also run over stdio: `docker run --rm -i daymet-mcp:local daymet-mcp --transport stdio`.
