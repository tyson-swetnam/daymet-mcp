---
title: "Architecture"
description: "The daymet-mcp modules and how a tool call flows from the MCP adapter through the registry to the upstream client and cache."
type: Reference
tags:
  - architecture
  - develop
generated:
  by: "claude/opus-5.5"
  at: "2026-11-15T00:00:00Z"
sources:
  - id: design
    resource: "DESIGN.md"
    title: "daymet-mcp design"
    author: "team:daymet-mcp"
  - id: neon-mcp
    resource: "https://github.com/idss-mesa/neon-mcp"
    title: "idss-mesa/neon-mcp reference server"
    author: "team:idss-mesa"
status: stable
---

# Architecture

```
src/daymet_mcp/
  server.py        the only module that imports the MCP SDK server API
  registry.py      @register_tool, validation, timeout, size budget
  tools/           one module per tool family; handlers are async (args, ctx) -> OutputModel
  models/          pydantic inputs (snake_case, extra=forbid) and outputs (camelCase)
  daymet/
    client.py      one httpx.AsyncClient: host allow-list, manual redirects, retries
    ratelimit.py   token buckets per host group
    cache.py       TTL + LRU, single flight, stale-if-error, optional disk layer
    catalog.py     variables, aggregation rules, regions, collections, grid
    calendar.py    the 365-day Daymet calendar
    lcc.py         pure-Python Lambert Conformal Conic and grid snapping
    single_pixel.py  request builder, parser and silent-failure guards
    cmr.py         latest published year per product
    aggregate.py   monthly and annual reductions
    earthdata.py   experimental OPeNDAP subsetting ([grid] extra)
    writers.py     AAIGrid + .prj, CSV, NetCDF
  resources.py, prompts.py, instructions.py
  transport/       stdio, stateless Streamable HTTP, /healthz and /readyz
```

A call arrives at `server.py`, which builds a per-call context (config, services, transport,
upstream statistics) and hands it to `registry.invoke`. The registry validates arguments against
the input model, runs the handler under the per-tool timeout, maps upstream failures onto the
error vocabulary, dumps the result model, trims it to the size budget and returns it; the adapter
wraps it as text plus `structuredContent` with `io.daymet-mcp/upstream` in `_meta`.

The layout, registry, envelope, error model and transports follow
[idss-mesa/neon-mcp](https://github.com/idss-mesa/neon-mcp){target=_blank}; `DESIGN.md` records
every decision (D1-D21).
