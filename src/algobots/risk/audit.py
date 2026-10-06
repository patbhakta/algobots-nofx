"""ClampEvent audit — one row per firing, always.

Every limit, envelope, or breaker firing anywhere in the risk rail writes
exactly one :class:`ClampEventRow` to a :class:`ClampEventSink`.
:class:`RiskGate` is the wiring point: it composes the vendored weight
limits (``limits.apply_limits``), the per-deployment envelope
(``envelopes.RiskEnvelope``), and the rate breakers
(``breakers.RateBreakers``) onto one sink, so no firing can skip the audit
trail.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Literal, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict

from algobots.risk.breakers import OrderKind, RateBreakers
from algobots.risk.envelopes import RiskEnvelope
from algobots.risk.limits import ClampEvent, RiskLimits, RiskResult, apply_limits

__all__ = [
    "ClampEventRow",
    "ClampEventSink",
    "InMemorySink",
    "JsonlSink",
    "OrderDecision",
    "RiskGate",
    "row_from_clamp",
    "utc_now_iso",
]

EventSource = Literal["limits", "envelope", "breaker"]


class ClampEventRow(BaseModel):
    """One audit row per firing — the explainability contract."""

    model_config = ConfigDict(extra="forbid")

    ts: str  # ISO-8601 UTC
    source: EventSource
    limit: str
    deployment_id: str | None = None
    ticker: str | None = None
    before: float | None = None
    after: float | None = None
    detail: str | None = None


@runtime_checkable
class ClampEventSink(Protocol):
    """Anything that can receive ClampEventRows."""

    def write(self, row: ClampEventRow) -> None: ...


class InMemorySink:
    """Collects rows in memory — for tests and short-lived processes."""

    def __init__(self) -> None:
        self.rows: list[ClampEventRow] = []

    def write(self, row: ClampEventRow) -> None:
        self.rows.append(row)


class JsonlSink:
    """Append-only JSONL file — exactly one JSON object per line per firing."""

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)

    def write(self, row: ClampEventRow) -> None:
        with self._path.open("a", encoding="utf-8") as fh:
            fh.write(row.model_dump_json() + "\n")


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def row_from_clamp(
    event: ClampEvent,
    *,
    deployment_id: str | None = None,
    ts: str | None = None,
) -> ClampEventRow:
    """Convert a vendored weight-clamp event into an audit row."""
    return ClampEventRow(
        ts=ts if ts is not None else utc_now_iso(),
        source="limits",
        limit=event.limit,
        deployment_id=deployment_id,
        ticker=event.ticker,
        before=event.before,
        after=event.after,
    )


class OrderDecision(BaseModel):
    """Result of :meth:`RiskGate.approve_order`."""

    model_config = ConfigDict(extra="forbid")

    kind: OrderKind
    allowed: bool
    approved_value: Decimal | None = None
    reason: str | None = None


class RiskGate:
    """Conviction requests, risk disposes.

    The single wiring point for the risk rail: vendored weight limits +
    per-deployment envelope + rate breakers + one audit sink. Every firing
    writes exactly one ClampEventRow.

    Exits are privileged: no envelope check, no breaker, and no value clamp
    ever blocks or shrinks an exit. An exit is still recorded with the
    breakers — it consumes rate budget and arms the 5s entry cooldown.
    """

    def __init__(
        self,
        *,
        limits: RiskLimits,
        envelope: RiskEnvelope,
        breakers: RateBreakers | None = None,
        sink: ClampEventSink | None = None,
        now: Callable[[], str] = utc_now_iso,
    ) -> None:
        self.limits = limits
        self.envelope = envelope
        self.breakers = breakers if breakers is not None else RateBreakers()
        self.sink = sink if sink is not None else InMemorySink()
        self._now = now

    # -- portfolio construction: weights ---------------------------------------

    def apply_weights(
        self,
        weights: dict[str, float],
        *,
        deployment_id: str = "default",
    ) -> RiskResult:
        """Clamp target weights through the vendored limits; audit every clamp."""
        result = apply_limits(weights, self.limits)
        for clamp in result.clamps:
            self.sink.write(
                row_from_clamp(clamp, deployment_id=deployment_id, ts=self._now())
            )
        return result

    # -- execution: orders -------------------------------------------------------

    def approve_order(
        self,
        *,
        kind: OrderKind,
        value: Decimal,
        daily_pnl: Decimal = Decimal(0),
        deployment_id: str = "default",
        ticker: str | None = None,
        now: float | None = None,
    ) -> OrderDecision:
        """Approve, clamp, or deny one order. Every firing writes one row.

        Entry gate order (first denial wins; only the gate that actually
        fired writes a row):

        1. envelope daily-loss — exhausted → deny (``max_daily_loss``)
        2. breakers — rate limit or post-exit cooldown → deny
        3. envelope order-value — clamp notional to ``max_order_value``

        An approved entry is then recorded with the breakers.
        """
        if kind == "exit":
            # Privileged: never blocked, never clamped. Recording still
            # consumes rate budget and arms the entry cooldown.
            self.breakers.record("exit", deployment_id=deployment_id, now=now)
            return OrderDecision(kind="exit", allowed=True, approved_value=value)

        loss_check = self.envelope.check_daily_loss(daily_pnl)
        if loss_check.tripped:
            self._write(
                source="envelope",
                limit="max_daily_loss",
                deployment_id=deployment_id,
                ticker=ticker,
                before=float(loss_check.daily_pnl),
                after=float(-self.envelope.max_daily_loss),
                detail="daily loss at/over cap; entries blocked, exits privileged",
            )
            return OrderDecision(kind="entry", allowed=False, reason="max_daily_loss")

        breaker_decision = self.breakers.check(
            "entry", deployment_id=deployment_id, now=now
        )
        if not breaker_decision.allowed:
            self._write(
                source="breaker",
                limit=breaker_decision.reason or "breaker",
                deployment_id=deployment_id,
                ticker=ticker,
                before=float(value),
                after=0.0,
                detail="entry denied by rate breaker",
            )
            return OrderDecision(
                kind="entry", allowed=False, reason=breaker_decision.reason
            )

        value_check = self.envelope.clamp_order_value(value)
        if value_check.fired:
            self._write(
                source="envelope",
                limit="max_order_value",
                deployment_id=deployment_id,
                ticker=ticker,
                before=float(value_check.requested),
                after=float(value_check.approved),
                detail="order notional clamped to envelope cap",
            )

        self.breakers.record("entry", deployment_id=deployment_id, now=now)
        return OrderDecision(
            kind="entry", allowed=True, approved_value=value_check.approved
        )

    def _write(self, **kwargs: object) -> None:
        kwargs.setdefault("ts", self._now())
        self.sink.write(ClampEventRow(**kwargs))  # type: ignore[arg-type]
