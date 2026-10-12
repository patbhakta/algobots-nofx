"""Research-symbol normalization, separate from executable IDs (A05 item 4).

Research symbols ("BTC-USD", "btc/usd", "BTCUSD") are *names for study*, not
identities: one research key maps to an explicit, enumerable list of candidate
executable instrument IDs. The mapping is never an implicit 1:1 — resolving
"BTC-USD" yields both venue instruments, and the caller picks (or the price
source precedence does). A normalized research key may never contain ``:``,
so it can never be confused with an executable ID.
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

from algobots.instruments.registry import InstrumentRegistry

__all__ = ["ResearchDirectory", "UnknownResearchSymbolError", "default_directory", "normalize"]

_SEPARATORS = re.compile(r"[/\-,]")
# Venue conventions that collapse onto canonical research keys.
_ALIASES = {
    "BTCUSD": "BTC-USD",
    "XBTUSD": "BTC-USD",
    "XBT-USD": "BTC-USD",
}


class UnknownResearchSymbolError(LookupError):
    """No research mapping exists for the normalized symbol."""


def normalize(symbol: str) -> str:
    """Normalize to uppercase, single-dash canonical form (BTC/usd -> BTC-USD)."""
    if ":" in symbol:
        raise ValueError(
            f"{symbol!r} looks like an executable ID; research symbols are not identities"
        )
    parts = [p for p in _SEPARATORS.split(symbol.strip().upper()) if p]
    if not parts:
        raise ValueError(f"cannot normalize research symbol {symbol!r}")
    key = "-".join(parts)
    return _ALIASES.get(key, key)


class ResearchDirectory:
    """The explicit research-key -> executable-IDs mapping from the spec file."""

    def __init__(self, mapping: dict[str, tuple[str, ...]]) -> None:
        self._mapping = {k: tuple(v) for k, v in mapping.items()}

    def executable_ids(self, symbol: str) -> tuple[str, ...]:
        key = normalize(symbol)
        try:
            return self._mapping[key]
        except KeyError:
            raise UnknownResearchSymbolError(
                f"no research mapping for {key!r} (known: {', '.join(sorted(self._mapping))})"
            ) from None

    def keys(self) -> tuple[str, ...]:
        return tuple(sorted(self._mapping))


@lru_cache(maxsize=1)
def default_directory(registry: InstrumentRegistry | None = None) -> ResearchDirectory:
    """Directory built from the bundled spec (shares the registry's file)."""
    from algobots.instruments.registry import InstrumentRegistry as _IR

    _, research = _IR.load(Path(__file__).with_name("instruments.json"))
    return ResearchDirectory(research)
