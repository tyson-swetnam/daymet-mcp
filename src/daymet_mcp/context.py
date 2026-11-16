# SPDX-FileCopyrightText: 2026 Tyson Lee Swetnam
# SPDX-License-Identifier: MIT
"""Per-call context handed to every tool handler."""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from daymet_mcp.config import Config
    from daymet_mcp.daymet.cmr import CmrService
    from daymet_mcp.daymet.earthdata import EarthdataService
    from daymet_mcp.daymet.single_pixel import SinglePixelService

TransportName = Literal["stdio", "http"]

current_request_id: ContextVar[str | None] = ContextVar("daymet_mcp_request_id", default=None)


@dataclass
class UpstreamStats:
    """What one call cost upstream (result ``_meta`` ``io.daymet-mcp/upstream``)."""

    requests: int = 0
    cache_hits: int = 0
    backend: str | None = None
    endpoints: list[str] = field(default_factory=list)

    def record_endpoint(self, endpoint: str) -> None:
        if endpoint not in self.endpoints:
            self.endpoints.append(endpoint)

    def as_meta(self) -> dict[str, Any]:
        return {
            "requests": self.requests,
            "cacheHits": self.cache_hits,
            "rateLimitRemaining": None,
            "rateLimitLimit": None,
            "backend": self.backend,
        }


@dataclass(frozen=True)
class Services:
    pixel: SinglePixelService
    cmr: CmrService
    earthdata: EarthdataService


@dataclass(frozen=True)
class ToolContext:
    config: Config
    services: Services
    transport: TransportName
    tool_name: str
    stats: UpstreamStats
    request_id: str | None = None

    @property
    def earthdata_usable(self) -> bool:
        has_token = self.config.token_value() is not None
        if self.transport == "http" and not self.config.earthdata.allow_in_http_mode:
            return False
        return has_token
