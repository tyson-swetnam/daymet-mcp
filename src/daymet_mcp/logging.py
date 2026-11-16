# SPDX-FileCopyrightText: 2026 Tyson Lee Swetnam
# SPDX-License-Identifier: MIT
"""Logging (structlog). Adapted from idss-mesa/neon-mcp ``logging.py`` (MIT).

stdio keeps stdout for MCP framing, so every log line goes to stderr: a console renderer
for stdio, JSON for HTTP. :func:`redact_secrets` masks credential-looking keys and every
registered secret value (the Earthdata token is registered at start-up).
"""

from __future__ import annotations

import logging
import re
import sys
from collections.abc import MutableMapping
from typing import Any

import structlog

_LEVEL_MAP: dict[str, int] = {
    "debug": logging.DEBUG,
    "info": logging.INFO,
    "warning": logging.WARNING,
    "error": logging.ERROR,
    "critical": logging.CRITICAL,
}

_SECRET_KEY_RE = re.compile(r"(?i)token|authorization|secret|password|cookie")
_SECRETS: set[str] = set()


def register_secret(value: str | None) -> None:
    """Remember a secret so log processors and error redaction mask it."""
    if value and len(value) >= 4:
        _SECRETS.add(value)


def registered_secrets() -> frozenset[str]:
    return frozenset(_SECRETS)


def forget_secrets() -> None:
    """Test helper."""
    _SECRETS.clear()


def mask(value: Any) -> Any:
    """Replace registered secrets inside strings, dicts and lists."""
    if isinstance(value, str):
        for secret in _SECRETS:
            if secret in value:
                value = value.replace(secret, "***")
        return value
    if isinstance(value, dict):
        return {k: ("***" if _is_secret_key(k, v) else mask(v)) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [mask(v) for v in value]
    return value


def _is_secret_key(key: Any, value: Any) -> bool:
    return isinstance(key, str) and isinstance(value, str) and bool(_SECRET_KEY_RE.search(key))


def redact_secrets(
    logger: Any, method_name: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    """structlog processor: mask credential-looking keys and registered secrets."""
    del logger, method_name
    for key in list(event_dict):
        value = event_dict[key]
        event_dict[key] = "***" if _is_secret_key(key, value) else mask(value)
    return event_dict


class _StdlibSecretFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if _SECRETS:
            record.msg = mask(str(record.msg))
            if isinstance(record.args, tuple):
                record.args = tuple(mask(a) for a in record.args)
        return True


class _Stderr:
    """File-like proxy resolving ``sys.stderr`` at write time."""

    def write(self, text: str) -> int:
        return sys.stderr.write(text)

    def flush(self) -> None:
        sys.stderr.flush()


def setup_logging(level: str = "info", transport: str = "stdio") -> None:
    log_level = _LEVEL_MAP.get(level.lower(), logging.INFO)
    logging.basicConfig(level=log_level, format="%(message)s", stream=_Stderr(), force=True)
    for handler in logging.getLogger().handlers:
        handler.addFilter(_StdlibSecretFilter())
    # httpx/httpcore print full URLs at INFO.
    for noisy in ("httpx", "httpcore", "httpx2", "httpcore2"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    renderer: Any = (
        structlog.dev.ConsoleRenderer(colors=False)
        if transport == "stdio"
        else structlog.processors.JSONRenderer()
    )
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            redact_secrets,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        logger_factory=structlog.PrintLoggerFactory(file=_Stderr()),  # type: ignore[arg-type]
        cache_logger_on_first_use=False,
    )
