"""Pluggable broker token refreshers for the token-health sweep.

A refresher receives the ORM `Account` and the decrypted secret dict and
returns a `RefreshOutcome` carrying the replacement bearer token (and optional
rotated secret / expiry). Brokers register adapters at process start; an
account whose broker has no refresher expires cleanly instead of crashing the
sweep. Refresher exceptions are caught, redacted, and recorded per account.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from algobots.api.models import Account


@dataclass(slots=True)
class RefreshOutcome:
    """Successful silent refresh: the new bearer token replaces the old one."""

    token: str
    token_expires_at: datetime | None = None
    api_secret: str | None = None


TokenRefresher = Callable[[Account, dict[str, Any]], RefreshOutcome]

# Broker slug (lowercased) -> refresher. Populated by broker adapter packages.
REFRESHERS: dict[str, TokenRefresher] = {}


def register_token_refresher(broker: str, refresher: TokenRefresher) -> None:
    """Register (or replace) the silent-refresh adapter for one broker."""
    REFRESHERS[broker.strip().lower()] = refresher


def get_token_refresher(broker: str) -> TokenRefresher | None:
    """Look up the adapter for a broker, if one is registered."""
    return REFRESHERS.get(broker.strip().lower())
