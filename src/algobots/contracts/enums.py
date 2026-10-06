"""Closed vocabularies shared across contracts. Unknown members are rejected."""

from __future__ import annotations

from enum import StrEnum

__all__ = [
    "AuthorityMode",
    "ConnectionState",
    "EvidenceClass",
    "IntentAction",
    "OrderSide",
    "OrderType",
    "ProductClass",
    "RuntimeEnvironment",
]


class RuntimeEnvironment(StrEnum):
    DEVELOPMENT = "development"
    SYNTHETIC_PAPER = "synthetic-paper"
    PAPER = "paper"
    LIVE = "live"


class ProductClass(StrEnum):
    EQUITY = "equity"
    ETF = "etf"
    SPOT_CRYPTO = "spot-crypto"


class OrderType(StrEnum):
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop-limit"


class OrderSide(StrEnum):
    BUY = "BUY"
    SELL = "SELL"


class ConnectionState(StrEnum):
    UNCONFIGURED = "UNCONFIGURED"
    CONNECTING = "CONNECTING"
    CONNECTED = "CONNECTED"
    DEGRADED = "DEGRADED"
    EXPIRED = "EXPIRED"
    REVOKED = "REVOKED"


class AuthorityMode(StrEnum):
    """Platform authority modes; deliberately not Nautilus environment enums."""

    PAPER = "PAPER"
    LIVE_APPROVAL = "LIVE_APPROVAL"
    LIVE_AUTO = "LIVE_AUTO"


class IntentAction(StrEnum):
    CREATE_TARGET = "CREATE_TARGET"
    PLACE_ORDER = "PLACE_ORDER"
    CANCEL_ORDER = "CANCEL_ORDER"
    REPLACE_ORDER = "REPLACE_ORDER"
    REDUCE = "REDUCE"
    FLATTEN = "FLATTEN"


class EvidenceClass(StrEnum):
    """Observation type, not a quality rank."""

    HYPOTHESIS = "HYPOTHESIS"
    BACKTESTED = "BACKTESTED"
    PAPER_OBSERVED = "PAPER_OBSERVED"
    LIVE_OBSERVED = "LIVE_OBSERVED"
