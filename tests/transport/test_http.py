# SPDX-FileCopyrightText: 2026 Tyson Lee Swetnam
# SPDX-License-Identifier: MIT
"""Stateless Streamable HTTP: a real uvicorn server on 127.0.0.1 (fixture-backed upstream),
driven by the MCP SDK client over HTTP; health/readiness, 405s and the Host guard."""

from __future__ import annotations

import socket
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager

import anyio
import httpx
import uvicorn
from mcp import Client

from daymet_mcp.server import DaymetServer
from daymet_mcp.transport.streamable_http import app_lifecycle, build_http_app
from tests.helpers import EVERY_TOOL_CALL


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@asynccontextmanager
async def running(server: DaymetServer) -> AsyncIterator[str]:
    port = _free_port()
    app = build_http_app(server)
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning", lifespan="on")
    userver = uvicorn.Server(config)
    async with app_lifecycle(server), anyio.create_task_group() as tg:
        tg.start_soon(userver.serve)
        with anyio.fail_after(20):
            while not userver.started:
                await anyio.sleep(0.05)
        try:
            yield f"http://127.0.0.1:{port}"
        finally:
            userver.should_exit = True


async def test_every_http_tool(make_server: Callable[..., DaymetServer]) -> None:
    server = make_server(transport="http")
    async with running(server) as base, Client(f"{base}/mcp") as client:
        assert client.protocol_version == "2026-07-28"
        names = [t.name for t in (await client.list_tools()).tools]
        assert names == sorted(n for n in EVERY_TOOL_CALL if n != "daymet_download_area")
        for name in names:
            result = await client.call_tool(name, EVERY_TOOL_CALL[name])
            assert not result.is_error, (name, result.structured_content)
        refused = await client.call_tool(
            "daymet_download_area", EVERY_TOOL_CALL["daymet_download_area"]
        )
        assert refused.is_error and refused.structured_content
        assert refused.structured_content["error"]["code"] == "not_available_in_http_mode"


async def test_health_ready_and_methods(make_server: Callable[..., DaymetServer]) -> None:
    server = make_server(transport="http")
    async with running(server) as base, httpx.AsyncClient(base_url=base) as http:
        health = await http.get("/healthz", headers={"x-request-id": "abc-123"})
        assert health.status_code == 200
        assert health.json() == {
            "status": "ok",
            "version": "0.1.0",
            "protocolVersion": "2026-07-28",
            "transport": "http",
        }
        assert health.headers["x-request-id"] == "abc-123"
        with anyio.fail_after(10):
            while (await http.get("/readyz")).status_code != 200:
                await anyio.sleep(0.05)
        assert (await http.get("/readyz")).json() == {"status": "ready", "degraded": False}
        for method in ("GET", "DELETE"):
            r = await http.request(method, "/mcp")
            assert r.status_code == 405 and r.headers["allow"] == "POST"
        evil = await http.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
            headers={"host": "evil.example", "accept": "application/json, text/event-stream"},
        )
        assert evil.status_code in (400, 403, 421)
        big = await http.post(
            "/mcp",
            content=b"x" * (1024 * 1024 + 10),
            headers={"content-type": "application/json", "accept": "application/json"},
        )
        assert big.status_code == 413
