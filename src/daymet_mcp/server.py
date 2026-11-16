# SPDX-FileCopyrightText: 2026 Tyson Lee Swetnam
# SPDX-License-Identifier: MIT
"""The MCP adapter — the only module that imports the MCP SDK server API.

Targets the MCP 2026-07-28 stateless core via the low-level ``mcp.server.Server`` with
constructor callbacks (SDK 2.x). Adapted from idss-mesa/neon-mcp ``server.py`` (MIT):

* ``tools/list`` is sorted, fixed per transport, public cache hint; every schema declares
  JSON Schema 2020-12;
* ``tools/call`` returns compact JSON as text *and* ``structuredContent`` plus
  ``io.daymet-mcp/upstream`` result ``_meta`` (the SDK adds ``serverInfo``).
"""

from __future__ import annotations

import json
import time
import uuid
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

import structlog
from mcp import types as t

from daymet_mcp import __version__
from daymet_mcp.config import Config
from daymet_mcp.context import Services, ToolContext, UpstreamStats, current_request_id
from daymet_mcp.errors import ToolError
from daymet_mcp.logging import register_secret
from daymet_mcp.registry import ToolSpec, get_registered_tools, get_tool, invoke

if TYPE_CHECKING:
    import httpx
    from mcp.server import Server

    from daymet_mcp.daymet.client import DaymetHttpClient

JSON_SCHEMA_DIALECT = "https://json-schema.org/draft/2020-12/schema"
TOOLS_LIST_TTL_MS = 300_000
RESOURCES_LIST_TTL_MS = 3_600_000
PROMPTS_LIST_TTL_MS = 86_400_000
DISCOVER_TTL_MS = 300_000

META_SURFACE = "io.daymet-mcp/surface"
META_ENDPOINTS = "io.daymet-mcp/endpoints"
META_STDIO_ONLY = "io.daymet-mcp/stdioOnly"
META_REQUIRES_TOKEN = "io.daymet-mcp/requiresToken"
META_UPSTREAM = "io.daymet-mcp/upstream"

SERVER_DESCRIPTION = (
    "Daymet V4 R1 daily weather, monthly/annual summaries with explicit aggregation, small-area "
    "grids and citations."
)

log = structlog.get_logger("daymet_mcp.server")


@dataclass
class CallOutcome:
    payload: dict[str, Any]
    is_error: bool
    stats: UpstreamStats


def dumps(payload: Any) -> str:
    return json.dumps(payload, separators=(",", ":"), ensure_ascii=False)


def compact_schema(schema: Any, keywords: tuple[str, ...]) -> Any:
    """Drop string-valued annotation keywords (a property *named* ``title`` survives)."""
    if isinstance(schema, dict):
        return {
            k: compact_schema(v, keywords)
            for k, v in schema.items()
            if not (k in keywords and isinstance(v, str))
        }
    if isinstance(schema, list):
        return [compact_schema(v, keywords) for v in schema]
    return schema


