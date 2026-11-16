# SPDX-FileCopyrightText: 2026 Tyson Lee Swetnam
# SPDX-License-Identifier: MIT
"""Error vocabulary (DESIGN.md §5).

Tool failures are tool results (``isError=true``) whose ``structuredContent`` is
``{"error": {code, message, details, hint?}}``. Only protocol faults become JSON-RPC
errors. Messages and details never carry request headers or credential values.
"""

from __future__ import annotations

from typing import Any, Literal, get_args

ErrorCode = Literal[
    "invalid_argument",
    "not_found",
    "auth_required",
    "upstream_forbidden",
    "rate_limited",
    "upstream_error",
    "upstream_unavailable",
    "feature_unavailable",
    "not_available_in_http_mode",
    "query_too_large",
    "result_too_large",
    "download_limit_exceeded",
    "unknown_tool",
    "internal_error",
]
ERROR_CODES: tuple[str, ...] = get_args(ErrorCode)


class ToolError(Exception):
    """A failure reported to the caller as an ``isError`` tool result."""

    def __init__(
        self,
        code: ErrorCode,
        message: str,
        *,
        details: dict[str, Any] | None = None,
        hint: str | None = None,
    ) -> None:
        super().__init__(message)
        self.code: ErrorCode = code
        self.message = message
        self.details: dict[str, Any] = dict(details or {})
        self.hint = hint

    def to_payload(self) -> dict[str, Any]:
        err: dict[str, Any] = {"code": self.code, "message": self.message, "details": self.details}
        if self.hint:
            err["hint"] = self.hint
        return {"error": err}


class UpstreamError(Exception):
    """Raised by the upstream client; mapped to a :class:`ToolError` by :func:`map_upstream`."""

    def __init__(
        self,
        kind: Literal["status", "transport", "timeout", "drift", "parse", "host"],
        message: str,
        *,
        status: int | None = None,
        host: str | None = None,
        retry_after_s: float | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.kind = kind
        self.message = message
        self.status = status
        self.host = host
        self.retry_after_s = retry_after_s
        self.details: dict[str, Any] = dict(details or {})


TILE_NOT_FOUND = "Daymet Tile was not found"


def map_upstream(exc: UpstreamError) -> ToolError:
    """Map an upstream failure onto the error vocabulary (DESIGN.md §5 table)."""
    details: dict[str, Any] = {"host": exc.host, **exc.details}
    if exc.status is not None:
        details["status"] = exc.status
    if exc.kind == "drift":
        return ToolError(
            "upstream_error",
            f"Daymet returned something other than what was requested: {exc.message}",
            details={**details, "reason": "drift"},
            hint="This guards against silent upstream changes; report it if it persists.",
        )
    if exc.kind == "parse":
        return ToolError(
            "upstream_error",
            f"Could not parse the upstream response: {exc.message}",
            details={**details, "reason": "unparseable"},
        )
    if exc.kind == "host":
        return ToolError(
            "upstream_error",
            exc.message,
            details={**details, "reason": "host_not_allowed"},
        )
    if exc.kind in ("transport", "timeout"):
        return ToolError(
            "upstream_unavailable",
            f"Daymet/Earthdata could not be reached: {exc.message}",
            details={**details, "reason": exc.kind},
            hint="Retry later; the upstream service may be down.",
        )
    status = exc.status or 0
    if status == 400 and TILE_NOT_FOUND in exc.message:
        return ToolError(
            "not_found",
            "No Daymet cell exists at this location (outside the land grid, e.g. over the ocean).",
            details={**details, "reason": "off_grid"},
            hint="Move the point onto land inside the Daymet regions (see daymet_list_variables).",
        )
    if status == 401:
        return ToolError(
            "auth_required",
            "NASA Earthdata rejected the configured token.",
            details={**details, "reason": "token_rejected"},
            hint="Check DAYMET_MCP_EARTHDATA__TOKEN (read daymet://guide/earthdata-credentials).",
        )
    if status == 403:
        return ToolError(
            "upstream_forbidden",
            "NASA Earthdata refused access (the account may not have authorised the ORNL DAAC application).",
            details={**details, "reason": "forbidden"},
        )
    if status == 429:
        return ToolError(
            "rate_limited",
            "The upstream service is rate limiting requests.",
            details={**details, "retryAfterS": exc.retry_after_s},
            hint="Wait and retry, or request fewer cells/years.",
        )
    if status >= 500:
        return ToolError(
            "upstream_unavailable",
            f"The upstream service returned HTTP {status}.",
            details={**details, "reason": "server_error"},
        )
    return ToolError(
        "upstream_error",
        f"The upstream service returned HTTP {status}: {exc.message[:200]}",
        details=details,
    )
