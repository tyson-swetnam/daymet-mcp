---
title: "Earthdata credentials"
description: "When daymet-mcp needs a NASA Earthdata token, how an operator sets it, and how the server keeps it out of logs and results."
type: Guide
tags:
  - earthdata
  - credentials
  - security
generated:
  by: "claude/opus-5.5"
  at: "2026-11-15T00:00:00Z"
sources:
  - id: edl-tokens
    resource: "https://urs.earthdata.nasa.gov/documentation/for_users/user_token"
    title: "Earthdata Login user tokens"
    author: "team:nasa-earthdata"
  - id: research
    resource: "RESEARCH.md"
    title: "daymet-mcp research notes"
    author: "team:daymet-mcp"
  - id: design
    resource: "DESIGN.md"
    title: "daymet-mcp design"
    author: "team:daymet-mcp"
status: draft
---

# Earthdata credentials

**Most uses need no credentials.** Points, monthly and annual summaries at a point, and areas up
to 121 cells (and 605 cell-years) use the ORNL single-pixel API, which answers without a login.

Larger areas need Daymet's gridded files. Every gridded endpoint tested (THREDDS/NCSS, OPeNDAP,
HTTPS) redirected to NASA Earthdata Login and answered HTTP 401 without credentials, so daymet-mcp
can read them only with an Earthdata Login (EDL) user token. **This backend is experimental: no
credentialed request has been made yet**, and its NetCDF parser is tested only against a synthetic
fixture.

## Setting the token (operator)

1. Create an Earthdata Login account and generate a user token in your EDL profile.
2. Install the `grid` extra (`uv sync --extra grid`).
3. Export the token before starting the server:

```bash
export DAYMET_MCP_EARTHDATA__TOKEN=...   # environment only
uv run daymet-mcp
```

The token is **only** read from that environment variable. It is not accepted from command-line
flags, YAML, tool arguments or HTTP headers, and the server never reads `~/.netrc` or cookie files.

## What the server does with it

* Sends it as `Authorization: Bearer` only to Earthdata hosts (`opendap.earthdata.nasa.gov`,
  `urs.earthdata.nasa.gov`, `data.ornldaac.earthdata.nasa.gov`), never to `daymet.ornl.gov` or
  CMR, and drops it on any redirect to another host.
* Masks it in logs, error messages, results, download manifests and `--print-config`.
* Over hosted HTTP the Earthdata backend is **off** unless the operator sets
  `earthdata.allow_in_http_mode=true`; then every anonymous caller can spend the operator's quota.
