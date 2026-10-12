"""Tick/lot rounding against the configured instrument (A05 acceptance case 2).

Rounding never drops the remainder: :class:`Rounded` carries the residual and
the increment count explicitly, so a caller can account for what was shaved
off. Policies come from the :class:`~algobots.contracts.instrument.Instrument`
record (prices default to ``nearest`` half-even; quantities default ``down``
so an order never grows past its intended size).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_DOWN, ROUND_HALF_EVEN, Decimal

from algobots.contracts.instrument import Instrument

__all__ = ["Rounded", "round_price", "round_quantity"]


@dataclass(frozen=True)
class Rounded:
    """A rounded value plus the explicit residual (``original - rounded``).

    A positive residual means value was rounded down, negative rounded up.
    ``increments`` is the whole number of ticks/lots the rounded value is.
    """

    value: Decimal
    residual: Decimal
    increments: int
    policy: str

    def is_exact(self) -> bool:
        return self.residual == 0


def _round(value: Decimal, increment: Decimal, policy: str) -> Rounded:
    if value < 0:
        raise ValueError(f"cannot round a negative amount: {value}")
    if policy == "nearest":
        quantized = (value / increment).quantize(Decimal("1"), rounding=ROUND_HALF_EVEN) * increment
    elif policy == "down":
        quantized = (value / increment).to_integral_value(rounding=ROUND_DOWN) * increment
    else:  # pragma: no cover - contract Literal already restricts this
        raise ValueError(f"unknown rounding policy {policy!r}")
    return Rounded(
        value=quantized,
        residual=value - quantized,
        increments=int(quantized / increment),
        policy=policy,
    )


def round_price(instrument: Instrument, price: Decimal) -> Rounded:
    """Round a price to the instrument's tick; residual is explicit."""
    return _round(price, instrument.price_increment, instrument.tick_policy)


def round_quantity(instrument: Instrument, quantity: Decimal) -> Rounded:
    """Round a quantity to the instrument's lot; residual is explicit."""
    return _round(quantity, instrument.quantity_increment, instrument.lot_policy)
