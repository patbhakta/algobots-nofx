"""Shared quantity primitives for the execution package.

One minimum-tradable-quantity constant and one Decimal coercion helper,
so the planner and the governor never disagree on arithmetic.
"""

from __future__ import annotations

from decimal import Decimal

__all__ = ["QTY_QUANT", "coerce_decimal"]

QTY_QUANT = Decimal("0.00000001")


def coerce_decimal(value: Decimal | int | str | float) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))
