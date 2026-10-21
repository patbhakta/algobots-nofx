"""Account/product entitlement checks against instrument metadata (A05 item 4).

Execution entitlement reuses A04's surface: a ``BrokerAccount`` carries
``product_permissions: tuple[ProductClass, ...]``. The identity-only
``perpetual-swap`` product is deliberately not a ``ProductClass`` member, so
no account can hold a permission for it — entitlement fails closed by
construction and the exclusion ("no options/futures execution") is enforced
by the type system rather than convention.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from algobots.contracts.enums import ProductClass
from algobots.contracts.instrument import Instrument

__all__ = ["Entitlement", "product_entitled"]


@dataclass(frozen=True)
class Entitlement:
    allowed: bool
    reason: str


def product_entitled(product_permissions: Iterable[ProductClass], instrument: Instrument) -> Entitlement:
    """Whether an account holding ``product_permissions`` may trade ``instrument``."""
    held = frozenset(product_permissions)
    if not isinstance(instrument.product, ProductClass):
        return Entitlement(
            allowed=False, reason=f"identity-only-product:{instrument.product}"
        )
    if instrument.product not in held:
        return Entitlement(
            allowed=False, reason=f"product-not-permitted:{instrument.product.value}"
        )
    return Entitlement(allowed=True, reason=f"permitted:{instrument.product.value}")
