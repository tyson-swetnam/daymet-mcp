# SPDX-FileCopyrightText: 2026 Tyson Lee Swetnam
# SPDX-License-Identifier: MIT
"""The tool registry: declaration, validation, invocation and the size budget.

Adapted from idss-mesa/neon-mcp ``registry.py`` (MIT); MRTR/elicitation removed (D18) and
the budget trims the time axis from the tail (DESIGN.md §4.0).
"""

from __future__ import annotations

import json
import re
from collections.abc import Awaitable, Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

import anyio
from pydantic import ValidationError

from daymet_mcp.errors import ToolError, UpstreamError, map_upstream
from daymet_mcp.logging import mask
from daymet_mcp.models.common import DaymetInput, ToolResultBase

if TYPE_CHECKING:
    from daymet_mcp.context import ToolContext, UpstreamStats

Surface = Literal["core", "catalog", "cell", "point", "area", "citation"]
SURFACES: tuple[str, ...] = ("core", "catalog", "cell", "point", "area", "citation")
ToolHandler = Callable[[Any, "ToolContext"], Awaitable[ToolResultBase]]

NAME_RE = re.compile(r"^daymet_[a-z_]+$")
NEXT_SENTENCE_RE = re.compile(r"(?:^|[.!?)]\s+)Next: [^\n]+$")
MAX_DESCRIPTION_CHARS = 600


@dataclass(frozen=True)
class ToolSpec:
    name: str
    title: str
    description: str
    handler: ToolHandler
    input_model: type[DaymetInput]
    output_model: type[ToolResultBase]
    surface: Surface
    endpoints: tuple[str, ...]
    transports: frozenset[str]
    requires_token: bool | Literal["optional"]
    read_only: bool
    destructive: bool
    idempotent: bool
    open_world: bool


_REGISTRY: dict[str, ToolSpec] = {}


def register_tool(
    name: str,
    *,
    title: str,
    description: str,
    input_model: type[DaymetInput],
    output_model: type[ToolResultBase],
    surface: Surface,
    endpoints: Sequence[str],
    transports: Iterable[str] = ("stdio", "http"),
    requires_token: bool | Literal["optional"] = False,
    read_only: bool = True,
    destructive: bool = False,
    idempotent: bool = True,
    open_world: bool = True,
) -> Callable[[ToolHandler], ToolHandler]:
    """Decorator adding a tool to the registry; validates the declaration."""
    if not NAME_RE.match(name):
        raise ValueError(f"tool name {name!r} must match {NAME_RE.pattern}")
    description = " ".join(description.split())
    if len(description) > MAX_DESCRIPTION_CHARS:
        raise ValueError(f"{name}: description is {len(description)} chars (max 600)")
    if not NEXT_SENTENCE_RE.search(description):
        raise ValueError(f"{name}: description must end with a sentence starting 'Next:'")
    if not (isinstance(input_model, type) and issubclass(input_model, DaymetInput)):
        raise TypeError(f"{name}: input_model must subclass DaymetInput")
    if not (isinstance(output_model, type) and issubclass(output_model, ToolResultBase)):
        raise TypeError(f"{name}: output_model must subclass ToolResultBase")
    if surface not in SURFACES:
        raise ValueError(f"{name}: unknown surface {surface!r}")

    def decorator(handler: ToolHandler) -> ToolHandler:
        if name in _REGISTRY:
            raise ValueError(f"Tool {name!r} already registered")
        _REGISTRY[name] = ToolSpec(
            name=name,
            title=title,
            description=description,
            handler=handler,
            input_model=input_model,
            output_model=output_model,
            surface=surface,
            endpoints=tuple(endpoints),
            transports=frozenset(transports),
            requires_token=requires_token,
            read_only=read_only,
            destructive=destructive,
            idempotent=idempotent,
            open_world=open_world,
        )
        return handler

    return decorator


def get_registered_tools(*, transport: str | None = None) -> list[ToolSpec]:
    specs = sorted(_REGISTRY.values(), key=lambda s: s.name)
    if transport is not None:
        specs = [s for s in specs if transport in s.transports]
    return specs


def get_tool(name: str) -> ToolSpec:
    return _REGISTRY[name]


def unregister_tool(name: str) -> None:
    _REGISTRY.pop(name, None)


# ---------------------------------------------------------------------------
# Invocation
# ---------------------------------------------------------------------------


