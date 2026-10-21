"""A05 item 5: currency-conversion snapshots for reporting — unavailable FX is
never reinterpreted as 1:1."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from algobots.contracts.base import Money
from algobots.marketdata import FxUnavailableError, load_fx_book


def test_rate_is_point_in_time():
    book = load_fx_book()
    noon = datetime(2026, 10, 30, 12, 0, tzinfo=UTC)
    evening = datetime(2026, 10, 30, 17, 0, tzinfo=UTC)
    assert book.rate("EUR", "USD", noon) == Decimal("1.0850")
    assert book.rate("EUR", "USD", evening) == Decimal("1.0900")


def test_rate_before_first_quote_is_unavailable_not_one():
    book = load_fx_book()
    early = datetime(2026, 10, 30, 9, 0, tzinfo=UTC)
    with pytest.raises(FxUnavailableError, match="never treated as 1:1"):
        book.rate("EUR", "USD", early)


def test_missing_pair_is_unavailable_not_one():
    book = load_fx_book()
    noon = datetime(2026, 10, 30, 12, 0, tzinfo=UTC)
    # USD->EUR has no recorded quote (only EUR/USD is recorded): refuse.
    with pytest.raises(FxUnavailableError):
        book.rate("USD", "EUR", noon)
    with pytest.raises(FxUnavailableError):
        book.rate("USD", "JPY", noon)


def test_identity_conversion_is_exact_one():
    book = load_fx_book()
    noon = datetime(2026, 10, 30, 12, 0, tzinfo=UTC)
    assert book.rate("USD", "USD", noon) == Decimal(1)


def test_convert_uses_the_as_of_rate():
    book = load_fx_book()
    noon = datetime(2026, 10, 30, 12, 0, tzinfo=UTC)
    hundred_eur = Money(amount=Decimal("100.00"), currency="EUR")
    usd = book.convert(hundred_eur, "USD", noon)
    assert usd.currency == "USD"
    assert usd.amount == Decimal("108.500")
    with pytest.raises(FxUnavailableError):
        book.convert(usd, "EUR", noon)  # no USD/EUR quote recorded
