# SPDX-FileCopyrightText: 2026 Tyson Lee Swetnam
# SPDX-License-Identifier: MIT
"""``/healthz`` (liveness) and ``/readyz`` (CMR prewarm) for HTTP deployments."""

from __future__ import annotations

from typing import Any

from mcp.types import LATEST_PROTOCOL_VERSION
from starlette.requests import Request
from starlette.responses import JSONResponse

from daymet_mcp import __version__


async def healthz(request: Request) -> JSONResponse:
    del request
    return JSONResponse(
        {
            "status": "ok",
            "version": __version__,
            "protocolVersion": LATEST_PROTOCOL_VERSION,
            "transport": "http",
        }
    )


async def readyz(request: Request) -> JSONResponse:
    server: Any = getattr(request.app.state, "daymet_server", None)
    if server is None or server.readiness == "warming":
        return JSONResponse({"status": "warming"}, status_code=503)
    return JSONResponse({"status": "ready", "degraded": server.readiness == "degraded"})
