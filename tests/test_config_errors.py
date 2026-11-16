# SPDX-FileCopyrightText: 2026 Tyson Lee Swetnam
# SPDX-License-Identifier: MIT
"""Configuration precedence, token rules, error mapping, secret redaction and the CLI."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest
import structlog

from daymet_mcp.__main__ import main
from daymet_mcp.config import ConfigError, load_config
from daymet_mcp.errors import TILE_NOT_FOUND, UpstreamError, map_upstream
from daymet_mcp.logging import mask, redact_secrets, register_secret, setup_logging
from tests.fixture_router import TEST_TOKEN


def test_defaults_and_env_precedence(tmp_path: Path) -> None:
    cfg = load_config(environ={})
    assert cfg.server.transport == "stdio" and cfg.server.port == 8080
    assert cfg.limits.pixel_mosaic_max_cells == 121
    assert cfg.daymet.latest_year_fallback.daily == 2025
    yaml_path = tmp_path / "c.yaml"
    yaml_path.write_text(
        "server:\n  port: 9000\n  log_level: DEBUG\nlimits:\n  pixel_mosaic_max_cells: 50\n"
    )
    env = {
        "DAYMET_MCP_SERVER__PORT": "9100",
        "DAYMET_MCP_SERVER__ALLOWED_HOSTS": "a.example, b.example",
        "DAYMET_MCP_CACHE__TTL_S__PIXEL": "60",
        "UNRELATED": "x",
    }
    cfg = load_config(yaml_path, environ=env, cli={"server": {"port": 9200}})
    assert cfg.server.port == 9200  # CLI > env > YAML
    assert cfg.server.log_level == "DEBUG"  # YAML
    assert cfg.limits.pixel_mosaic_max_cells == 50
    assert cfg.server.allowed_hosts == ["a.example", "b.example"]
    assert cfg.cache.ttl_s.pixel == 60


def test_token_only_from_env(tmp_path: Path) -> None:
    yaml_path = tmp_path / "c.yaml"
    yaml_path.write_text(f"earthdata:\n  token: {TEST_TOKEN}\n")
    with pytest.raises(ConfigError) as info:
        load_config(yaml_path, environ={})
    assert TEST_TOKEN not in str(info.value)
    assert "DAYMET_MCP_EARTHDATA__TOKEN" in str(info.value)
    cfg = load_config(environ={"DAYMET_MCP_EARTHDATA__TOKEN": TEST_TOKEN})
    assert cfg.token_value() == TEST_TOKEN
    dumped = json.dumps(cfg.model_dump_redacted())
    assert TEST_TOKEN not in dumped and '"token": "***"' in dumped


@pytest.mark.parametrize(
    ("env", "fragment"),
    [
        ({"DAYMET_MCP_LIMITS__MAX_RESULT_BYTES": "1"}, "limits.max_result_bytes"),
        ({"DAYMET_MCP_LIMITS__PIXEL_MOSAIC_MAX_CELLS": "100000"}, "pixel_mosaic_max_cells"),
        ({"DAYMET_MCP_SERVER__BOGUS": "1"}, "server.bogus"),
        ({"DAYMET_MCP_SERVER__PORT": "not-a-port"}, "server.port"),
    ],
)
def test_invalid_config_names_setting_not_value(env: dict[str, str], fragment: str) -> None:
    with pytest.raises(ConfigError) as info:
        load_config(environ=env)
    assert fragment in str(info.value)
    assert "not-a-port" not in str(info.value)


def test_bad_yaml(tmp_path: Path) -> None:
    p = tmp_path / "bad.yaml"
    p.write_text("server: [unclosed\n")
    with pytest.raises(ConfigError, match="not valid YAML"):
        load_config(p, environ={})
    p.write_text("- a list\n")
    with pytest.raises(ConfigError, match="mapping"):
        load_config(p, environ={})
    with pytest.raises(ConfigError, match="cannot read"):
        load_config(tmp_path / "missing.yaml", environ={})


@pytest.mark.parametrize(
    ("exc", "code", "reason"),
    [
        (
            UpstreamError("status", f"{TILE_NOT_FOUND} with input", status=400),
            "not_found",
            "off_grid",
        ),
        (UpstreamError("status", "denied", status=401), "auth_required", "token_rejected"),
        (UpstreamError("status", "no", status=403), "upstream_forbidden", "forbidden"),
        (UpstreamError("status", "slow down", status=429, retry_after_s=5), "rate_limited", None),
        (UpstreamError("status", "oops", status=502), "upstream_unavailable", "server_error"),
        (UpstreamError("status", "teapot", status=418), "upstream_error", None),
        (UpstreamError("transport", "ConnectError"), "upstream_unavailable", "transport"),
        (UpstreamError("timeout", "ReadTimeout"), "upstream_unavailable", "timeout"),
        (UpstreamError("drift", "changed"), "upstream_error", "drift"),
        (UpstreamError("parse", "bad json"), "upstream_error", "unparseable"),
        (UpstreamError("host", "refused"), "upstream_error", "host_not_allowed"),
    ],
)
def test_map_upstream(exc: UpstreamError, code: str, reason: str | None) -> None:
    err = map_upstream(exc)
    assert err.code == code
    if reason:
        assert err.details["reason"] == reason
    payload = err.to_payload()["error"]
    assert set(payload) >= {"code", "message", "details"}


def test_secret_redaction(capsys: pytest.CaptureFixture[str]) -> None:
    register_secret(TEST_TOKEN)
    assert mask(f"Bearer {TEST_TOKEN}") == "Bearer ***"
    assert mask({"authorization": "x", "nested": [TEST_TOKEN]}) == {
        "authorization": "***",
        "nested": ["***"],
    }
    event = redact_secrets(None, "info", {"event": "x", "token": "abc", "url": f"u?t={TEST_TOKEN}"})
    assert event["token"] == "***" and TEST_TOKEN not in event["url"]
    setup_logging("info", "http")
    structlog.get_logger("t").info("leak.check", value=TEST_TOKEN, authorization="Bearer zz")
    logging.getLogger("stdlib").warning("stdlib %s", TEST_TOKEN)
    err = capsys.readouterr().err
    assert TEST_TOKEN not in err and "leak.check" in err
    setup_logging("info", "stdio")


@pytest.mark.parametrize("transport", ["http", "stdio"])
def test_secret_redaction_in_tracebacks(capsys: pytest.CaptureFixture[str], transport: str) -> None:
    # Regression (protocol-security review): redaction ran before format_exc_info, so a
    # registered secret inside an exception message or traceback reached the log.
    register_secret(TEST_TOKEN)
    setup_logging("info", transport)
    try:
        raise RuntimeError(f"upstream said: Bearer {TEST_TOKEN}")
    except RuntimeError:
        structlog.get_logger("t").exception("tool.crash", note=TEST_TOKEN)
        logging.getLogger("uvicorn.error").exception("stdlib crash")
    err = capsys.readouterr().err
    assert "tool.crash" in err and "RuntimeError" in err and "stdlib crash" in err
    assert err.count("Traceback") == 2
    assert TEST_TOKEN not in err
    setup_logging("info", "stdio")


def test_cli_print_config_and_version(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DAYMET_MCP_EARTHDATA__TOKEN", TEST_TOKEN)
    main(["--print-config", "--port", "8181", "--transport", "http", "--downloads-dir", "/tmp/x"])
    out = capsys.readouterr().out
    data = json.loads(out)
    assert data["server"]["port"] == 8181 and data["earthdata"]["token"] == "***"
    assert TEST_TOKEN not in out
    with pytest.raises(SystemExit) as info:
        main(["--version"])
    assert info.value.code == 0
    assert "daymet-mcp 0.1.0" in capsys.readouterr().out


def test_cli_config_error_exits_2(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DAYMET_MCP_SERVER__PORT", "0")
    with pytest.raises(SystemExit) as info:
        main(["--print-config"])
    assert info.value.code == 2
    assert "server.port" in capsys.readouterr().err


def test_cli_offline_check(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as info:
        main(["--check", "--log-level", "WARNING"])
    assert info.value.code == 0
    report = json.loads(capsys.readouterr().out)
    assert report["ok"] and len(report["tools"]) == 8


def test_example_files_are_valid() -> None:
    root = Path(__file__).resolve().parent.parent
    cfg = load_config(root / "config.yaml.example", environ={})
    assert cfg.limits.pixel_mosaic_max_cells == 121
    env_example = (root / ".env.example").read_text(encoding="utf-8")
    for line in env_example.splitlines():
        assert not line.strip() or line.startswith("#"), "no live values in .env.example"
