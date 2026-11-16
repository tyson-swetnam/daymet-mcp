---
title: "Security"
description: "The daymet-mcp security model: anonymous read-only access, no credentials over HTTP, downloads only over stdio."
type: Policy
tags:
  - security
  - credentials
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

# Security

* **No user data, no OAuth.** Hosted daymet-mcp offers anonymous read access to public data.
  Deployers who need access control put it behind a reverse proxy that authenticates.
* **No credentials over the wire.** The Earthdata token comes only from the operator's environment
  (`DAYMET_MCP_EARTHDATA__TOKEN`); no tool argument or HTTP header carries one. The token is sent
  only to Earthdata hosts and is masked in logs, errors, results and manifests.
* **Earthdata over HTTP is off by default.** With `earthdata.allow_in_http_mode=true` every
  anonymous caller can use the operator's Earthdata quota.
* **No disk writes over HTTP.** `daymet_download_area` exists only over stdio, writes only under
  `downloads.dir` and refuses symbolic links and paths that leave it.
* **Outbound requests** go only to an allow-list of HTTPS hosts (`daymet.ornl.gov`,
  `cmr.earthdata.nasa.gov` and three Earthdata hosts), GET only, with a generic User-Agent and local
  rate limits.
* **Bounded CPU per call.** An area request is sized from its bounding rectangle before any
  cell is enumerated and refused when no backend open to the caller could serve it; the
  enumeration itself runs in a worker thread, so `/healthz` and the per-tool timeout keep working.