class DaymetServer:
    """Process-wide server object; one per transport deployment."""

    def __init__(
        self,
        config: Config,
        *,
        transport: Literal["stdio", "http"],
        client: DaymetHttpClient,
        services: Services,
    ) -> None:
        self.config = config
        self.transport: Literal["stdio", "http"] = transport
        self.client = client
        self.services = services
        self.readiness: Literal["ready", "warming", "degraded"] = "ready"

    @property
    def tools(self) -> list[ToolSpec]:
        return get_registered_tools(transport=self.transport)

    @staticmethod
    def input_schema(spec: ToolSpec) -> dict[str, Any]:
        raw = spec.input_model.model_json_schema(by_alias=True, mode="validation")
        schema: dict[str, Any] = dict(compact_schema(raw, ("title",)))
        schema["$schema"] = JSON_SCHEMA_DIALECT
        return schema

    @staticmethod
    def output_schema(spec: ToolSpec) -> dict[str, Any]:
        raw = spec.output_model.model_json_schema(by_alias=True, mode="serialization")
        schema: dict[str, Any] = dict(compact_schema(raw, ("title", "description")))
        schema["$schema"] = JSON_SCHEMA_DIALECT
        return schema

    def tool_definitions(self) -> list[t.Tool]:
        out: list[t.Tool] = []
        for spec in self.tools:
            meta: dict[str, Any] = {
                META_SURFACE: spec.surface,
                META_ENDPOINTS: list(spec.endpoints),
                META_REQUIRES_TOKEN: spec.requires_token,
                META_STDIO_ONLY: "http" not in spec.transports,
            }
            out.append(
                t.Tool(
                    name=spec.name,
                    title=spec.title,
                    description=spec.description,
                    input_schema=self.input_schema(spec),
                    output_schema=self.output_schema(spec),
                    annotations=t.ToolAnnotations(
                        title=spec.title,
                        read_only_hint=spec.read_only,
                        destructive_hint=spec.destructive,
                        idempotent_hint=spec.idempotent,
                        open_world_hint=spec.open_world,
                    ),
                    meta=meta,
                )
            )
        return out

    def tool_context(self, name: str, stats: UpstreamStats, request_id: str | None) -> ToolContext:
        return ToolContext(
            config=self.config,
            services=self.services,
            transport=self.transport,
            tool_name=name,
            stats=stats,
            request_id=request_id,
        )

    async def call(
        self, name: str, args: Mapping[str, Any] | None = None, *, request_id: str | None = None
    ) -> CallOutcome:
        """Run one tool call in-process (the adapter, resources, tests and ``--check``)."""
        stats = UpstreamStats()
        started = time.monotonic()
        request_id = request_id or current_request_id.get() or uuid.uuid4().hex[:16]
        try:
            spec = get_tool(name)
        except KeyError:
            err = ToolError(
                "unknown_tool",
                f"No tool named {name!r}.",
                details={"name": name, "available": [s.name for s in self.tools]},
            )
            return CallOutcome(err.to_payload(), True, stats)
        try:
            payload = await invoke(spec, args, self.tool_context(name, stats, request_id))
            outcome = CallOutcome(payload, False, stats)
        except ToolError as exc:
            outcome = CallOutcome(exc.to_payload(), True, stats)
        except Exception:
            log.exception("tool.crash", tool=name, request_id=request_id)
            err = ToolError(
                "internal_error",
                "The tool failed unexpectedly; the error was logged on the server.",
                details={"correlationId": request_id},
            )
            outcome = CallOutcome(err.to_payload(), True, stats)
        log.info(
            "tool.call",
            tool=name,
            ms=round((time.monotonic() - started) * 1000, 1),
            ok=not outcome.is_error,
            code=(outcome.payload.get("error") or {}).get("code") if outcome.is_error else None,
            result_bytes=len(dumps(outcome.payload)),
            upstream_requests=stats.requests,
            cache_hits=stats.cache_hits,
            request_id=request_id,
        )
        return outcome

    # ------------------------------------------------------------------ MCP

    def build_mcp_server(self) -> Server[Any]:
        from mcp.server import Server
        from mcp.server.caching import CacheHint
        from mcp.shared.exceptions import MCPError

        from daymet_mcp import prompts as prompt_mod
        from daymet_mcp import resources as resource_mod
        from daymet_mcp.instructions import SERVER_INSTRUCTIONS

        async def _on_list_tools(_ctx: Any, _params: Any = None) -> t.ListToolsResult:
            return t.ListToolsResult(tools=self.tool_definitions())

        async def _on_call_tool(ctx: Any, params: t.CallToolRequestParams) -> t.CallToolResult:
            rid = current_request_id.get() or (
                str(ctx.request_id) if getattr(ctx, "request_id", None) is not None else None
            )
            outcome = await self.call(params.name, params.arguments, request_id=rid)
            return t.CallToolResult(
                content=[t.TextContent(type="text", text=dumps(outcome.payload))],
                structured_content=outcome.payload,
                is_error=outcome.is_error,
                meta={META_UPSTREAM: outcome.stats.as_meta()},
            )

        async def _on_list_resources(_ctx: Any, _params: Any = None) -> t.ListResourcesResult:
            return t.ListResourcesResult(resources=resource_mod.list_resources())

        async def _on_list_resource_templates(
            _ctx: Any, _params: Any = None
        ) -> t.ListResourceTemplatesResult:
            return t.ListResourceTemplatesResult(
                resource_templates=resource_mod.list_resource_templates()
            )

        async def _on_read_resource(
            _ctx: Any, params: t.ReadResourceRequestParams
        ) -> t.ReadResourceResult:
            uri = str(params.uri)
            try:
                content = await resource_mod.read_resource(uri, self)
            except ToolError as exc:
                data: dict[str, Any] = {"code": exc.code}
                for key in ("didYouMean", "uri", "reason"):
                    if key in exc.details:
                        data[key] = exc.details[key]
                raise MCPError(t.INVALID_PARAMS, exc.message, data=data) from None
            return t.ReadResourceResult(
                contents=[
                    t.TextResourceContents(uri=uri, text=content.text, mime_type=content.mime_type)
                ],
                ttl_ms=content.ttl_ms,
                cache_scope="public",
            )

        async def _on_list_prompts(_ctx: Any, _params: Any = None) -> t.ListPromptsResult:
            return t.ListPromptsResult(prompts=prompt_mod.list_prompts())

        async def _on_get_prompt(_ctx: Any, params: t.GetPromptRequestParams) -> t.GetPromptResult:
            try:
                return prompt_mod.get_prompt(params.name, params.arguments)
            except ToolError as exc:
                raise MCPError(t.INVALID_PARAMS, exc.message, data={"code": exc.code}) from None

        instructions = SERVER_INSTRUCTIONS
        if self.config.server.instructions_extra:
            instructions += "\n\n" + self.config.server.instructions_extra
        return Server(
            "daymet-mcp",
            version=__version__,
            title="Daymet",
            description=SERVER_DESCRIPTION,
            instructions=instructions,
            cache_hints={
                "tools/list": CacheHint(ttl_ms=TOOLS_LIST_TTL_MS, scope="public"),
                "resources/list": CacheHint(ttl_ms=RESOURCES_LIST_TTL_MS, scope="public"),
                "resources/templates/list": CacheHint(ttl_ms=RESOURCES_LIST_TTL_MS, scope="public"),
                "resources/read": CacheHint(ttl_ms=RESOURCES_LIST_TTL_MS, scope="public"),
                "prompts/list": CacheHint(ttl_ms=PROMPTS_LIST_TTL_MS, scope="public"),
                "server/discover": CacheHint(ttl_ms=DISCOVER_TTL_MS, scope="public"),
            },
            on_list_tools=_on_list_tools,
            on_call_tool=_on_call_tool,
            on_list_resources=_on_list_resources,
            on_list_resource_templates=_on_list_resource_templates,
            on_read_resource=_on_read_resource,
            on_list_prompts=_on_list_prompts,
            on_get_prompt=_on_get_prompt,
        )

    async def prewarm(self) -> bool:
        """Learn the latest published year from CMR (HTTP readiness)."""
        latest = await self.services.cmr.latest_daily(UpstreamStats())
        return latest.source == "cmr"

    async def serve(self) -> None:
        if self.transport == "stdio":
            from daymet_mcp.transport.stdio import serve_stdio

            await serve_stdio(self)
        else:
            from daymet_mcp.transport.streamable_http import serve_http

            await serve_http(self)

    async def aclose(self) -> None:
        await self.client.aclose()


