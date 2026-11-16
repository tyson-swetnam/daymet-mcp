# SPDX-FileCopyrightText: 2026 Tyson Lee Swetnam
# SPDX-License-Identifier: MIT
"""Configuration (DESIGN.md §12).

Precedence: CLI flag > environment > YAML (``--config``) > defaults. Environment variables
are ``DAYMET_MCP_<SECTION>__<FIELD>`` (``__`` descends one level; list fields are
comma-separated). ``.env`` files are never loaded automatically.

The Earthdata token is accepted **only** from ``DAYMET_MCP_EARTHDATA__TOKEN`` (DESIGN.md D15).
A ``token`` key in YAML is a :class:`ConfigError`. Errors name the setting, never its value.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, SecretStr, ValidationError, field_validator

ENV_PREFIX = "DAYMET_MCP_"
TOKEN_ENV = "DAYMET_MCP_EARTHDATA__TOKEN"
MIB = 1024 * 1024


class ConfigError(Exception):
    """A configuration problem; the message names settings, never values."""


class _Section(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class ServerConfig(_Section):
    transport: Literal["stdio", "http"] = Field("stdio", description="stdio or http.")
    host: str = Field("127.0.0.1", description="HTTP bind address.")
    port: int = Field(8080, ge=1, le=65535, description="HTTP port.")
    public_base_url: str | None = Field(None, description="Public URL when behind a proxy.")
    allowed_hosts: list[str] = Field(
        default_factory=list, description="Extra Host values accepted (DNS-rebinding guard)."
    )
    allowed_origins: list[str] = Field(
        default_factory=list, description="Extra Origin values accepted."
    )
    dns_rebinding_protection: bool = Field(True, description="Validate Host/Origin headers.")
    json_response: bool = Field(True, description="Plain JSON responses instead of SSE.")
    log_level: str = Field("INFO", description="DEBUG, INFO, WARNING or ERROR.")
    instructions_extra: str | None = Field(
        None, description="Text appended to the server instructions."
    )


class LatestYearFallback(_Section):
    daily: int = Field(2025, ge=1980, description="Latest daily year if CMR cannot be reached.")


class DaymetConfig(_Section):
    single_pixel_url: str = Field(
        "https://daymet.ornl.gov/single-pixel/api/data", description="Single-pixel API endpoint."
    )
    cmr_url: str = Field("https://cmr.earthdata.nasa.gov/search", description="CMR search root.")
    latest_year_fallback: LatestYearFallback = Field(default_factory=LatestYearFallback)
    first_year: int = Field(1980, ge=1980, description="First year served (D8).")


class EarthdataConfig(_Section):
    token: SecretStr | None = Field(
        None, description=f"EDL user token; environment only ({TOKEN_ENV})."
    )
    opendap_url: str = Field(
        "https://opendap.earthdata.nasa.gov/collections", description="Hyrax OPeNDAP root."
    )
    allow_in_http_mode: bool = Field(
        False, description="Let anonymous HTTP callers use the operator's token (D17)."
    )


class CacheTTL(_Section):
    pixel: int = Field(604_800, ge=0, description="Single-pixel cell-year TTL (s).")
    cmr: int = Field(86_400, ge=0, description="CMR latest-year TTL (s).")


class CacheConfig(_Section):
    max_cell_years: int = Field(20_000, ge=1, description="In-memory cell-year entries.")
    ttl_s: CacheTTL = Field(default_factory=CacheTTL)
    stale_if_error_s: int = Field(86_400, ge=0, description="Serve stale entries on errors (s).")
    disk_dir: str | None = Field(None, description="Optional gzip-JSON disk cache directory.")


class LimitsConfig(_Section):
    max_result_bytes: int = Field(50_000, description="Result budget (fixed).")
    hard_max_result_bytes: int = Field(200_000, description="Hard result cap (fixed).")
    max_years_per_point: int = Field(46, ge=1, le=46, description="Years per point call.")
    pixel_mosaic_max_cells: int = Field(121, ge=1, le=400, description="Cells via single-pixel.")
    pixel_mosaic_max_cell_years: int = Field(
        605, ge=1, le=2000, description="Cell-years via single-pixel per call."
    )
    earthdata_max_values: int = Field(
        25_000_000, ge=1, le=200_000_000, description="cells x days x variables (Earthdata)."
    )
    tool_timeout_s: float = Field(120.0, gt=0, le=600, description="Per-tool wall clock (s).")

    @field_validator("max_result_bytes", "hard_max_result_bytes")
    @classmethod
    def _fixed(cls, value: int, info: Any) -> int:
        fixed = {"max_result_bytes": 50_000, "hard_max_result_bytes": 200_000}[info.field_name]
        if value != fixed:
            raise ValueError("this limit is fixed by convention and cannot be changed")
        return value


class DownloadsConfig(_Section):
    dir: str = Field("./daymet-downloads", description="Download root (stdio only).")
    max_bytes: int = Field(500 * MIB, ge=1, le=5 * 1024 * MIB, description="Bytes per call.")

    def resolved_dir(self) -> Path:
        return Path(self.dir).expanduser().resolve()


class Config(_Section):
    server: ServerConfig = Field(default_factory=ServerConfig)
    daymet: DaymetConfig = Field(default_factory=DaymetConfig)
    earthdata: EarthdataConfig = Field(default_factory=EarthdataConfig)
    cache: CacheConfig = Field(default_factory=CacheConfig)
    limits: LimitsConfig = Field(default_factory=LimitsConfig)
    downloads: DownloadsConfig = Field(default_factory=DownloadsConfig)

    def token_value(self) -> str | None:
        tok = self.earthdata.token
        return tok.get_secret_value() if tok is not None and tok.get_secret_value() else None

    def model_dump_redacted(self) -> dict[str, Any]:
        data = self.model_dump(mode="json")
        data["earthdata"]["token"] = "***" if self.token_value() else None
        return data


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------


def _deep_merge(base: dict[str, Any], extra: Mapping[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for key, value in extra.items():
        if isinstance(value, Mapping) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def _list_fields() -> set[tuple[str, str]]:
    found: set[tuple[str, str]] = set()
    for section, info in Config.model_fields.items():
        model = info.annotation
        if isinstance(model, type) and issubclass(model, BaseModel):
            for name, finfo in model.model_fields.items():
                if "list[" in str(finfo.annotation):
                    found.add((section, name))
    return found


def env_overrides(environ: Mapping[str, str]) -> dict[str, Any]:
    """Nested dict from ``DAYMET_MCP_<SECTION>__<FIELD>[__<SUB>]`` variables."""
    lists = _list_fields()
    out: dict[str, Any] = {}
    for key, raw in environ.items():
        if not key.startswith(ENV_PREFIX):
            continue
        parts = [p.lower() for p in key[len(ENV_PREFIX) :].split("__") if p]
        if len(parts) < 2:
            continue
        value: Any = raw
        if len(parts) == 2 and (parts[0], parts[1]) in lists:
            value = [v.strip() for v in raw.split(",") if v.strip()]
        node = out
        for part in parts[:-1]:
            node = node.setdefault(part, {})
            if not isinstance(node, dict):
                raise ConfigError(f"environment variable {key} conflicts with another setting")
        node[parts[-1]] = value
    return out


def _format_validation(exc: ValidationError) -> str:
    lines = []
    for err in exc.errors(include_url=False, include_input=False):
        loc = ".".join(str(p) for p in err.get("loc", ()))
        lines.append(f"{loc}: {err.get('msg')}")
    return "invalid configuration: " + "; ".join(lines)


def load_config(
    path: str | Path | None = None,
    *,
    environ: Mapping[str, str] | None = None,
    cli: Mapping[str, Any] | None = None,
) -> Config:
    """Build the effective configuration (defaults < YAML < env < CLI)."""
    data: dict[str, Any] = {}
    if path is not None:
        try:
            loaded = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
        except OSError as exc:
            raise ConfigError(f"cannot read config file: {exc.strerror}") from None
        except yaml.YAMLError:
            raise ConfigError("config file is not valid YAML") from None
        if not isinstance(loaded, dict):
            raise ConfigError("config file must contain a mapping")
        if isinstance(loaded.get("earthdata"), dict) and "token" in loaded["earthdata"]:
            raise ConfigError(
                f"earthdata.token must not be set in YAML; use the environment variable {TOKEN_ENV}"
            )
        data = loaded
    env = env_overrides(os.environ if environ is None else environ)
    data = _deep_merge(data, env)
    if cli:
        data = _deep_merge(data, cli)
    try:
        return Config.model_validate(data)
    except ValidationError as exc:
        raise ConfigError(_format_validation(exc)) from None
