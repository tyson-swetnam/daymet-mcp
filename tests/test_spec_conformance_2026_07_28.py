# SPDX-FileCopyrightText: 2026 Tyson Lee Swetnam
# SPDX-License-Identifier: MIT
"""MCP 2026-07-28 conformance through the MCP SDK client (in-process server).

Every tool is listed and called through ``mcp.Client``; schemas, annotations, ``_meta``,
cache hints, structured/text equality, resources and prompts are checked.
"""

from __future__ import annotations

import json
from typing import Any

import jsonschema
import pytest
from mcp import Client
from mcp.shared.exceptions import MCPError
from mcp.types import LATEST_PROTOCOL_VERSION

from daymet_mcp.server import JSON_SCHEMA_DIALECT, META_UPSTREAM, DaymetServer
from tests.fixture_router import FixtureRouter
from tests.helpers import EVERY_TOOL_CALL

ANNOTATION_KEYS = ("read_only_hint", "destructive_hint", "idempotent_hint", "open_world_hint")
#: Measured compact size of tools/list (stdio) when written; the bound allows 25 % growth.
TOOLS_LIST_MEASURED_BYTES = 41_300


def test_protocol_version_and_sdk() -> None:
    from importlib.metadata import version

    assert LATEST_PROTOCOL_VERSION == "2026-07-28"
    assert int(version("mcp").split(".")[0]) == 2


async def test_tools_list(server: DaymetServer) -> None:
    async with Client(server.build_mcp_server()) as client:
        result = await client.list_tools()
        names = [t.name for t in result.tools]
        assert names == sorted(names) == sorted(EVERY_TOOL_CALL)
        size = len(json.dumps(result.model_dump(by_alias=True, mode="json", exclude_none=True)))
        assert size <= TOOLS_LIST_MEASURED_BYTES * 1.25
        for tool in result.tools:
            assert tool.title and tool.description and len(tool.description) <= 600
            assert tool.description.rstrip().split(". ")[-1].startswith("Next:") or (
                "Next:" in tool.description
            )
            assert tool.input_schema["$schema"] == JSON_SCHEMA_DIALECT
            assert tool.output_schema is not None
            assert tool.output_schema["$schema"] == JSON_SCHEMA_DIALECT
            jsonschema.Draft202012Validator.check_schema(tool.input_schema)
            jsonschema.Draft202012Validator.check_schema(tool.output_schema)
            assert tool.input_schema.get("additionalProperties") is False
            ann = tool.annotations
            assert ann is not None and ann.title
            for key in ANNOTATION_KEYS:
                assert isinstance(getattr(ann, key), bool), (tool.name, key)
            meta = tool.meta or {}
            for key in ("surface", "endpoints", "stdioOnly", "requiresToken"):
                assert f"io.daymet-mcp/{key}" in meta, (tool.name, key)
        download = next(t for t in result.tools if t.name == "daymet_download_area")
        assert download.meta and download.meta["io.daymet-mcp/stdioOnly"] is True
        assert download.annotations and download.annotations.read_only_hint is False


async def test_every_tool_through_the_sdk(server: DaymetServer, router: FixtureRouter) -> None:
    async with Client(server.build_mcp_server()) as client:
        tools = {t.name: t for t in (await client.list_tools()).tools}
        for name, args in EVERY_TOOL_CALL.items():
            result = await client.call_tool(name, args)
            assert not result.is_error, (name, result.structured_content)
            structured = result.structured_content
            assert isinstance(structured, dict)
            text = result.content[0].text  # type: ignore[union-attr]
            assert json.loads(text) == structured
            schema = tools[name].output_schema
            assert schema is not None
            jsonschema.Draft202012Validator(schema).validate(structured)
            meta = result.meta or {}
            assert META_UPSTREAM in meta and "io.modelcontextprotocol/serverInfo" in meta
            assert set(meta[META_UPSTREAM]) == {
                "requests",
                "cacheHits",
                "rateLimitRemaining",
                "rateLimitLimit",
                "backend",
            }
            assert structured["nextSteps"]
    assert not router.unexpected


async def test_tool_errors_are_results(server: DaymetServer) -> None:
    async with Client(server.build_mcp_server()) as client:
        bad = await client.call_tool("daymet_locate_cell", {"lat": 999, "lon": 0})
        assert bad.is_error
        assert isinstance(bad.structured_content, dict)
        assert bad.structured_content["error"]["code"] == "invalid_argument"
        unknown = await client.call_tool("daymet_nope", {})
        assert unknown.is_error and unknown.structured_content
        assert unknown.structured_content["error"]["code"] == "unknown_tool"


async def test_resources_and_prompts(server: DaymetServer) -> None:
    async with Client(server.build_mcp_server()) as client:
        listed = await client.list_resources()
        assert {str(r.uri) for r in listed.resources} >= {"daymet://guide/aggregation"}
        templates = await client.list_resource_templates()
        assert len(templates.resource_templates) == 2
        read = await client.read_resource("daymet://guide/aggregation")
        assert "mm/month" in read.contents[0].text  # type: ignore[union-attr]
        with pytest.raises(MCPError) as info:
            await client.read_resource("daymet://guide/agregation")
        assert info.value.code == -32602
        assert info.value.data["code"] == "not_found"
        assert "daymet://guide/aggregation" in info.value.data["didYouMean"]
        prompts = await client.list_prompts()
        assert len(prompts.prompts) == 3
        got = await client.get_prompt(
            "daymet_monthly_precip_check", {"lat": "35.8", "lon": "-106.6", "year": "2020"}
        )
        assert "SUM" in got.messages[0].content.text  # type: ignore[union-attr]
        with pytest.raises(MCPError) as info:
            await client.get_prompt("daymet_site_climate", {"lat": "x"})
        assert info.value.code == -32602


async def test_cache_hints(server: DaymetServer) -> None:
    async with Client(server.build_mcp_server(), cache=None) as client:
        tools: Any = await client.list_tools()
        assert tools.ttl_ms == 300_000 and tools.cache_scope == "public"
        prompts: Any = await client.list_prompts()
        assert prompts.ttl_ms == 86_400_000 and prompts.cache_scope == "public"
        res: Any = await client.list_resources()
        assert res.ttl_ms == 3_600_000 and res.cache_scope == "public"


async def test_http_tool_list_excludes_downloads(http_server: DaymetServer) -> None:
    async with Client(http_server.build_mcp_server()) as client:
        names = [t.name for t in (await client.list_tools()).tools]
        assert "daymet_download_area" not in names and len(names) == 7
        result = await client.call_tool(
            "daymet_download_area", EVERY_TOOL_CALL["daymet_download_area"]
        )
        assert result.is_error and result.structured_content
        assert result.structured_content["error"]["code"] == "not_available_in_http_mode"
