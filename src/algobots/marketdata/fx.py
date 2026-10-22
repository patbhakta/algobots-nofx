"""Currency-conversion snapshots for reporting (A05 item 5).

FX conversion is a *recorded* surface with the same as-of discipline as
market data: a rate is usable only if it was available at the as-of time. An
unavailable pair raises :class:`FxUnavailableError` — it is never reinterpreted
as 1:1. Only a true identity conversion (same currency) yields 1.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from functools import lru_cache
from pathlib import Path

from algobots.contracts.base import Money

__all__ = ["FxRateBook", "FxUnavailableError", "fx_path", "load_fx_book"]


class FxUnavailableError(LookupError):
    """No available quote covers the pair at the as-of time — never silently 1:1."""


@dataclass(frozen=True)
class FxQuote:
    base: str
    quote: str
    event_time: datetime
    available_time: datetime
    rate: Decimal


class FxRateBook:
    """As-of FX rate lookup over recorded quotes."""

    def __init__(self, quotes: tuple[FxQuote, ...]) -> None:
        self._quotes = tuple(sorted(quotes, key=lambda q: (q.available_time, q.base, q.quote)))

    def rate(self, base: str, quote: str, as_of: datetime | None = None) -> Decimal:
        """The latest rate for base/quote published by ``as_of``.

        Same currency is an exact 1. Anything else must have an available
        recorded quote, else :class:`FxUnavailableError`.
        """
        if base == quote:
            return Decimal(1)
        if as_of is None:
            as_of = (
                self._quotes[-1].available_time
                if self._quotes
                else datetime.min.replace(tzinfo=UTC)
            )
        cutoff = as_of.astimezone(UTC) if as_of.utcoffset() is not None else as_of
        candidates = [
            q
            for q in self._quotes
            if q.base == base and q.quote == quote and q.available_time <= cutoff
        ]
        if not candidates:
            raise FxUnavailableError(
                f"no available {base}/{quote} quote at {cutoff.isoformat()} — "
                "unavailable FX is never treated as 1:1"
            )
        return candidates[-1].rate

    def convert(self, money: Money, to_currency: str, as_of: datetime | None = None) -> Money:
        rate = self.rate(money.currency, to_currency, as_of)
        return Money(amount=money.amount * rate, currency=to_currency)

    @classmethod
    def load(cls, path: Path) -> FxRateBook:
        quotes: list[FxQuote] = []
        for line in path.read_text().splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            quotes.append(
                FxQuote(
                    base=row["base"],
                    quote=row["quote"],
                    event_time=datetime.fromisoformat(row["event_time"]),
                    available_time=datetime.fromisoformat(row["available_time"]),
                    rate=Decimal(row["rate"]),
                )
            )
        return cls(tuple(quotes))


def fx_path() -> Path:
    return Path(__file__).with_name("fixtures") / "fx.jsonl"


@lru_cache(maxsize=1)
def load_fx_book(path: Path | None = None) -> FxRateBook:
    return FxRateBook.load(path if path is not None else fx_path())
