---
title: "Testing"
description: "The daymet-mcp test suite: hermetic unit tests on recorded fixtures, MCP protocol tests, and network-marked live tests."
type: Guide
tags:
  - testing
  - fixtures
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

# Testing

```bash
uv run pytest                       # hermetic: no network (the 'network' marker is deselected)
uv run pytest -m network tests/live # live tests against the real services
uv run python scripts/record_fixtures.py check
```

* **Hermetic by default.** `tests/fixture_router.py` is an `httpx.MockTransport` that replays the
  fixtures in `tests/fixtures/<host>/` and fails the test on any request it has no fixture for.
* **Fixtures** were recorded from real GETs without credentials (`scripts/record_fixtures.py
  record`): single-pixel 2020 (a leap year) at the EEMT sample DEM centre and in Hawaii, a 3x3
  mosaic, a 2-day window, an off-grid point, the unpublished-year response (truncated), CMR
  latest-granule pages and the Earthdata redirect chain. The NetCDF subset under
  `tests/fixtures/synthetic/` is **synthetic** (no subset can be recorded without credentials).
* **Science tests**: calendar, LCC against service-reported coordinates and pyproj, aggregation
  golden values from the fixture computed by an independent loop, and property tests (annual sum
  equals the sum of monthly sums).
* **Protocol tests**: the SDK client in-process, against a real stdio subprocess, and against a
  real HTTP server on 127.0.0.1, calling every tool.
* **Live tests** (marker `network`): one per tool, comparing values with the fixtures to detect
  revisions; `-m "network and edl"` needs `DAYMET_MCP_EARTHDATA__TOKEN`.

Coverage must stay at or above 85 %; `mypy --strict src` and `ruff check` must be clean.
