"""Frozen deployment decisions, admitted through the gateway (ALG-3431).

The supervisor owns the processes; this owns the orders. Each tick reads the
Kalshi observer's jsonl once, asks :func:`~algobots.api.deployments.momentum.momentum_intent`
for every deployment whose paper node is alive, and POSTs the result to the
gateway's ``/v1/orders`` with the deployment's market-scoped idempotency key.

Nothing here publishes to Redis. Admission (scope, PAPER-only, node fitness,
the deployment's lifecycle, the pre-trade gate) is the gateway's, so a stopped
deployment is refused there even if this process has not caught up.

A key is retried only while the answer could still change: ``503`` (the node is
still reconciling) and transport errors. Any other answer is final for that
market, and a supervisor restart that re-POSTs gets the gateway's idempotent
replay rather than a second order.
"""

from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from algobots.api.deployments.momentum import momentum_intent
from algobots.node.kalshi import KalshiObservation, parse_line

log = logging.getLogger("algobots.deployment_dispatch")

RETRYABLE = frozenset({503})


def read_feed(path: str) -> tuple[list[dict], KalshiObservation | None]:
    """Every observer row (for settled history) and the newest book."""
    rows: list[dict] = []
    book = None
    try:
        lines = Path(path).read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return [], None
    for number, line in enumerate(lines, start=1):
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict):
            rows.append(row)
            book = parse_line(number, line) or book
    return rows, book


def gateway_poster(url: str, token: str, timeout: float = 5.0) -> Callable[[str, dict], int]:
    """``POST {url}/v1/orders`` as the dispatcher; returns the HTTP status (0 = no answer)."""

    def post(key: str, body: dict) -> int:
        request = urllib.request.Request(
            f"{url.rstrip('/')}/v1/orders",
            data=json.dumps(body).encode(),
            method="POST",
            headers={
                "Authorization": f"Bearer {token}",
                "Idempotency-Key": key,
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.status
        except urllib.error.HTTPError as exc:
            log.info("dispatch %s refused %s: %s", key, exc.code, exc.read()[:300])
            return exc.code
        except OSError as exc:
            log.warning("dispatch %s: gateway unreachable: %s", key, exc)
            return 0

    return post


@dataclass
class Dispatcher:
    post: Callable[[str, dict], int]
    feed_path: str
    clock: Callable[[], float] = time.time
    #: idempotency key -> final gateway status
    done: dict[str, int] = field(default_factory=dict)

    def __call__(self, rows: list[tuple[Any, Any, Any]], children: dict[str, Any]) -> list[str]:
        """Admit each live deployment's decision once. Returns keys posted this tick."""
        live = [(d, a) for d, a, _ in rows if str(d.id) in children]
        if not live:
            return []
        history, book = read_feed(self.feed_path)
        if book is None:
            return []
        posted = []
        for deployment, account in live:
            try:
                intent = momentum_intent(
                    deployment, account, history, book, now_ns=int(self.clock() * 1e9)
                )
            except ValueError as exc:
                log.warning("dispatch %s: %s", deployment.id, exc)
                continue
            if intent is None or intent.idempotency_key in self.done:
                continue
            status = self.post(intent.idempotency_key, intent.body)
            posted.append(intent.idempotency_key)
            if status and status not in RETRYABLE:
                self.done[intent.idempotency_key] = status
                log.info(
                    "dispatch %s %s %s -> %s",
                    deployment.id,
                    book.market,
                    intent.idempotency_key,
                    status,
                )
        return posted


__all__ = ["RETRYABLE", "Dispatcher", "gateway_poster", "read_feed"]
