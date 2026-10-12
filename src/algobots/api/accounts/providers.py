"""Provider catalog and per-(provider, environment) capability registry (A04).

- :data:`PROVIDERS` — onboarding surface: the `mock` provider (fully local,
  synthetic venue) and `alpaca` as a *candidate* real provider whose
  configuration is recorded but whose sessions stay UNCONFIGURED until a
  later packet activates real connectivity. Nothing here dials a network.
- :data:`CAPABILITY_CATALOG` — :class:`BrokerAdapterCapabilities` statements
  per (provider, environment). Deployment previews consult the catalog and
  are default-deny: an absent (product, order_type) row is "unsupported".
"""

from __future__ import annotations

from dataclasses import dataclass

from algobots.contracts.account import BrokerAdapterCapabilities
from algobots.contracts.base import Quantity
from algobots.contracts.enums import OrderType, ProductClass

__all__ = [
    "CANDIDATE",
    "MOCK",
    "PROVIDERS",
    "ProviderConfig",
    "UnknownProviderError",
    "capabilities_for",
    "default_egress_hosts",
]


class UnknownProviderError(LookupError):
    """No provider/environment is registered under that key."""


@dataclass(frozen=True)
class ProviderConfig:
    slug: str
    kind: str  # "mock" | "candidate"
    display_name: str
    environments: tuple[str, ...]
    default_egress_hosts: tuple[str, ...]
    note: str = ""


MOCK = ProviderConfig(
    slug="mock",
    kind="mock",
    display_name="Mock venue",
    environments=("development", "synthetic-paper"),
    default_egress_hosts=("mock.local",),
    note="Fully local synthetic venue; no network egress beyond mock.local.",
)
CANDIDATE = ProviderConfig(
    slug="alpaca",
    kind="candidate",
    display_name="Alpaca (candidate)",
    environments=("paper",),
    default_egress_hosts=("*.alpaca.markets",),
    note="Configuration-only in A04: sessions stay UNCONFIGURED; live activation is a later packet.",
)

PROVIDERS: dict[str, ProviderConfig] = {p.slug: p for p in (MOCK, CANDIDATE)}


def default_egress_hosts(provider: str) -> tuple[str, ...]:
    config = PROVIDERS.get(provider)
    return config.default_egress_hosts if config else ()


def _entry(
    product: ProductClass,
    order_type: OrderType,
    support: str,
    *,
    reusable: bool = False,
    protections: tuple[str, ...] = (),
    rate: int = 600,
) -> dict:
    return {
        "product": product,
        "order_type": order_type,
        "support": support,
        "price_decimals": 2 if product is not ProductClass.SPOT_CRYPTO else 4,
        "quantity_decimals": 4,
        "min_order": Quantity(value="1", unit="shares" if product is not ProductClass.SPOT_CRYPTO else "BTC"),
        "client_order_id_max_length": 48,
        "client_order_id_reusable": reusable,
        "client_order_id_uniqueness": "trading-day",
        "lookup_methods": ("by-client-order-id", "open-orders"),
        "reconcile_methods": ("positions", "balances", "open-orders"),
        "protection_options": protections,
        "cancel_semantics": "sync",
        "rate_limit_per_minute": rate,
        "market_data_entitled": True,
        "test_environment_fidelity": "high",
    }


def _mock_capabilities(environment: str, revision: int) -> BrokerAdapterCapabilities:
    entries = (
        _entry(ProductClass.EQUITY, OrderType.MARKET, "native", protections=("stop", "stop-limit")),
        _entry(ProductClass.EQUITY, OrderType.LIMIT, "native"),
        _entry(ProductClass.EQUITY, OrderType.STOP_LIMIT, "emulated"),
        _entry(ProductClass.ETF, OrderType.MARKET, "native"),
        _entry(ProductClass.ETF, OrderType.LIMIT, "native"),
    )
    return BrokerAdapterCapabilities(
        schema_version="1.0",
        provider="mock",
        environment=environment,
        revision=revision,
        observed_at="2026-10-12T00:00:00+00:00",
        sandbox_fidelity="high",
        reconcile_methods=("positions", "balances", "open-orders"),
        entries=entries,  # type: ignore[arg-type]
    )


def _alpaca_candidate_capabilities(environment: str) -> BrokerAdapterCapabilities:
    entries = (
        _entry(ProductClass.EQUITY, OrderType.MARKET, "native", rate=200),
        _entry(ProductClass.EQUITY, OrderType.LIMIT, "native", rate=200),
    )
    return BrokerAdapterCapabilities(
        schema_version="1.0",
        provider="alpaca",
        environment=environment,
        revision=0,
        observed_at="2026-10-12T00:00:00+00:00",
        sandbox_fidelity="partial",
        reconcile_methods=("positions", "balances"),
        entries=entries,  # type: ignore[arg-type]
    )


CAPABILITY_CATALOG: dict[tuple[str, str], BrokerAdapterCapabilities] = {
    ("mock", "development"): _mock_capabilities("development", 2),
    ("mock", "synthetic-paper"): _mock_capabilities("synthetic-paper", 2),
    ("alpaca", "paper"): _alpaca_candidate_capabilities("paper"),
}


def capabilities_for(provider: str, environment: str) -> BrokerAdapterCapabilities:
    """The registered statement for one (provider, environment) pair.

    Unknown pairs raise :class:`UnknownProviderError` — callers treat that as
    "every feature disabled" rather than falling back to permissive defaults.
    """
    key = (provider.strip().lower(), environment.strip().lower())
    statement = CAPABILITY_CATALOG.get(key)
    if statement is None:
        raise UnknownProviderError(
            f"no capability statement registered for provider={key[0]!r} environment={key[1]!r}; "
            "unknown providers are fully disabled"
        )
    return statement


def provider_config(provider: str) -> ProviderConfig:
    config = PROVIDERS.get(provider.strip().lower())
    if config is None:
        raise UnknownProviderError(f"unknown provider {provider!r}")
    return config


def environment_allowed_for_onboarding(config: ProviderConfig, environment: str) -> bool:
    """A04 onboarding is confined to the provider's registered, non-live
    environments: development + synthetic-paper for the mock venue, paper
    configuration-only for the candidate. `live` is never onboardable here."""
    return environment != "live" and environment in config.environments
