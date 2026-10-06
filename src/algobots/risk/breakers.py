"""Rate breakers — deterministic trip, window recovery, privileged exits.

Defaults come from the Fincept manual, Algo section 19 (via the ALG-3070
study, section R4):

- per-deployment: 10 orders/minute, 200 orders/day
- fleet-wide:     75 entries/minute, 500 entries/day
- per-deployment: 5-second entry cooldown after an exit

Law of this module: EXITS ARE PRIVILEGED. Nothing here ever blocks an exit
or a reducing order. Exits are recorded — they consume per-deployment order
budget and arm the post-exit entry cooldown — but they are always allowed.

Windows are sliding windows over recorded event timestamps. Time is
injected (``clock``), so with a fixed clock the breakers are fully
deterministic; the tests prove exact trip and recovery points.
"""

from __future__ import annotations

import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

__all__ = ["BreakerConfig", "BreakerDecision", "OrderKind", "RateBreakers"]

OrderKind = Literal["entry", "exit"]

MINUTE_SECONDS = 60.0
DAY_SECONDS = 86400.0


@dataclass(frozen=True)
class BreakerConfig:
    """Rate-breaker thresholds. Defaults = Fincept manual Algo §19."""

    per_deployment_orders_per_minute: int = 10
    per_deployment_orders_per_day: int = 200
    fleet_entries_per_minute: int = 75
    fleet_entries_per_day: int = 500
    post_exit_entry_cooldown_seconds: float = 5.0


@dataclass(frozen=True)
class BreakerDecision:
    """Result of one breaker check. Exits are always allowed."""

    kind: OrderKind
    allowed: bool
    reason: str | None = None  # name of the breaker that fired, when denied


class RateBreakers:
    """Sliding-window rate breakers with privileged exits.

    State is one timestamp deque per deployment (all orders) plus one
    fleet-wide deque (entries only). A breaker trips when the window count
    has reached its limit — the next entry is denied — and recovers
    deterministically once events age out of the window.
    """

    def __init__(
        self,
        config: BreakerConfig | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.config = config or BreakerConfig()
        self._clock = clock
        self._deployment_orders: dict[str, deque[float]] = {}
        self._fleet_entries: deque[float] = deque()
        self._last_exit: dict[str, float] = {}

    # -- public API ----------------------------------------------------------

    def check(
        self,
        kind: OrderKind,
        deployment_id: str = "default",
        now: float | None = None,
    ) -> BreakerDecision:
        """Would this order be allowed right now? Does not record it."""
        now = self._now(now)
        if kind == "exit":
            return BreakerDecision(kind="exit", allowed=True)  # privileged
        return self._check_entry(deployment_id, now)

    def record(
        self,
        kind: OrderKind,
        deployment_id: str = "default",
        now: float | None = None,
    ) -> None:
        """Record a dispatched order against the rate windows."""
        now = self._now(now)
        orders = self._deployment_orders.setdefault(deployment_id, deque())
        self._prune_day(orders, now)
        orders.append(now)
        if kind == "exit":
            self._last_exit[deployment_id] = now  # arms the entry cooldown
        else:
            self._prune_day(self._fleet_entries, now)
            self._fleet_entries.append(now)

    def check_and_record(
        self,
        kind: OrderKind,
        deployment_id: str = "default",
        now: float | None = None,
    ) -> BreakerDecision:
        """Check, and record iff allowed (denials consume no rate budget)."""
        decision = self.check(kind, deployment_id, now)
        if decision.allowed:
            self.record(kind, deployment_id, now)
        return decision

    # -- internals -------------------------------------------------------------

    def _check_entry(self, deployment_id: str, now: float) -> BreakerDecision:
        cfg = self.config
        orders = self._deployment_orders.setdefault(deployment_id, deque())
        self._prune_day(orders, now)
        self._prune_day(self._fleet_entries, now)

        last_exit = self._last_exit.get(deployment_id)
        if (
            last_exit is not None
            and now - last_exit < cfg.post_exit_entry_cooldown_seconds
        ):
            return self._deny("post_exit_entry_cooldown")
        if (
            self._count_window(orders, now, MINUTE_SECONDS)
            >= cfg.per_deployment_orders_per_minute
        ):
            return self._deny("per_deployment_orders_per_minute")
        if len(orders) >= cfg.per_deployment_orders_per_day:
            return self._deny("per_deployment_orders_per_day")
        if (
            self._count_window(self._fleet_entries, now, MINUTE_SECONDS)
            >= cfg.fleet_entries_per_minute
        ):
            return self._deny("fleet_entries_per_minute")
        if len(self._fleet_entries) >= cfg.fleet_entries_per_day:
            return self._deny("fleet_entries_per_day")
        return BreakerDecision(kind="entry", allowed=True)

    def _deny(self, reason: str) -> BreakerDecision:
        return BreakerDecision(kind="entry", allowed=False, reason=reason)

    def _now(self, now: float | None) -> float:
        return self._clock() if now is None else now

    @staticmethod
    def _count_window(events: deque[float], now: float, window: float) -> int:
        cutoff = now - window
        return sum(1 for ts in events if ts > cutoff)

    @staticmethod
    def _prune_day(events: deque[float], now: float) -> None:
        while events and events[0] <= now - DAY_SECONDS:
            events.popleft()
