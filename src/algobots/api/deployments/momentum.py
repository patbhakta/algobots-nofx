"""Pure frozen momentum decisions for the deployment gateway dispatcher.

No transport or execution lives here. The dispatcher must recheck lifecycle and
risk at gateway admission. This first leg buys YES only; NO needs a separately
quoted NO instrument, so negative signals abstain rather than short YES.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from decimal import ROUND_FLOOR, Decimal
from typing import Any

from algobots.api.deployments.command_identity import deployment_order_id
from algobots.api.deployments.runtime import launch_spec
from algobots.marketdata.kalshi_observer import contiguous_closes, momentum_signal
from algobots.node.kalshi import KalshiObservation


@dataclass(frozen=True)
class MomentumIntent:
    idempotency_key: str
    body: dict[str, str]


def momentum_intent(
    deployment: Any,
    account: Any,
    settled_rows: list[dict],
    book: KalshiObservation,
    *,
    now_ns: int,
    max_book_age_ns: int = 60 * 10**9,
) -> MomentumIntent | None:
    """Produce a bounded limit request, or abstain on unusable market data.

    Settlements at or after the book timestamp are excluded to avoid lookahead.
    Re-served quote timestamps must never replace the observer's timestamp.
    """
    spec = launch_spec(deployment, account)  # validate canonical frozen inputs
    if (
        not book.market.startswith("KXBTC15M-")
        or book.ts_ns <= 0
        or max_book_age_ns <= 0
        or not 0 <= now_ns - book.ts_ns <= max_book_age_ns
        or not book.bid.is_finite()
        or not book.ask.is_finite()
        or not Decimal(0) < book.bid <= book.ask < Decimal(1)
        or book.ask != book.ask.quantize(Decimal(".01"))
    ):
        return None
    try:
        history = [
            row for row in settled_rows if 0 < float(row.get("close_ts") or 0) < book.ts_ns / 1e9
        ]
        settled = [row for row in history if row.get("outcome") is not None]
        if not settled or book.ts_ns / 1e9 - max(float(r["close_ts"]) for r in settled) > 900:
            return None
        closes = contiguous_closes(history)
        if any(not math.isfinite(close) or close <= 0 for close in closes):
            return None
        probability, _, source = momentum_signal({}, closes)
    except (ValueError, TypeError, ArithmeticError):
        return None
    edge = Decimal(str(probability)) - Decimal(".5")
    threshold = Decimal(str(deployment.frozen_spec["artifact"]["nautilus"]["params"]["min_edge"]))
    if source == "none" or edge <= 0 or edge < threshold:
        return None
    # The frozen deployment cap bounds notional; gateway risk can shrink it.
    qty = (Decimal(deployment.max_order_value) / book.ask).to_integral_value(rounding=ROUND_FLOOR)
    if qty < 1:
        return None
    return MomentumIntent(
        deployment_order_id(deployment.id, deployment.artifact_hash, book.market),
        {
            "account_id": str(account.id),
            "symbol": spec.environment["ALGOBOTS_NODE_SYMBOL"],
            "side": "buy",
            "qty": str(qty),
            "order_type": "limit",
            "limit_px": str(book.ask),
            "time_in_force": "ioc",
        },
    )
