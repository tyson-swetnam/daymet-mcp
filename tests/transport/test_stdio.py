# SPDX-FileCopyrightText: 2026 Tyson Lee Swetnam
# SPDX-License-Identifier: MIT
"""A real stdio server subprocess, driven by the MCP SDK client (every tool) and by raw
JSON-RPC lines (stdout must carry protocol framing only)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from pathlib import Path

from mcp import Client, StdioServerParameters

from tests.helpers import EVERY_TOOL_CALL

ROOT = Path(__file__).resolve().parents[2]


def _env() -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith("DAYMET_MCP_")}
    env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    return env


async def test_every_tool_over_stdio(tmp_path: Path) -> None:
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "tests.helpers.fixture_stdio", str(tmp_path / "downloads")],
        env=_env(),
        cwd=str(ROOT),
    )
    async with Client(params) as client:
        assert client.protocol_version == "2026-07-28"
        names = [t.name for t in (await client.list_tools()).tools]
        assert names == sorted(EVERY_TOOL_CALL)
        for name, args in EVERY_TOOL_CALL.items():
            result = await client.call_tool(name, args)
            assert not result.is_error, (name, result.structured_content)
            assert isinstance(result.structured_content, dict)
    manifest = list((tmp_path / "downloads").rglob("manifest.json"))
    assert len(manifest) == 1


def test_stdout_is_protocol_only(tmp_path: Path) -> None:
    lines = [
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "raw", "version": "0"},
            },
        },
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "daymet_locate_cell",
                "arguments": {"lat": 35.802997, "lon": -106.624036},
            },
        },
    ]
    proc = subprocess.Popen(
        [sys.executable, "-m", "tests.helpers.fixture_stdio", str(tmp_path / "d")],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=_env(),
        cwd=str(ROOT),
    )
    watchdog = threading.Timer(60, proc.kill)
    watchdog.start()
    assert proc.stdin is not None and proc.stdout is not None and proc.stderr is not None
    raw: list[str] = []
    try:
        for message in lines:
            proc.stdin.write(json.dumps(message) + "\n")
            proc.stdin.flush()
            if "id" in message:  # wait for each response before sending the next request
                raw.append(proc.stdout.readline())
        proc.stdin.close()
        raw.extend(proc.stdout.readlines())
        stderr = proc.stderr.read()
        proc.wait(timeout=30)
    finally:
        watchdog.cancel()
        if proc.poll() is None:
            proc.kill()
    out = [json.loads(line) for line in raw if line.strip()]
    assert all(m.get("jsonrpc") == "2.0" for m in out)
    by_id = {m.get("id"): m for m in out}
    assert by_id[1]["result"]["serverInfo"]["name"] == "daymet-mcp"
    assert len(by_id[2]["result"]["tools"]) == 8
    assert by_id[3]["result"]["structuredContent"]["cell"]["col"] == 3985
    assert "tool.call" in stderr  # logs go to stderr


def test_console_script_check_offline() -> None:
    exe = Path(sys.executable).with_name("daymet-mcp")
    cmd = [str(exe)] if exe.exists() else [sys.executable, "-m", "daymet_mcp"]
    proc = subprocess.run(
        [*cmd, "--check"], capture_output=True, text=True, env=_env(), timeout=60, check=False
    )
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout)["ok"] is True
