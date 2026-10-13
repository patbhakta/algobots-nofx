"""Latency + traffic stats for the bridge endpoints (ALG-3340, OpenAlgo pull #6).

In-process per-endpoint registry: request count and a bounded ring of recent
latencies (ms) → p50 / p95 / max. OpenAlgo's Latency/Traffic Monitor is the
feature reference (pattern only, AGPL — no code); these counters are ours.

The registry is process-local: uvicorn runs one API process, and the
snapshot endpoint itself reports process uptime so a reader can tell a
freshly restarted plane from a quiet one.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass, field

_RING = 512  # bounded: p95 over the last 512 calls, not all history


@dataclass
class _Endpoint:
    count: int = 0
    latencies: deque = field(default_factory=lambda: deque(maxlen=_RING))

    def snapshot(self) -> dict:
        xs = sorted(self.latencies)
        if not xs:
            return {"count": self.count, "latency_ms": None}
        pct = lambda p: xs[min(len(xs) - 1, int(round(p * len(xs))))]  # noqa: E731
        return {
            "count": self.count,
            "latency_ms": {
                "p50": pct(0.50),
                "p95": pct(0.95),
                "max": xs[-1],
            },
        }


class _Registry:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._endpoints: dict[str, _Endpoint] = {}
        self.started_at = time.time()

    def observe(self, endpoint: str, t0: float) -> None:
        ms = round((time.perf_counter() - t0) * 1000, 3)
        with self._lock:
            ep = self._endpoints.setdefault(endpoint, _Endpoint())
            ep.count += 1
            ep.latencies.append(ms)

    def snapshot(self) -> dict:
        with self._lock:
            endpoints = {k: v.snapshot() for k, v in sorted(self._endpoints.items())}
        return {
            "process_uptime_s": round(time.time() - self.started_at, 1),
            "endpoints": endpoints,
        }


REGISTRY = _Registry()


def observe(endpoint: str, t0: float) -> None:
    REGISTRY.observe(endpoint, t0)


def snapshot() -> dict:
    return REGISTRY.snapshot()


__all__ = ["observe", "snapshot"]
