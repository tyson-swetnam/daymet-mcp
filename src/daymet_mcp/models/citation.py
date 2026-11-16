# SPDX-FileCopyrightText: 2026 Tyson Lee Swetnam
# SPDX-License-Identifier: MIT
"""Models for ``daymet_get_citation``."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import Field

from daymet_mcp.models.common import DaymetInput, DaymetOutput, ToolResultBase, VariablesField

Product = Literal["daily", "monthly", "annual"]
Access = Literal["single_pixel", "earthdata"]


def _default_products() -> list[Product]:
    return ["daily"]


def _default_access() -> list[Access]:
    return ["single_pixel"]


class CitationInput(DaymetInput):
    products: list[Product] = Field(
        default_factory=_default_products,
        json_schema_extra={"uniqueItems": True},
        description=(
            "Products the values came from. Server-computed monthly/annual values come from "
            "the daily product, so cite 'daily' for them."
        ),
    )
    access: list[Access] = Field(
        default_factory=_default_access,
        json_schema_extra={"uniqueItems": True},
        description="How the data were retrieved (adds the single-pixel tool citation).",
    )
    variables: VariablesField = None
    include_method_papers: bool = Field(True, description="Add the recommended method papers.")
    accessed_on: date | None = Field(None, description="Access date. Default: today (UTC).")


class CitationOut(DaymetOutput):
    role: Literal["dataset", "tool", "method"]
    requirement: Literal["required", "recommended"]
    text: str
    doi: str
    doi_url: str
    bibtex: str


class CitationOutput(ToolResultBase):
    citations: list[CitationOut]
    accessed_on: str
    data_policy_url: str
