# SPDX-FileCopyrightText: 2026 Tyson Lee Swetnam
# SPDX-License-Identifier: MIT
"""Hermetic upstream: an ``httpx.MockTransport`` that replays recorded fixtures.

Every request is recorded in ``router.calls``; a request with no fixture is recorded in
``router.unexpected`` (the ``router`` pytest fixture fails the test on any).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit

import httpx

FIXTURES = Path(__file__).parent / "fixtures"
TEST_TOKEN = "edl-test-token-0123456789abcdef"

DEM_CENTRE = (35.802997, -106.624036)
DEM_CELL = (3985, 5672)
HAWAII = (21.3, -157.8)
OCEAN = (30.0, -130.0)
# bbox containing exactly the 3x3 cells c3984-3986 / r5671-5673 (recorded mosaic)
MOSAIC_BBOX = {"west": -106.6405, "south": 35.7940, "east": -106.6120, "north": 35.8172}


def normalise(key: str) -> str:
    method, rest = key.split(" ", 1)
    parts = urlsplit("https://" + rest)
    query = urlencode(sorted(parse_qsl(parts.query, keep_blank_values=True)))
    base = f"{method} {parts.hostname}{parts.path}"
    return f"{base}?{query}" if query else base


@dataclass
class Call:
    method: str
    url: str
    key: str
    headers: dict[str, str]


@dataclass
class Route:
    status: int
    headers: dict[str, str]
    content: bytes


class FixtureRouter:
    def __init__(self) -> None:
        self.routes: dict[str, Route] = {}
        self.calls: list[Call] = []
        self.unexpected: list[str] = []
        self.overrides: dict[str, list[Route]] = {}
        manifest = json.loads((FIXTURES / "manifest.json").read_text(encoding="utf-8"))
        for entry in manifest["fixtures"]:
            path = FIXTURES / entry["file"]
            if entry.get("origin") == "synthetic":
                route = Route(
                    entry["status"], {"content-type": entry["contentType"]}, path.read_bytes()
                )
            else:
                stored = json.loads(path.read_text(encoding="utf-8"))
                if "json" in stored:
                    body = json.dumps(stored["json"]).encode()
                    headers = {"content-type": "application/json", **stored.get("headers", {})}
                else:
                    body = str(stored.get("text", "")).encode()
                    headers = dict(stored.get("headers", {}))
                route = Route(stored["status"], headers, body)
            self.routes[normalise(entry["key"])] = route
        self.transport = httpx.MockTransport(self._handle)

    def add(
        self,
        key: str,
        status: int = 200,
        *,
        json_body: Any = None,
        text: str = "",
        headers: dict[str, str] | None = None,
        times: int = 1,
    ) -> None:
        """Queue ``times`` one-shot responses for ``key`` (used before the recorded route)."""
        body = json.dumps(json_body).encode() if json_body is not None else text.encode()
        h = {"content-type": "application/json"} if json_body is not None else {}
        h.update(headers or {})
        self.overrides.setdefault(normalise(key), []).extend([Route(status, h, body)] * times)

    def _handle(self, request: httpx.Request) -> httpx.Response:
        key = normalise(f"{request.method} {request.url.host}{request.url.raw_path.decode()}")
        self.calls.append(Call(request.method, str(request.url), key, dict(request.headers)))
        queued = self.overrides.get(key)
        if queued:
            r = queued.pop(0)
            return httpx.Response(r.status, headers=r.headers, content=r.content)
        route = self.routes.get(key)
        if route is None:
            self.unexpected.append(key)
            return httpx.Response(418, text="no fixture")
        return httpx.Response(route.status, headers=route.headers, content=route.content)

    def count(self, fragment: str) -> int:
        return sum(1 for c in self.calls if fragment in c.key)


def pixel_key(lat: float, lon: float, **extra: str) -> str:
    params = {
        "lat": f"{lat:.6f}",
        "lon": f"{lon:.6f}",
        "vars": "dayl,prcp,srad,swe,tmax,tmin,vp",
        "format": "json",
        **extra,
    }
    return normalise(f"GET daymet.ornl.gov/single-pixel/api/data?{urlencode(params)}")


def fixture_json(name_prefix: str) -> Any:
    for path in FIXTURES.rglob(f"{name_prefix}_*.json"):
        return json.loads(path.read_text(encoding="utf-8"))["json"]
    raise FileNotFoundError(name_prefix)
