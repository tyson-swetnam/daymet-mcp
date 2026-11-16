# SPDX-FileCopyrightText: 2026 Tyson Lee Swetnam
# SPDX-License-Identifier: MIT
"""``daymet_ping``."""

from __future__ import annotations

import time
from datetime import date

from mcp.types import LATEST_PROTOCOL_VERSION

from daymet_mcp import __version__
from daymet_mcp.context import ToolContext
from daymet_mcp.daymet.earthdata import describe_backend
from daymet_mcp.daymet.single_pixel import ENDPOINT, location_for
from daymet_mcp.errors import UpstreamError
from daymet_mcp.models.catalog import Backends, PingInput, PingOutput, ServerInfo, UpstreamCheck
from daymet_mcp.registry import register_tool

#: A fixed 2-day probe at the EEMT sample DEM cell (Valles Caldera, NM).
PROBE_LAT, PROBE_LON = 35.802997, -106.624036
PROBE_START, PROBE_END = date(2020, 1, 1), date(2020, 1, 2)


@register_tool(
    "daymet_ping",
    title="Ping daymet-mcp",
    description=(
        "Report the daymet-mcp version, MCP protocol version, transport and which backends are "
        "usable (single-pixel always; Earthdata only with an operator token). With "
        "check_upstream=true it makes one tiny live single-pixel request and reports latency. "
        "Next: call daymet_list_variables to see variables, units and aggregation rules."
    ),
    input_model=PingInput,
    output_model=PingOutput,
    surface="core",
    endpoints=[ENDPOINT],
)
async def daymet_ping(args: PingInput, ctx: ToolContext) -> PingOutput:
    upstream = None
    if args.check_upstream:
        where = location_for(PROBE_LAT, PROBE_LON, "na")
        started = time.monotonic()
        try:
            _, rows = await ctx.services.pixel.get_window(
                where.query_lat, where.query_lon, PROBE_START, PROBE_END, ctx.stats
            )
            upstream = UpstreamCheck(
                ok=True,
                latency_ms=round((time.monotonic() - started) * 1000, 1),
                status="ok",
                rows=rows,
            )
        except UpstreamError as exc:
            upstream = UpstreamCheck(
                ok=False,
                latency_ms=round((time.monotonic() - started) * 1000, 1),
                status=f"{exc.kind}:{exc.status or ''}".rstrip(":"),
            )
    earthdata = describe_backend(
        ctx.config.token_value() is not None, ctx.transport, ctx.config.earthdata.allow_in_http_mode
    )
    return PingOutput(
        server=ServerInfo(
            name="daymet-mcp",
            version=__version__,
            protocol_version=LATEST_PROTOCOL_VERSION,
            transport=ctx.transport,
        ),
        backends=Backends(earthdata=earthdata),  # type: ignore[arg-type]
        upstream=upstream,
        notes=["The Earthdata backend is experimental: no credentialed request has been tested."],
        next_steps=["daymet_list_variables()", "daymet_locate_cell(lat=..., lon=...)"],
    )