def create_server(
    config: Config,
    *,
    transport: Literal["stdio", "http"] | None = None,
    http_transport: httpx.AsyncBaseTransport | None = None,
    sleep: Callable[[float], Awaitable[None]] | None = None,
) -> DaymetServer:
    """Wire cache, limiter, client and services; import every tool module."""
    from daymet_mcp import tools as _tools  # noqa: F401  (registration side effect)
    from daymet_mcp.daymet.cache import TTLCache
    from daymet_mcp.daymet.client import DaymetHttpClient
    from daymet_mcp.daymet.cmr import CmrService
    from daymet_mcp.daymet.earthdata import EarthdataService
    from daymet_mcp.daymet.ratelimit import RateLimiter
    from daymet_mcp.daymet.single_pixel import SinglePixelService

    mode: Literal["stdio", "http"] = transport or config.server.transport
    token = config.token_value()
    register_secret(token)
    client = DaymetHttpClient(
        limiter=RateLimiter(sleep=sleep), transport=http_transport, sleep=sleep, token=token
    )
    disk = config.cache.disk_dir if mode == "stdio" or config.cache.disk_dir else None
    pixel_cache = TTLCache(
        max_entries=config.cache.max_cell_years,
        ttl_s=config.cache.ttl_s.pixel,
        stale_if_error_s=config.cache.stale_if_error_s,
        disk_dir=disk,
    )
    cmr_cache = TTLCache(
        max_entries=64, ttl_s=config.cache.ttl_s.cmr, stale_if_error_s=config.cache.stale_if_error_s
    )
    services = Services(
        pixel=SinglePixelService(client, pixel_cache, config.daymet.single_pixel_url),
        cmr=CmrService(
            client, cmr_cache, config.daymet.cmr_url, config.daymet.latest_year_fallback.daily
        ),
        earthdata=EarthdataService(client, config.earthdata.opendap_url),
    )
    return DaymetServer(config, transport=mode, client=client, services=services)


def run(config: Config, transport: str | None = None) -> None:
    import anyio

    mode: Literal["stdio", "http"] = (
        "http" if (transport or config.server.transport) == "http" else "stdio"
    )
    server = create_server(config, transport=mode)
    anyio.run(server.serve)
