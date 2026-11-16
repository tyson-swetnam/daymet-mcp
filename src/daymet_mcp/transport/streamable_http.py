# SPDX-FileCopyrightText: 2026 Tyson Lee Swetnam
# SPDX-License-Identifier: MIT
"""Stateless Streamable HTTP at ``/mcp`` (MCP 2026-07-28).

Adapted from idss-mesa/neon-mcp ``transport/streamable_http.py`` (MIT). The SDK builds the
Starlette app (``stateless_http=True``: no session header); daymet-mcp adds ``/healthz`` and
``/readyz`` and one raw ASGI middleware for request ids. ``GET``/``DELETE /mcp`` -> 405.
No credentials are accepted over HTTP (D17).
"""

from __future__ import annotations

import re
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

import anyio
import structlog
from mcp.server.transport_security import TransportSecuritySettings
from starlette.routing import Route

from daymet_mcp.config import MIB, ServerConfig
from daymet_mcp.context import current_request_id
from daymet_mcp.transport.healthz import healthz, readyz

if TYPE_CHECKING:
    from starlette.applications import Starlette
    from starlette.types import ASGIApp, Message, Receive, Scope, Send

    from daymet_mcp.server import DaymetServer

MCP_PATH = "/mcp"
MAX_BODY = 1 * MIB
_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
log = structlog.get_logger("daymet_mcp.http")


def transport_security(cfg: ServerConfig) -> TransportSecuritySettings:
    hosts = list(cfg.allowed_hosts)
    origins = list(cfg.allowed_origins)
    if cfg.public_base_url:
        parts = urlsplit(cfg.public_base_url)
        if parts.netloc:
            hosts.append(parts.netloc)
            origins.append(f"{parts.scheme}://{parts.netloc}")
    if not cfg.dns_rebinding_protection:
        return TransportSecuritySettings(enable_dns_rebinding_protection=False)
    hosts += [f"{cfg.host}:*", "127.0.0.1:*", "localhost:*", "[::1]:*"]
    origins += [
        f"http://{cfg.host}:*",
        "http://127.0.0.1:*",
        "http://localhost:*",
        "http://[::1]:*",
    ]
    return TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=list(dict.fromkeys(hosts)),
        allowed_origins=list(dict.fromkeys(origins)),
    )


class RequestContextMiddleware:
    """Raw ASGI middleware: request id, contextvar, log binding, 405 for GET/DELETE /mcp."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        if scope.get("path") == MCP_PATH + "/":
            scope = {**scope, "path": MCP_PATH, "raw_path": MCP_PATH.encode("ascii")}
        if scope.get("path") == MCP_PATH and scope.get("method") in ("GET", "DELETE"):
            await _method_not_allowed(send)
            return
        headers = {
            k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])
        }
        supplied = headers.get("x-request-id", "")
        request_id = supplied if _REQUEST_ID_RE.match(supplied) else uuid.uuid4().hex[:16]
        token = current_request_id.set(request_id)
        structlog.contextvars.bind_contextvars(request_id=request_id, path=scope.get("path"))

        async def send_with_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                raw = [
                    *list(message.get("headers", [])),
                    (b"x-request-id", request_id.encode("latin-1")),
                ]
                message = {**message, "headers": raw}
            await send(message)

        try:
            await self.app(scope, receive, send_with_id)
        finally:
            current_request_id.reset(token)
            structlog.contextvars.unbind_contextvars("request_id", "path")


async def _method_not_allowed(send: Send) -> None:
    body = b'{"error":"method_not_allowed","detail":"POST JSON-RPC requests to /mcp"}'
    await send(
        {
            "type": "http.response.start",
            "status": 405,
            "headers": [
                (b"content-type", b"application/json"),
                (b"allow", b"POST"),
                (b"content-length", str(len(body)).encode("ascii")),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})


def build_http_app(server: DaymetServer) -> Starlette:
    cfg = server.config.server
    mcp_server = server.build_mcp_server()
    app = mcp_server.streamable_http_app(
        streamable_http_path=MCP_PATH,
        stateless_http=True,
        json_response=cfg.json_response,
        max_request_body_size=MAX_BODY,
        host=cfg.host,
        transport_security=transport_security(cfg),
        custom_starlette_routes=[
            Route("/healthz", healthz, methods=["GET"]),
            Route("/readyz", readyz, methods=["GET"]),
        ],
    )
    app.state.daymet_server = server
    app.add_middleware(RequestContextMiddleware)
    return app


@asynccontextmanager
async def app_lifecycle(server: DaymetServer, *, prewarm: bool = True) -> AsyncIterator[None]:
    try:
        async with anyio.create_task_group() as tg:
            if prewarm:
                server.readiness = "warming"

                async def _prewarm() -> None:
                    ok = await server.prewarm()
                    server.readiness = "ready" if ok else "degraded"

                tg.start_soon(_prewarm)
            try:
                yield
            finally:
                tg.cancel_scope.cancel()
    finally:
        await server.aclose()


async def serve_http(server: DaymetServer) -> None:
    import uvicorn

    cfg = server.config.server
    app = build_http_app(server)
    async with app_lifecycle(server):
        config = uvicorn.Config(
            app,
            host=cfg.host,
            port=cfg.port,
            log_level=cfg.log_level.lower(),
            lifespan="on",
            proxy_headers=True,
            server_header=False,
        )
        await uvicorn.Server(config).serve()
