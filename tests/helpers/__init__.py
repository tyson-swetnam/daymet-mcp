# SPDX-FileCopyrightText: 2026 Tyson Lee Swetnam
# SPDX-License-Identifier: MIT
"""``call_ok`` / ``call_err``: run a tool in-process and validate against its outputSchema."""

from __future__ import annotations

import json
from typing import Any

import jsonschema

from daymet_mcp.registry import get_tool
from daymet_mcp.server import DaymetServer


async def call_ok(
    server: DaymetServer, name: str, args: dict[str, Any] | None = None
) -> dict[str, Any]:
    outcome = await server.call(name, args or {})
    assert not outcome.is_error, json.dumps(outcome.payload)[:2000]
    schema = DaymetServer.output_schema(get_tool(name))
    jsonschema.Draft202012Validator(schema).validate(outcome.payload)
    assert outcome.payload.get("nextSteps"), "nextSteps must not be empty"
    return outcome.payload


async def call_err(
    server: DaymetServer, name: str, args: dict[str, Any] | None = None, code: str | None = None
) -> dict[str, Any]:
    outcome = await server.call(name, args or {})
    assert outcome.is_error, json.dumps(outcome.payload)[:2000]
    err = outcome.payload["error"]
    assert set(err) >= {"code", "message", "details"}
    if code is not None:
        assert err["code"] == code, err
    return err


#: One representative, fixture-backed call per tool (MCP protocol tests call every tool).
BBOX_3X3 = {"west": -106.6405, "south": 35.7940, "east": -106.6120, "north": 35.8172}
EVERY_TOOL_CALL: dict[str, dict[str, Any]] = {
    "daymet_download_area": {
        "bbox": BBOX_3X3,
        "variables": ["prcp"],
        "start_year": 2020,
        "end_year": 2020,
        "temporal": "annual",
    },
    "daymet_get_area": {
        "bbox": BBOX_3X3,
        "variables": ["prcp"],
        "start_year": 2020,
        "end_year": 2020,
        "temporal": "monthly",
    },
    "daymet_get_citation": {"accessed_on": "2026-11-15"},
    "daymet_get_point_daily": {"lat": 35.802997, "lon": -106.624036, "years": [2020], "limit": 5},
    "daymet_get_point_summary": {
        "lat": 35.802997,
        "lon": -106.624036,
        "period": "monthly",
        "start_year": 2020,
        "end_year": 2020,
        "variables": ["prcp"],
    },
    "daymet_list_variables": {},
    "daymet_locate_cell": {"lat": 35.802997, "lon": -106.624036},
    "daymet_ping": {"check_upstream": True},
}
