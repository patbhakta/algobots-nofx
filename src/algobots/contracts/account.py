"""Broker account and capability contracts (roadmap §2)."""

from __future__ import annotations

from typing import Annotated, ClassVar, Literal

from pydantic import Field, model_validator

from . import registry
from .base import ContractModel, Identifier, Quantity, UtcDatetime, VersionedContract
from .enums import ConnectionState, OrderType, ProductClass, RuntimeEnvironment

__all__ = ["BrokerAccount", "CapabilityEntry", "Capabilities", "SupportStatus"]

Currency = Annotated[str, Field(pattern=r"^[A-Z0-9]{3,10}$")]
SupportStatus = Literal["native", "emulated", "unsupported"]


@registry.register
class BrokerAccount(VersionedContract):
    """One broker account. ``secret_ref`` is a reference, never the credential itself."""

    contract_name: ClassVar[str] = "BrokerAccount"
    contract_version: ClassVar[str] = "1.0"

    account_id: Identifier
    tenant_id: Identifier
    broker_connection_ref: Identifier
    external_account_fingerprint: Annotated[str, Field(pattern=r"^[0-9a-f]{16,64}$")]
    environment: RuntimeEnvironment
    product_permissions: tuple[ProductClass, ...]
    base_currency: Currency
    settlement_currencies: tuple[Currency, ...]
    secret_ref: Annotated[str, Field(pattern=r"^secret://[A-Za-z0-9._/-]+$")]
    capability_revision: Annotated[int, Field(ge=0)]
    session_health: ConnectionState
    entry_status: Literal["ACTIVE", "SUSPENDED", "CLOSED"]
    ownership_epoch: Annotated[int, Field(ge=0)]
    reconciliation_watermark: UtcDatetime | None = None


class CapabilityEntry(ContractModel):
    product: ProductClass
    order_type: OrderType
    support: SupportStatus
    price_decimals: Annotated[int, Field(ge=0, le=18)]
    quantity_decimals: Annotated[int, Field(ge=0, le=18)]
    min_order: Quantity
    client_order_id_max_length: Annotated[int, Field(ge=1)] | None = None
    client_order_id_reusable: bool
    cancel_semantics: Literal["sync", "async-ack", "best-effort"]
    rate_limit_per_minute: Annotated[int, Field(ge=1)] | None = None
    market_data_entitled: bool
    test_environment_fidelity: Literal["high", "partial", "none", "unknown"]


@registry.register
class Capabilities(VersionedContract):
    """Observed per-(product, order type) capabilities. Unknown means disabled."""

    contract_name: ClassVar[str] = "Capabilities"
    contract_version: ClassVar[str] = "1.0"

    account_id: Identifier
    capability_revision: Annotated[int, Field(ge=0)]
    observed_at: UtcDatetime
    entries: tuple[CapabilityEntry, ...]

    @model_validator(mode="after")
    def _unique_entries(self) -> Capabilities:
        keys = [(e.product, e.order_type) for e in self.entries]
        if len(set(keys)) != len(keys):
            raise ValueError("duplicate capability entry for a (product, order_type) pair")
        return self

    def support_for(self, product: ProductClass, order_type: OrderType) -> SupportStatus:
        for entry in self.entries:
            if entry.product is product and entry.order_type is order_type:
                return entry.support
        return "unsupported"

    def is_enabled(self, product: ProductClass, order_type: OrderType) -> bool:
        return self.support_for(product, order_type) != "unsupported"
