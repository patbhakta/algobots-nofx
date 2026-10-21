"""Price-source precedence (A05 item 4).

Per venue, sources are ranked explicitly (e.g. live websocket above the REST
poller). Only entitled sources compete; an unentitled snapshot never satisfies
a price request regardless of rank. Unknown sources fail closed — they are
excluded — so a typo can never win precedence by accident.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from algobots.contracts.marketdata import MarketSnapshot

__all__ = ["PriceSourcePrecedence", "UnknownSourceError"]

# Fixture venue ranking: websocket feeds beat REST pollers.
DEFAULT_RANKING: dict[str, tuple[str, ...]] = {
    "COINBASE": ("coinbase-ws", "coinbase-rest"),
    "KRAKEN": ("kraken-ws",),
    "BYBIT": ("bybit-ws",),
    "XNAS": ("xnas-sip",),
    "XNYS": ("xnys-sip",),
}


class UnknownSourceError(LookupError):
    """The source is not ranked for the venue."""


@dataclass(frozen=True)
class PriceSourcePrecedence:
    ranking: Mapping[str, tuple[str, ...]]

    def rank(self, venue: str, source: str) -> int:
        """Lower rank wins; unknown sources raise (fail closed)."""
        order = self.ranking.get(venue, ())
        try:
            return order.index(source)
        except ValueError:
            raise UnknownSourceError(
                f"source {source!r} is not ranked for venue {venue!r} "
                f"(ranked: {', '.join(order) or 'none'})"
            ) from None

    def select(
        self, venue: str, candidates: Mapping[str, MarketSnapshot]
    ) -> tuple[str, MarketSnapshot] | None:
        """Best-precedence entitled snapshot per source; ``None`` when nothing qualifies.

        Unranked sources are excluded (fail closed — a typo never wins), and
        unentitled snapshots never qualify regardless of rank.
        """
        order = self.ranking.get(venue, ())
        entitled = [
            (source, snap)
            for source, snap in candidates.items()
            if snap.entitled and source in order
        ]
        entitled.sort(key=lambda pair: order.index(pair[0]))
        return entitled[0] if entitled else None
