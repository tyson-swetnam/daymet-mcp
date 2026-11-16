---
okf_version: "0.2"
title: daymet-mcp
description: "daymet-mcp is a Model Context Protocol (MCP 2026-07-28) server that retrieves Daymet V4 R1 weather data on demand, with explicit monthly aggregation."
---

# daymet-mcp

**daymet-mcp** is a [Model Context Protocol](https://modelcontextprotocol.io/){target=_blank}
server for [Daymet V4 R1](https://daymet.ornl.gov/){target=_blank}, the 1 km daily surface
weather grids for North America, Hawaii and Puerto Rico published by the ORNL DAAC. It lets AI
agents and the EEMT pipelines fetch Daymet values when they need them: daily values at a point,
monthly and annual summaries, the grid cell that contains a point, small-area grids, files on
disk and citations.

Every summary states how it was computed. **Monthly and annual precipitation are totals of daily
values** (mm/month, mm/year); temperature, vapour pressure, snow water equivalent, radiation and
day length are means. Each series carries its aggregation, units and a field label such as
`prcp_monthly_total_mm`, so "is this a total or a mean?" never has to be guessed.

Point data and areas up to 121 cells need no login: they use the ORNL single-pixel API. Larger
areas need a NASA Earthdata token set by the operator (experimental backend).

## Install in one minute

```bash
git clone <repository-url> daymet-mcp && cd daymet-mcp
uv sync
claude mcp add daymet -s user -- uv --directory "$PWD" run daymet-mcp
```

Then ask your agent to call `daymet_ping`.

## Documentation

This site is an [Open Knowledge Format (OKF) v0.2](https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md){target=_blank}
bundle: every page carries YAML frontmatter with `type`, provenance and lifecycle fields, and the
whole corpus is available to agents at [`llms.txt`](llms.txt) and [`llms-full.txt`](llms-full.txt).

* [Getting started](getting-started/index.md) - Install daymet-mcp, connect an MCP client, configure it and add Earthdata credentials if you need large areas.
* [Tools](tools/index.md) - The eight tools, the generated reference, aggregation rules, points, areas, downloads, resources and prompts.
* [MCP protocol](mcp/index.md) - How daymet-mcp implements the MCP 2026-07-28 stateless core over stdio and Streamable HTTP.
* [Deploy](deploy/index.md) - Run daymet-mcp as a hosted HTTP service and the security model it assumes.
* [Develop](develop/index.md) - Architecture, adding a tool, the hermetic test suite and contributing.
* [About](about/index.md) - Using daymet-mcp with EEMT, guidance for AI agents, citing Daymet and licences.