def format_validation_error(exc: ValidationError, spec: ToolSpec) -> ToolError:
    errors = exc.errors(include_url=False, include_input=False)
    first = errors[0] if errors else {"loc": (), "msg": str(exc), "type": "value_error"}
    loc = ".".join(str(p) for p in first.get("loc", ())) or "arguments"
    valid = sorted(spec.input_model.model_fields)
    if first.get("type") == "extra_forbidden":
        message = f"Unknown argument {loc!r} for {spec.name}. Valid arguments: {', '.join(valid)}."
    else:
        message = f"Invalid argument {loc!r} for {spec.name}: {first.get('msg')}"
    return ToolError(
        "invalid_argument",
        message,
        details={
            "tool": spec.name,
            "validArguments": valid,
            "errors": [
                {
                    "loc": [str(p) for p in e.get("loc", ())],
                    "msg": e.get("msg"),
                    "type": e.get("type"),
                }
                for e in errors[:10]
            ],
        },
    )


def default_source(stats: UpstreamStats) -> dict[str, Any]:
    endpoints = list(stats.endpoints)
    if not endpoints:
        via = "local"
    elif all("cmr." in e for e in endpoints):
        via = "cmr"
    elif any("opendap." in e for e in endpoints):
        via = "earthdata-opendap"
    else:
        via = "single-pixel"
    return {
        "endpoints": endpoints,
        "via": via,
        "cached": stats.requests == 0 and stats.cache_hits > 0,
        "derived": [],
    }


async def invoke(
    spec: ToolSpec, raw_args: Mapping[str, Any] | None, ctx: ToolContext
) -> dict[str, Any]:
    """Validate, run (under the per-tool timeout) and shape one call."""
    if spec.name not in {s.name for s in get_registered_tools(transport=ctx.transport)}:
        raise ToolError(
            "not_available_in_http_mode",
            f"{spec.name} writes files and is offered only over stdio.",
            details={"tool": spec.name, "transport": ctx.transport},
            hint="Use daymet_get_area over HTTP, or run the server locally over stdio.",
        )
    try:
        args = spec.input_model.model_validate(dict(raw_args or {}))
    except ValidationError as exc:
        raise format_validation_error(exc, spec) from None
    timeout = ctx.config.limits.tool_timeout_s
    try:
        with anyio.fail_after(timeout):
            result = await spec.handler(args, ctx)
    except UpstreamError as exc:
        err = map_upstream(exc)
        err.details = mask(err.details)
        err.message = mask(err.message)
        raise err from None
    except TimeoutError:
        raise ToolError(
            "upstream_unavailable",
            f"The call did not finish within {timeout:g} s.",
            details={"reason": "timeout", "limitS": timeout},
            hint="Request fewer cells or years.",
        ) from None
    if not isinstance(result, spec.output_model):
        raise ToolError("internal_error", f"{spec.name} returned {type(result).__name__}.")
    payload = result.model_dump(by_alias=True, exclude_none=True, mode="json")
    if "source" not in payload:
        payload["source"] = default_source(ctx.stats)
    limits = ctx.config.limits
    payload = fit_to_budget(payload, spec.output_model, limits.max_result_bytes)
    size = json_size(payload)
    if size > limits.hard_max_result_bytes:
        raise ToolError(
            "result_too_large",
            f"The result is {size} bytes, above the {limits.hard_max_result_bytes}-byte hard limit.",
            details={"bytes": size, "limit": limits.hard_max_result_bytes},
            hint="Request fewer variables, a smaller limit or a coarser period.",
        )
    return payload


def json_size(obj: Any) -> int:
    return len(json.dumps(obj, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))


def fit_to_budget(
    payload: dict[str, Any], output_model: type[ToolResultBase], max_bytes: int
) -> dict[str, Any]:
    """Trim the time axis from the tail until the compact JSON fits ``max_bytes``."""
    if json_size(payload) <= max_bytes or not output_model.budget_time_axis:
        return payload
    total = output_model.time_length(payload)
    lo, hi = 0, total
    best = 0
    while lo <= hi:
        mid = (lo + hi) // 2
        trial = json.loads(json.dumps(payload))
        output_model.trim_time(trial, mid)
        _mark_trimmed(trial, mid)
        if json_size(trial) <= max_bytes:
            best = mid
            lo = mid + 1
        else:
            hi = mid - 1
    output_model.trim_time(payload, best)
    _mark_trimmed(payload, best)
    return payload


def _mark_trimmed(payload: dict[str, Any], kept: int) -> None:
    page = payload.get("page")
    next_offset = kept
    if isinstance(page, dict):
        next_offset = int(page.get("offset", 0)) + kept
        page.update(returned=kept, truncated=True, nextOffset=next_offset, truncatedReason="budget")
    steps = payload.setdefault("nextSteps", [])
    note = (
        f"Result trimmed to fit the 50000-byte budget; call again with offset={next_offset}, "
        "fewer variables, or a coarser period."
    )
    if note not in steps:
        steps.insert(0, note)
