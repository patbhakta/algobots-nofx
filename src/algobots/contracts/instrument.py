"""Instrument identity and precision contract (A05, roadmap §2).

The canonical executable identity is ``{venue}:{product}:{symbol}`` — BTC/USD
spot at two venues and a BTC perpetual are three distinct instruments by
construction (:class:`Instrument` enforces the triple). Research symbols are
normalized separately in :mod:`algobots.instruments.research`; they never
 masquerade as executable IDs.

``perpetual-swap`` is identity-only: it keeps perp IDs distinct from spot but
asserts no options/futures execution support (A05 exclusions). Execution
entitlement still flows through A04 ``ProductClass`` permissions, which can
never contain it.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated, Any, ClassVar, Literal

from pydantic import Field, model_validator

from . import registry
from .base import ContractModel, DecimalStr, Identifier, Money, VersionedContract
from .enums import ProductClass

__all__ = [
    "ASSET_CODE",
    "Instrument",
    "LotPolicy",
    "Product",
    "TickPolicy",
]

# A venue asset code (ISO 4217 or crypto/venue convention), e.g. USD, BTC.
ASSET_CODE = Annotated[str, Field(pattern=r"^[A-Z0-9]{2,10}$")]

# Identity taxonomy: A01 ProductClass plus the identity-only perpetual swap.
Product = ProductClass | Literal["perpetual-swap"]

# Price/quantity rounding policies an instrument may declare. Residuals are
# always returned explicitly by algobots.instruments.rounding, never dropped.
TickPolicy = Literal["nearest", "down"]
LotPolicy = Literal["down", "nearest"]


def _product_code(product: Any) -> str:
    return product.value if isinstance(product, ProductClass) else str(product)


@registry.register
class Instrument(VersionedContract):
    """One executable instrument as the canonical identity record.

    ``price_increment`` (tick) and ``quantity_increment`` (lot) are decimal
    strings; quantities/rounding maths happen in :mod:`algobots.instruments`.
    ``calendar`` is a session-calendar key (``24x7`` for continuous markets)
    interpreted in ``timezone`` (IANA). ``metadata_version`` is the registry
    revision of this entry — replaying an as-of decision sees only the
    metadata version available at that time.
    """

    contract_name: ClassVar[str] = "Instrument"
    contract_version: ClassVar[str] = "1.0"

    instrument_id: Identifier
    venue: Identifier
    product: Product
    symbol: Identifier
    base_asset: ASSET_CODE | None = None
    quote_currency: ASSET_CODE
    lot_unit: Annotated[str, Field(min_length=1, max_length=16, pattern=r"^[A-Za-z0-9_]+$")]
    price_increment: DecimalStr
    quantity_increment: DecimalStr
    tick_policy: TickPolicy = "nearest"
    lot_policy: LotPolicy = "down"
    multiplier: DecimalStr = Decimal("1")
    min_notional: Money | None = None
    calendar: Identifier
    timezone: Annotated[str, Field(pattern=r"^[A-Za-z0-9_+\-/]+$")]
    metadata_version: Annotated[int, Field(ge=1)]

    @model_validator(mode="after")
    def _identity_and_precision(self) -> Instrument:
        if self.instrument_id != f"{self.venue}:{_product_code(self.product)}:{self.symbol}":
            raise ValueError(
                "instrument_id must be '{venue}:{product}:{symbol}' of its own fields"
            )
        if self.price_increment <= 0:
            raise ValueError("price_increment (tick) must be positive")
        if self.quantity_increment <= 0:
            raise ValueError("quantity_increment (lot) must be positive")
        if self.multiplier <= 0:
            raise ValueError("multiplier must be positive")
        return self

    def price_decimals(self) -> int:
        """Decimal places the configured tick can represent (0.01 -> 2)."""
        return max(0, -self.price_increment.as_tuple().exponent)

    def quantity_decimals(self) -> int:
        return max(0, -self.quantity_increment.as_tuple().exponent)
