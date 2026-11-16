# SPDX-FileCopyrightText: 2026 Tyson Lee Swetnam
# SPDX-License-Identifier: MIT
"""TTL + LRU cache with single-flight and stale-if-error (DESIGN.md §9).

An optional disk layer keeps gzip JSON per key (atomic writes); a disk error never fails
a call. The cache never changes values: aggregates are recomputed from cached daily data.
"""

from __future__ import annotations

import contextlib
import gzip
import hashlib
import json
import os
import tempfile
import time
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import anyio


@dataclass
class _Entry:
    value: Any
    stored_at: float


class TTLCache:
    def __init__(
        self,
        *,
        max_entries: int,
        ttl_s: float,
        stale_if_error_s: float,
        disk_dir: str | None = None,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self.max_entries = max_entries
        self.ttl_s = ttl_s
        self.stale_if_error_s = stale_if_error_s
        self.disk_dir = Path(disk_dir).expanduser() if disk_dir else None
        self._clock = clock or time.time
        self._data: OrderedDict[str, _Entry] = OrderedDict()
        self._inflight: dict[str, anyio.Event] = {}
        self._lock = anyio.Lock()

    # -- raw access ---------------------------------------------------------

    def _fresh(self, entry: _Entry) -> bool:
        return self._clock() - entry.stored_at <= self.ttl_s

    def peek(self, key: str) -> Any | None:
        """A fresh value from memory or disk, else ``None`` (no single-flight)."""
        entry = self._data.get(key)
        if entry is not None and self._fresh(entry):
            self._data.move_to_end(key)
            return entry.value
        disk = self._disk_read(key)
        if disk is not None and self._fresh(disk):
            self._put(key, disk)
            return disk.value
        return None

    def put(self, key: str, value: Any) -> None:
        entry = _Entry(value, self._clock())
        self._put(key, entry)
        self._disk_write(key, entry)

    def _put(self, key: str, entry: _Entry) -> None:
        self._data[key] = entry
        self._data.move_to_end(key)
        while len(self._data) > self.max_entries:
            self._data.popitem(last=False)

    def stale(self, key: str) -> Any | None:
        entry = self._data.get(key) or self._disk_read(key)
        if (
            entry is not None
            and self._clock() - entry.stored_at <= self.ttl_s + self.stale_if_error_s
        ):
            return entry.value
        return None

    def __len__(self) -> int:
        return len(self._data)

    # -- single flight ------------------------------------------------------

    async def get_or_fetch(self, key: str, fetch: Callable[[], Awaitable[Any]]) -> tuple[Any, bool]:
        """Return ``(value, from_cache)``; concurrent misses for one key share one fetch."""
        while True:
            hit = self.peek(key)
            if hit is not None:
                return hit, True
            async with self._lock:
                event = self._inflight.get(key)
                if event is None:
                    event = anyio.Event()
                    self._inflight[key] = event
                    leader = True
                else:
                    leader = False
            if not leader:
                await event.wait()
                continue
            try:
                try:
                    value = await fetch()
                except Exception:
                    old = self.stale(key)
                    if old is not None:
                        return old, True
                    raise
                self.put(key, value)
                return value, False
            finally:
                async with self._lock:
                    self._inflight.pop(key, None)
                event.set()

    # -- disk layer ---------------------------------------------------------

    def _path(self, key: str) -> Path | None:
        if self.disk_dir is None:
            return None
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
        return self.disk_dir / digest[:2] / f"{digest}.json.gz"

    def _disk_read(self, key: str) -> _Entry | None:
        path = self._path(key)
        if path is None or not path.is_file():
            return None
        try:
            raw = json.loads(gzip.decompress(path.read_bytes()))
            if raw.get("key") != key:
                return None
            return _Entry(raw["value"], float(raw["storedAt"]))
        except (OSError, ValueError, KeyError, TypeError):
            return None

    def _disk_write(self, key: str, entry: _Entry) -> None:
        path = self._path(key)
        if path is None:
            return
        tmp: str | None = None
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            blob = gzip.compress(
                json.dumps({"key": key, "storedAt": entry.stored_at, "value": entry.value}).encode()
            )
            fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".part")
            with os.fdopen(fd, "wb") as fh:
                fh.write(blob)
            os.replace(tmp, path)
        except (OSError, TypeError, ValueError):
            if tmp is not None:
                with contextlib.suppress(OSError):
                    os.unlink(tmp)
